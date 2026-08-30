"""Deterministic SHA-256 helpers used by frozen experiment artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_bytes(value: bytes) -> str:
    """Return the lowercase SHA-256 hex digest for *value*."""

    if not isinstance(value, bytes):
        raise TypeError("sha256_bytes expects bytes")
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    """Hash UTF-8 text exactly; no implicit whitespace normalization is applied."""

    if not isinstance(value, str):
        raise TypeError("sha256_text expects str")
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Stream a file into SHA-256 without loading protected bundles into memory."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON-compatible data in the repository's canonical form."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    """Hash a JSON-compatible value after canonical serialization."""

    return sha256_bytes(canonical_json_bytes(value))


def is_sha256(value: object) -> bool:
    """Return whether *value* is a canonical lowercase SHA-256 digest."""

    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None
