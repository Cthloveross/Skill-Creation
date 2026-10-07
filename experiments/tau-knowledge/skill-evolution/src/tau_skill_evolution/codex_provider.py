"""Credential-free Codex Responses relay into a bounded, journaled host provider.

Only the relay and a Unix socket enter the task container. Provider credentials,
the experiment checkout and the request journal stay on the host. Responses are
buffered and sealed before delivery; no dispatched POST is automatically retried.
"""

from __future__ import annotations

import base64
import contextlib
import http.server
import io
import json
import math
import os
import socketserver
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from .core._canonical import canonical_json_sha256
from .credentials import bearer_token_source
from .journal import Journal, UnknownOperation
from .model import (
    CredentialError,
    InputTokenBudgetExceeded,
    ModelClientError,
    anthropic_to_responses,
    responses_to_anthropic,
)
from .runtime_controls import RuntimeControls

RELAY_PORT = 18765
OUTPUT_TOKEN_BUDGET_STOP = "provider_output_token_budget_exhausted"


def _input_estimate(payload: Mapping[str, Any], counter: Callable[[str], int]) -> dict[str, int]:
    """Count text and conservative visual patches, never base64 as prose.

    Only an estimate copy loses image bytes. The journal and provider request keep
    the original image. Inline dimensions are read without decoding pixels; URLs
    are never fetched. Raw unscaled patches deliberately overestimate resized
    images. Sources: OpenAI images-vision and Claude build-with-claude/vision.
    """
    image_tokens = image_count = 0
    messages = payload.get("model") == "anthropic.claude-opus-4-8"

    def image(url: str | None, data: str | None) -> dict[str, Any]:
        nonlocal image_tokens, image_count
        width = height = None
        if data is None and url and url.startswith("data:image/"):
            head, separator, data = url.partition(",")
            if not separator or not head.endswith(";base64"):
                raise ModelClientError("provider_invalid_image", "invalid inline image source")
        if data is not None:
            try:
                from PIL import Image
            except ImportError as error:
                raise ModelClientError(
                    "provider_image_dependency_missing", "install the pinned Codex image dependency"
                ) from error
            try:
                raw = base64.b64decode(data, validate=True)
                with Image.open(io.BytesIO(raw)) as picture:
                    width, height = picture.size
                    picture.verify()
                if width <= 0 or height <= 0:
                    raise ValueError("empty image dimensions")
            except (ValueError, OSError, SyntaxError, Image.DecompressionBombError) as error:
                raise ModelClientError(
                    "provider_invalid_image", "inline image dimensions cannot be verified"
                ) from error
            patch = 28 if messages else 32
            # Terra's multiplier is 1.2; use the same margin for other models.
            reserve = math.ceil(math.ceil(width / patch) * math.ceil(height / patch) * 1.2)
        else:
            reserve = 36_000  # Conservative Terra original-detail maximum; no URL fetch.
        image_count += 1
        image_tokens += reserve
        return {"type": "image_admission_metadata", "width": width, "height": height}

    def visit(value: Any) -> Any:
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, Mapping):
            return value
        if value.get("type") == "input_image" and isinstance(value.get("image_url"), str):
            return image(value["image_url"], None)
        source = value.get("source")
        if value.get("type") == "image" and isinstance(source, Mapping):
            if source.get("type") == "base64" and isinstance(source.get("data"), str):
                return image(None, source["data"])
            if source.get("type") == "url" and isinstance(source.get("url"), str):
                return image(source["url"], None)
        return {key: visit(item) for key, item in value.items()}

    text_tokens = counter(_json_bytes(visit(payload)).decode())
    if isinstance(text_tokens, bool) or not isinstance(text_tokens, int) or text_tokens <= 0:
        raise ValueError("token counter returned no positive count")
    return {
        "text_tokens": text_tokens,
        "image_tokens": image_tokens,
        "image_count": image_count,
        "total_tokens": text_tokens + image_tokens,
    }


