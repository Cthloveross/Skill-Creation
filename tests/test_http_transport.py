from __future__ import annotations

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from r2sp.model_client import ModelClientError, OpenAICompatibleClient
from r2sp.preflight import _fetch_model_record


class _RedirectFixture:
    def __init__(self) -> None:
        self.sink_requests: list[tuple[str, str | None]] = []
        fixture = self

        class Sink(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                fixture.sink_requests.append(("GET", self.headers.get("Authorization")))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "11")
                self.end_headers()
                self.wfile.write(b'{"data":[]}')

            do_POST = do_GET

            def log_message(self, _format, *_args):
                return

        self.sink = ThreadingHTTPServer(("127.0.0.1", 0), Sink)
        sink_port = self.sink.server_address[1]

        class Redirect(BaseHTTPRequestHandler):
            def _redirect(self):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{sink_port}/captured")
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = _redirect
            do_POST = _redirect

            def log_message(self, _format, *_args):
                return

        self.redirect = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        self.threads = [
            threading.Thread(target=self.sink.serve_forever, daemon=True),
            threading.Thread(target=self.redirect.serve_forever, daemon=True),
        ]
        for thread in self.threads:
            thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.redirect.server_address[1]}/v1"

    def close(self) -> None:
        self.redirect.shutdown()
        self.sink.shutdown()
        self.redirect.server_close()
        self.sink.server_close()
        for thread in self.threads:
            thread.join(timeout=2)


class RedirectSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _RedirectFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_preflight_does_not_forward_api_key_across_redirect(self) -> None:
        record, detail = _fetch_model_record(
            self.fixture.base_url,
            "Qwen/Qwen3.8-27B",
            api_key="EXPERIMENT_SECRET",
        )
        self.assertIsNone(record)
        self.assertIn("302", detail)
        self.assertEqual(self.fixture.sink_requests, [])

    def test_model_client_rejects_redirect_without_replaying_request(self) -> None:
        client = OpenAICompatibleClient(
            self.fixture.base_url,
            api_key="EXPERIMENT_SECRET",
            timeout_seconds=2,
        )
        with self.assertRaises(ModelClientError) as raised:
            client.complete([{"role": "user", "content": "probe"}])
        self.assertEqual(raised.exception.status, 302)
        self.assertEqual(self.fixture.sink_requests, [])


if __name__ == "__main__":
    unittest.main()
