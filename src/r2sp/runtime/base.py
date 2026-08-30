"""Runtime contracts shared by the synthetic and AppWorld gateways."""

from __future__ import annotations

import json
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_])/(?:[^\s/:]+/)+[^\s:]+")
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwords",
        "passcode",
        "token",
        "accesstoken",
        "refreshtoken",
        "apikey",
        "secret",
        "credential",
        "credentials",
        "authorization",
        "cardnumber",
        "cvv",
        "cvvnumber",
        "cvc",
        "cvcnumber",
        "securitycode",
    }
)


class RuntimeStateError(RuntimeError):
    """Raised when the lifecycle contract is violated by the runner."""


@dataclass(frozen=True)
class RuntimeIdentity:
    world_id: str
    context_id: str
    session_id: str


@dataclass(frozen=True)
class RuntimeObservation:
    app: str
    api: str
    args: dict[str, Any]
    ok: bool
    result: Any = None
    error_code: str | None = None
    error_message: str | None = None

    def as_trace(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "app": self.app,
            "api": self.api,
            "args": self.args,
            "ok": self.ok,
        }
        if self.ok:
            item["result"] = self.result
        else:
            item["error_code"] = self.error_code or "runtime_error"
            item["error_message"] = self.error_message or "tool execution failed"
        return item


@dataclass(frozen=True)
class FinishResult:
    status: str
    answer: str
    task_success: bool
    score: float | None = None
    failure: str | None = None


class RuntimeAdapter(ABC):
    """Narrow task runtime exposed through ``execute`` and ``finish`` only."""

    @property
    @abstractmethod
    def identity(self) -> RuntimeIdentity | None:
        raise NotImplementedError

    @abstractmethod
    def start(self) -> RuntimeIdentity:
        raise NotImplementedError

    @abstractmethod
    def execute(self, app: str, api: str, args: Mapping[str, Any]) -> RuntimeObservation:
        raise NotImplementedError

    @abstractmethod
    def finish(self, status: str, answer: str) -> FinishResult:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> RuntimeAdapter:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


def validate_identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field} must match {_IDENTIFIER.pattern}")
    return value


def normalize_args(args: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a tool argument object while rejecting executable/non-JSON values."""

    if not isinstance(args, Mapping):
        raise TypeError("args must be an object")
    for key in args:
        if not isinstance(key, str):
            raise TypeError("argument keys must be strings")
    _validate_json_value(args)
    return json.loads(json.dumps(dict(args), ensure_ascii=False, allow_nan=False))


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers are not allowed")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("object keys must be strings")
            _validate_json_value(child)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _validate_json_value(child)
        return
    raise TypeError("tool arguments must contain JSON-compatible values")


def normalize_exception(exc: BaseException, *, reveal_message: bool = False) -> tuple[str, str]:
    """Map implementation exceptions to stable, non-schema-leaking errors."""

    if isinstance(exc, TimeoutError):
        code, generic = "timeout", "tool execution timed out"
    elif isinstance(exc, PermissionError):
        code, generic = "permission_denied", "tool execution was denied"
    elif isinstance(exc, KeyError):
        code, generic = "not_found", "requested API was not found"
    elif isinstance(exc, (TypeError, ValueError)):
        code, generic = "invalid_request", "tool request was invalid"
    else:
        code, generic = "runtime_error", "tool execution failed"
    if not reveal_message:
        return code, generic
    message = normalize_text(str(exc), max_chars=240)
    return code, (generic + ": " + message) if message else generic


def normalize_text(value: Any, *, max_chars: int = 4096) -> str:
    """Normalize tool text and remove trace/file-system details."""

    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    text = _ANSI_ESCAPE.sub("", text)
    text = _ABSOLUTE_PATH.sub("<path>", text)
    text = " ".join(text.split())
    return text[:max_chars]


def normalize_result(value: Any) -> Any:
    """Return a bounded JSON value suitable for prompts and normalized traces."""

    if isinstance(value, (str, bytes)):
        text = normalize_text(value)
        if not text:
            return ""
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return text
        try:
            _validate_json_value(decoded)
        except (TypeError, ValueError):
            return text
        return decoded
    try:
        _validate_json_value(value)
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False, default=str))
    except (TypeError, ValueError):
        return normalize_text(value)


def redact_sensitive(value: Any) -> Any:
    """Redact simulated credentials before traces cross episode boundaries."""

    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            text_key = str(key)
            normalized_key = re.sub(r"[^a-z0-9]", "", text_key.casefold())
            redacted[text_key] = (
                "<redacted>" if normalized_key in _SENSITIVE_KEYS else redact_sensitive(child)
            )
        return redacted
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(child) for child in value]
    return value


__all__ = [
    "FinishResult",
    "RuntimeAdapter",
    "RuntimeIdentity",
    "RuntimeObservation",
    "RuntimeStateError",
    "normalize_args",
    "normalize_exception",
    "normalize_result",
    "normalize_text",
    "redact_sensitive",
    "validate_identifier",
]
