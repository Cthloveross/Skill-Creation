"""Immutable artifact writer for tau preliminary matrix runs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import EXPERIMENT_ROOT


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha256_json(value: Any) -> str:
    compact = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(compact).hexdigest()


class ImmutableRunWriter:
    """Build under a sibling staging directory, then publish with one rename."""

    def __init__(
        self,
        commitment: Any,
        *,
        runs_root: Path = EXPERIMENT_ROOT / "runs",
        now: datetime | None = None,
    ) -> None:
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None:
            raise ValueError("run timestamp must be timezone-aware")
        self.created_at = instant.astimezone(timezone.utc)
        self.commitment_sha256 = sha256_json(commitment)
        stamp = self.created_at.strftime("%Y%m%dT%H%M%S.%fZ")
        self.run_id = f"tau-preliminary-{stamp}-{self.commitment_sha256[:12]}"
        self.runs_root = Path(runs_root).resolve()
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.destination = self.runs_root / self.run_id
        if self.destination.exists():
            raise FileExistsError(f"run already exists: {self.destination}")
        self.staging = Path(tempfile.mkdtemp(prefix=f".{self.run_id}-", dir=self.runs_root))
        self._published = False

    def write_json(self, relative: str, value: Any) -> Path:
        return self.write_bytes(relative, canonical_json_bytes(value))

    def write_text(self, relative: str, value: str) -> Path:
        if not isinstance(value, str):
            raise TypeError("artifact text must be str")
        return self.write_bytes(relative, value.encode("utf-8"))

    def write_bytes(self, relative: str, value: bytes) -> Path:
        if self._published:
            raise RuntimeError("run already published")
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("artifact path must be a safe relative path")
        destination = self.staging / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        return destination

    def publish(self) -> Path:
        if self._published:
            raise RuntimeError("run already published")
        os.rename(self.staging, self.destination)
        self._published = True
        return self.destination

    def abort(self) -> None:
        if not self._published and self.staging.exists():
            shutil.rmtree(self.staging)

    def __enter__(self) -> ImmutableRunWriter:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc, traceback
        if exc_type is not None:
            self.abort()
