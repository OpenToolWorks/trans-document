"""Opt-in real BabelDOC smoke with a local fake API; downloads engine assets."""

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pymupdf

from trans_document.jobs import JobRunner, TranslationRequest


class FakeAPI(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = payload["messages"][-1]["content"]
        if "## Here is the input:" in prompt:
            entries = json.loads(prompt.split("## Here is the input:")[-1].strip())
            content = json.dumps([{"id": entry["id"], "output": "Đây là một tài liệu thử nghiệm."}
                                  for entry in entries], ensure_ascii=False)
        else:
            content = "Đây là một tài liệu thử nghiệm."
        response = json.dumps({
            "id": "local-test", "object": "chat.completion", "created": 0, "model": "local-test",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def main():
    api = ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            with pymupdf.open() as document:
                for page_number in range(1, 4):
                    page = document.new_page()
                    for line in range(20):
                        page.insert_text(
                            (72, 60 + line * 30),
                            f"Page marker {page_number}, line {line + 1}. This is a sample document for translation."
                        )
                document.save(source)
            runner = JobRunner(root / "outputs")
            for preview_pages, expected_count in ((2, 2), (None, 3)):
                request = TranslationRequest(
                    str(source), f"http://127.0.0.1:{api.server_port}/v1", "local-test", "dummy",
                    preview_pages=preview_pages,
                )
                terminal = None
                for event in runner.stream(request, "smoke"):
                    print(json.dumps(event, ensure_ascii=True), flush=True)
                    terminal = event
                assert terminal["type"] == "finish", terminal
                with pymupdf.open(terminal["mono"]) as document:
                    text = "\n".join(page.get_text() for page in document)
                    assert document.page_count == expected_count, document.page_count
                    assert "tài liệu" in text, text
                with pymupdf.open(terminal["dual"]) as document:
                    assert document.page_count == expected_count, document.page_count
            print("REAL BABELDOC TRIAL + FULL TRANSLATION: PASS")
    finally:
        api.shutdown()
        api.server_close()


if __name__ == "__main__":
    main()
