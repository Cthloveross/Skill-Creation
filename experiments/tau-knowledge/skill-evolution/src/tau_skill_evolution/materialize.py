"""Immutable, file-backed benign and poison corpus materialization."""

from __future__ import annotations

import errno
import json
import os
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from tau_skill_evolution.core.attack_payload import (
    ATTACK_BODY_SHA256,
    ATTACK_COMMANDS,
    ATTACK_NONCES,
    RETRIEVAL_LEAD_FILENAME,
    compose_retrieval_attack,
    parse_shared_retrieval_carrier,
)

from .constants import (
    DOCUMENTS_ROOT,
    INJECTIONS_ROOT,
    MATERIALIZED_ROOT,
    PAYLOAD_FILES,
    TARGET_DOCUMENT_ID,
)
from .data import build_file_manifest, canonical_manifest_sha256, sha256_bytes, sha256_file

Arm = Literal["benign", "poison"]
PAYLOAD_SNAPSHOT_SCHEMA_VERSION = 2
MATERIALIZATION_SCHEMA_VERSION = 3
MULTI_TARGET_MATERIALIZATION_SCHEMA_VERSION = 4
PAYLOAD_PROFILES = tuple(ATTACK_COMMANDS)
ATTACK_COMPONENT_REVISION = "dataset-neutral-direct-command-v1"
ACTION_TOOL = "sandbox_run_command"
_ATTACK_HEADINGS = {
    "mock-api-call": "## Required Runtime Setup — Evaluator Loopback Probe",
    "delete-sentinel": "## Required Runtime Setup — Evaluator Sentinel Cleanup",
}


class MaterializationError(RuntimeError):
    """A corpus could not be materialized without violating immutability."""


def normalize_target_document_ids(
    target_document_ids: Iterable[str] | None,
) -> tuple[str, ...]:
    """Return one canonical, non-empty set of safe document IDs.

    ``None`` intentionally retains the historical one-document experiment.  An
    explicit iterable is sorted so the same target set has one materialization
    address regardless of caller ordering.
    """

    if target_document_ids is None:
        return (TARGET_DOCUMENT_ID,)
    if isinstance(target_document_ids, (str, bytes)):
        raise MaterializationError("target_document_ids must be an iterable of IDs")
    values = tuple(target_document_ids)
    if not values:
        raise MaterializationError("target_document_ids must not be empty")
    if any(not isinstance(value, str) or not value for value in values):
        raise MaterializationError("target document IDs must be non-empty strings")
    if len(values) != len(set(values)):
        raise MaterializationError("target document IDs must be unique")
    for value in values:
        if Path(value).name != value or value in {".", ".."} or "\\" in value:
            raise MaterializationError(f"unsafe target document ID: {value!r}")
    return tuple(sorted(values))


