import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests import test_jobs
from trans_document.jobs import JobRunner, TranslationRequest


class DeniedAPI(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        response = b'{"error":{"message":"secret-key is invalid","type":"invalid_api_key"}}'
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


class WorkerTests(unittest.TestCase):
    def test_real_worker_rejects_bad_key_before_document_translation(self):
        setup = test_jobs.JobTests()
        setup.setUp()
        self.addCleanup(setup.doCleanups)
        api = ThreadingHTTPServer(("127.0.0.1", 0), DeniedAPI)
        threading.Thread(target=api.serve_forever, daemon=True).start()
        self.addCleanup(api.server_close)
        self.addCleanup(api.shutdown)
        request = TranslationRequest(str(setup.source), f"http://127.0.0.1:{api.server_port}/v1",
                                     "test", "secret-key")
        runner = JobRunner(setup.root / "real-worker")
        events = list(runner.stream(request, "session"))
        self.assertEqual(events[-1], {"type": "error", "code": "authentication"})
        self.assertFalse(any("mono" in event for event in events))
        self.assertNotIn("secret-key", str(events))
