import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

import pymupdf

from trans_document.jobs import JobRunner, TranslationRequest


def scripted_worker(request, output_dir, connection):
    try:
        connection.send({"type": "progress", "stage": "Translate Paragraphs", "percent": 40,
                         "preview_pages": request.preview_pages})
        if request.model == "blocked":
            time.sleep(60)
        elif request.model == "crash":
            os._exit(2)
        elif request.model == "failure":
            connection.send({"type": "error", "code": "authentication"})
            return
        mono = Path(output_dir) / "mono.pdf"
        dual = Path(output_dir) / "dual.pdf"
        mono.write_bytes(Path(request.pdf_path).read_bytes())
        dual.write_bytes(mono.read_bytes())
        connection.send({"type": "finish", "mono": str(mono),
                         "dual": str(Path(request.pdf_path) if request.model == "foreign" else dual)})
    finally:
        connection.close()


class JobTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source.pdf"
        with pymupdf.open() as document:
            document.new_page().insert_text((40, 40), "Hello world")
            document.save(self.source)
        self.runner = JobRunner(self.root / "outputs", worker=scripted_worker)
        self.request = TranslationRequest(str(self.source), "http://127.0.0.1:1/v1", "test", "secret-key")

    def test_progress_and_two_valid_pdf_downloads(self):
        events = list(self.runner.stream(self.request, "session"))
        self.assertTrue(any(e.get("percent") == 40 for e in events))
        self.assertEqual(events[-1]["type"], "finish")
        self.assertTrue(Path(events[-1]["mono"]).is_file())
        self.assertTrue(Path(events[-1]["dual"]).is_file())
        self.assertTrue(Path(events[-1]["source"]).is_file())
        self.assertEqual(events[-1]["source"], str(Path(events[-1]["mono"]).parents[1] / "input.pdf"))
        self.assertNotIn("secret-key", repr(self.request))
        self.assertNotIn("secret-key", str(events))

    def test_error_never_exposes_partial_downloads(self):
        request = replace(self.request, model="failure")
        events = list(self.runner.stream(request, "session"))
        self.assertEqual(events[-1], {"type": "error", "code": "authentication"})
        self.assertFalse(any("mono" in event for event in events))

    def test_foreign_output_is_rejected(self):
        events = list(self.runner.stream(replace(self.request, model="foreign"), "session"))
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(events[-1]["code"], "output")

    def test_worker_crash_is_terminal(self):
        events = list(self.runner.stream(replace(self.request, model="crash"), "session"))
        self.assertEqual(events[-1], {"type": "error", "code": "worker"})

    def test_cancel_is_owned_and_releases_active_job(self):
        stream = self.runner.stream(replace(self.request, model="blocked"), "owner")
        self.addCleanup(stream.close)
        self.assertEqual(next(stream)["type"], "progress")
        self.assertFalse(self.runner.cancel("another-session"))
        with self.assertRaisesRegex(ValueError, "đang chạy"):
            list(self.runner.stream(self.request, "another-session"))
        started = time.monotonic()
        self.assertTrue(self.runner.cancel("owner"))
        self.assertEqual(list(stream)[-1]["type"], "cancelled")
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(list(self.runner.stream(self.request, "owner"))[-1]["type"], "finish")

    def test_invalid_pdf_and_credential_url_are_rejected(self):
        bad = self.root / "bad.pdf"
        bad.write_text("not a PDF")
        for request in (
            TranslationRequest(str(bad), self.request.base_url, "test", "key"),
            TranslationRequest(str(self.source), "https://key@example.com/v1", "test", "key"),
            TranslationRequest(str(self.source), "ftp://example.com/v1", "test", "key"),
            TranslationRequest(str(self.source), self.request.base_url, "test", ""),
        ):
            with self.subTest(url=request.base_url), self.assertRaises(ValueError):
                list(self.runner.stream(request, "session"))

    def test_preview_page_count_validated_before_worker(self):
        with pymupdf.open() as document:
            document.new_page()
            document.new_page()
            document.new_page()
            three_pages = self.root / "three-pages.pdf"
            document.save(three_pages)
        for pages in (0, 4, True, "2"):
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                list(self.runner.stream(replace(self.request, preview_pages=pages), "session"))
        request = replace(self.request, pdf_path=str(three_pages), preview_pages=3)
        self.assertEqual(list(self.runner.stream(request, "session"))[-1]["type"], "finish")

    def test_preview_request_reaches_worker(self):
        event = next(event for event in self.runner.stream(
            replace(self.request, preview_pages=1), "session") if "preview_pages" in event)
        self.assertEqual(event["preview_pages"], 1)


if __name__ == "__main__":
    unittest.main()
