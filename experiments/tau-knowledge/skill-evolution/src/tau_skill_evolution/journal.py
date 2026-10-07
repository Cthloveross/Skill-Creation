"""Durable dispatch records that never automatically repeat an unknown request."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from tau_skill_evolution.core._canonical import (
    canonical_json_bytes,
    canonical_json_sha256,
    sha256_text,
)

from .artifacts import PROTOCOL, atomic_json
from .model import CredentialError

IDENTITY_TEMPORARY_PREFIX = ".identity.json."


class UnknownOperation(RuntimeError):
    """A request may have reached an external service but has no sealed response."""


def identity_temporary(name: str) -> bool:
    """In-flight temporaries of a concurrent ``identity.json`` creation."""
    return name.startswith(IDENTITY_TEMPORARY_PREFIX)


def _create_identity_exclusive(path: Path, value: Any) -> None:
    """Create ``identity.json`` once; a concurrent first writer wins untouched.

    ``os.link`` fails with EEXIST instead of replacing, so several processes
    racing on one fresh journal never overwrite each other; every process then
    verifies the file it observes.
    """
    descriptor, temporary = tempfile.mkstemp(prefix=IDENTITY_TEMPORARY_PREFIX, dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        with contextlib.suppress(FileExistsError):
            os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(temporary)


def _short_code(exc: BaseException) -> str | None:
    """Return a short machine code for diagnostics, walking the cause chain."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "code", None)
        if isinstance(code, str) and code and len(code) <= 80 and " " not in code:
            return code
        text = str(current)
        # Code-like messages (no spaces, e.g. "bank_worker_operation_failed:..." or
        # "skillsbench_public_artifact_not_regular") carry no task or provider text.
        if text and len(text) <= 120 and re.fullmatch(r"[A-Za-z0-9_.:\-]+", text):
            return text
        current = current.__cause__ or current.__context__
    return None


