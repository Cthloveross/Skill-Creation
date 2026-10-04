"""Immutable public bases and safely sealed multi-file Skill packages."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from tau_skill_evolution.core._canonical import (
    canonical_json_bytes,
    canonical_json_sha256,
    freeze_json,
    require_sha256,
    sha256_text,
    thaw_json,
)

PROTOCOL = "tau.skill-evolution.v1"


def normalize_document(document: Any) -> dict[str, str]:
    """Admit only an actual full-text search result and its public identity."""
    if hasattr(document, "to_open_dict"):
        document = document.to_open_dict()
    elif hasattr(document, "to_page_mapping"):
        document = document.to_page_mapping()
    elif hasattr(document, "to_dict") and not isinstance(document, Mapping):
        document = document.to_dict()
    if not isinstance(document, Mapping):
        raise ValueError("document must be a full-text mapping")
    identifier = document.get("document_id", document.get("page_id", document.get("id")))
    content = document.get("content", document.get("body"))
    title = document.get("title")
    if not isinstance(identifier, str) or not identifier or not isinstance(title, str):
        raise ValueError("document requires a public ID and title")
    if not isinstance(content, str):
        raise ValueError("document was not returned in full")
    content.encode("utf-8")
    observed = sha256_text(content)
    supplied = document.get("content_hash", document.get("content_sha256"))
    if supplied is not None and supplied != observed:
        raise ValueError("document content hash mismatch")
    return {"document_id": identifier, "title": title, "content": content, "content_hash": observed}


@dataclass(frozen=True)
class FrozenBase:
    documents: tuple[Mapping[str, Any], ...]
    public_inputs: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...] = ()
    stop_reason: str = "sufficient"
    token_count: int = 0
    base_hash: str = ""

    def __post_init__(self) -> None:
        documents = tuple(normalize_document(item) for item in self.documents)
        if len({item["document_id"] for item in documents}) != len(documents):
            raise ValueError("duplicate frozen document ID")
        if not isinstance(self.public_inputs, Mapping):
            raise ValueError("public_inputs must be an object")
        if (
            isinstance(self.token_count, bool)
            or not isinstance(self.token_count, int)
            or self.token_count < 0
        ):
            raise ValueError("token_count must be a nonnegative integer")
        if not isinstance(self.stop_reason, str) or not self.stop_reason:
            raise ValueError("stop_reason is required")
        object.__setattr__(self, "documents", freeze_json(documents))
        object.__setattr__(self, "public_inputs", freeze_json(self.public_inputs))
        object.__setattr__(self, "evidence", freeze_json(self.evidence))
        digest = canonical_json_sha256(self._payload())
        if self.base_hash and self.base_hash != digest:
            raise ValueError("frozen base hash mismatch")
        object.__setattr__(self, "base_hash", digest)

    def _payload(self) -> dict[str, Any]:
        return {
            "protocol": PROTOCOL,
            "documents": thaw_json(self.documents),
            "public_inputs": thaw_json(self.public_inputs),
            "evidence": thaw_json(self.evidence),
            "stop_reason": self.stop_reason,
            "token_count": self.token_count,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "base_hash": self.base_hash}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> FrozenBase:
        if value.get("protocol") != PROTOCOL:
            raise ValueError("incompatible frozen-base protocol")
        require_sha256("base_hash", value.get("base_hash"))
        return cls(
            documents=tuple(value["documents"]),
            public_inputs=value["public_inputs"],
            evidence=tuple(value["evidence"]),
            stop_reason=value["stop_reason"],
            token_count=value["token_count"],
            base_hash=value["base_hash"],
        )


def validate_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("invalid package path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("package paths must be canonical relative paths")
    if ":" in value or any(ord(char) < 32 for char in value):
        raise ValueError("invalid package path")
    if value == "SKILL.md":
        return value
    if len(path.parts) < 2 or path.parts[0] not in {"scripts", "references"}:
        raise ValueError("package files must be SKILL.md, scripts/*.py or references/*")
    if path.parts[0] == "scripts" and path.suffix != ".py":
        raise ValueError("script files must have a .py extension")
    return value


@dataclass(frozen=True)
class SkillBundle:
    files: Mapping[str, str]
    bundle_hash: str = ""
    parent_hash: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.files, Mapping) or not self.files or "SKILL.md" not in self.files:
            raise ValueError("package requires SKILL.md")
        copied: dict[str, str] = {}
        for path, content in self.files.items():
            validate_relative_path(path)
            if not isinstance(content, str):
                raise ValueError("package content must be UTF-8 text")
            content.encode("utf-8")
            copied[path] = content
        for path in copied:
            if any(
                parent.as_posix() in copied
                for parent in PurePosixPath(path).parents
                if parent.as_posix() != "."
            ):
                raise ValueError("package path is both a file and directory")
        if not copied["SKILL.md"].strip():
            raise ValueError("empty SKILL.md")
        if self.parent_hash is not None:
            require_sha256("parent_hash", self.parent_hash)
        object.__setattr__(self, "files", freeze_json(copied))
        digest = canonical_json_sha256(self.file_manifest())
        if self.bundle_hash and self.bundle_hash != digest:
            raise ValueError("package hash mismatch")
        object.__setattr__(self, "bundle_hash", digest)

    def file_manifest(self) -> list[dict[str, Any]]:
        return [
            {
                "path": path,
                "content_hash": sha256_text(content),
                "bytes": len(content.encode("utf-8")),
            }
            for path, content in sorted(self.files.items())
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": PROTOCOL,
            "files": dict(self.files),
            "manifest": self.file_manifest(),
            "bundle_hash": self.bundle_hash,
            "parent_hash": self.parent_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SkillBundle:
        if value.get("protocol") != PROTOCOL:
            raise ValueError("incompatible package protocol")
        require_sha256("bundle_hash", value.get("bundle_hash"))
        result = cls(
            files=value["files"],
            bundle_hash=value["bundle_hash"],
            parent_hash=value.get("parent_hash"),
        )
        if value.get("manifest") != result.file_manifest():
            raise ValueError("package manifest mismatch")
        return result


def atomic_json(path: Path, value: Any) -> None:
    """Durably replace one JSON file; used before and after external requests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def seal_base(path: str | Path, base: FrozenBase) -> Path:
    path = Path(path)
    if path.exists():
        if load_base(path).base_hash != base.base_hash:
            raise ValueError("refusing to replace a different frozen base")
        return path
    atomic_json(path, base.to_dict())
    return path


