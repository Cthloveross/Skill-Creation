"""Loopback-only metadata gateway for an OpenAI-compatible model service.

The gateway preserves the upstream model records and only augments the
``metadata`` object of an existing, matching record.  The injected values are
caller-supplied operational declarations; this module does not verify model
weights, process arguments, or the effective serving configuration.
"""

from __future__ import annotations

import copy
import http.client
import ipaddress
import json
import socket
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

DEFAULT_MAX_REQUEST_BODY_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_RESPONSE_BODY_BYTES = 64 * 1024 * 1024

_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


class ModelGatewayError(ValueError):
    """Invalid or unsafe gateway configuration or upstream model payload."""


@dataclass(frozen=True)
class BackendAddress:
    """Validated loopback HTTP backend."""

    host: str
    port: int
    base_path: str


def is_loopback_host(host: str) -> bool:
    """Return whether *host* is a literal loopback address or ``localhost``.

    Arbitrary DNS names are deliberately rejected, even when they currently
    resolve to loopback, so DNS rebinding cannot change the proxy destination.
    """

    if not isinstance(host, str) or not host:
        return False
    candidate = host.casefold()
    if candidate == "localhost":
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def parse_loopback_backend(backend_url: str) -> BackendAddress:
    """Parse a fixed loopback HTTP backend URL without credentials or query."""

    if not isinstance(backend_url, str) or not backend_url.strip():
        raise ModelGatewayError("backend_url must be a non-empty string")
    try:
        parsed = urllib.parse.urlsplit(backend_url)
        port = parsed.port
    except ValueError as exc:
        raise ModelGatewayError(f"invalid backend_url: {exc}") from exc
    if parsed.scheme.casefold() != "http":
        raise ModelGatewayError("backend_url must use http")
    if parsed.username is not None or parsed.password is not None:
        raise ModelGatewayError("backend_url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ModelGatewayError("backend_url must not contain a query or fragment")
    if parsed.hostname is None or not is_loopback_host(parsed.hostname):
        raise ModelGatewayError("backend_url host must be loopback")
    resolved_port = 80 if port is None else port
    if not 1 <= resolved_port <= 65535:
        raise ModelGatewayError("backend_url port is outside 1..65535")
    base_path = parsed.path.rstrip("/")
    if base_path and not base_path.startswith("/"):
        raise ModelGatewayError("backend_url path is invalid")
    backend_host = "127.0.0.1" if parsed.hostname.casefold() == "localhost" else parsed.hostname
    return BackendAddress(backend_host, resolved_port, base_path)


def normalize_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached, strict-JSON copy of caller-supplied metadata."""

    if not isinstance(metadata, Mapping):
        raise ModelGatewayError("metadata must be a mapping")
    try:
        encoded = json.dumps(
            dict(metadata),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ModelGatewayError(f"metadata must contain only strict JSON values: {exc}") from exc
    if not isinstance(decoded, dict):  # pragma: no cover - guarded by Mapping input
        raise ModelGatewayError("metadata must encode as a JSON object")
    return decoded


def inject_model_metadata(
    payload: Mapping[str, Any],
    *,
    model_id: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Inject declarations into existing records matching *model_id*.

    No record is synthesized and the input object is not mutated.  Existing
    upstream metadata is retained unless the caller supplies the same key.
    """

    if not isinstance(payload, Mapping):
        raise ModelGatewayError("/v1/models payload must be a JSON object")
    if not isinstance(model_id, str) or not model_id:
        raise ModelGatewayError("model_id must be a non-empty string")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ModelGatewayError("/v1/models payload must contain a data array")
    normalized = normalize_metadata(metadata)
    result = copy.deepcopy(dict(payload))
    for record in result["data"]:
        if not isinstance(record, dict) or record.get("id") != model_id:
            continue
        existing = record.get("metadata")
        if existing is not None and not isinstance(existing, dict):
            raise ModelGatewayError("matching model metadata must be a JSON object")
        record["metadata"] = {**(existing or {}), **copy.deepcopy(normalized)}
    return result


def filter_hop_by_hop_headers(
    headers: Mapping[str, str] | list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Remove standard and ``Connection``-nominated hop-by-hop headers."""

    items = list(headers.items()) if isinstance(headers, Mapping) else list(headers)
    connection_tokens: set[str] = set()
    for name, value in items:
        if name.casefold() == "connection":
            connection_tokens.update(token.strip().casefold() for token in value.split(","))
    blocked = _HOP_BY_HOP_HEADERS | connection_tokens | {"content-length", "host"}
    return [(name, value) for name, value in items if name.casefold() not in blocked]


class _GatewayHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        backend: BackendAddress,
        model_id: str,
        metadata: Mapping[str, Any],
        *,
        max_request_body_bytes: int,
        max_response_body_bytes: int,
        timeout_seconds: float,
    ) -> None:
        self.backend = backend
        self.model_id = model_id
        self.metadata = normalize_metadata(metadata)
        self.max_request_body_bytes = max_request_body_bytes
        self.max_response_body_bytes = max_response_body_bytes
        self.timeout_seconds = timeout_seconds
        super().__init__(server_address, _GatewayRequestHandler)


class _GatewayHTTPServerV6(_GatewayHTTPServer):
    address_family = socket.AF_INET6


class _GatewayRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(self.gateway.timeout_seconds)

    @property
    def gateway(self) -> _GatewayHTTPServer:
        server = self.server
        if not isinstance(server, _GatewayHTTPServer):  # pragma: no cover - construction invariant
            raise RuntimeError("gateway handler attached to the wrong server")
        return server

    def do_GET(self) -> None:  # noqa: N802
        self._proxy("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._proxy("POST")

    def do_CONNECT(self) -> None:  # noqa: N802
        self._json_error(405, "method_not_allowed", "only GET and POST are supported")

    def do_PUT(self) -> None:  # noqa: N802
        self._json_error(405, "method_not_allowed", "only GET and POST are supported")

    def do_DELETE(self) -> None:  # noqa: N802
        self._json_error(405, "method_not_allowed", "only GET and POST are supported")

    def do_PATCH(self) -> None:  # noqa: N802
        self._json_error(405, "method_not_allowed", "only GET and POST are supported")

    def do_HEAD(self) -> None:  # noqa: N802
        self._json_error(405, "method_not_allowed", "only GET and POST are supported")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._json_error(405, "method_not_allowed", "only GET and POST are supported")

    def do_TRACE(self) -> None:  # noqa: N802
        self._json_error(405, "method_not_allowed", "only GET and POST are supported")

    def _request_target(self) -> str:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.scheme or parsed.netloc or not self.path.startswith("/") or parsed.fragment:
            raise ModelGatewayError("request target must be an origin-form path")
        return f"{self.gateway.backend.base_path}{self.path}"

    def _request_body(self, method: str) -> bytes:
        transfer_encoding = self.headers.get("Transfer-Encoding")
        if transfer_encoding:
            raise ModelGatewayError("transfer-encoded request bodies are not supported")
        content_lengths = self.headers.get_all("Content-Length", failobj=[])
        if not content_lengths:
            return b""
        if len(content_lengths) != 1:
            raise ModelGatewayError("request must contain at most one Content-Length header")
        raw_length = content_lengths[0]
        try:
            length = int(raw_length, 10)
        except ValueError as exc:
            raise ModelGatewayError("Content-Length must be an integer") from exc
        if length < 0:
            raise ModelGatewayError("Content-Length must not be negative")
        if length > self.gateway.max_request_body_bytes:
            raise OverflowError("request body exceeds the configured limit")
        if method == "GET" and length:
            raise ModelGatewayError("GET request bodies are not supported")
        body = self.rfile.read(length)
        if len(body) != length:
            raise ModelGatewayError("request body is shorter than Content-Length")
        return body

    def _proxy(self, method: str) -> None:
        try:
            target = self._request_target()
            body = self._request_body(method)
        except TimeoutError:
            self._json_error(408, "request_timeout", "timed out while reading request body")
            return
        except OverflowError as exc:
            self._json_error(413, "request_too_large", str(exc))
            return
        except ModelGatewayError as exc:
            self._json_error(400, "invalid_request", str(exc))
            return

        request_headers = filter_hop_by_hop_headers(list(self.headers.items()))
        if urllib.parse.urlsplit(self.path).path == "/v1/models":
            request_headers = [
                (name, value)
                for name, value in request_headers
                if name.casefold() != "accept-encoding"
            ]
            request_headers.append(("Accept-Encoding", "identity"))
        request_headers.append(("Host", _format_authority(self.gateway.backend)))
        if body:
            request_headers.append(("Content-Length", str(len(body))))

        connection = http.client.HTTPConnection(
            self.gateway.backend.host,
            self.gateway.backend.port,
            timeout=self.gateway.timeout_seconds,
        )
        try:
            connection.request(method, target, body=body or None, headers=dict(request_headers))
            response = connection.getresponse()
            response_body = response.read(self.gateway.max_response_body_bytes + 1)
            if len(response_body) > self.gateway.max_response_body_bytes:
                self._json_error(502, "upstream_response_too_large", "upstream body exceeds limit")
                return
            response_headers = list(response.getheaders())
            status = response.status
            reason = response.reason
        except TimeoutError:
            self._json_error(504, "upstream_timeout", "upstream model service timed out")
            return
        except (OSError, http.client.HTTPException) as exc:
            self._json_error(502, "upstream_error", str(exc))
            return
        finally:
            connection.close()

        if urllib.parse.urlsplit(self.path).path == "/v1/models" and 200 <= status < 300:
            try:
                payload = json.loads(response_body.decode("utf-8"))
                transformed = inject_model_metadata(
                    payload,
                    model_id=self.gateway.model_id,
                    metadata=self.gateway.metadata,
                )
                response_body = json.dumps(
                    transformed,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (UnicodeDecodeError, json.JSONDecodeError, ModelGatewayError) as exc:
                self._json_error(502, "invalid_models_response", str(exc))
                return

        self.send_response(status, reason)
        for name, value in filter_hop_by_hop_headers(response_headers):
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        if response_body:
            self.wfile.write(response_body)

    def _json_error(self, status: int, code: str, message: str) -> None:
        body = json.dumps(
            {"error": {"code": code, "message": message}}, separators=(",", ":")
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


def _format_authority(backend: BackendAddress) -> str:
    host = f"[{backend.host}]" if ":" in backend.host else backend.host
    return f"{host}:{backend.port}"


def create_model_gateway_server(
    *,
    backend_url: str,
    model_id: str,
    metadata: Mapping[str, Any],
    host: str = "127.0.0.1",
    port: int = 0,
    max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES,
    max_response_body_bytes: int = DEFAULT_MAX_RESPONSE_BODY_BYTES,
    timeout_seconds: float = 120.0,
) -> ThreadingHTTPServer:
    """Create a validated gateway server without starting its event loop."""

    if not is_loopback_host(host):
        raise ModelGatewayError("gateway host must be loopback")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ModelGatewayError("gateway port must be an integer in 0..65535")
    if not isinstance(model_id, str) or not model_id:
        raise ModelGatewayError("model_id must be a non-empty string")
    if (
        isinstance(max_request_body_bytes, bool)
        or not isinstance(max_request_body_bytes, int)
        or max_request_body_bytes <= 0
    ):
        raise ModelGatewayError("max_request_body_bytes must be a positive integer")
    if (
        isinstance(max_response_body_bytes, bool)
        or not isinstance(max_response_body_bytes, int)
        or max_response_body_bytes <= 0
    ):
        raise ModelGatewayError("max_response_body_bytes must be a positive integer")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ModelGatewayError("timeout_seconds must be a positive number")
    if timeout_seconds <= 0:
        raise ModelGatewayError("timeout_seconds must be a positive number")
    bind_host = "127.0.0.1" if host.casefold() == "localhost" else host
    server_class = _GatewayHTTPServerV6 if ":" in bind_host else _GatewayHTTPServer
    return server_class(
        (bind_host, port),
        parse_loopback_backend(backend_url),
        model_id,
        metadata,
        max_request_body_bytes=max_request_body_bytes,
        max_response_body_bytes=max_response_body_bytes,
        timeout_seconds=float(timeout_seconds),
    )


def serve_model_gateway(
    *,
    backend_url: str,
    model_id: str,
    metadata: Mapping[str, Any],
    host: str = "127.0.0.1",
    port: int = 8001,
    max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES,
    max_response_body_bytes: int = DEFAULT_MAX_RESPONSE_BODY_BYTES,
    timeout_seconds: float = 120.0,
) -> None:
    """Serve the loopback gateway until interrupted by the caller."""

    server = create_model_gateway_server(
        backend_url=backend_url,
        model_id=model_id,
        metadata=metadata,
        host=host,
        port=port,
        max_request_body_bytes=max_request_body_bytes,
        max_response_body_bytes=max_response_body_bytes,
        timeout_seconds=timeout_seconds,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
