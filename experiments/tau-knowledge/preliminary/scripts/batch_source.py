"""Verify the deterministic source bundle used by a benign batch job."""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

from build_source_bundle import BUNDLE_PREFIX, MANIFEST_NAME, build


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_bundle(path: Path, expected: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    if path.is_symlink() or not path.is_file() or sha256_file(path) != expected:
        raise ValueError("source bundle is missing, a symlink, or does not match its SHA-256")
    members: dict[str, bytes] = {}
    with tarfile.open(path, "r:") as archive:
        for member in archive.getmembers():
            relative = PurePosixPath(member.name)
            if (
                relative.is_absolute()
                or len(relative.parts) < 2
                or relative.parts[0] != BUNDLE_PREFIX
                or any(part in {"", ".", ".."} for part in relative.parts)
                or str(relative) != member.name
                or not member.isfile()
                or str(PurePosixPath(*relative.parts[1:])) in members
            ):
                raise ValueError("source bundle contains an unsafe or duplicate member")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("source bundle member is unreadable")
            members[str(PurePosixPath(*relative.parts[1:]))] = stream.read()
    raw_manifest = members.pop(MANIFEST_NAME)
    manifest = json.loads(raw_manifest)
    if manifest.get("schema_version") != "r2sp.source-bundle.v1":
        raise ValueError("source manifest schema is invalid")
    records = manifest.get("files")
    if not isinstance(records, list) or manifest.get("file_count") != len(records):
        raise ValueError("source manifest file count is invalid")
    if hashlib.sha256(canonical_bytes(records)).hexdigest() != manifest.get("source_tree_sha256"):
        raise ValueError("source manifest tree SHA-256 is invalid")
    if len({record["path"] for record in records}) != len(records):
        raise ValueError("source manifest contains duplicate paths")
    if set(members) != {record["path"] for record in records}:
        raise ValueError("source archive and manifest inventories differ")
    for record in records:
        data = members[record["path"]]
        if (
            len(data) != record["size_bytes"]
            or hashlib.sha256(data).hexdigest() != record["sha256"]
        ):
            raise ValueError("source file does not match the source manifest")
    return {
        "source_bundle_path": str(path.resolve()),
        "source_bundle_sha256": expected,
        "source_tree_sha256": manifest["source_tree_sha256"],
        "source_manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
    }, members


def verify_checkout(root: Path, members: dict[str, bytes]) -> None:
    for relative, data in members.items():
        path = root / relative
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            raise ValueError(f"executing checkout differs from source bundle: {relative}")
    # New Python modules must not silently enter imports after the snapshot was sealed.
    for directory in (root / "src", root / "experiments/tau-knowledge/preliminary/scripts"):
        for path in directory.rglob("*.py"):
            if str(path.relative_to(root)) not in members:
                raise ValueError("executing checkout has an unbundled Python module")


def source_provenance(root: Path, output_dir: Path) -> dict[str, Any]:
    supplied = os.environ.get("R2SP_TAU_SOURCE_BUNDLE")
    if supplied:
        identity, members = verified_bundle(
            Path(supplied), os.environ.get("R2SP_TAU_SOURCE_BUNDLE_SHA256", "")
        )
        verify_checkout(root, members)
        return identity
    identity = build(root=root, output_dir=output_dir, write=True)
    result, members = verified_bundle(
        Path(str(identity["bundle_path"])), str(identity["bundle_sha256"])
    )
    verify_checkout(root, members)
    return result
