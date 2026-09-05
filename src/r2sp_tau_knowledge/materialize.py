"""Immutable, file-backed benign and poison corpus materialization."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .constants import DOCUMENTS_ROOT, MATERIALIZED_ROOT, PAYLOAD_FILES, TARGET_DOCUMENT_ID
from .data import build_file_manifest, canonical_manifest_sha256, sha256_bytes, sha256_file

Arm = Literal["benign", "poison"]


class MaterializationError(RuntimeError):
    """A corpus could not be materialized without violating immutability."""


@dataclass(frozen=True)
class Materialization:
    profile: str
    arm: Arm
    payload_sha256: str
    corpus_sha256: str
    output_root: Path
    manifest_path: Path
    target_source_sha256: str
    target_output_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "profile": self.profile,
            "arm": self.arm,
            "payload_sha256": self.payload_sha256,
            "corpus_sha256": self.corpus_sha256,
            "output_root": str(self.output_root),
            "target_document_id": TARGET_DOCUMENT_ID,
            "target_source_sha256": self.target_source_sha256,
            "target_output_sha256": self.target_output_sha256,
        }


def read_payload_bytes(profile: str, payload_files: dict[str, Path] = PAYLOAD_FILES) -> bytes:
    try:
        path = payload_files[profile]
    except KeyError as exc:
        raise ValueError(f"unknown payload profile: {profile}") from exc
    payload = path.read_bytes()
    if not payload:
        raise MaterializationError(f"payload is empty: {path}")
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MaterializationError(f"payload must be UTF-8: {path}") from exc
    return payload


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _load_object(raw: bytes, path: Path) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MaterializationError(f"invalid source JSON: {path}") from exc
    if not isinstance(value, dict):
        raise MaterializationError(f"source JSON is not an object: {path}")
    return value


class CorpusMaterializer:
    def __init__(
        self,
        *,
        source_documents: Path = DOCUMENTS_ROOT,
        output_root: Path = MATERIALIZED_ROOT,
        payload_files: dict[str, Path] = PAYLOAD_FILES,
    ) -> None:
        self.source_documents = Path(source_documents).resolve()
        self.output_root = Path(output_root).resolve()
        self.payload_files = {key: Path(value).resolve() for key, value in payload_files.items()}

    def materialize(self, profile: str, arm: Arm) -> Materialization:
        if arm not in {"benign", "poison"}:
            raise ValueError("arm must be benign or poison")
        payload = read_payload_bytes(profile, self.payload_files)
        payload_hash = sha256_bytes(payload)
        destination = self.output_root / profile / payload_hash / arm
        if destination.exists():
            return self._verify_existing(destination, profile, arm, payload_hash, payload)

        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{arm}-", dir=destination.parent))
        try:
            documents_out = staging / "documents"
            documents_out.mkdir()
            target_name = TARGET_DOCUMENT_ID + ".json"
            for source in sorted(self.source_documents.glob("*.json"), key=lambda item: item.name):
                target = documents_out / source.name
                raw = source.read_bytes()
                if arm == "poison" and source.name == target_name:
                    original = _load_object(raw, source)
                    if set(original) != {"id", "title", "content"}:
                        raise MaterializationError("target document schema mismatch")
                    modified = dict(original)
                    modified["content"] = payload.decode("utf-8") + "\n\n" + original["content"]
                    raw = _canonical_json(modified)
                    decoded = _load_object(raw, target)
                    differing = {key for key in original if original[key] != decoded.get(key)}
                    if differing != {"content"} or decoded["content"] != modified["content"]:
                        raise MaterializationError("poison target differs outside content")
                target.write_bytes(raw)

            files = build_file_manifest(documents_out)
            corpus_hash = canonical_manifest_sha256(files)
            target_source = self.source_documents / target_name
            target_output = documents_out / target_name
            manifest = {
                "schema_version": 1,
                "profile": profile,
                "arm": arm,
                "payload_sha256": payload_hash,
                "payload_size_bytes": len(payload),
                "target_document_id": TARGET_DOCUMENT_ID,
                "target_field": "content",
                "target_source_sha256": sha256_file(target_source),
                "target_output_sha256": sha256_file(target_output),
                "document_count": len(files),
                "corpus_sha256": corpus_hash,
                "files": files,
            }
            (staging / "manifest.json").write_bytes(_canonical_json(manifest))
            try:
                os.rename(staging, destination)
            except FileExistsError:
                shutil.rmtree(staging)
            return self._verify_existing(destination, profile, arm, payload_hash, payload)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    def _verify_existing(
        self,
        destination: Path,
        profile: str,
        arm: Arm,
        payload_hash: str,
        payload: bytes,
    ) -> Materialization:
        manifest_path = destination / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MaterializationError(f"invalid existing materialization: {destination}") from exc
        expected_identity = (profile, arm, payload_hash, TARGET_DOCUMENT_ID, "content")
        actual_identity = (
            manifest.get("profile"),
            manifest.get("arm"),
            manifest.get("payload_sha256"),
            manifest.get("target_document_id"),
            manifest.get("target_field"),
        )
        if actual_identity != expected_identity:
            raise MaterializationError("existing materialization identity mismatch")
        files = build_file_manifest(destination / "documents")
        corpus_hash = canonical_manifest_sha256(files)
        if corpus_hash != manifest.get("corpus_sha256") or files != manifest.get("files"):
            raise MaterializationError("existing materialization content mismatch")
        if manifest.get("payload_size_bytes") != len(payload):
            raise MaterializationError("existing materialization payload size mismatch")
        if manifest.get("document_count") != len(files):
            raise MaterializationError("existing materialization manifest count mismatch")
        if len(files) != len(tuple(self.source_documents.glob("*.json"))):
            raise MaterializationError("existing materialization document count mismatch")
        target_name = TARGET_DOCUMENT_ID + ".json"
        target_source = self.source_documents / target_name
        target_output = destination / "documents" / target_name
        if manifest.get("target_source_sha256") != sha256_file(target_source):
            raise MaterializationError("existing materialization source target hash mismatch")
        if manifest.get("target_output_sha256") != sha256_file(target_output):
            raise MaterializationError("existing materialization output target hash mismatch")
        if arm == "benign":
            for entry in files:
                source = self.source_documents / entry["path"]
                if source.read_bytes() != (destination / "documents" / entry["path"]).read_bytes():
                    raise MaterializationError(f"benign byte mismatch: {entry['path']}")
        else:
            self._verify_poison(destination / "documents", payload)
        return Materialization(
            profile=profile,
            arm=arm,
            payload_sha256=payload_hash,
            corpus_sha256=corpus_hash,
            output_root=destination,
            manifest_path=manifest_path,
            target_source_sha256=str(manifest["target_source_sha256"]),
            target_output_sha256=str(manifest["target_output_sha256"]),
        )

    def _verify_poison(self, documents_out: Path, payload: bytes) -> None:
        target_name = TARGET_DOCUMENT_ID + ".json"
        for source in sorted(self.source_documents.glob("*.json"), key=lambda item: item.name):
            output = documents_out / source.name
            if source.name != target_name:
                if source.read_bytes() != output.read_bytes():
                    raise MaterializationError(f"non-target byte mismatch: {source.name}")
                continue
            original = _load_object(source.read_bytes(), source)
            modified = _load_object(output.read_bytes(), output)
            if set(original) != set(modified):
                raise MaterializationError("target key set changed")
            differing = {key for key in original if original[key] != modified[key]}
            if differing != {"content"}:
                raise MaterializationError("target differs outside content")
            expected_content = payload.decode("utf-8") + "\n\n" + original["content"]
            if modified["content"] != expected_content:
                raise MaterializationError("target content does not contain the exact payload")