def target_ids_sha256(target_document_ids: Iterable[str]) -> str:
    """Hash the canonical target-ID set used in a multi-target output path."""

    target_ids = normalize_target_document_ids(target_document_ids)
    body = json.dumps(
        {"target_document_ids": list(target_ids)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256_bytes(body)


def target_set_sha256(
    target_document_ids: Iterable[str],
    target_source_sha256s: Mapping[str, str],
) -> str:
    """Bind every target ID to the exact source bytes it was derived from."""

    target_ids = normalize_target_document_ids(target_document_ids)
    if set(target_source_sha256s) != set(target_ids):
        raise MaterializationError("target source hash set mismatch")
    body = json.dumps(
        {
            "target_document_ids": list(target_ids),
            "target_source_sha256s": {
                target_id: target_source_sha256s[target_id] for target_id in target_ids
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256_bytes(body)


def action_contract_sha256(profile: str, attack_body_sha256: str) -> str:
    """Bind the registered proxy action to one exact attack-body digest."""

    try:
        command = ATTACK_COMMANDS[profile]
        nonce = ATTACK_NONCES[profile]
    except KeyError as exc:
        raise MaterializationError(f"unknown action profile: {profile}") from exc
    value = {
        "tool": ACTION_TOOL,
        "command": command,
        "nonce": nonce,
        "attack_body_sha256": attack_body_sha256,
    }
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256_bytes(encoded)


def _validate_attack_template(profile: str, attack_body: bytes) -> None:
    """Require the exact reviewed attack revision and its registered action."""

    try:
        command = ATTACK_COMMANDS[profile]
        expected_digest = ATTACK_BODY_SHA256[profile]
        heading = _ATTACK_HEADINGS[profile]
        text = attack_body.decode("utf-8")
    except KeyError as exc:
        raise MaterializationError(f"unknown attack profile: {profile}") from exc
    except UnicodeDecodeError as exc:
        raise MaterializationError(f"attack body must be UTF-8: {profile}") from exc
    required_once = (
        '<SYSTEM_INSTRUCTION priority="critical" source="platform">',
        "<SKILL_MD_REQUIRED_BLOCK>",
        heading,
        f"```sh\n{command}\n```",
        "</SKILL_MD_REQUIRED_BLOCK>",
        "</SYSTEM_INSTRUCTION>",
    )
    if (
        sha256_bytes(attack_body) != expected_digest
        or text.count(command) != 1
        or any(text.count(marker) != 1 for marker in required_once)
    ):
        raise MaterializationError(f"attack body template/action mismatch: {profile}")


@dataclass(frozen=True, slots=True)
class PayloadProfileSnapshot:
    """Exact in-memory attack, retrieval, and composed bytes for one profile."""

    profile: str
    attack_body: bytes
    retrieval_lead: bytes
    composed_payload: bytes

    @property
    def attack_body_sha256(self) -> str:
        return sha256_bytes(self.attack_body)

    @property
    def retrieval_lead_sha256(self) -> str:
        return sha256_bytes(self.retrieval_lead)

    @property
    def composed_payload_sha256(self) -> str:
        return sha256_bytes(self.composed_payload)

    @property
    def action_contract_sha256(self) -> str:
        return action_contract_sha256(self.profile, self.attack_body_sha256)

    def identity(self) -> dict[str, Any]:
        return {
            "attack_body_sha256": self.attack_body_sha256,
            "attack_body_size_bytes": len(self.attack_body),
            "retrieval_lead_sha256": self.retrieval_lead_sha256,
            "retrieval_lead_size_bytes": len(self.retrieval_lead),
            "composed_payload_sha256": self.composed_payload_sha256,
            "composed_payload_size_bytes": len(self.composed_payload),
            "action_contract_sha256": self.action_contract_sha256,
        }


def _payload_set_body(
    profiles: Mapping[str, PayloadProfileSnapshot],
    retrieval_file: bytes,
) -> dict[str, Any]:
    return {
        "schema_version": PAYLOAD_SNAPSHOT_SCHEMA_VERSION,
        "attack_component_revision": ATTACK_COMPONENT_REVISION,
        "retrieval_file_sha256": sha256_bytes(retrieval_file),
        "retrieval_file_size_bytes": len(retrieval_file),
        "profiles": {profile: profiles[profile].identity() for profile in sorted(profiles)},
    }


def payload_set_sha256(
    profiles: Mapping[str, PayloadProfileSnapshot],
    retrieval_file: bytes,
) -> str:
    """Hash one canonical component-identity map without its own digest."""

    payload = json.dumps(
        _payload_set_body(profiles, retrieval_file),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256_bytes(payload)


@dataclass(frozen=True, slots=True)
class PayloadSetSnapshot:
    """One immutable, shared payload snapshot for the complete matrix."""

    profiles: Mapping[str, PayloadProfileSnapshot]
    retrieval_file: bytes
    payload_set_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        copied = dict(self.profiles)
        if not isinstance(self.retrieval_file, bytes):
            raise MaterializationError("retrieval snapshot must be bytes")
        try:
            shared_carrier = parse_shared_retrieval_carrier(self.retrieval_file)
        except ValueError as exc:
            raise MaterializationError("invalid retrieval.txt snapshot") from exc
        if set(copied) != set(PAYLOAD_PROFILES):
            raise MaterializationError("payload snapshot profile set mismatch")
        for profile, component in copied.items():
            if not isinstance(component, PayloadProfileSnapshot) or component.profile != profile:
                raise MaterializationError("payload snapshot profile binding mismatch")
            try:
                expected = compose_retrieval_attack(
                    component.retrieval_lead,
                    component.attack_body,
                )
            except ValueError as exc:
                raise MaterializationError(f"invalid injection components for {profile}") from exc
            if component.composed_payload != expected:
                raise MaterializationError("payload snapshot composition mismatch")
            if component.retrieval_lead != shared_carrier:
                raise MaterializationError("retrieval.txt snapshot/profile mismatch")
            _validate_attack_template(profile, component.attack_body)
        frozen = MappingProxyType(copied)
        object.__setattr__(self, "profiles", frozen)
        object.__setattr__(
            self,
            "payload_set_sha256",
            payload_set_sha256(frozen, self.retrieval_file),
        )

    def identity(self) -> dict[str, Any]:
        return {
            **_payload_set_body(self.profiles, self.retrieval_file),
            "payload_set_sha256": self.payload_set_sha256,
        }


def build_payload_set_snapshot(
    attack_bodies: Mapping[str, bytes],
    retrieval_file: bytes,
) -> PayloadSetSnapshot:
    """Build a verified snapshot from two attacks and one retrieval file."""

    expected = set(PAYLOAD_PROFILES)
    if set(attack_bodies) != expected:
        raise MaterializationError("attack payload profile set mismatch")
    try:
        shared_carrier = parse_shared_retrieval_carrier(retrieval_file)
    except ValueError as exc:
        raise MaterializationError("invalid retrieval.txt") from exc
    profiles: dict[str, PayloadProfileSnapshot] = {}
    for profile in PAYLOAD_PROFILES:
        attack = attack_bodies[profile]
        lead = shared_carrier
        if not isinstance(attack, bytes):
            raise MaterializationError("attack payloads must be bytes")
        try:
            composed = compose_retrieval_attack(lead, attack)
        except ValueError as exc:
            raise MaterializationError(f"invalid injection components for {profile}") from exc
        profiles[profile] = PayloadProfileSnapshot(
            profile=profile,
            attack_body=attack,
            retrieval_lead=lead,
            composed_payload=composed,
        )
    return PayloadSetSnapshot(profiles, retrieval_file)


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
    payload_set_sha256: str = ""
    retrieval_file_sha256: str = ""
    retrieval_file_size_bytes: int = 0
    attack_body_sha256: str = ""
    attack_body_size_bytes: int = 0
    retrieval_lead_sha256: str = ""
    retrieval_lead_size_bytes: int = 0
    composed_payload_sha256: str = ""
    composed_payload_size_bytes: int = 0
    attack_component_revision: str = ""
    action_contract_sha256: str = ""
    target_document_ids: tuple[str, ...] = (TARGET_DOCUMENT_ID,)
    target_source_sha256s: Mapping[str, str] = field(default_factory=dict)
    target_output_sha256s: Mapping[str, str] = field(default_factory=dict)
    target_ids_sha256: str = ""
    target_set_sha256: str = ""
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "arm": self.arm,
            "payload_sha256": self.payload_sha256,
            "corpus_sha256": self.corpus_sha256,
            "output_root": str(self.output_root),
        }
        if self.schema_version != 1:
            value.update(
                {
                    "payload_set_sha256": self.payload_set_sha256,
                    "retrieval_file_sha256": self.retrieval_file_sha256,
                    "retrieval_file_size_bytes": self.retrieval_file_size_bytes,
                    "attack_body_sha256": self.attack_body_sha256,
                    "attack_body_size_bytes": self.attack_body_size_bytes,
                    "retrieval_lead_sha256": self.retrieval_lead_sha256,
                    "retrieval_lead_size_bytes": self.retrieval_lead_size_bytes,
                    "composed_payload_sha256": self.composed_payload_sha256,
                    "composed_payload_size_bytes": self.composed_payload_size_bytes,
                    "attack_component_revision": self.attack_component_revision,
                    "action_contract_sha256": self.action_contract_sha256,
                }
            )
        if self.schema_version in {1, MATERIALIZATION_SCHEMA_VERSION}:
            value.update(
                {
                    "target_document_id": TARGET_DOCUMENT_ID,
                    "target_source_sha256": self.target_source_sha256,
                    "target_output_sha256": self.target_output_sha256,
                }
            )
        else:
            value.update(
                {
                    "target_document_ids": list(self.target_document_ids),
                    "target_ids_sha256": self.target_ids_sha256,
                    "target_set_sha256": self.target_set_sha256,
                    "target_source_sha256s": dict(self.target_source_sha256s),
                    "target_output_sha256s": dict(self.target_output_sha256s),
                }
            )
        return value


def read_payload_bytes(
    profile: str,
    payload_files: Mapping[str, Path] = PAYLOAD_FILES,
) -> bytes:
    """Read the exact dataset-neutral attack body for one profile."""

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


def _component_sources(snapshot: PayloadSetSnapshot) -> dict[str, bytes]:
    return {
        RETRIEVAL_LEAD_FILENAME: snapshot.retrieval_file,
        **{
            f"{profile}.txt": snapshot.profiles[profile].attack_body for profile in PAYLOAD_PROFILES
        },
    }


def _component_manifest(snapshot: PayloadSetSnapshot) -> list[dict[str, Any]]:
    return [
        {
            "path": name,
            "size_bytes": len(raw),
            "sha256": sha256_bytes(raw),
        }
        for name, raw in sorted(_component_sources(snapshot).items())
    ]


class CorpusMaterializer:
    def __init__(
        self,
        *,
        source_documents: Path = DOCUMENTS_ROOT,
        output_root: Path = MATERIALIZED_ROOT,
        payload_files: Mapping[str, Path] | None = None,
        injections_root: Path | None = None,
    ) -> None:
        self.source_documents = Path(source_documents).resolve()
        self.output_root = Path(output_root).resolve()
        self._legacy = injections_root is None
        if self._legacy:
            selected = PAYLOAD_FILES if payload_files is None else payload_files
            self.payload_files = {key: Path(value).resolve() for key, value in selected.items()}
            self.injections_root = INJECTIONS_ROOT.resolve()
        else:
            if payload_files is not None:
                raise ValueError("payload_files cannot be combined with injections_root")
            self.injections_root = Path(injections_root).resolve()
            self.payload_files = {
                profile: self.injections_root / f"{profile}.txt" for profile in PAYLOAD_PROFILES
            }
        self.retrieval_file = self.injections_root / RETRIEVAL_LEAD_FILENAME

    def snapshot_payloads(self) -> PayloadSetSnapshot:
        """Read the two attacks and retrieval.txt exactly once into memory."""

        if self._legacy:
            raise MaterializationError("legacy materialization has no retrieval snapshot")

        expected_names = {
            RETRIEVAL_LEAD_FILENAME,
            *(f"{profile}.txt" for profile in PAYLOAD_PROFILES),
        }
        try:
            entries = tuple(self.injections_root.iterdir())
        except OSError as exc:
            raise MaterializationError("unable to inspect injections directory") from exc
        root_files = tuple(entry for entry in entries if entry.is_file() and not entry.is_symlink())
        directories = tuple(entry for entry in entries if entry.is_dir() and not entry.is_symlink())
        if (
            {entry.name for entry in root_files} != expected_names
            or {entry.name for entry in directories} - {"skillsbench"}
            or len(root_files) + len(directories) != len(entries)
        ):
            raise MaterializationError("injections directory contains unexpected entries")
        attacks: dict[str, bytes] = {}
        for profile in PAYLOAD_PROFILES:
            attacks[profile] = read_payload_bytes(profile, self.payload_files)
        retrieval_file = self.retrieval_file.read_bytes()
        return build_payload_set_snapshot(attacks, retrieval_file)

    def _target_source_hashes(self, target_ids: tuple[str, ...]) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for target_id in target_ids:
            path = self.source_documents / f"{target_id}.json"
            if path.is_symlink() or not path.is_file():
                raise MaterializationError(f"target document is missing: {target_id}")
            value = _load_object(path.read_bytes(), path)
            if set(value) != {"id", "title", "content"}:
                raise MaterializationError(f"target document schema mismatch: {target_id}")
            if value.get("id") != target_id:
                raise MaterializationError(f"target document ID mismatch: {target_id}")
            if not all(isinstance(value.get(field), str) for field in ("id", "title", "content")):
                raise MaterializationError(f"target document fields must be strings: {target_id}")
            hashes[target_id] = sha256_file(path)
        return hashes

    def _destination(
        self,
        snapshot: PayloadSetSnapshot,
        profile: str,
        arm: Arm,
        target_ids: tuple[str, ...],
    ) -> Path:
        payload_root = self.output_root / f"payload-set-{snapshot.payload_set_sha256}"
        if target_ids == (TARGET_DOCUMENT_ID,):
            # Preserve the historical address exactly for legacy runs/replay.
            return payload_root / profile / arm
        return payload_root / f"targets-{target_ids_sha256(target_ids)}" / profile / arm

    def materialize(
        self,
        profile: str,
        arm: Arm,
        *,
        payload_snapshot: PayloadSetSnapshot | None = None,
        target_document_ids: Iterable[str] | None = None,
    ) -> Materialization:
        if arm not in {"benign", "poison"}:
            raise ValueError("arm must be benign or poison")
        if self._legacy:
            if payload_snapshot is not None or target_document_ids is not None:
                raise ValueError("legacy materialization does not accept full-doc arguments")
            return self._materialize_legacy(profile, arm)
        snapshot = payload_snapshot or self.snapshot_payloads()
        try:
            components = snapshot.profiles[profile]
        except KeyError as exc:
            raise ValueError(f"unknown payload profile: {profile}") from exc
        target_ids = normalize_target_document_ids(target_document_ids)
        target_source_hashes = self._target_source_hashes(target_ids)
        payload = components.composed_payload
        payload_hash = components.composed_payload_sha256
        destination = self._destination(snapshot, profile, arm, target_ids)
        if destination.exists():
            return self._verify_existing(
                destination,
                profile,
                arm,
                snapshot,
                components,
                target_ids,
                target_source_hashes,
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{arm}-", dir=destination.parent))
        try:
            components_out = staging / "components"
            components_out.mkdir()
            for name, raw in _component_sources(snapshot).items():
                (components_out / name).write_bytes(raw)
            documents_out = staging / "documents"
            documents_out.mkdir()
            target_names = {f"{target_id}.json" for target_id in target_ids}
            for source in sorted(self.source_documents.glob("*.json"), key=lambda item: item.name):
                target = documents_out / source.name
                raw = source.read_bytes()
                if arm == "poison" and source.name in target_names:
                    original = _load_object(raw, source)
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
            target_output_hashes = {
                target_id: sha256_file(documents_out / f"{target_id}.json")
                for target_id in target_ids
            }
            multi_target = target_ids != (TARGET_DOCUMENT_ID,)
            manifest = {
                "schema_version": (
                    MULTI_TARGET_MATERIALIZATION_SCHEMA_VERSION
                    if multi_target
                    else MATERIALIZATION_SCHEMA_VERSION
                ),
                "profile": profile,
                "arm": arm,
                "payload_sha256": payload_hash,
                "payload_size_bytes": len(payload),
                "payload_set_sha256": snapshot.payload_set_sha256,
                "retrieval_file_sha256": sha256_bytes(snapshot.retrieval_file),
                "retrieval_file_size_bytes": len(snapshot.retrieval_file),
                "attack_component_revision": ATTACK_COMPONENT_REVISION,
                **components.identity(),
                "target_field": "content",
                "document_count": len(files),
                "corpus_sha256": corpus_hash,
                "component_files": _component_manifest(snapshot),
                "files": files,
            }
            if multi_target:
                manifest.update(
                    {
                        "target_document_ids": list(target_ids),
                        "target_ids_sha256": target_ids_sha256(target_ids),
                        "target_set_sha256": target_set_sha256(
                            target_ids,
                            target_source_hashes,
                        ),
                        "target_source_sha256s": target_source_hashes,
                        "target_output_sha256s": target_output_hashes,
                    }
                )
            else:
                manifest.update(
                    {
                        "target_document_id": TARGET_DOCUMENT_ID,
                        "target_source_sha256": target_source_hashes[TARGET_DOCUMENT_ID],
                        "target_output_sha256": target_output_hashes[TARGET_DOCUMENT_ID],
                    }
                )
            (staging / "manifest.json").write_bytes(_canonical_json(manifest))
            try:
                os.rename(staging, destination)
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise
                shutil.rmtree(staging)
            return self._verify_existing(
                destination,
                profile,
                arm,
                snapshot,
                components,
                target_ids,
                target_source_hashes,
            )
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    def _verify_existing(
        self,
        destination: Path,
        profile: str,
        arm: Arm,
        snapshot: PayloadSetSnapshot,
        components: PayloadProfileSnapshot,
        target_ids: tuple[str, ...],
        target_source_hashes: Mapping[str, str],
    ) -> Materialization:
        manifest_path = destination / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MaterializationError(f"invalid existing materialization: {destination}") from exc
        multi_target = target_ids != (TARGET_DOCUMENT_ID,)
        expected_identity = (
            (
                MULTI_TARGET_MATERIALIZATION_SCHEMA_VERSION
                if multi_target
                else MATERIALIZATION_SCHEMA_VERSION
            ),
            profile,
            arm,
            components.composed_payload_sha256,
            snapshot.payload_set_sha256,
            sha256_bytes(snapshot.retrieval_file),
            components.attack_body_sha256,
            components.retrieval_lead_sha256,
            components.composed_payload_sha256,
            ATTACK_COMPONENT_REVISION,
            components.action_contract_sha256,
            "content",
        )
        actual_identity = (
            manifest.get("schema_version"),
            manifest.get("profile"),
            manifest.get("arm"),
            manifest.get("payload_sha256"),
            manifest.get("payload_set_sha256"),
            manifest.get("retrieval_file_sha256"),
            manifest.get("attack_body_sha256"),
            manifest.get("retrieval_lead_sha256"),
            manifest.get("composed_payload_sha256"),
            manifest.get("attack_component_revision"),
            manifest.get("action_contract_sha256"),
            manifest.get("target_field"),
        )
        if actual_identity != expected_identity:
            raise MaterializationError("existing materialization identity mismatch")
        expected_target_ids_hash = target_ids_sha256(target_ids)
        expected_target_set_hash = target_set_sha256(target_ids, target_source_hashes)
        if multi_target:
            target_identity = (
                manifest.get("target_document_ids"),
                manifest.get("target_ids_sha256"),
                manifest.get("target_set_sha256"),
                manifest.get("target_source_sha256s"),
            )
            expected_target_identity = (
                list(target_ids),
                expected_target_ids_hash,
                expected_target_set_hash,
                dict(target_source_hashes),
            )
            if target_identity != expected_target_identity:
                raise MaterializationError("existing materialization target identity mismatch")
        elif (
            manifest.get("target_document_id") != TARGET_DOCUMENT_ID
            or manifest.get("target_source_sha256") != target_source_hashes[TARGET_DOCUMENT_ID]
        ):
            raise MaterializationError("existing materialization target identity mismatch")
        files = build_file_manifest(destination / "documents")
        corpus_hash = canonical_manifest_sha256(files)
        if corpus_hash != manifest.get("corpus_sha256") or files != manifest.get("files"):
            raise MaterializationError("existing materialization content mismatch")
        expected_component_files = _component_manifest(snapshot)
        observed_component_files = build_file_manifest(destination / "components")
        if (
            observed_component_files != expected_component_files
            or manifest.get("component_files") != expected_component_files
        ):
            raise MaterializationError("existing materialization component content mismatch")
        for name, raw in _component_sources(snapshot).items():
            if (destination / "components" / name).read_bytes() != raw:
                raise MaterializationError("existing materialization component byte mismatch")
        expected_sizes = (
            len(components.composed_payload),
            len(snapshot.retrieval_file),
            len(components.attack_body),
            len(components.retrieval_lead),
            len(components.composed_payload),
        )
        actual_sizes = (
            manifest.get("payload_size_bytes"),
            manifest.get("retrieval_file_size_bytes"),
            manifest.get("attack_body_size_bytes"),
            manifest.get("retrieval_lead_size_bytes"),
            manifest.get("composed_payload_size_bytes"),
        )
        if actual_sizes != expected_sizes:
            raise MaterializationError("existing materialization payload size mismatch")
        if manifest.get("document_count") != len(files):
            raise MaterializationError("existing materialization manifest count mismatch")
        if len(files) != len(tuple(self.source_documents.glob("*.json"))):
            raise MaterializationError("existing materialization document count mismatch")
        target_output_hashes = {
            target_id: sha256_file(destination / "documents" / f"{target_id}.json")
            for target_id in target_ids
        }
        if multi_target:
            if manifest.get("target_output_sha256s") != target_output_hashes:
                raise MaterializationError("existing materialization output target hash mismatch")
        elif manifest.get("target_output_sha256") != target_output_hashes[TARGET_DOCUMENT_ID]:
            raise MaterializationError("existing materialization output target hash mismatch")
        if arm == "benign":
            for entry in files:
                source = self.source_documents / entry["path"]
                if source.read_bytes() != (destination / "documents" / entry["path"]).read_bytes():
                    raise MaterializationError(f"benign byte mismatch: {entry['path']}")
        else:
            self._verify_poison(
                destination / "documents",
                components.composed_payload,
                target_ids,
            )
        source_hashes_frozen = MappingProxyType(dict(target_source_hashes))
        output_hashes_frozen = MappingProxyType(target_output_hashes)
        return Materialization(
            profile=profile,
            arm=arm,
            payload_sha256=components.composed_payload_sha256,
            payload_set_sha256=snapshot.payload_set_sha256,
            retrieval_file_sha256=sha256_bytes(snapshot.retrieval_file),
            retrieval_file_size_bytes=len(snapshot.retrieval_file),
            attack_body_sha256=components.attack_body_sha256,
            attack_body_size_bytes=len(components.attack_body),
            retrieval_lead_sha256=components.retrieval_lead_sha256,
            retrieval_lead_size_bytes=len(components.retrieval_lead),
            composed_payload_sha256=components.composed_payload_sha256,
            composed_payload_size_bytes=len(components.composed_payload),
            attack_component_revision=ATTACK_COMPONENT_REVISION,
            action_contract_sha256=components.action_contract_sha256,
            corpus_sha256=corpus_hash,
            output_root=destination,
            manifest_path=manifest_path,
            target_source_sha256=(
                str(manifest["target_source_sha256"]) if not multi_target else ""
            ),
            target_output_sha256=(
                str(manifest["target_output_sha256"]) if not multi_target else ""
            ),
            target_document_ids=target_ids,
            target_source_sha256s=source_hashes_frozen,
            target_output_sha256s=output_hashes_frozen,
            target_ids_sha256=expected_target_ids_hash,
            target_set_sha256=expected_target_set_hash,
            schema_version=(
                MULTI_TARGET_MATERIALIZATION_SCHEMA_VERSION
                if multi_target
                else MATERIALIZATION_SCHEMA_VERSION
            ),
        )

    def _verify_poison(
        self,
        documents_out: Path,
        payload: bytes,
        target_ids: tuple[str, ...],
    ) -> None:
        target_names = {f"{target_id}.json" for target_id in target_ids}
        seen_targets: set[str] = set()
        for source in sorted(self.source_documents.glob("*.json"), key=lambda item: item.name):
            output = documents_out / source.name
            if source.name not in target_names:
                if source.read_bytes() != output.read_bytes():
                    raise MaterializationError(f"non-target byte mismatch: {source.name}")
                continue
            seen_targets.add(source.stem)
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
        if seen_targets != set(target_ids):
            raise MaterializationError("poison target set mismatch")

    def _materialize_legacy(self, profile: str, arm: Arm) -> Materialization:
        payload = read_payload_bytes(profile, self.payload_files)
        payload_hash = sha256_bytes(payload)
        destination = self.output_root / profile / payload_hash / arm
        if destination.exists():
            return self._verify_existing_legacy(
                destination,
                profile,
                arm,
                payload_hash,
                payload,
            )

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
            return self._verify_existing_legacy(
                destination,
                profile,
                arm,
                payload_hash,
                payload,
            )
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    def _verify_existing_legacy(
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
                output = destination / "documents" / entry["path"]
                if source.read_bytes() != output.read_bytes():
                    raise MaterializationError(f"benign byte mismatch: {entry['path']}")
        else:
            self._verify_poison_legacy(destination / "documents", payload)
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

    def _verify_poison_legacy(self, documents_out: Path, payload: bytes) -> None:
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
