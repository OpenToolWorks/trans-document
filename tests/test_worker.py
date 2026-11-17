import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests import test_jobs
from trans_document.jobs import JobRunner, TranslationRequest
from trans_document.worker import check_connection


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


class ProbeAPI(BaseHTTPRequestHandler):
    status = 200
    payloads = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        self.payloads.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        if self.status != 200:
            body = b'{"error":{"message":"secret-marker leaked"}}'
            self.send_response(self.status)
        else:
            body = json.dumps({"choices": [{"message": {"content": "hello"}}]}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class WorkerTests(unittest.TestCase):
    def test_babeldoc_binary_reader_imports(self):
        from bitstring import BitStream

        self.assertTrue(BitStream)

    def test_connection_probe_uses_only_hello(self):
        ProbeAPI.status = 200
        ProbeAPI.payloads = []
        api = ThreadingHTTPServer(("127.0.0.1", 0), ProbeAPI)
        threading.Thread(target=api.serve_forever, daemon=True).start()
        self.addCleanup(api.server_close)
        self.addCleanup(api.shutdown)
        result = check_connection(f"http://127.0.0.1:{api.server_port}/v1", "local-test", "dummy-key")
        self.assertEqual(result, "ok")
        self.assertEqual(len(ProbeAPI.payloads), 1)
        self.assertEqual(ProbeAPI.payloads[0]["model"], "local-test")
        self.assertEqual(ProbeAPI.payloads[0]["messages"][-1]["content"], "Hello")

    def test_connection_probe_classifies_errors_without_exposing_response(self):
        api = ThreadingHTTPServer(("127.0.0.1", 0), ProbeAPI)
        threading.Thread(target=api.serve_forever, daemon=True).start()
        self.addCleanup(api.server_close)
        self.addCleanup(api.shutdown)
        url = f"http://127.0.0.1:{api.server_port}/v1"
        for status, expected in ((401, "authentication"), (403, "authentication"),
                                 (429, "quota"), (500, "backend")):
            with self.subTest(status=status):
                ProbeAPI.status = status
                result = check_connection(url, "local-test", "dummy-key")
                self.assertEqual(result, expected)
                self.assertNotIn("secret-marker", result)
                self.assertNotIn("dummy-key", result)
        self.assertEqual(check_connection("http://127.0.0.1:1/v1", "local-test", "dummy-key"), "connection")

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
