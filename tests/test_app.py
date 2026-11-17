import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pymupdf

from tests.test_jobs import scripted_worker
from trans_document.app import (
    _connection_status,
    _is_insecure_external_url,
    _reset_connection_status,
    _translate_profile_ui,
    build_app,
    clear_profile_key,
    save_profile,
    translate_ui,
)
from trans_document.jobs import JobRunner
from trans_document.preview import render_first_page
from trans_document.profiles import ProfileStore


class AppTests(unittest.TestCase):
    def test_http_warning_distinguishes_loopback_from_remote_hosts(self):
        self.assertTrue(_is_insecure_external_url("http://api.example.com/v1"))
        self.assertTrue(_is_insecure_external_url("http://192.0.2.5/v1"))
        self.assertFalse(_is_insecure_external_url("http://127.0.0.1:8765/v1"))
        self.assertFalse(_is_insecure_external_url("http://localhost:8765/v1"))
        self.assertFalse(_is_insecure_external_url("https://api.example.com/v1"))

    def test_connection_probe_discards_changed_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles.json")
            profile = store.read().profiles[0]
            keys = {profile.key_slot: "dummy"}

            def check_then_change(*_):
                store.save(profile_id=profile.id, name=profile.name, provider=profile.provider,
                           base_url=profile.base_url, model="changed-model")
                return "ok"

            with mock.patch("trans_document.app.check_connection", side_effect=check_then_change):
                status = _connection_status(profile.id, keys, store, profile.provider,
                                            profile.base_url, profile.model)
            self.assertIn("đã thay đổi", status.lower())

    def test_connection_probe_discards_changed_session_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles.json")
            profile = store.read().profiles[0]
            request = SimpleNamespace(session_hash="browser")
            keys = {profile.key_slot: "dummy"}

            def change_while_checking(*_):
                _reset_connection_status(request)
                return "ok"

            with mock.patch("trans_document.app.check_connection", side_effect=change_while_checking):
                status = _connection_status(profile.id, keys, store, profile.provider,
                                            profile.base_url, profile.model, "browser")
            self.assertIn("đã thay đổi", status.lower())

    def test_invalid_translation_scope_does_not_become_full_document(self):
        class RecordingRunner:
            called = False

            def stream(self, request, owner):
                self.called = True
                yield {"type": "error", "code": "backend"}

        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles.json")
            profile = store.read().profiles[0]
            keys = {profile.key_slot: "dummy"}
            runner = RecordingRunner()
            updates = list(_translate_profile_ui(
                "input.pdf", profile.id, "unexpected", "en", "vi", keys,
                SimpleNamespace(session_hash="browser"), runner=runner, store=store,
            ))
            self.assertFalse(runner.called)
            self.assertIn("không hợp lệ", updates[-1][0].lower())

    def test_preview_failure_keeps_downloads(self):
        class FinishedRunner:
            def stream(self, request, owner):
                yield {"type": "finish", "mono": str(mono), "dual": str(dual)}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ProfileStore(root / "profiles.json")
            profile = store.read().profiles[0]
            _, _, _, keys = save_profile(profile.id, profile.name, profile.provider,
                                         profile.base_url, profile.model, "dummy", {}, store)
            job = root / "job"
            result = job / "result"
            result.mkdir(parents=True)
            source = job / "input.pdf"
            mono = result / "mono.pdf"
            dual = result / "dual.pdf"
            for target in (source, mono, dual):
                with pymupdf.open() as document:
                    document.new_page().insert_text((40, 40), "PDF")
                    document.save(target)
            with mock.patch("trans_document.app.render_first_page", return_value=None):
                updates = list(_translate_profile_ui(
                    str(source), profile.id, "all", "en", "vi", keys,
                    SimpleNamespace(session_hash="browser"), runner=FinishedRunner(), store=store,
                ))
            self.assertEqual(updates[-1][1:3], (str(mono), str(dual)))
            self.assertIsNone(updates[-1][3])
            self.assertIsNone(updates[-1][4])
            self.assertIn("ảnh xem trước", updates[-1][0].lower())

    def test_profile_key_is_session_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles.json")
            profile = store.read().profiles[0]
            _, _, _, state_a = save_profile(profile.id, profile.name, profile.provider,
                                             profile.base_url, profile.model, "marker-key", {}, store)
            state_b = {}
            self.assertEqual(state_a[profile.key_slot], "marker-key")
            self.assertNotIn(profile.key_slot, state_b)

    def test_add_profile_from_empty_form(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles.json")
            profile_id, cleared, status, keys = save_profile(
                "", "My API", "custom", "https://api.example.com/v1", "model", "new-key", {}, store,
            )
            profile = next(item for item in store.read().profiles if item.id == profile_id)
            self.assertEqual(profile.name, "My API")
            self.assertEqual(cleared, "")
            self.assertIn("đã nhập", status.lower())
            self.assertEqual(keys[profile.key_slot], "new-key")

    def test_save_and_clear_never_exposes_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            store = ProfileStore(path)
            profile = store.read().profiles[0]
            profile_id, key_field, status, state = save_profile(
                profile.id, profile.name, profile.provider, profile.base_url, profile.model,
                "unique-secret-marker", {}, store,
            )
            self.assertEqual(key_field, "")
            self.assertIn("đã nhập", status.lower())
            self.assertNotIn("unique-secret-marker", path.read_text(encoding="utf-8"))
            cleared = clear_profile_key(profile_id, state, store)
            self.assertNotIn(profile.key_slot, cleared)

    def test_stale_endpoint_slot_requires_new_key(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles.json")
            profile = store.read().profiles[0]
            _, _, _, state = save_profile(profile.id, profile.name, profile.provider,
                                           profile.base_url, profile.model, "old-secret", {}, store)
            changed = store.save(profile_id=profile.id, name=profile.name, provider=profile.provider,
                                 base_url="https://api.example.com/v1", model=profile.model)
            self.assertEqual(state.get(changed.key_slot), None)

    def test_first_page_preview_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "large.pdf"
            with pymupdf.open() as document:
                page = document.new_page(width=1800, height=2400)
                page.insert_text((72, 90), "Preview")
                document.save(source)
            image = render_first_page(source)
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(max(image.size), 1200)
            self.assertAlmostEqual(image.width / image.height, 1800 / 2400, places=2)

    def test_unreadable_pdf_returns_no_preview(self):
        self.assertIsNone(render_first_page("missing-preview.pdf"))

    def test_ui_resets_stale_downloads_and_returns_both_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            with pymupdf.open() as document:
                document.new_page().insert_text((40, 40), "Hello world")
                document.save(source)
            runner = JobRunner(root / "outputs", worker=scripted_worker)
            updates = list(translate_ui(
                str(source), "http://127.0.0.1:1/v1", "test", "test-key", "en", "vi",
                SimpleNamespace(session_hash="browser"), runner=runner,
            ))
            self.assertIsNone(updates[0][1])
            self.assertIsNone(updates[0][2])
            self.assertTrue(Path(updates[-1][1]).is_file())
            self.assertTrue(Path(updates[-1][2]).is_file())
            self.assertTrue(updates[-1][3]["interactive"])
            self.assertNotIn("test-key", str(updates))

    def test_missing_upload_is_a_readable_error(self):
        updates = list(translate_ui(
            None, "https://example.com/v1", "test", "key", "en", "vi",
            SimpleNamespace(session_hash="browser"),
        ))
        self.assertIn("chọn", updates[-1][0].lower())
        self.assertIsNone(updates[-1][1])
        self.assertTrue(updates[-1][3]["interactive"])

    def test_screen_has_masked_key_and_both_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles.json")
            async def create():
                return build_app(store=store)
            app = asyncio.run(create())
            self.addCleanup(app.close)
            components = app.config["components"]
            passwords = [c for c in components if c["type"] == "textbox"
                         and c["props"].get("type") == "password"]
            self.assertEqual(len(passwords), 1)
            self.assertEqual(passwords[0]["props"].get("value", ""), "")
            downloads = [c for c in components if c["type"] == "file" and not c["props"].get("interactive", True)]
            self.assertEqual(len(downloads), 2)
            self.assertFalse(app.analytics_enabled)


if __name__ == "__main__":
    unittest.main()
