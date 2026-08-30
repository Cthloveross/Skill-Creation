"""Deterministic, path-safe content snapshots for research runtime inputs.

The digests produced here bind bytes to an experiment fingerprint.  They do
not establish publisher authenticity and are not remote-service attestations.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import os
import re
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .hashing import canonical_json_sha256, sha256_text

_SNAPSHOT_SCHEMA = "r2sp.content-snapshot.v1"
_APPWORLD_SNAPSHOT_SCHEMA = "r2sp.appworld-runtime-snapshot.v1"
_TASK_ID_PATTERN = re.compile(r"[^_/:\\\s]+_[1-9][0-9]*")
_EXPECTED_TASK_COUNT = 48


class IntegrityError(ValueError):
    """Raised when a content snapshot cannot be computed safely."""


@dataclass(frozen=True)
class ContentDigest:
    """Non-sensitive summary of a deterministic content inventory."""

    sha256: str
    file_count: int
    size_bytes: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "sha256": self.sha256,
            "file_count": self.file_count,
            "size_bytes": self.size_bytes,
        }


def hash_tree(root: str | Path) -> ContentDigest:
    """Hash every stable regular file below *root* in deterministic order.

    Python bytecode is included because an import can execute it. A symbolic
    link, special file, missing directory, or empty tree fails closed. The
    returned object contains no source paths.
    """

    return _hash_tree(Path(root), label="content tree")


def hash_appworld_runtime_snapshot(
    appworld_root: str | Path,
    task_ids: Iterable[str],
) -> ContentDigest:
    """Bind the AppWorld bytes used by the fixed 16-case research pilot.

    The snapshot covers the imported package, its distribution metadata, base
    databases, the 48 selected task trees, the train split, and standard API
    documentation.  Only the aggregate digest and counts are returned; task
    identifiers and filesystem paths are not exposed.
    """

    root = Path(appworld_root)
    normalized_task_ids = _normalize_task_ids(task_ids)
    package_root = _locate_appworld_package_root()
    metadata_root = _locate_appworld_distribution_metadata_root()

    components: list[dict[str, Any]] = []
    total_files = 0
    total_bytes = 0

    def add_component(name: str, digest: ContentDigest) -> None:
        nonlocal total_files, total_bytes
        components.append({"name": name, **digest.to_dict()})
        total_files += digest.file_count
        total_bytes += digest.size_bytes

    add_component(
        "appworld_package",
        _hash_tree(package_root, label="AppWorld package tree"),
    )
    add_component(
        "appworld_distribution_metadata",
        _hash_tree(metadata_root, label="AppWorld distribution metadata"),
    )
    data_root = root / "data"
    add_component(
        "base_databases",
        _hash_tree(data_root / "base_dbs", label="AppWorld base database tree"),
    )
    add_component(
        "standard_api_docs",
        _hash_tree(
            data_root / "api_docs" / "standard",
            label="AppWorld standard API documentation tree",
        ),
    )
    add_component(
        "train_split",
        _hash_single_file(
            data_root / "datasets" / "train.txt",
            logical_name="train.txt",
            label="AppWorld train split",
        ),
    )

    task_components: list[dict[str, Any]] = []
    for task_id in normalized_task_ids:
        task_digest = _hash_tree(
            data_root / "tasks" / task_id,
            label="selected AppWorld task tree",
        )
        task_components.append(
            {
                "task_id_sha256": sha256_text(task_id),
                **task_digest.to_dict(),
            }
        )
        total_files += task_digest.file_count
        total_bytes += task_digest.size_bytes

    aggregate = canonical_json_sha256(
        {
            "schema_version": _APPWORLD_SNAPSHOT_SCHEMA,
            "components": components,
            "selected_tasks": task_components,
        }
    )
    return ContentDigest(aggregate, total_files, total_bytes)


def _normalize_task_ids(task_ids: Iterable[str]) -> tuple[str, ...]:
    if isinstance(task_ids, (str, bytes)):
        raise IntegrityError("selected AppWorld task IDs must be an iterable of strings")
    try:
        values = tuple(task_ids)
    except TypeError as exc:
        raise IntegrityError("selected AppWorld task IDs are not iterable") from exc
    if (
        len(values) != _EXPECTED_TASK_COUNT
        or len(set(values)) != _EXPECTED_TASK_COUNT
        or any(
            not isinstance(value, str) or _TASK_ID_PATTERN.fullmatch(value) is None
            for value in values
        )
    ):
        raise IntegrityError("exactly 48 unique, safely formatted AppWorld task IDs are required")
    return tuple(sorted(values))


def _hash_tree(root: Path, *, label: str) -> ContentDigest:
    try:
        root_status = root.lstat()
    except OSError as exc:
        raise IntegrityError(f"{label} is missing or unreadable") from exc
    if stat.S_ISLNK(root_status.st_mode):
        raise IntegrityError(f"{label} cannot be a symbolic link")
    if not stat.S_ISDIR(root_status.st_mode):
        raise IntegrityError(f"{label} must be a directory")

    records: list[dict[str, str | int]] = []

    def visit(directory: Path, relative_parts: tuple[str, ...]) -> None:
        try:
            with os.scandir(directory) as scanner:
                entries = sorted(scanner, key=lambda entry: entry.name)
        except OSError as exc:
            raise IntegrityError(f"{label} is unreadable") from exc
        for entry in entries:
            try:
                entry_status = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise IntegrityError(f"{label} changed or became unreadable") from exc
            mode = entry_status.st_mode
            if stat.S_ISLNK(mode):
                raise IntegrityError(f"{label} contains a symbolic link")
            next_parts = (*relative_parts, entry.name)
            if stat.S_ISDIR(mode):
                visit(Path(entry.path), next_parts)
                continue
            if not stat.S_ISREG(mode):
                raise IntegrityError(f"{label} contains a special file")
            digest, size = _hash_regular_file(Path(entry.path), label=label)
            records.append(
                {
                    "path": PurePosixPath(*next_parts).as_posix(),
                    "sha256": digest,
                    "size_bytes": size,
                }
            )

    visit(root, ())
    if not records:
        raise IntegrityError(f"{label} contains no hashable files")
    return ContentDigest(
        sha256=canonical_json_sha256({"schema_version": _SNAPSHOT_SCHEMA, "files": records}),
        file_count=len(records),
        size_bytes=sum(int(record["size_bytes"]) for record in records),
    )


def _hash_single_file(path: Path, *, logical_name: str, label: str) -> ContentDigest:
    digest, size = _hash_regular_file(path, label=label)
    return ContentDigest(
        sha256=canonical_json_sha256(
            {
                "schema_version": _SNAPSHOT_SCHEMA,
                "files": [
                    {
                        "path": logical_name,
                        "sha256": digest,
                        "size_bytes": size,
                    }
                ],
            }
        ),
        file_count=1,
        size_bytes=size,
    )


def _hash_regular_file(path: Path, *, label: str) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise IntegrityError(f"{label} contains a missing or unreadable file") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise IntegrityError(f"{label} contains a symbolic link or special file")
        hasher = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            hasher.update(chunk)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise IntegrityError(f"{label} changed or became unreadable") from exc
    finally:
        os.close(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after:
        raise IntegrityError(f"{label} changed while it was being hashed")
    return hasher.hexdigest(), before.st_size


def _locate_appworld_package_root() -> Path:
    try:
        spec = importlib.util.find_spec("appworld")
    except (ImportError, AttributeError, ValueError) as exc:
        raise IntegrityError("the AppWorld package cannot be located") from exc
    locations = tuple(spec.submodule_search_locations or ()) if spec is not None else ()
    if len(locations) != 1:
        raise IntegrityError("the AppWorld package must have exactly one import root")
    return Path(locations[0])


def _locate_appworld_distribution_metadata_root() -> Path:
    try:
        distribution = importlib.metadata.distribution("appworld")
    except importlib.metadata.PackageNotFoundError as exc:
        raise IntegrityError("the AppWorld distribution metadata cannot be located") from exc
    roots: set[Path] = set()
    for item in distribution.files or ():
        parts = Path(str(item)).parts
        for index, part in enumerate(parts):
            if part.endswith((".dist-info", ".egg-info")):
                roots.add(Path(distribution.locate_file(Path(*parts[: index + 1]))))
                break
    if len(roots) != 1:
        raise IntegrityError("the AppWorld distribution must have one metadata directory")
    return roots.pop()


__all__ = [
    "ContentDigest",
    "IntegrityError",
    "hash_appworld_runtime_snapshot",
    "hash_tree",
]