def load_base(path: str | Path) -> FrozenBase:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("frozen base must be a regular file")
    return FrozenBase.from_dict(json.loads(path.read_text(encoding="utf-8")))


def verify_base(value: FrozenBase | str | Path) -> FrozenBase:
    return (
        FrozenBase.from_dict(value.to_dict()) if isinstance(value, FrozenBase) else load_base(value)
    )


def seal_bundle(path: str | Path, bundle: SkillBundle) -> Path:
    path = Path(path)
    if path.exists():
        if load_bundle(path).to_dict() != bundle.to_dict():
            raise ValueError("refusing to replace a different sealed package")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{path.name}.", dir=path.parent))
    try:
        for name, content in bundle.files.items():
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as stream:
                stream.write(content.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
        atomic_json(
            temporary / "manifest.json",
            {key: value for key, value in bundle.to_dict().items() if key != "files"},
        )
        # Helpers/references can be nested. Persist their directory entries before
        # publishing the package so its complete hash remains recoverable.
        for nested in sorted(
            (item for item in temporary.rglob("*") if item.is_dir()),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            descriptor = os.open(nested, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return path


def load_bundle(path: str | Path) -> SkillBundle:
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("package must be a directory")
    files: dict[str, str] = {}
    for item in path.rglob("*"):
        mode = item.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError("package contains a symlink or special file")
        relative = item.relative_to(path).as_posix()
        if relative == "manifest.json":
            continue
        validate_relative_path(relative)
        files[relative] = item.read_text(encoding="utf-8")
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    return SkillBundle.from_dict({**manifest, "files": files})


def verify_bundle(value: SkillBundle | str | Path) -> SkillBundle:
    return (
        SkillBundle.from_dict(value.to_dict())
        if isinstance(value, SkillBundle)
        else load_bundle(value)
    )
