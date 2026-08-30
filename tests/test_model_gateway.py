import copy
import http.client
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from r2sp.model_gateway import (
    ModelGatewayError,
    create_model_gateway_server,
    filter_hop_by_hop_headers,
    inject_model_metadata,
    is_loopback_host,
    parse_loopback_backend,
)


class _UpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/v1/models"):
            body = json.dumps(
                {
                    "object": "list",
                    "data": [
                        {"id": "other/model", "metadata": {"untouched": True}},
                        {"id": "Qwen/Qwen3.8-27B", "metadata": {"upstream": "kept"}},
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "X-Upstream-Hop")
            self.send_header("X-Upstream-Hop", "must-not-pass")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b'{"error":"missing"}'
        self.send_response(418)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        body = json.dumps(
            {
                "payload": payload,
                "hop_header": self.headers.get("X-Client-Hop"),
                "host": self.headers.get("Host"),
            }
        ).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


class ModelGatewayFunctionTests(unittest.TestCase):
    def test_loopback_validation_rejects_dns_and_remote_addresses(self):
        self.assertTrue(is_loopback_host("localhost"))
        self.assertTrue(is_loopback_host("127.8.9.10"))
        self.assertTrue(is_loopback_host("::1"))
        self.assertFalse(is_loopback_host("example.test"))
        self.assertFalse(is_loopback_host("0.0.0.0"))
        with self.assertRaisesRegex(ModelGatewayError, "loopback"):
            parse_loopback_backend("http://192.0.2.1:8000")
        with self.assertRaisesRegex(ModelGatewayError, "credentials"):
            parse_loopback_backend("http://user:secret@127.0.0.1:8000")
        self.assertEqual(parse_loopback_backend("http://localhost:8000").host, "127.0.0.1")

    def test_gateway_bind_address_must_be_loopback(self):
        with self.assertRaisesRegex(ModelGatewayError, "gateway host must be loopback"):
            create_model_gateway_server(
                backend_url="http://127.0.0.1:8000",
                model_id="model",
                metadata={},
                host="0.0.0.0",
            )

    def test_metadata_is_only_merged_into_a_real_matching_record(self):
        payload = {
            "object": "list",
            "data": [
                {"id": "expected", "metadata": {"source": "upstream", "dtype": "old"}},
                {"id": "other"},
            ],
        }
        original = copy.deepcopy(payload)

        result = inject_model_metadata(
            payload,
            model_id="expected",
            metadata={"dtype": "bfloat16", "runtime": {"max_model_len": 65536}},
        )

        self.assertEqual(payload, original)
        self.assertEqual(
            result["data"][0]["metadata"],
            {
                "source": "upstream",
                "dtype": "bfloat16",
                "runtime": {"max_model_len": 65536},
            },
        )
        self.assertNotIn("metadata", result["data"][1])

    def test_missing_model_is_not_synthesized(self):
        payload = {"object": "list", "data": [{"id": "actual"}]}
        result = inject_model_metadata(payload, model_id="requested", metadata={"x": 1})
        self.assertEqual(result, payload)

    def test_hop_by_hop_and_connection_named_headers_are_filtered(self):
        filtered = filter_hop_by_hop_headers(
            [
                ("Connection", "X-Private, keep-alive"),
                ("X-Private", "secret"),
                ("Transfer-Encoding", "chunked"),
                ("Content-Type", "application/json"),
            ]
        )
        self.assertEqual(filtered, [("Content-Type", "application/json")])


class ModelGatewayHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
        cls.upstream_thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.upstream_thread.start()
        upstream_port = cls.upstream.server_address[1]
        cls.gateway = create_model_gateway_server(
            backend_url=f"http://127.0.0.1:{upstream_port}",
            model_id="Qwen/Qwen3.8-27B",
            metadata={"revision": "pinned", "dtype": "bfloat16"},
            max_request_body_bytes=32,
        )
        cls.gateway_thread = threading.Thread(target=cls.gateway.serve_forever, daemon=True)
        cls.gateway_thread.start()
        cls.gateway_port = cls.gateway.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.gateway.shutdown()
        cls.gateway.server_close()
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.gateway_thread.join(timeout=2)
        cls.upstream_thread.join(timeout=2)

    def request(self, method, path, *, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.gateway_port, timeout=2)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        response_headers = response.getheaders()
        status = response.status
        connection.close()
        return status, response_headers, payload

    def test_models_response_keeps_identity_and_injects_declarations(self):
        status, headers, body = self.request("GET", "/v1/models?source=probe")
        payload = json.loads(body)

        self.assertEqual(status, 200)
        self.assertEqual(payload["data"][0]["metadata"], {"untouched": True})
        self.assertEqual(
            payload["data"][1]["metadata"],
            {"upstream": "kept", "revision": "pinned", "dtype": "bfloat16"},
        )
        self.assertNotIn("x-upstream-hop", {name.casefold() for name, _ in headers})

    def test_post_body_status_and_json_are_forwarded_without_hop_header(self):
        status, _headers, body = self.request(
            "POST",
            "/v1/chat/completions",
            body=b'{"prompt":"ok"}',
            headers={
                "Content-Type": "application/json",
                "Connection": "X-Client-Hop",
                "X-Client-Hop": "must-not-pass",
            },
        )
        payload = json.loads(body)

        self.assertEqual(status, 201)
        self.assertEqual(payload["payload"], {"prompt": "ok"})
        self.assertIsNone(payload["hop_header"])
        self.assertRegex(payload["host"], r"^127\.0\.0\.1:\d+$")

    def test_request_body_limit_is_enforced_before_upstream(self):
        status, _headers, body = self.request(
            "POST",
            "/v1/chat/completions",
            body=b"x" * 33,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(body)["error"]["code"], "request_too_large")

    def test_upstream_error_status_and_json_are_forwarded(self):
        status, _headers, body = self.request("GET", "/not-found")
        self.assertEqual(status, 418)
        self.assertEqual(json.loads(body), {"error": "missing"})

    def test_non_get_post_method_is_rejected(self):
        status, _headers, body = self.request("PUT", "/v1/models")
        self.assertEqual(status, 405)
        self.assertEqual(json.loads(body)["error"]["code"], "method_not_allowed")


if __name__ == "__main__":
    unittest.main()
