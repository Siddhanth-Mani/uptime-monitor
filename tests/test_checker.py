import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from monitor.checker import check_site


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ok":
            body = b"<h1>Hello status page</h1>"
            self.send_response(200)
        elif self.path == "/flaky":
            Handler.flaky_calls += 1
            code = 503 if Handler.flaky_calls == 1 else 200
            body = b"recovered"
            self.send_response(code)
        else:
            body = b"broken"
            self.send_response(500)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class CheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def check(self, path, expect=None):
        self.sleeps = []
        return check_site(self.base + path, expect, timeout=5, sleep=self.sleeps.append, cert_lookup=lambda h: 42)

    def test_up(self):
        r = self.check("/ok", "Hello")
        self.assertTrue(r.ok)
        self.assertEqual(r.status, 200)
        self.assertIsNotNone(r.ms)
        self.assertIsNone(r.cert_days)  # plain http: no certificate
        self.assertEqual(self.sleeps, [])

    def test_expected_text_missing(self):
        r = self.check("/ok", "Goodbye")
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "Expected text missing")

    def test_http_error(self):
        r = self.check("/boom")
        self.assertFalse(r.ok)
        self.assertEqual((r.status, r.error), (500, "HTTP 500"))
        self.assertEqual(len(self.sleeps), 1)  # retried once

    def test_retry_recovers(self):
        Handler.flaky_calls = 0
        r = self.check("/flaky")
        self.assertTrue(r.ok)
        self.assertEqual(Handler.flaky_calls, 2)

    def test_connection_refused(self):
        s = HTTPServer(("127.0.0.1", 0), Handler)
        port = s.server_port
        s.server_close()
        r = check_site(f"http://127.0.0.1:{port}/", timeout=3, sleep=lambda _: None, cert_lookup=lambda h: None)
        self.assertFalse(r.ok)
        self.assertIsNone(r.status)
        self.assertIn(r.error, ("Connection refused", "Timed out"))

    def test_https_reads_cert(self):
        r = check_site("https://127.0.0.1:1/", timeout=1, sleep=lambda _: None, cert_lookup=lambda h: 42)
        self.assertEqual(r.cert_days, 42)


if __name__ == "__main__":
    unittest.main()
