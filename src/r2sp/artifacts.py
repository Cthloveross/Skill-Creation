"""Collision-safe, resumable artifact storage using only the standard library."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from secrets import compare_digest
from typing import Any


class ArtifactError(RuntimeError):
    """Base class for artifact storage failures."""


class ArtifactPathError(ArtifactError):
    """Raised for an unsafe path outside the artifact root."""


class ArtifactCollisionError(ArtifactError):
    """Raised when a path already contains different bytes."""


class ArtifactIntegrityError(ArtifactError):
    """Raised when content does not match a caller-supplied digest."""


@dataclass(frozen=True)
class ArtifactRecord:
    relative_path: str
    path: Path
    sha256: str
    size_bytes: int
    resumed: bool

    @property
    def created(self) -> bool:
        return not self.resumed

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "resumed": self.resumed,
        }


def sha256_bytes(data: bytes | bytearray | memoryview) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_sha256(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("expected_sha256 must be a string")
    normalized = value.strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized[len("sha256:") :]
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError("expected_sha256 must be a 64-character SHA-256 hex digest")
    return normalized


class ArtifactStore:
    """Write-once artifact tree with deterministic resume semantics.

    A destination is atomically published only after the temporary file has
    been flushed.  Repeating a write with identical bytes resumes.  Reusing a
    path with different bytes fails and never overwrites the first artifact.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        directory_mode: int = 0o700,
        file_mode: int = 0o600,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=False)
        self._directory_mode = directory_mode
        self._file_mode = file_mode
        if not 0 <= directory_mode <= 0o777:
            raise ValueError("directory_mode must be a permission mode")
        if not 0 <= file_mode <= 0o777:
            raise ValueError("file_mode must be a permission mode")

    def write_bytes(
        self,
        relative_path: str | os.PathLike[str],
        data: bytes | bytearray | memoryview,
        *,
        expected_sha256: str | None = None,
    ) -> ArtifactRecord:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("artifact data must be bytes-like")
        payload = bytes(data)
        digest = sha256_bytes(payload)
        if expected_sha256 is not None:
            expected = _normalize_sha256(expected_sha256)
            if not compare_digest(digest, expected):
                raise ArtifactIntegrityError(
                    f"artifact digest mismatch: expected {expected}, observed {digest}"
                )

        destination = self._destination(relative_path)
        destination.parent.mkdir(mode=self._directory_mode, parents=True, exist_ok=True)
        self._assert_parent_inside_root(destination)

        existing = self._resume_or_collision(destination, payload, digest)
        if existing is not None:
            return existing

        descriptor = -1
        temporary_name = ""
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
            )
            os.fchmod(descriptor, self._file_mode)
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:  # pragma: no cover - OS invariant
                    raise ArtifactError("short write while staging artifact")
                view = view[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1

            try:
                # A hard-link publication is atomic and, unlike os.replace,
                # cannot overwrite a concurrent writer's artifact.
                os.link(temporary_name, destination)
            except FileExistsError:
                existing = self._resume_or_collision(destination, payload, digest)
                if existing is None:  # pragma: no cover - race invariant
                    raise ArtifactError("artifact disappeared during publication") from None
                return existing
            except OSError as exc:
                raise ArtifactError(f"cannot publish artifact atomically: {destination}") from exc

            _fsync_directory(destination.parent)
            return self._record(destination, digest, len(payload), resumed=False)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary_name:
                with suppress(FileNotFoundError):
                    os.unlink(temporary_name)

    def write_text(
        self,
        relative_path: str | os.PathLike[str],
        text: str,
        *,
        expected_sha256: str | None = None,
    ) -> ArtifactRecord:
        if not isinstance(text, str):
            raise TypeError("artifact text must be a string")
        return self.write_bytes(
            relative_path,
            text.encode("utf-8"),
            expected_sha256=expected_sha256,
        )

    def write_json(
        self,
        relative_path: str | os.PathLike[str],
        value: Any,
        *,
        expected_sha256: str | None = None,
    ) -> ArtifactRecord:
        try:
            encoded = (
                json.dumps(
                    value,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ArtifactIntegrityError("artifact is not canonical JSON") from exc
        return self.write_bytes(relative_path, encoded, expected_sha256=expected_sha256)

    def _destination(self, relative_path: str | os.PathLike[str]) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute() or not candidate.parts:
            raise ArtifactPathError("artifact path must be non-empty and relative")
        if any(part in ("", ".", "..") for part in candidate.parts):
            raise ArtifactPathError("artifact path cannot contain '.', '..', or blanks")

        destination = (self.root / candidate).resolve(strict=False)
        try:
            destination.relative_to(self.root)
        except ValueError as exc:
            raise ArtifactPathError("artifact path escapes the artifact root") from exc
        if destination == self.root:
            raise ArtifactPathError("artifact path must name a file")
        return destination

    def _assert_parent_inside_root(self, destination: Path) -> None:
        resolved_parent = destination.parent.resolve(strict=True)
        try:
            resolved_parent.relative_to(self.root)
        except ValueError as exc:
            raise ArtifactPathError("artifact parent escapes the artifact root") from exc

    def _resume_or_collision(
        self, destination: Path, payload: bytes, digest: str
    ) -> ArtifactRecord | None:
        try:
            info = destination.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ArtifactCollisionError(
                f"artifact destination is not a regular file: {destination}"
            )
        if info.st_size == len(payload) and _file_equals(destination, payload):
            observed_digest = sha256_file(destination)
            if not compare_digest(observed_digest, digest):  # pragma: no cover
                raise ArtifactIntegrityError(
                    f"artifact changed while verifying resume: {destination}"
                )
            return self._record(destination, observed_digest, info.st_size, resumed=True)
        raise ArtifactCollisionError(
            f"artifact collision at {destination}: existing content differs"
        )

    def _record(
        self, destination: Path, digest: str, size: int, *, resumed: bool
    ) -> ArtifactRecord:
        return ArtifactRecord(
            relative_path=destination.relative_to(self.root).as_posix(),
            path=destination,
            sha256=digest,
            size_bytes=size,
            resumed=resumed,
        )


def _file_equals(path: Path, payload: bytes) -> bool:
    view = memoryview(payload)
    offset = 0
    try:
        with path.open("rb") as handle:
            while offset < len(view):
                chunk = handle.read(min(1024 * 1024, len(view) - offset))
                if not chunk or chunk != view[offset : offset + len(chunk)]:
                    return False
                offset += len(chunk)
            return handle.read(1) == b""
    except OSError as exc:
        raise ArtifactError(f"cannot verify existing artifact: {path}") from exc


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ArtifactError(f"cannot open artifact directory: {path}") from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise ArtifactError(f"cannot sync artifact directory: {path}") from exc
    finally:
        os.close(descriptor)


_ARTIFACT_MANIFEST_PATH = "artifacts-manifest.json"
_ARTIFACT_MANIFEST_EXCLUSIONS = frozenset(
    {".active.lock", _ARTIFACT_MANIFEST_PATH, "complete.json"}
)


def write_artifact_manifest(
    output: str | os.PathLike[str],
    store: ArtifactStore,
) -> ArtifactRecord:
    """Write a deterministic manifest covering every durable artifact in *output*.

    The active lock, the manifest itself, and the completion marker are control
    files and are intentionally excluded. Symlinks fail closed because their
    targets are not immutable members of the artifact tree.
    """

    root = Path(output)
    entries: list[dict[str, Any]] = []
    try:
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ArtifactIntegrityError("artifact tree contains a symlink")
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative in _ARTIFACT_MANIFEST_EXCLUSIONS:
                continue
            entries.append(
                {
                    "path": relative,
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    except ArtifactError:
        raise
    except OSError as exc:
        raise ArtifactError("cannot inspect artifact tree") from exc

    return store.write_json(
        _ARTIFACT_MANIFEST_PATH,
        {
            "schema_version": 1,
            "artifact_count": len(entries),
            "artifacts": entries,
        },
    )


def verify_artifact_manifest(
    output: str | os.PathLike[str],
    manifest_path: str | os.PathLike[str],
) -> None:
    """Fail unless *manifest_path* exactly describes the durable artifact tree."""

    root = Path(output)
    manifest = Path(manifest_path)
    try:
        if not manifest.is_file() or manifest.is_symlink():
            raise ValueError("artifact manifest is not a regular file")
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        entries = payload["artifacts"]
        if not isinstance(entries, list):
            raise ValueError("artifact list must be a list")
        if payload.get("schema_version") != 1 or payload.get("artifact_count") != len(entries):
            raise ValueError("invalid artifact manifest structure")

        expected_paths: set[str] = set()
        for entry in entries:
            if not isinstance(entry, Mapping) or set(entry) != {
                "path",
                "sha256",
                "size_bytes",
            }:
                raise ValueError("invalid artifact manifest entry")
            relative = entry["path"]
            relative_path = Path(relative) if isinstance(relative, str) else Path()
            if (
                not isinstance(relative, str)
                or not relative
                or relative_path.is_absolute()
                or relative_path.as_posix() != relative
                or any(part in {"", ".", ".."} for part in relative_path.parts)
                or relative in _ARTIFACT_MANIFEST_EXCLUSIONS
                or relative in expected_paths
                or not _is_canonical_sha256(entry["sha256"])
                or isinstance(entry["size_bytes"], bool)
                or not isinstance(entry["size_bytes"], int)
                or entry["size_bytes"] < 0
            ):
                raise ValueError("invalid artifact manifest entry values")
            path = root / relative
            expected_paths.add(relative)
            if (
                not path.is_file()
                or path.is_symlink()
                or path.stat().st_size != entry["size_bytes"]
                or sha256_file(path) != entry["sha256"]
            ):
                raise ValueError(f"artifact integrity mismatch: {relative}")

        actual_paths: set[str] = set()
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError("artifact tree contains a symlink")
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative not in _ARTIFACT_MANIFEST_EXCLUSIONS:
                actual_paths.add(relative)
        if actual_paths != expected_paths:
            raise ValueError("artifact manifest file set mismatch")
    except ArtifactError:
        raise
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ArtifactIntegrityError("artifact manifest verification failed") from exc


def _is_canonical_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "ArtifactCollisionError",
    "ArtifactError",
    "ArtifactIntegrityError",
    "ArtifactPathError",
    "ArtifactRecord",
    "ArtifactStore",
    "sha256_bytes",
    "sha256_file",
    "verify_artifact_manifest",
    "write_artifact_manifest",
]