RELAY_SCRIPT = r'''"""Forward container-local Responses HTTP to the host Unix socket."""
import http.client
import http.server
import socket
import sys

class Connection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(PROVIDER_TIMEOUT_SECONDS)
        self.sock.connect(sys.argv[1])

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 8388608 or self.headers.get("Transfer-Encoding"):
                self.send_error(413)
                return
            body = self.rfile.read(length)
            connection = Connection("localhost")
            try:
                connection.request("POST", self.path, body, {"Content-Type": "application/json"})
                response = connection.getresponse()
                self.send_response(response.status)
                content_type = response.getheader("Content-Type", "application/json")
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", response.getheader("Content-Length", "0"))
                self.end_headers()
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                self.wfile.flush()
            finally:
                connection.close()
        except (OSError, ValueError, http.client.HTTPException):
            self.close_connection = True
    def log_message(self, *args):
        pass

http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[2])), Handler).serve_forever()
'''


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True).encode("utf-8")


def _completed_response(body: bytes) -> tuple[dict[str, Any], bool]:
    """Read the terminal Responses event without rewriting native Codex tools."""
    stripped = body.lstrip()
    streamed = stripped.startswith((b"event:", b"data:"))
    if not streamed:
        value = json.loads(body)
    else:
        value = None
        text = body.decode("utf-8").replace("\r\n", "\n")
        for event in text.split("\n\n"):
            data = "\n".join(
                line[5:].lstrip() for line in event.splitlines() if line.startswith("data:")
            )
            if not data or data == "[DONE]":
                continue
            parsed = json.loads(data)
            if parsed.get("type") in {"response.completed", "response.incomplete"}:
                value = parsed.get("response")
            elif parsed.get("type") in {"error", "response.failed"}:
                raise ModelClientError("provider_stream_failed", "provider stream failed")
    if not isinstance(value, dict) or value.get("status") not in {"completed", "incomplete"}:
        raise ModelClientError("provider_response_incomplete", "no terminal Responses result")
    if not isinstance(value.get("output"), list) or not isinstance(value.get("usage"), dict):
        raise ModelClientError("provider_response_invalid", "Responses output or usage is missing")
    return value, streamed


def _response_sse(response: Mapping[str, Any]) -> bytes:
    """Emit Responses events only when the provider ignored stream=true."""
    events: list[bytes] = []

    def emit(kind: str, **fields: Any) -> None:
        payload = {"type": kind, "sequence_number": len(events), **fields}
        events.append(b"event: " + kind.encode() + b"\ndata: " + _json_bytes(payload) + b"\n\n")

    emit("response.created", response={**response, "status": "in_progress", "output": []})
    for index, item in enumerate(response["output"]):
        item_id = item.get("id", f"output_{index}")
        opening = dict(item)
        if item["type"] == "message":
            opening["content"] = []
        elif item["type"] == "function_call":
            opening["arguments"] = ""
        elif item["type"] == "custom_tool_call":
            opening["input"] = ""
        emit("response.output_item.added", output_index=index, item=opening)
        common = {"output_index": index, "item_id": item_id}
        if item["type"] == "message":
            for part_index, part in enumerate(item.get("content", [])):
                coordinates = {**common, "content_index": part_index}
                if part["type"] == "output_text":
                    emit("response.content_part.added", **coordinates, part={**part, "text": ""})
                    emit("response.output_text.delta", **coordinates, delta=part["text"])
                    emit("response.output_text.done", **coordinates, text=part["text"])
                elif part["type"] == "refusal":
                    emit("response.content_part.added", **coordinates, part={**part, "refusal": ""})
                    emit("response.refusal.delta", **coordinates, delta=part["refusal"])
                    emit("response.refusal.done", **coordinates, refusal=part["refusal"])
                else:
                    emit("response.content_part.added", **coordinates, part=part)
                emit("response.content_part.done", **coordinates, part=part)
        elif item["type"] == "function_call":
            emit("response.function_call_arguments.delta", **common, delta=item["arguments"])
            emit("response.function_call_arguments.done", **common, arguments=item["arguments"])
        elif item["type"] == "custom_tool_call":
            emit("response.custom_tool_call_input.delta", **common, delta=item["input"])
            emit("response.custom_tool_call_input.done", **common, input=item["input"])
        emit("response.output_item.done", output_index=index, item=item)
    kind = "response.completed" if response["status"] == "completed" else "response.incomplete"
    emit(kind, response=response)
    return b"".join(events)


