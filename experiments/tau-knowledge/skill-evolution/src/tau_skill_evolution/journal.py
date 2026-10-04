"""Durable dispatch records that never automatically repeat an unknown request."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from tau_skill_evolution.core._canonical import canonical_json_sha256, sha256_text

from .artifacts import PROTOCOL, atomic_json


class UnknownOperation(RuntimeError):
    """A request may have reached an external service but has no sealed response."""


class Journal:
    def __init__(self, root: str | Path, *, identity: Mapping[str, Any] | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        identity_path = self.root / "identity.json"
        expected = {"protocol": PROTOCOL, "identity": dict(identity or {})}
        if identity_path.exists():
            if json.loads(identity_path.read_text(encoding="utf-8")) != expected:
                raise ValueError("checkpoint protocol or configuration identity differs")
        else:
            if any(self.root.iterdir()):
                raise ValueError("checkpoint has no new-protocol identity")
            atomic_json(identity_path, expected)

    def _directory(self, operation_id: str) -> Path:
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("operation_id must be non-empty")
        return self.root / sha256_text(operation_id)

    def dispatch(self, operation_id: str, payload: Any, callback: Callable[[], Any]) -> Any:
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
            if (directory / "response.json").is_file():
                return self.response(operation_id)
            raise UnknownOperation(
                f"operation {operation_id!r} was dispatched without a sealed response"
            )
        directory.mkdir()
        atomic_json(request_path, request)
        # Persist the new operation directory itself before contacting a service.
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            response = callback()
            envelope = {
                "protocol": PROTOCOL,
                "operation_id": operation_id,
                "request_hash": request["request_hash"],
                "response_hash": canonical_json_sha256(response),
                "response": response,
            }
            atomic_json(directory / "response.json", envelope)
        except BaseException as exc:
            # The request record intentionally remains pending. A transport failure
            # does not establish that the remote service did not execute it.
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            from .model import authentication_status

            status = authentication_status(exc)
            if status is not None:
                atomic_json(
                    directory / "failure.json",
                    {
                        "operation_id": operation_id,
                        "code": "authentication_failed",
                        "status": status,
                    },
                )
            raise UnknownOperation(f"operation {operation_id!r} has an unknown result") from exc
        return response

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

    def dispatched(self, operation_id: str) -> bool:
        return (self._directory(operation_id) / "request.json").is_file()

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