class Journal:
    def __init__(self, root: str | Path, *, identity: Mapping[str, Any] | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        identity_path = self.root / "identity.json"
        expected = {"protocol": PROTOCOL, "identity": dict(identity or {})}
        if not identity_path.exists():
            # Several processes may create the same identity concurrently: ignore
            # their temporaries and an identity.json that appeared meanwhile.
            stray = [
                path
                for path in self.root.iterdir()
                if path != identity_path and not identity_temporary(path.name)
            ]
            if stray:
                raise ValueError("checkpoint has no new-protocol identity")
            _create_identity_exclusive(identity_path, expected)
        if json.loads(identity_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("checkpoint protocol or configuration identity differs")

    def _directory(self, operation_id: str) -> Path:
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("operation_id must be non-empty")
        return self.root / sha256_text(operation_id)

    def _request(self, operation_id: str, payload: Any) -> tuple[Path, dict[str, Any]]:
        directory = self._directory(operation_id)
        request = {
            "protocol": PROTOCOL,
            "operation_id": operation_id,
            "request_hash": canonical_json_sha256(payload),
            "payload": payload,
        }
        request_path = directory / "request.json"
        if directory.exists():
            if (
                not request_path.is_file()
                or json.loads(request_path.read_text(encoding="utf-8")) != request
            ):
                raise ValueError("journal operation payload differs or is corrupt")
        else:
            directory.mkdir()
            atomic_json(request_path, request)
            self._state(operation_id, "NOT_SENT")
        return directory, request

    def _state(self, operation_id: str, status: str) -> None:
        atomic_json(self._directory(operation_id) / "state.json", {"status": status})

    def status(self, operation_id: str) -> str:
        directory = self._directory(operation_id)
        if (directory / "response.json").is_file():
            return "COMPLETED"
        path = directory / "state.json"
        if path.is_file():
            return json.loads(path.read_text())["status"]
        return "UNKNOWN" if (directory / "request.json").is_file() else "NOT_SENT"

    def _failure(self, operation_id: str, exc: BaseException, status: str) -> None:
        from .model import InputTokenBudgetExceeded, authentication_status

        authentication = authentication_status(exc)
        value = {
            "operation_id": operation_id,
            "code": "authentication_failed" if authentication else status.lower(),
            "exception": type(exc).__name__,
            "error_code": _short_code(exc),
        }
        if authentication is not None:
            value["status"] = authentication
        if isinstance(exc, InputTokenBudgetExceeded):
            value["context_admission"] = dict(exc.details)
        atomic_json(self._directory(operation_id) / "failure.json", value)
        self._state(operation_id, status)

    def _seal(self, operation_id: str, request: Mapping[str, Any], response: Any) -> Any:
        atomic_json(
            self._directory(operation_id) / "response.json",
            {
                "protocol": PROTOCOL,
                "operation_id": operation_id,
                "request_hash": request["request_hash"],
                "response_hash": canonical_json_sha256(response),
                "response": response,
            },
        )
        self._state(operation_id, "COMPLETED")
        return response

    def dispatch(
        self,
        operation_id: str,
        payload: Any,
        callback: Callable[[], Any],
        *,
        external: bool = True,
    ) -> Any:
        directory, request = self._request(operation_id, payload)
        if self.completed(operation_id):
            return self.response(operation_id)
        if self.status(operation_id) != "NOT_SENT":
            raise UnknownOperation(f"operation {operation_id!r} has an unknown result")
        if external:
            self._state(operation_id, "UNKNOWN")
        try:
            response = callback()
            return self._seal(operation_id, request, response)
        except CredentialError:
            # The client resolves its bearer token before building any request, so
            # nothing reached a service: withdraw the record this call created and
            # let the invocation abort; a later invocation sends it for the first time.
            shutil.rmtree(directory)
            raise
        except BaseException as exc:
            # The request record intentionally remains pending. A transport failure
            # does not establish that the remote service did not execute it.
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            self._failure(operation_id, exc, "UNKNOWN" if external else "NOT_SENT")
            if not external:
                raise
            raise UnknownOperation(f"operation {operation_id!r} has an unknown result") from exc

    def dispatch_raw(
        self,
        operation_id: str,
        payload: Any,
        prepare: Callable[[], Any],
        send: Callable[[Any], tuple[int, bytes]],
        normalize: Callable[[int, bytes], Any],
    ) -> Any:
        """Seal provider bytes before parsing; never resend an uncertain POST."""
        directory, request = self._request(operation_id, payload)
        if self.completed(operation_id):
            return self.response(operation_id)
        metadata = directory / "raw-response.json"
        if metadata.is_file():
            raw = json.loads(metadata.read_text())
            body = base64.b64decode(raw["body_base64"], validate=True)
            if (
                raw.get("request_hash") != request["request_hash"]
                or raw.get("sha256") != hashlib.sha256(body).hexdigest()
                or raw.get("length") != len(body)
                or raw.get("response_hash")
                != canonical_json_sha256(
                    {"http_status": raw["http_status"], "body_base64": raw["body_base64"]}
                )
            ):
                raise ValueError("provider response integrity failure")
            status = raw["http_status"]
        else:
            if self.status(operation_id) != "NOT_SENT":
                raise UnknownOperation(f"operation {operation_id!r} has an unknown result")
            try:
                prepared = prepare()
            except BaseException as exc:
                self._failure(operation_id, exc, "NOT_SENT")
                raise
            self._state(operation_id, "UNKNOWN")
            try:
                status, body = send(prepared)
                encoded = base64.b64encode(body).decode("ascii")
                atomic_json(
                    metadata,
                    {
                        "request_hash": request["request_hash"],
                        "http_status": status,
                        "sha256": hashlib.sha256(body).hexdigest(),
                        "length": len(body),
                        "body_base64": encoded,
                        "response_hash": canonical_json_sha256(
                            {"http_status": status, "body_base64": encoded}
                        ),
                    },
                )
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                self._failure(operation_id, exc, "UNKNOWN")
                raise UnknownOperation(f"operation {operation_id!r} has an unknown result") from exc
        try:
            return self._seal(operation_id, request, normalize(status, body))
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            self._failure(operation_id, exc, "RECEIVED_INVALID")
            raise

    def response(self, operation_id: str) -> Any:
        directory = self._directory(operation_id)
        try:
            request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
            envelope = json.loads((directory / "response.json").read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise UnknownOperation(f"operation {operation_id!r} has no sealed response") from exc
        if (
            request.get("protocol") != PROTOCOL
            or request.get("operation_id") != operation_id
            or request.get("request_hash") != canonical_json_sha256(request.get("payload"))
            or envelope.get("protocol") != PROTOCOL
            or envelope.get("operation_id") != operation_id
            or envelope.get("request_hash") != request.get("request_hash")
            or envelope.get("response_hash") != canonical_json_sha256(envelope.get("response"))
        ):
            raise ValueError("journal response integrity failure")
        return envelope["response"]

    def completed(self, operation_id: str) -> bool:
        return (self._directory(operation_id) / "response.json").is_file()

    def received(self, operation_id: str) -> bool:
        """Raw provider bytes exist; parsing may resume without dispatching again."""
        return (self._directory(operation_id) / "raw-response.json").is_file()

    def dispatched(self, operation_id: str) -> bool:
        return self.status(operation_id) != "NOT_SENT"

    def authentication_failure(self) -> int | None:
        for path in self.root.glob("*/failure.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("code") == "authentication_failed" and value.get("status") in (401, 403):
                return value["status"]
        return None

    def record_result(self, operation_id: str, result: Any) -> None:
        directory = self._directory(operation_id)
        self.response(operation_id)
        path = directory / "result.json"
        expected = {
            "protocol": PROTOCOL,
            "result": result,
            "result_hash": canonical_json_sha256(result),
        }
        if path.exists() and json.loads(path.read_text(encoding="utf-8")) != expected:
            raise ValueError("refusing to replace a different derived result")
        atomic_json(path, expected)

    def result(self, operation_id: str) -> Any | None:
        path = self._directory(operation_id) / "result.json"
        if not path.exists():
            return None
        self.response(operation_id)
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if envelope.get("protocol") != PROTOCOL or envelope.get(
            "result_hash"
        ) != canonical_json_sha256(envelope.get("result")):
            raise ValueError("journal result integrity failure")
        return envelope["result"]
