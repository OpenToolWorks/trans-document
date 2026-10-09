import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pymupdf

from tests.test_jobs import scripted_worker
from trans_document.app import build_app, translate_ui
from trans_document.jobs import JobRunner


class AppTests(unittest.TestCase):
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
        async def create():
            return build_app()
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
