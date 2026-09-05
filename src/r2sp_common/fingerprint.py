"""Location-independent fingerprints for shared and dataset-specific code."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar

from ._canonical import canonical_json_sha256, require_sha256, sha256_bytes


@dataclass(frozen=True, slots=True)
class CodeFileFingerprint:
    logical_path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        _validate_logical_path(self.logical_path, name="logical_path")
        require_sha256("sha256", self.sha256)
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_path": self.logical_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CodeFileFingerprint:
        return cls(
            logical_path=value["logical_path"],
            sha256=value["sha256"],
            size_bytes=value["size_bytes"],
        )


@dataclass(frozen=True, slots=True)
class CodeFingerprint:
    SCHEMA_VERSION: ClassVar[str] = "r2sp.code-fingerprint.v1"

    files: tuple[CodeFileFingerprint, ...]
    digest: str | None = None

    def __post_init__(self) -> None:
        files = tuple(sorted(self.files, key=lambda item: item.logical_path))
        if not files:
            raise ValueError("code fingerprint requires at least one file")
        if any(not isinstance(item, CodeFileFingerprint) for item in files):
            raise TypeError("files must contain only CodeFileFingerprint values")
        paths = [item.logical_path for item in files]
        if len(paths) != len(set(paths)):
            raise ValueError("code fingerprint contains duplicate logical paths")
        object.__setattr__(self, "files", files)
        observed = canonical_json_sha256(self._hash_payload())
        if self.digest is None:
            object.__setattr__(self, "digest", observed)
        elif require_sha256("digest", self.digest) != observed:
            raise ValueError("digest does not match the code-file manifest")

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "files": [item.to_dict() for item in self.files],
        }

    def to_dict(self) -> dict[str, Any]:
        value = self._hash_payload()
        value["file_count"] = len(self.files)
        value["digest"] = self.digest
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CodeFingerprint:
        if value.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported code fingerprint schema_version")
        files = tuple(CodeFileFingerprint.from_dict(item) for item in value["files"])
        if value.get("file_count") != len(files):
            raise ValueError("file_count does not match files")
        return cls(files=files, digest=value.get("digest"))


def _validate_logical_path(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{name} must be a safe POSIX relative path")
    return value


def _normalize_suffixes(include_suffixes: Iterable[str]) -> tuple[str, ...]:
    if isinstance(include_suffixes, (str, bytes)):
        raise TypeError("include_suffixes must be an iterable of suffix strings")
    suffixes = tuple(include_suffixes)
    if not suffixes or any(not isinstance(value, str) or not value for value in suffixes):
        raise ValueError("include_suffixes must contain non-empty strings")
    return suffixes


def _files_under(
    root: Path,
    *,
    include_suffixes: tuple[str, ...],
    excluded_dir_names: frozenset[str],
) -> list[Path]:
    files: list[Path] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            if dirname in excluded_dir_names:
                continue
            child = current / dirname
            if child.is_symlink():
                raise ValueError(f"code tree contains a symlink: {child}")
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for filename in sorted(filenames):
            path = current / filename
            if path.is_symlink():
                raise ValueError(f"code tree contains a symlink: {path}")
            if path.suffix in include_suffixes:
                files.append(path)
    return files


def fingerprint_code_roots(
    roots: Mapping[str, str | os.PathLike[str]],
    *,
    include_suffixes: Iterable[str] = (".py",),
    excluded_dir_names: Iterable[str] = ("__pycache__",),
) -> CodeFingerprint:
    """Fingerprint code under stable caller-supplied logical namespaces."""

    if not isinstance(roots, Mapping) or not roots:
        raise ValueError("roots must be a non-empty mapping")
    suffixes = _normalize_suffixes(include_suffixes)
    excluded = frozenset(excluded_dir_names)
    if any(not isinstance(name, str) or not name for name in excluded):
        raise ValueError("excluded_dir_names must contain non-empty strings")

    entries: list[CodeFileFingerprint] = []
    for label, root_value in sorted(roots.items()):
        _validate_logical_path(label, name="root label")
        unresolved = Path(root_value).expanduser()
        if unresolved.is_symlink():
            raise ValueError(f"code root must not be a symlink: {unresolved}")
        root = unresolved.resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"code root must be a directory: {root}")
        for path in _files_under(
            root,
            include_suffixes=suffixes,
            excluded_dir_names=excluded,
        ):
            payload = path.read_bytes()
            relative = path.relative_to(root).as_posix()
            logical_path = f"{label}/{relative}"
            entries.append(
                CodeFileFingerprint(
                    logical_path=logical_path,
                    sha256=sha256_bytes(payload),
                    size_bytes=len(payload),
                )
            )
    return CodeFingerprint(tuple(entries))


def fingerprint_code_tree(
    root: str | os.PathLike[str],
    *,
    label: str = "code",
    include_suffixes: Iterable[str] = (".py",),
    excluded_dir_names: Iterable[str] = ("__pycache__",),
) -> CodeFingerprint:
    return fingerprint_code_roots(
        {label: root},
        include_suffixes=include_suffixes,
        excluded_dir_names=excluded_dir_names,
    )
