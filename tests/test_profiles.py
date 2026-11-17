import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trans_document.profiles import ProfileStore, profile_store_path, validate_base_url


class ProfileStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "profiles.json"
        self.store = ProfileStore(self.path)

    def test_seed_and_persist_default(self):
        catalog = self.store.read()
        self.assertEqual([profile.name for profile in catalog.profiles], ["Gemini cá nhân", "OpenAI"])
        self.assertEqual(catalog.profiles[0].provider, "gemini")
        self.assertEqual(catalog.default_id, catalog.profiles[0].id)
        self.store.set_default(catalog.profiles[1].id)
        self.assertEqual(ProfileStore(self.path).read().default_id, catalog.profiles[1].id)

    def test_delete_default_and_keep_empty_catalog(self):
        catalog = self.store.read()
        self.store.delete(catalog.default_id)
        remaining = self.store.read()
        self.assertEqual(len(remaining.profiles), 1)
        self.assertEqual(remaining.default_id, remaining.profiles[0].id)
        self.store.delete(remaining.profiles[0].id)
        empty = ProfileStore(self.path).read()
        self.assertEqual(empty.profiles, ())
        self.assertIsNone(empty.default_id)

    def test_url_edits_rotate_key_slot(self):
        profile = self.store.read().profiles[0]
        edited = self.store.save(profile_id=profile.id, name=profile.name, provider=profile.provider,
                                 base_url=profile.base_url, model="another-model")
        self.assertEqual(edited.key_slot, profile.key_slot)
        changed = self.store.save(profile_id=profile.id, name=profile.name, provider=profile.provider,
                                  base_url="https://api.example.com/v1", model=profile.model)
        reverted = self.store.save(profile_id=profile.id, name=profile.name, provider=profile.provider,
                                   base_url=profile.base_url, model=profile.model)
        self.assertNotEqual(changed.key_slot, profile.key_slot)
        self.assertNotEqual(reverted.key_slot, profile.key_slot)
        self.assertNotEqual(reverted.key_slot, changed.key_slot)

    def test_bad_config_preserved(self):
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.read()
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{broken")

    def test_duplicate_key_slots_are_rejected(self):
        self.store.read()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["profiles"][1]["key_slot"] = payload["profiles"][0]["key_slot"]
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.read()

    def test_rejects_unsafe_base_urls(self):
        for url in ("https://user:pass@example.com/v1", "https://example.com/v1?key=x",
                    "https://example.com/v1#key", "file:///tmp/key"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_base_url(url)
        validate_base_url("http://127.0.0.1:8765/v1")

    def test_store_path_uses_local_application_data(self):
        with mock.patch.dict("os.environ", {"LOCALAPPDATA": "C:/Users/test/AppData/Local"}):
            self.assertEqual(profile_store_path(), Path("C:/Users/test/AppData/Local/TransDocument/profiles.json"))

    def test_saved_json_contains_no_secret_fields(self):
        profile = self.store.save(profile_id=None, name="Custom", provider="custom",
                                  base_url="https://api.example.com/v1", model="model")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(set(payload["profiles"][-1]), {
            "id", "name", "provider", "base_url", "model", "key_slot"
        })
        self.assertNotIn("api_key", payload["profiles"][-1])
        self.assertEqual(profile.model, "model")


if __name__ == "__main__":
    unittest.main()