class ProviderGateway:
    def __init__(
        self,
        directory: Path,
        provider: Mapping[str, Any],
        controls: RuntimeControls,
        journal: Journal,
        token_counter: Callable[[str], int],
        timeout_seconds: float,
        max_requests: int,
        max_request_bytes: int,
        max_response_bytes: int,
        opener: Any = None,
    ) -> None:
        self.base_url = f"http://127.0.0.1:{RELAY_PORT}/v1"
        self.socket_path = directory / "provider.sock"
        self.relay_path = directory / "relay.py"
        self.provider, self.controls, self.journal = dict(provider), controls, journal
        self.messages_transport = self.provider.get("transport") == "bedrock-messages"
        self.token_counter, self.timeout_seconds = token_counter, timeout_seconds
        self._opener = opener or urllib.request.urlopen
        self.max_requests = max_requests
        self.max_request_bytes, self.max_response_bytes = max_request_bytes, max_response_bytes
        self._lock = threading.Lock()
        self._cached: dict[str, tuple[bytes, str]] = {}
        self._active_operation: str | None = None
        self.statistics: dict[str, Any] = {
            "requests": 0,
            "input_tokens_estimate": 0,
            "input_token_estimates": [],
            "vision_estimation_basis": (
                "raw_unscaled_patches_x1.2; Responses32px/Messages28px; URL36000"
            ),
            "input_token_estimation_basis": (
                "serialized_anthropic_messages_payload"
                if self.messages_transport
                else "serialized_native_responses_payload"
            ),
            "output_tokens": 0,
            "usage": [],
            "halted": False,
            "closed": False,
            "failure_code": None,
            "authentication_status": None,
            "unknown_operation": False,
            "terminal_stop": None,
        }
        self._restore()

    def close_public(self) -> None:
        """Wait for any dispatched request, then refuse model calls during grading."""
        with self._lock:
            self.statistics["closed"] = True

    @staticmethod
    def _delivery(result: Mapping[str, Any], streaming: bool) -> tuple[bytes, str]:
        if result.get("provider_transport") == "bedrock-messages":
            # The sealed body is the actual Messages response, never Responses wire bytes.
            return (
                _response_sse(result["response"]) if streaming else _json_bytes(result["response"]),
                "text/event-stream" if streaming else "application/json",
            )
        raw = base64.b64decode(result["body_base64"], validate=True)
        delivered = (
            raw if result["streamed"] or not streaming else _response_sse(result["response"])
        )
        content_type = (
            "text/event-stream" if result["streamed"] or streaming else "application/json"
        )
        return delivered, content_type

    def _restore(self) -> None:
        for path in self.journal.root.glob("*/request.json"):
            request = json.loads(path.read_text())
            key = request["operation_id"]
            status = self.journal.status(key)
            if status == "NOT_SENT":
                continue
            self.statistics["requests"] += 1
            if status != "COMPLETED" and self.journal.received(key):

                def no_dispatch(*_args: Any) -> Any:
                    raise UnknownOperation("provider recovery cannot dispatch a POST")

                try:
                    self.journal.dispatch_raw(
                        key,
                        request["payload"],
                        no_dispatch,
                        no_dispatch,
                        self._normalizer(request["payload"]),
                    )
                    status = "COMPLETED"
                except BaseException as error:
                    self._halt(error)
                    continue
            if status != "COMPLETED":
                self.statistics.update(
                    halted=True,
                    failure_code="provider_previous_operation_unresolved",
                    unknown_operation=self.statistics["unknown_operation"] or status == "UNKNOWN",
                    authentication_status=self.statistics["authentication_status"]
                    or self.journal.authentication_failure(),
                )
                continue
            result = self.journal.response(key)
            details = _input_estimate(
                request["payload"].get("provider_request", request["payload"]), self.token_counter
            )
            estimate = details["total_tokens"]
            self.statistics["input_token_estimates"].append({"operation_key": key, **details})
            self.statistics["input_tokens_estimate"] += estimate
            try:
                self._account_response(key, self._output_limit(request["payload"]), result)
            except ModelClientError as error:
                self._halt(error)
                continue
            self._cached[key] = self._delivery(result, request["payload"].get("stream", False))

    def _account_usage(self, key: str, usage: Mapping[str, Any]) -> None:
        self.statistics["output_tokens"] += usage["output_tokens"]
        self.statistics["usage"].append({"operation_key": key, **usage})

    def _output_limit(self, payload: Mapping[str, Any]) -> int | None:
        if self.messages_transport:
            return payload["provider_request"]["max_tokens"]
        return payload.get("max_output_tokens")

    def _normalizer(self, payload: Mapping[str, Any]) -> Callable[[int, bytes], dict[str, Any]]:
        if self.messages_transport:
            return lambda status, body: self._normalize(
                status, body, tools=payload.get("tools", ())
            )
        return self._normalize

    def _account_response(self, key: str, limit: int | None, result: Mapping[str, Any]) -> None:
        response = result["response"]
        self._account_usage(key, response["usage"])
        self._check_output_usage(limit, response["usage"])
        if response["status"] != "incomplete":
            return
        details = response.get("incomplete_details")
        reason = details.get("reason") if isinstance(details, dict) else None
        code, kind = {
            "max_output_tokens": (OUTPUT_TOKEN_BUDGET_STOP, "budget"),
            "interrupted": ("provider_response_interrupted", "interrupted"),
            "content_filter": ("provider_content_filter", "policy"),
        }.get(
            reason if isinstance(reason, str) else None,
            ("provider_incomplete_reason_unknown", "provider"),
        )
        if not self.statistics["halted"]:
            self.statistics.update(
                halted=True,
                failure_code=code,
                terminal_stop={
                    "kind": kind,
                    "reason": reason if isinstance(reason, str) else None,
                    "operation_key": key,
                    "response_status": "incomplete",
                },
            )

    def _check_output_usage(self, limit: int | None, usage: Mapping[str, Any]) -> None:
        if limit is not None and usage["output_tokens"] > limit:
            self.statistics["output_budget_violation"] = {
                "requested_max_output_tokens": limit,
                "reported_output_tokens": usage["output_tokens"],
            }
            raise ModelClientError(
                "provider_output_token_limit_exceeded", "provider exceeded requested output limit"
            )

    def _halt(self, error: BaseException) -> None:
        authentication = getattr(error, "status", None)
        authentication = authentication if authentication in (401, 403) else None
        unknown = isinstance(error, UnknownOperation) or bool(
            self._active_operation and self.journal.status(self._active_operation) == "UNKNOWN"
        )
        preserve = self.statistics["unknown_operation"] or self.statistics["authentication_status"]
        self.statistics.update(
            halted=True,
            failure_code=self.statistics["failure_code"]
            if preserve and not (unknown or authentication)
            else getattr(error, "code", type(error).__name__),
            authentication_status=self.statistics["authentication_status"] or authentication,
            unknown_operation=self.statistics["unknown_operation"] or unknown,
        )
        if isinstance(error, InputTokenBudgetExceeded):
            self.statistics["context_admission"] = dict(error.details)

    def _send(self, request: urllib.request.Request) -> tuple[int, bytes]:
        started = time.monotonic()
        self.statistics["requests"] += 1
        try:
            response = self._opener(request, timeout=self.timeout_seconds)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            chunks: list[bytes] = []
            length = 0
            while True:
                remaining = self.timeout_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError("provider response exceeded time limit")
                # urllib's timeout bounds idle reads; this also bounds a slowly
                # arriving stream without waiting for a whole 64 KiB block.
                sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                if sock is not None:
                    sock.settimeout(remaining)
                read = getattr(response, "read1", response.read)
                chunk = read(min(65536, self.max_response_bytes + 1 - length))
                if not chunk:
                    break
                chunks.append(chunk)
                length += len(chunk)
                if length > self.max_response_bytes:
                    raise ModelClientError(
                        "provider_output_bytes_exceeded", "provider body too large"
                    )
            return getattr(response, "status", getattr(response, "code", 200)), b"".join(chunks)

    def _normalize(self, status: int, body: bytes, *, tools: Any = ()) -> dict[str, Any]:
        if not 200 <= status < 300:
            raise ModelClientError(
                "provider_http_error", f"provider returned HTTP {status}", status=status
            )
        try:
            if self.messages_transport:
                response = anthropic_to_responses(json.loads(body), tools=tools)
                streamed = False
            else:
                response, streamed = _completed_response(body)
        except (ValueError, KeyError, TypeError) as error:
            raise ModelClientError(
                "provider_response_invalid", "provider response is invalid"
            ) from error
        usage = response["usage"]
        for key in ("input_tokens", "output_tokens"):
            if (
                isinstance(usage.get(key), bool)
                or not isinstance(usage.get(key), int)
                or usage[key] < 0
            ):
                raise ModelClientError("provider_usage_invalid", "provider usage is invalid")
        return {
            "body_base64": base64.b64encode(body).decode(),
            "streamed": streamed,
            "response": response,
            "provider_transport": (
                "bedrock-messages" if self.messages_transport else "bedrock-responses"
            ),
            "response_origin": (
                "host_messages_to_responses_conversion"
                if self.messages_transport
                else "provider_responses"
            ),
        }

    def respond(self, body: bytes) -> tuple[bytes, str]:
        with self._lock:
            if self.statistics["closed"]:
                raise ModelClientError(
                    "provider_episode_closed", "provider episode is closed", status=403
                )
            if self.statistics["halted"]:
                raise ModelClientError("provider_episode_halted", "provider episode is halted")
            try:
                payload = json.loads(body)
                if not isinstance(payload, dict) or "input" not in payload:
                    raise ValueError("native Responses input is required")
                key = canonical_json_sha256(payload)
                if key in self._cached:
                    return self._cached[key]
                # A task cannot choose a different model or enlarge experiment budgets.
                payload["model"] = self.provider["model"]
                payload["reasoning"] = {
                    **payload.get("reasoning", {}),
                    "effort": self.controls.agent.reasoning_effort,
                }
                budget = self.controls.assistant_completion_budget
                remaining = None if budget is None else budget - self.statistics["output_tokens"]
                limits = [
                    limit
                    for limit in (self.controls.agent.max_output_tokens, remaining)
                    if limit is not None
                ]
                if limits:
                    payload["max_output_tokens"] = min(limits)
                else:
                    payload.pop("max_output_tokens", None)
                payload["store"] = False
                provider_payload = (
                    responses_to_anthropic(
                        payload,
                        model=self.provider["model"],
                        reasoning_effort=self.controls.agent.reasoning_effort,
                        max_tokens=payload.get("max_output_tokens"),
                    )
                    if self.messages_transport
                    else payload
                )
                encoded = _json_bytes(provider_payload)
                if self.messages_transport:
                    payload = {
                        **payload,
                        "provider_transport": "bedrock-messages",
                        "provider_request": provider_payload,
                    }
                if self.statistics["requests"] >= self.max_requests or (
                    remaining is not None and remaining <= 0
                ):
                    raise ModelClientError(
                        "provider_completion_budget_exhausted", "provider budget exhausted"
                    )
                if len(encoded) > self.max_request_bytes:
                    raise ModelClientError(
                        "provider_input_bytes_exceeded", "provider body too large"
                    )
                details = _input_estimate(provider_payload, self.token_counter)
                estimate = details["total_tokens"]
                self.statistics["input_token_estimates"].append({"operation_key": key, **details})
                if estimate > self.controls.max_input_tokens:
                    raise InputTokenBudgetExceeded(estimate, self.controls.max_input_tokens)

                def prepare() -> urllib.request.Request:
                    token = bearer_token_source(self.provider["api_key_env"])()
                    return urllib.request.Request(
                        # Codex continues to use Responses only at its local relay.
                        self.provider["api_base"].rstrip("/")
                        + ("/messages" if self.messages_transport else "/responses"),
                        data=encoded,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                            **(
                                {"anthropic-version": "2023-06-01"}
                                if self.messages_transport
                                else {}
                            ),
                        },
                        method="POST",
                    )

                self._active_operation = key
                result = self.journal.dispatch_raw(
                    key, payload, prepare, self._send, self._normalizer(payload)
                )
                self.statistics["input_tokens_estimate"] += estimate
                self._account_response(key, self._output_limit(payload), result)
                self._cached[key] = self._delivery(result, payload.get("stream", False))
                return self._cached[key]
            except BaseException as error:
                self._halt(error)
                raise


