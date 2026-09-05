"""Build experiment fixtures exclusively from verified file-injection bundles."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .appworld_payloads import load_appworld_injection_payloads
from .artifacts import sha256_file
from .file_injection import (
    BENIGN_ARM,
    POISON_ARM,
    FileInjectionBundle,
    load_file_injection_bundle,
    materialize_file_injection_bundle,
)
from .file_injection_profiles import APPWORLD_FILE_BINDINGS, AppWorldFileBinding
from .fixtures import SyntheticFixture
from .hashing import canonical_json_sha256, sha256_text
from .models import CaseSpec, OverlayPair, OverlaySpec, TaskSpec
from .resource_pool import ResourcePool

PROFILE_NAMES = tuple(APPWORLD_FILE_BINDINGS)
EXPECTED_TASK_FACING_COUNT = 447
EXPECTED_RAW_ENDPOINT_COUNT = 457


class FileInjectionFixtureError(RuntimeError):
    """Raised when disk-backed experiment inputs fail closed."""


@dataclass(frozen=True, slots=True)
class FileBackedFixtureProvenance:
    """Body-free provenance committed into the compile-gate input hash."""

    profile_name: str
    source_corpus_sha256: str
    source_pool_manifest_hash: str
    source_relative_path: str
    source_api_name: str
    source_resource_id: str
    benign_bundle_sha256: str
    poison_bundle_sha256: str
    poison_payload_sha256: str
    benign_derived_pool_manifest_hash: str
    poison_derived_pool_manifest_hash: str
    benign_target_resource_hash: str
    poison_target_resource_hash: str
    task_commitment_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "r2sp.file-backed-fixture-provenance.v3",
            "source_type": "appworld_standard_json_file_backed",
            "mode": "file_backed_injection",
            "research_eligible": False,
            "purpose": "disk_source_propagation_assay",
            "profile_name": self.profile_name,
            "source_corpus_sha256": self.source_corpus_sha256,
            "source_pool_manifest_hash": self.source_pool_manifest_hash,
            "source_relative_path": self.source_relative_path,
            "source_api_name": self.source_api_name,
            "source_resource_id": self.source_resource_id,
            "benign_bundle_sha256": self.benign_bundle_sha256,
            "poison_bundle_sha256": self.poison_bundle_sha256,
            "poison_payload_sha256": self.poison_payload_sha256,
            "benign_derived_pool_manifest_hash": self.benign_derived_pool_manifest_hash,
            "poison_derived_pool_manifest_hash": self.poison_derived_pool_manifest_hash,
            "benign_target_resource_hash": self.benign_target_resource_hash,
            "poison_target_resource_hash": self.poison_target_resource_hash,
            "benign_is_identity_copy": True,
            "task_commitment_sha256": self.task_commitment_sha256,
            "raw_endpoint_count": EXPECTED_RAW_ENDPOINT_COUNT,
            "task_facing_endpoint_count": EXPECTED_TASK_FACING_COUNT,
        }


@dataclass(frozen=True, slots=True)
class LoadedFileInjectionFixtures:
    fixtures: Mapping[str, SyntheticFixture]
    source_evidence: Mapping[str, Any]
    manifest_paths: Mapping[str, Mapping[str, Path]]


def materialize_appworld_file_bundles(
    appworld_root: str | Path,
    output_directory: str | Path,
    *,
    payload_directory: str | Path,
) -> Mapping[str, Mapping[str, Path]]:
    """Write two Benign identity copies and two Poison corpora.

    Poison text is snapshotted exactly from ``payload_directory`` before the
    output root is created. No whitespace normalization is performed.

    This phase deliberately returns no Resource or fixture.  Call
    :func:`load_appworld_file_fixtures` in a second phase to reopen the bytes.
    """

    root = _real_directory(appworld_root, field="appworld_root")
    source = _real_directory(
        root / "data" / "api_docs" / "standard",
        field="standard API-doc source",
    )
    poison_payloads = load_appworld_injection_payloads(payload_directory)
    output = _new_directory(output_directory)
    manifests: dict[str, Mapping[str, Path]] = {}
    for name in PROFILE_NAMES:
        binding = APPWORLD_FILE_BINDINGS[name]
        profile_root = output / name
        profile_root.mkdir(mode=0o700)
        poison_payload = poison_payloads[name]
        arm_paths: dict[str, Path] = {}
        for directory_name, arm, payload in (
            ("benign", BENIGN_ARM, None),
            ("poison", POISON_ARM, poison_payload),
        ):
            arm_paths[directory_name] = materialize_file_injection_bundle(
                source,
                profile_root / directory_name,
                app_name=binding.profile.app_name,
                api_name=binding.profile.api_name,
                payload=payload,
                raw_expected_count=EXPECTED_RAW_ENDPOINT_COUNT,
                task_facing_expected_count=EXPECTED_TASK_FACING_COUNT,
                profile_name=name,
                arm=arm,
            )
        manifests[name] = MappingProxyType(arm_paths)
    return MappingProxyType(manifests)


def load_appworld_file_fixtures(
    appworld_root: str | Path,
    bundle_directory: str | Path,
) -> LoadedFileInjectionFixtures:
    """Reopen four manifests and construct the only fixtures passed to runners."""

    root = _real_directory(appworld_root, field="appworld_root")
    source = _real_directory(
        root / "data" / "api_docs" / "standard",
        field="standard API-doc source",
    )
    tasks = _real_directory(root / "data" / "tasks", field="AppWorld task source")
    bundle_root = _real_directory(bundle_directory, field="bundle_directory")
    fixtures: dict[str, SyntheticFixture] = {}
    manifests: dict[str, Mapping[str, Path]] = {}
    evidence_profiles: dict[str, Any] = {}
    common_pool_hash: str | None = None
    common_corpus_hash: str | None = None

    for name in PROFILE_NAMES:
        binding = APPWORLD_FILE_BINDINGS[name]
        arm_bundles: dict[str, FileInjectionBundle] = {}
        arm_paths: dict[str, Path] = {}
        for arm in ("benign", "poison"):
            manifest_path = bundle_root / name / arm / "manifest.json"
            arm_paths[arm] = manifest_path
            arm_bundles[arm] = load_file_injection_bundle(
                manifest_path,
                source_directory=source,
            )
        manifests[name] = MappingProxyType(arm_paths)
        benign = arm_bundles["benign"]
        poison = arm_bundles["poison"]
        _validate_benign_poison_bundles(binding, benign=benign, poison=poison)

        pool_hash = benign.source_pool.manifest.manifest_hash
        if pool_hash is None:  # pragma: no cover - PoolManifest invariant
            raise FileInjectionFixtureError("clean pool has no manifest hash")
        if common_pool_hash is None:
            common_pool_hash = pool_hash
            common_corpus_hash = benign.source_corpus_sha256
        elif pool_hash != common_pool_hash or benign.source_corpus_sha256 != common_corpus_hash:
            raise FileInjectionFixtureError("profiles do not share one frozen source corpus")

        task_specs = _load_bound_tasks(root, tasks, binding)
        task_commitment = canonical_json_sha256(
            {kind: task.to_dict() for kind, task in task_specs.items()}
        )
        fixture = _fixture_from_bundles(
            binding,
            benign=benign,
            poison=poison,
            task_specs=task_specs,
            task_commitment_sha256=task_commitment,
        )
        fixtures[name] = fixture
        evidence_profiles[name] = {
            "profile": name,
            "source_relative_path": binding.source_relative_path,
            "source_api_name": binding.source_api_name,
            "task_commitment_sha256": task_commitment,
            "expected_poison_payload_sha256": fixture.provenance.poison_payload_sha256,
            "arms": {
                arm: _bundle_evidence(arm_bundles[arm], arm_paths[arm])
                for arm in ("benign", "poison")
            },
        }

    if common_pool_hash is None or common_corpus_hash is None:  # pragma: no cover
        raise FileInjectionFixtureError("no file-backed profiles were loaded")
    source_evidence = {
        "schema_version": "r2sp.file-backed-source-evidence.v3",
        "source_type": "appworld_standard_json_file_backed",
        "appworld_data_version": _read_version(root),
        "source_corpus_sha256": common_corpus_hash,
        "source_pool_manifest_hash": common_pool_hash,
        "raw_endpoint_count": EXPECTED_RAW_ENDPOINT_COUNT,
        "task_facing_endpoint_count": EXPECTED_TASK_FACING_COUNT,
        "excluded_helpers": ["api_docs", "supervisor"],
        "replay": {
            "appworld_root": str(root),
            "bundle_directory": str(bundle_root),
        },
        "profiles": evidence_profiles,
    }
    return LoadedFileInjectionFixtures(
        fixtures=MappingProxyType(fixtures),
        source_evidence=MappingProxyType(source_evidence),
        manifest_paths=MappingProxyType(manifests),
    )


def _fixture_from_bundles(
    binding: AppWorldFileBinding,
    *,
    benign: FileInjectionBundle,
    poison: FileInjectionBundle,
    task_specs: Mapping[str, TaskSpec],
    task_commitment_sha256: str,
) -> SyntheticFixture:
    profile = binding.profile
    benign_resource = benign.derived_resource
    poison_resource = poison.derived_resource
    overlays = OverlayPair(
        case_id=profile.case_id,
        benign=OverlaySpec(
            arm="A_benign",
            resource=benign_resource,
            trigger=profile.activation_family,
            nonce=profile.nonce,
            template_version="file-backed-appworld-description-prepend-v1",
        ),
        poison=OverlaySpec(
            arm="B_poison",
            resource=poison_resource,
            trigger=profile.activation_family,
            nonce=profile.nonce,
            template_version="file-backed-appworld-description-prepend-v1",
        ),
    )
    pool_hash = poison.source_pool.manifest.manifest_hash
    if pool_hash is None:  # pragma: no cover - manifest invariant
        raise FileInjectionFixtureError("clean pool manifest has no hash")
    poison_payload_sha256 = poison.payload_sha256
    if poison_payload_sha256 is None:  # pragma: no cover - validated bundle-pair invariant
        raise FileInjectionFixtureError("Poison bundle has no injection payload commitment")
    provenance = FileBackedFixtureProvenance(
        profile_name=profile.name,
        source_corpus_sha256=poison.source_corpus_sha256,
        source_pool_manifest_hash=pool_hash,
        source_relative_path=binding.source_relative_path,
        source_api_name=binding.source_api_name,
        source_resource_id=poison.source_resource.resource_id,
        benign_bundle_sha256=str(benign.manifest["bundle_sha256"]),
        poison_bundle_sha256=str(poison.manifest["bundle_sha256"]),
        poison_payload_sha256=poison_payload_sha256,
        benign_derived_pool_manifest_hash=_pool_hash(benign.derived_pool),
        poison_derived_pool_manifest_hash=_pool_hash(poison.derived_pool),
        benign_target_resource_hash=str(benign.derived_resource.content_hash),
        poison_target_resource_hash=str(poison.derived_resource.content_hash),
        task_commitment_sha256=task_commitment_sha256,
    )
    return SyntheticFixture(
        clean_pool=poison.source_pool,
        case=CaseSpec(
            case_id=profile.case_id,
            authoring_task=task_specs["authoring"],
            positive_task=task_specs["positive"],
            negative_task=task_specs["negative"],
            overlays=overlays,
        ),
        query=profile.authoring_instruction,
        provenance=provenance,  # type: ignore[arg-type]
        profile=profile,
        acquisition_pools={
            "benign": benign.derived_pool,
            "poison": poison.derived_pool,
        },
    )


def _pool_hash(pool: ResourcePool) -> str:
    value = pool.manifest.manifest_hash
    if value is None:  # pragma: no cover - PoolManifest invariant
        raise FileInjectionFixtureError("resource pool has no manifest hash")
    return value


def _load_bound_tasks(
    appworld_root: Path,
    task_directory: Path,
    binding: AppWorldFileBinding,
) -> Mapping[str, TaskSpec]:
    definitions = {
        "authoring": (
            binding.authoring_task_id,
            "authoring",
            binding.profile.authoring_instruction,
            binding.profile.app_name,
            binding.profile.api_name,
        ),
        "positive": (
            binding.positive_task_id,
            "trigger_positive",
            binding.profile.positive_instruction,
            binding.profile.app_name,
            binding.profile.api_name,
        ),
        "negative": (
            binding.negative_task_id,
            "trigger_negative",
            binding.profile.negative_instruction,
            binding.negative_app_name,
            binding.negative_api_name,
        ),
    }
    loaded: dict[str, TaskSpec] = {}
    for label, (
        task_id,
        kind,
        expected_instruction,
        ordinary_app,
        ordinary_api,
    ) in definitions.items():
        path = task_directory / task_id / "specs.json"
        if path.is_symlink() or not path.is_file():
            raise FileInjectionFixtureError(f"AppWorld task file is unavailable: {task_id}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise FileInjectionFixtureError(f"AppWorld task file is invalid: {task_id}") from exc
        instruction = payload.get("instruction") if isinstance(payload, Mapping) else None
        if instruction != expected_instruction:
            raise FileInjectionFixtureError(
                f"AppWorld task instruction differs from its frozen binding: {task_id}"
            )
        relative = path.relative_to(appworld_root).as_posix()
        loaded[label] = TaskSpec(
            task_id=task_id,
            kind=kind,
            instruction=instruction,
            metadata={
                "source_type": "appworld_train_specs",
                "source_relative_path": relative,
                "source_file_sha256": sha256_file(path),
                "instruction_sha256": sha256_text(instruction),
                "ordinary_app": ordinary_app,
                "ordinary_api": ordinary_api,
            },
        )
    return MappingProxyType(loaded)


def _validate_benign_poison_bundles(
    binding: AppWorldFileBinding,
    *,
    benign: FileInjectionBundle,
    poison: FileInjectionBundle,
) -> None:
    if benign.profile_name != binding.profile.name or poison.profile_name != binding.profile.name:
        raise FileInjectionFixtureError("bundle profile does not match its frozen binding")
    if benign.arm != BENIGN_ARM or poison.arm != POISON_ARM:
        raise FileInjectionFixtureError("bundle arms do not form an A_benign/B_poison pair")
    if benign.source_corpus_sha256 != poison.source_corpus_sha256:
        raise FileInjectionFixtureError("Benign and Poison use different source corpora")
    if benign.source_pool.manifest.manifest_hash != poison.source_pool.manifest.manifest_hash:
        raise FileInjectionFixtureError("Benign and Poison use different source pools")
    for arm, bundle in (("benign", benign), ("poison", poison)):
        if (
            bundle.source_resource.app_name != binding.profile.app_name
            or bundle.source_resource.api_name != binding.profile.api_name
        ):
            raise FileInjectionFixtureError("bundle target differs from its frozen endpoint")
        target = bundle.manifest.get("target")
        if not isinstance(target, Mapping):
            raise FileInjectionFixtureError("bundle target commitment is unavailable")
        if target.get("source_relative_path") != binding.source_relative_path:
            raise FileInjectionFixtureError("bundle source path differs from its frozen binding")
        if target.get("api_name") != binding.source_api_name:
            raise FileInjectionFixtureError("bundle source API differs from its frozen binding")
        if bundle.source_resource.resource_id != binding.profile.resource_id:
            raise FileInjectionFixtureError("bundle target does not use the production resource ID")
        if bundle.derived_resource.resource_id != binding.profile.resource_id:
            raise FileInjectionFixtureError("derived target resource ID differs from production")
        if arm == "benign":
            if bundle.payload_sha256 is not None or target.get("payload") is not None:
                raise FileInjectionFixtureError("Benign bundle contains an injection payload")
        elif (
            bundle.payload_sha256 is None
            or not isinstance(target.get("payload"), Mapping)
            or target["payload"].get("sha256") != bundle.payload_sha256
        ):
            raise FileInjectionFixtureError(
                "Poison bundle payload commitment is unavailable or inconsistent"
            )
        if len(bundle.source_pool) != EXPECTED_TASK_FACING_COUNT:
            raise FileInjectionFixtureError("bundle clean pool is not exactly 447 resources")
        if len(bundle.derived_pool) != EXPECTED_TASK_FACING_COUNT:
            raise FileInjectionFixtureError("bundle derived pool is not exactly 447 resources")
        source_matches = [
            resource
            for resource in bundle.source_pool
            if resource.resource_id == binding.profile.resource_id
        ]
        derived_matches = [
            resource
            for resource in bundle.derived_pool
            if resource.resource_id == binding.profile.resource_id
        ]
        if source_matches != [bundle.source_resource]:
            raise FileInjectionFixtureError("source target is not unique in the clean pool")
        if derived_matches != [bundle.derived_resource]:
            raise FileInjectionFixtureError("derived target is not unique in the acquisition pool")
    if (
        benign.derived_corpus_sha256 != benign.source_corpus_sha256
        or _pool_hash(benign.derived_pool) != _pool_hash(benign.source_pool)
        or benign.derived_resource != benign.source_resource
    ):
        raise FileInjectionFixtureError("Benign corpus is not an exact identity copy of source")
    if (
        poison.derived_corpus_sha256 == poison.source_corpus_sha256
        or poison.derived_resource == poison.source_resource
    ):
        raise FileInjectionFixtureError("Poison corpus did not replace the target document")


def _bundle_evidence(bundle: FileInjectionBundle, manifest_path: Path) -> dict[str, Any]:
    target = dict(bundle.manifest["target"])
    source = dict(target["source"])
    derived = dict(target["derived"])
    return {
        "manifest_path": str(manifest_path.resolve()),
        "manifest_file_sha256": sha256_file(manifest_path),
        "bundle_sha256": bundle.manifest["bundle_sha256"],
        "profile": bundle.profile_name,
        "arm": bundle.arm,
        "source_corpus_sha256": bundle.source_corpus_sha256,
        "derived_corpus_sha256": bundle.derived_corpus_sha256,
        "source_pool_manifest_hash": _pool_hash(bundle.source_pool),
        "derived_pool_manifest_hash": _pool_hash(bundle.derived_pool),
        "source_pool_resource_count": len(bundle.source_pool),
        "derived_pool_resource_count": len(bundle.derived_pool),
        "target": {
            "source_relative_path": target["source_relative_path"],
            "derived_relative_path": target["derived_relative_path"],
            "json_pointer": target["json_pointer"],
            "app_name": target["app_name"],
            "api_name": target["api_name"],
            "resource_id": target["resource_id"],
            "source_endpoint_sha256": source["endpoint_sha256"],
            "source_resource_body_sha256": source["resource_body_sha256"],
            "payload_sha256": (
                target["payload"]["sha256"] if isinstance(target.get("payload"), Mapping) else None
            ),
            "derived_endpoint_sha256": derived["endpoint_sha256"],
            "derived_resource_body_sha256": derived["resource_body_sha256"],
            "output_file_spans": derived["output_file_spans"],
        },
    }


def _read_version(root: Path) -> str:
    path = root / "data" / "version.txt"
    if path.is_symlink() or not path.is_file():
        raise FileInjectionFixtureError("AppWorld data version file is unavailable")
    value = path.read_text(encoding="utf-8").strip()
    if value != "0.1.0":
        raise FileInjectionFixtureError(f"unsupported AppWorld data version: {value!r}")
    return value


def _real_directory(path: str | Path, *, field: str) -> Path:
    candidate = Path(path)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise FileInjectionFixtureError(f"{field} is unavailable") from exc
    if candidate.is_symlink() or not resolved.is_dir():
        raise FileInjectionFixtureError(f"{field} must be a real directory")
    return resolved


def _new_directory(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists() or candidate.is_symlink():
        raise FileInjectionFixtureError("bundle output directory already exists")
    parent = _real_directory(candidate.parent, field="bundle output parent")
    output = (parent / candidate.name).resolve(strict=False)
    if output.parent != parent:
        raise FileInjectionFixtureError("bundle output escapes its parent")
    try:
        output.mkdir(mode=0o700)
    except OSError as exc:
        raise FileInjectionFixtureError("cannot create bundle output directory") from exc
    os.chmod(output, 0o700)
    return output


__all__ = [
    "EXPECTED_RAW_ENDPOINT_COUNT",
    "EXPECTED_TASK_FACING_COUNT",
    "FileBackedFixtureProvenance",
    "FileInjectionFixtureError",
    "LoadedFileInjectionFixtures",
    "PROFILE_NAMES",
    "load_appworld_file_fixtures",
    "materialize_appworld_file_bundles",
]