class _UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    request_queue_size = 4

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._slots = threading.BoundedSemaphore(4)
        super().__init__(*args, **kwargs)

    def process_request(self, request: Any, address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, address)

    def process_request_thread(self, request: Any, address: Any) -> None:
        try:
            super().process_request_thread(request, address)
        finally:
            self._slots.release()


@contextlib.contextmanager
def open_provider(
    directory: str | Path,
    provider_settings: Mapping[str, Any],
    controls: RuntimeControls | Mapping[str, Any],
    journalroot: str | Path,
    identity: Mapping[str, Any],
    *,
    token_counter: Callable[[str], int],
    timeout_seconds: float,
    max_requests: int = 100,
    max_request_bytes: int = 8 * 1024 * 1024,
    max_response_bytes: int = 16 * 1024 * 1024,
    opener: Any = None,
) -> Iterator[ProviderGateway]:
    if not callable(token_counter) or timeout_seconds <= 0:
        raise ValueError("pinned token counter and positive provider timeout are required")
    for limit in (max_requests, max_request_bytes, max_response_bytes):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("provider limits must be positive integers")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "provider.sock").exists() or (directory / "relay.py").exists():
        raise ValueError("provider relay directory is not fresh")
    settings = (
        controls if isinstance(controls, RuntimeControls) else RuntimeControls.from_dict(controls)
    )
    gateway = ProviderGateway(
        directory,
        provider_settings,
        settings,
        Journal(journalroot, identity=identity),
        token_counter,
        timeout_seconds,
        max_requests,
        max_request_bytes,
        max_response_bytes,
        opener,
    )

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(30)

        def do_POST(self) -> None:
            try:
                if self.path not in {"/responses", "/v1/responses"}:
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if (
                    length <= 0
                    or length > max_request_bytes
                    or self.headers.get("Transfer-Encoding")
                ):
                    self.send_error(413)
                    return
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError("incomplete request body")
                delivered, content_type = gateway.respond(body)
                status = 200
            except Exception as error:
                status = getattr(error, "status", None) or (
                    503 if isinstance(error, CredentialError) else 502
                )
                delivered = _json_bytes(
                    {
                        "error": {
                            "code": getattr(error, "code", "provider_failed"),
                            "message": "host provider request failed",
                        }
                    }
                )
                content_type = "application/json"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(delivered)))
            self.end_headers()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(delivered)

        def log_message(self, *args: Any) -> None:
            pass

    # The host buffers and seals the response before returning HTTP headers.
    # Leave room for sealing after the bounded upstream request has completed.
    gateway.relay_path.write_text(
        f"PROVIDER_TIMEOUT_SECONDS = {timeout_seconds + 30!r}\n" + RELAY_SCRIPT,
        encoding="utf-8",
    )
    os.chmod(directory, 0o755)
    os.chmod(gateway.relay_path, 0o444)
    server = _UnixServer(str(gateway.socket_path), Handler)
    os.chmod(gateway.socket_path, 0o666)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield gateway
    finally:
        gateway.close_public()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        gateway.socket_path.unlink(missing_ok=True)
        gateway.relay_path.unlink(missing_ok=True)
