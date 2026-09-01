"""Auditable Benign/Poison corpora for file-backed API documentation.

The transformation and loading phases are intentionally separate.  The
materializer either byte-copies an original ``standard/*.json`` corpus for the
``A_benign`` arm or prepends one payload to one endpoint ``description`` for
the ``B_poison`` arm.  Both arms are full on-disk corpora with manifests.  The
loader reopens both source and derived bytes and recomputes every commitment
before it constructs any ``Resource`` objects used by an experiment.

This module does not generate payload text and does not execute anything found
in a document.  It only performs a deterministic local data transformation.
"""

from __future__ import annotations

import copy
import importlib.resources
import json
import os
import shutil
import stat
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import sha256_file
from .hashing import canonical_json_sha256, is_sha256, sha256_bytes, sha256_text
from .models import Resource
from .resource_pool import ResourcePool, load_standard_api_docs

SCHEMA_VERSION = "r2sp.file-injection-bundle.v3"
IDENTITY_TRANSFORM_ID = "r2sp.identity-copy-corpus.v1"
TRANSFORM_ID = "r2sp.prepend-endpoint-description.v1"
TRANSFORM_IMPLEMENTATION_RESOURCE = "r2sp/file_injection.py"
MANIFEST_NAME = "manifest.json"
DERIVED_DIRECTORY_NAME = "standard"
DESCRIPTION_SEPARATOR = "\n\n"
DEFAULT_EXCLUDED_HELPERS = ("api_docs", "supervisor")
BENIGN_ARM = "A_benign"
POISON_ARM = "B_poison"


class FileInjectionError(RuntimeError):
    """Raised when a source, derived corpus, or manifest fails closed."""


@dataclass(frozen=True, slots=True)
class FileInjectionBundle:
    """A fully reloaded and hash-verified file-backed injection bundle."""

    manifest_path: Path
    source_directory: Path
    derived_directory: Path
    profile_name: str
    arm: str
    json_pointer: str
    payload_sha256: str | None
    source_corpus_sha256: str
    derived_corpus_sha256: str
    source_pool: ResourcePool
    derived_pool: ResourcePool
    source_resource: Resource
    derived_resource: Resource
    manifest: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _EndpointRef:
    relative_path: str
    api_key: str
    json_pointer: str
    app_name: str
    api_name: str
    record: Mapping[str, Any]
    excluded: bool


@dataclass(frozen=True, slots=True)
class _CorpusScan:
    root: Path
    payloads: Mapping[str, Any]
    endpoints: tuple[_EndpointRef, ...]
    files: tuple[Mapping[str, Any], ...]
    corpus_sha256: str
    raw_endpoint_count: int
    task_facing_endpoint_count: int
    excluded_endpoint_count: int


def materialize_file_injection_bundle(
    source_directory: str | Path,
    output_directory: str | Path,
    *,
    app_name: str,
    api_name: str,
    payload: str | None,
    raw_expected_count: int = 457,
    task_facing_expected_count: int = 447,
    expected_count: int | None = None,
    configured_clean_count: int | None = None,
    excluded_helpers: Iterable[str] = DEFAULT_EXCLUDED_HELPERS,
    profile_name: str = "unspecified",
    arm: str = POISON_ARM,
    json_pointer: str | None = None,
) -> Path:
    """Create one immutable copy-on-write corpus and return its manifest path.

    ``raw_expected_count`` is enforced before helper exclusion;
    ``task_facing_expected_count`` is enforced after helper exclusion.
    ``expected_count`` and ``configured_clean_count`` remain compatibility
    aliases for the task-facing and raw counts, respectively.  Unlike the old
    manifest, both aliases are fail-closed and neither describes 457 as clean.
    """

    source = _validated_directory(source_directory, field="source_directory")
    destination = _new_output_path(output_directory)
    app = _required_text(app_name, field="app_name")
    api = _required_text(api_name, field="api_name")
    profile = _required_text(profile_name, field="profile_name")
    arm_name = _canonical_arm(arm)
    injection = _arm_payload(arm_name, payload)
    raw_expected = _resolve_count_alias(
        raw_expected_count,
        configured_clean_count,
        primary_field="raw_expected_count",
        alias_field="configured_clean_count",
    )
    task_expected = _resolve_count_alias(
        task_facing_expected_count,
        expected_count,
        primary_field="task_facing_expected_count",
        alias_field="expected_count",
    )
    helpers = _normalized_helpers(excluded_helpers)

    source_scan = _scan_corpus(source, excluded_helpers=helpers)
    if source_scan.raw_endpoint_count != raw_expected:
        raise FileInjectionError(
            "source raw endpoint count mismatch: "
            f"expected {raw_expected}, observed {source_scan.raw_endpoint_count}"
        )
    if source_scan.task_facing_endpoint_count != task_expected:
        raise FileInjectionError(
            "source task-facing endpoint count mismatch: "
            f"expected {task_expected}, observed {source_scan.task_facing_endpoint_count}"
        )
    target = _locate_target(source_scan, app_name=app, api_name=api)
    if target.excluded:
        raise FileInjectionError("target endpoint is excluded from the task-facing corpus")
    if json_pointer is not None and json_pointer != target.json_pointer:
        raise FileInjectionError(
            f"target JSON pointer mismatch: expected {target.json_pointer!r}, "
            f"observed {json_pointer!r}"
        )

    source_description = target.record.get("description")
    if not isinstance(source_description, str) or not source_description:
        raise FileInjectionError("target endpoint description must be non-empty text")
    if injection is not None and _count_text_occurrences(source_scan.payloads.values(), injection):
        raise FileInjectionError("payload already occurs in the source corpus")

    derived_payloads = copy.deepcopy(dict(source_scan.payloads))
    derived_description = source_description
    if injection is not None:
        derived_record = _record_at_pointer(derived_payloads, target)
        derived_description = injection + DESCRIPTION_SEPARATOR + source_description
        derived_record["description"] = derived_description

    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    derived_directory = destination / DERIVED_DIRECTORY_NAME
    derived_directory.mkdir(mode=0o700)
    try:
        for item in source_scan.files:
            relative = _safe_relative_path(str(item["path"]), field="source file path")
            source_path = source / relative
            derived_path = derived_directory / relative
            if injection is not None and relative == target.relative_path:
                root_payload = derived_payloads[relative]
                encoded = _render_json_like_source(source_path, root_payload)
                _exclusive_write(derived_path, encoded)
            else:
                _copy_regular_file(source_path, derived_path)

        derived_scan = _scan_corpus(derived_directory, excluded_helpers=helpers)
        _validate_corpus_relationship(
            source_scan,
            derived_scan,
            target=target,
            payload=injection,
        )
        derived_target = _locate_target(derived_scan, app_name=app, api_name=api)
        source_pool = load_standard_api_docs(
            source,
            expected_count=task_expected,
            excluded_helpers=helpers,
        )
        derived_pool = load_standard_api_docs(
            derived_directory,
            expected_count=task_expected,
            excluded_helpers=helpers,
        )
        source_resource = _pool_resource(source_pool, app_name=app, api_name=api)
        derived_resource = _pool_resource(derived_pool, app_name=app, api_name=api)
        raw_spans = (
            _derived_file_spans(
                derived_directory / derived_target.relative_path,
                description=derived_description,
                payload=injection,
            )
            if injection is not None
            else None
        )

        manifest_without_hash: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "transform": _transform_commitment(arm_name),
            "profile": {"name": profile, "arm": arm_name},
            "source_corpus": _corpus_manifest(
                source_scan,
                expected_raw_count=raw_expected,
                expected_task_facing_count=task_expected,
                excluded_helpers=helpers,
            ),
            "derived_corpus": _corpus_manifest(
                derived_scan,
                expected_raw_count=raw_expected,
                expected_task_facing_count=task_expected,
                excluded_helpers=helpers,
            ),
            "target": {
                "source_relative_path": target.relative_path,
                "derived_relative_path": (
                    f"{DERIVED_DIRECTORY_NAME}/{derived_target.relative_path}"
                ),
                "json_pointer": target.json_pointer,
                "app_name": app,
                "api_name": api,
                "resource_id": source_resource.resource_id,
                "title": source_resource.title,
                "source": _target_hashes(target.record, source_resource),
                "payload": (
                    {
                        "sha256": sha256_text(injection),
                        "size_bytes": len(injection.encode("utf-8")),
                    }
                    if injection is not None
                    else None
                ),
                "derived": {
                    **_target_hashes(derived_target.record, derived_resource),
                    "decoded_description_insertion": (
                        {
                            "coordinate_system": "decoded_description_utf8",
                            "start_byte": 0,
                            "end_byte": len(injection.encode("utf-8")),
                            "benign_suffix_start_byte": len(
                                (injection + DESCRIPTION_SEPARATOR).encode("utf-8")
                            ),
                        }
                        if injection is not None
                        else None
                    ),
                    "output_file_spans": raw_spans,
                },
            },
        }
        manifest = {
            **manifest_without_hash,
            "bundle_sha256": canonical_json_sha256(manifest_without_hash),
        }
        manifest_path = destination / MANIFEST_NAME
        _exclusive_write(manifest_path, _canonical_manifest_bytes(manifest))
    except BaseException:
        # An incomplete destination is never loadable because it has no valid
        # manifest.  Keep it in place instead of deleting user-visible evidence.
        raise
    return manifest_path


def load_file_injection_bundle(
    manifest_path: str | Path,
    *,
    source_directory: str | Path,
) -> FileInjectionBundle:
    """Reload and verify a materialized bundle from disk.

    No object from the materialization phase is accepted here.  Both source and
    derived JSON files are reopened, parsed, hashed, compared, and finally
    passed through the production resource-pool loader.
    """

    manifest_file = _validated_regular_file(manifest_path, field="manifest_path")
    if manifest_file.name != MANIFEST_NAME:
        raise FileInjectionError(f"manifest file must be named {MANIFEST_NAME!r}")
    bundle_root = _validated_directory(manifest_file.parent, field="bundle_directory")
    source = _validated_directory(source_directory, field="source_directory")
    manifest = _read_json_mapping(manifest_file, field="manifest")
    _validate_manifest_shape(manifest)

    committed_bundle_hash = manifest["bundle_sha256"]
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_sha256"}
    if canonical_json_sha256(unsigned) != committed_bundle_hash:
        raise FileInjectionError("bundle_sha256 does not match manifest contents")

    profile_payload = _mapping(manifest["profile"], field="profile")
    if set(profile_payload) != {"name", "arm"}:
        raise FileInjectionError("manifest profile has an invalid field set")
    profile_name = _required_text(profile_payload.get("name"), field="profile.name")
    arm = _canonical_arm(profile_payload.get("arm"))

    transform = _mapping(manifest["transform"], field="transform")
    expected_transform = _transform_commitment(arm)
    if transform != expected_transform:
        raise FileInjectionError("unsupported or corrupt file-injection transform")

    source_commitment = _mapping(manifest["source_corpus"], field="source_corpus")
    derived_commitment = _mapping(manifest["derived_corpus"], field="derived_corpus")
    helpers = _normalized_helpers(source_commitment.get("excluded_helpers", ()))
    if list(helpers) != derived_commitment.get("excluded_helpers"):
        raise FileInjectionError("source and derived helper exclusions differ")
    expected_raw_count = _positive_int(
        source_commitment.get("expected_raw_endpoint_count"),
        field="source_corpus.expected_raw_endpoint_count",
    )
    expected_task_facing_count = _positive_int(
        source_commitment.get("expected_task_facing_endpoint_count"),
        field="source_corpus.expected_task_facing_endpoint_count",
    )
    if (
        derived_commitment.get("expected_raw_endpoint_count") != expected_raw_count
        or derived_commitment.get("expected_task_facing_endpoint_count")
        != expected_task_facing_count
    ):
        raise FileInjectionError("source and derived expected endpoint counts differ")

    derived_relative = _safe_relative_path(
        DERIVED_DIRECTORY_NAME,
        field="derived directory",
    )
    derived_directory = _validated_directory(
        bundle_root / derived_relative,
        field="derived_directory",
    )
    source_scan = _scan_corpus(source, excluded_helpers=helpers)
    derived_scan = _scan_corpus(derived_directory, excluded_helpers=helpers)
    _verify_corpus_manifest(source_scan, source_commitment, field="source_corpus")
    _verify_corpus_manifest(derived_scan, derived_commitment, field="derived_corpus")

    target_payload = _mapping(manifest["target"], field="target")
    app = _required_text(target_payload.get("app_name"), field="target.app_name")
    api = _required_text(target_payload.get("api_name"), field="target.api_name")
    source_target = _locate_target(source_scan, app_name=app, api_name=api)
    derived_target = _locate_target(derived_scan, app_name=app, api_name=api)
    if source_target.excluded or derived_target.excluded:
        raise FileInjectionError("manifest target is excluded from the task-facing corpus")
    expected_source_path = _safe_relative_path(
        str(target_payload.get("source_relative_path")),
        field="target.source_relative_path",
    )
    expected_derived_path = _safe_relative_path(
        str(target_payload.get("derived_relative_path")),
        field="target.derived_relative_path",
    )
    if expected_source_path != source_target.relative_path:
        raise FileInjectionError("manifest source path does not locate the target endpoint")
    if expected_derived_path != f"{DERIVED_DIRECTORY_NAME}/{derived_target.relative_path}":
        raise FileInjectionError("manifest derived path does not locate the target endpoint")
    if target_payload.get("json_pointer") != source_target.json_pointer:
        raise FileInjectionError("manifest JSON pointer does not locate the target endpoint")
    if derived_target.json_pointer != source_target.json_pointer:
        raise FileInjectionError("source and derived JSON pointers differ")

    source_description = source_target.record.get("description")
    derived_description = derived_target.record.get("description")
    if not isinstance(source_description, str) or not source_description:
        raise FileInjectionError("source target description is invalid")
    if not isinstance(derived_description, str) or not derived_description:
        raise FileInjectionError("derived target description is invalid")
    derived_payload = _mapping(target_payload.get("derived"), field="target.derived")
    insertion_value = derived_payload.get("decoded_description_insertion")
    payload_commitment_value = target_payload.get("payload")
    if arm == BENIGN_ARM:
        if insertion_value is not None or payload_commitment_value is not None:
            raise FileInjectionError("Benign identity copy must not contain an injection payload")
        if derived_payload.get("output_file_spans") is not None:
            raise FileInjectionError("Benign identity copy must not contain payload spans")
        payload_text = None
    else:
        insertion = _mapping(
            insertion_value,
            field="target.derived.decoded_description_insertion",
        )
        payload_text = _payload_from_derived_description(
            source_description,
            derived_description,
            insertion,
        )
        payload_commitment = _mapping(payload_commitment_value, field="target.payload")
        if payload_commitment != {
            "sha256": sha256_text(payload_text),
            "size_bytes": len(payload_text.encode("utf-8")),
        }:
            raise FileInjectionError("payload commitment does not match the derived description")
        if _count_text_occurrences(derived_scan.payloads.values(), payload_text) != 1:
            raise FileInjectionError("payload must occur exactly once in the derived corpus")
        if _count_text_occurrences(source_scan.payloads.values(), payload_text) != 0:
            raise FileInjectionError("payload unexpectedly occurs in the source corpus")

    _validate_corpus_relationship(
        source_scan,
        derived_scan,
        target=source_target,
        payload=payload_text,
    )
    source_pool = load_standard_api_docs(
        source,
        expected_count=expected_task_facing_count,
        excluded_helpers=helpers,
    )
    derived_pool = load_standard_api_docs(
        derived_directory,
        expected_count=expected_task_facing_count,
        excluded_helpers=helpers,
    )
    source_resource = _pool_resource(source_pool, app_name=app, api_name=api)
    derived_resource = _pool_resource(derived_pool, app_name=app, api_name=api)
    if target_payload.get("resource_id") != source_resource.resource_id:
        raise FileInjectionError("target resource_id commitment does not match the source")
    if derived_resource.resource_id != source_resource.resource_id:
        raise FileInjectionError("source and derived resource IDs differ")
    if target_payload.get("title") != source_resource.title:
        raise FileInjectionError("target title commitment does not match the source")
    if target_payload.get("source") != _target_hashes(source_target.record, source_resource):
        raise FileInjectionError("source endpoint/body commitments do not recompute")

    expected_derived_hashes = _target_hashes(derived_target.record, derived_resource)
    if any(derived_payload.get(key) != value for key, value in expected_derived_hashes.items()):
        raise FileInjectionError("derived endpoint/body commitments do not recompute")
    expected_spans = (
        _derived_file_spans(
            derived_directory / derived_target.relative_path,
            description=derived_description,
            payload=payload_text,
        )
        if payload_text is not None
        else None
    )
    if derived_payload.get("output_file_spans") != expected_spans:
        raise FileInjectionError("derived output-file spans do not recompute")

    return FileInjectionBundle(
        manifest_path=manifest_file,
        source_directory=source,
        derived_directory=derived_directory,
        profile_name=profile_name,
        arm=arm,
        json_pointer=source_target.json_pointer,
        payload_sha256=sha256_text(payload_text) if payload_text is not None else None,
        source_corpus_sha256=source_scan.corpus_sha256,
        derived_corpus_sha256=derived_scan.corpus_sha256,
        source_pool=source_pool,
        derived_pool=derived_pool,
        source_resource=source_resource,
        derived_resource=derived_resource,
        manifest=copy.deepcopy(dict(manifest)),
    )


def _transform_commitment(arm: str) -> dict[str, Any]:
    canonical_arm = _canonical_arm(arm)
    is_benign = canonical_arm == BENIGN_ARM
    return {
        "id": IDENTITY_TRANSFORM_ID if is_benign else TRANSFORM_ID,
        "strategy": "identity_copy" if is_benign else "prepend",
        "target_field": None if is_benign else "description",
        "separator_sha256": None if is_benign else sha256_text(DESCRIPTION_SEPARATOR),
        "separator_size_bytes": (0 if is_benign else len(DESCRIPTION_SEPARATOR.encode("utf-8"))),
        "implementation": {
            "kind": "python_package_resource",
            "resource": TRANSFORM_IMPLEMENTATION_RESOURCE,
            "sha256": _transform_implementation_sha256(),
        },
    }


def _transform_implementation_sha256() -> str:
    """Hash this module through package resources in source or installed layouts."""

    package_name = __package__
    if not package_name:
        raise FileInjectionError("file-injection package identity is unavailable")
    try:
        source = importlib.resources.files(package_name).joinpath("file_injection.py")
        payload = source.read_bytes()
    except (AttributeError, FileNotFoundError, OSError, TypeError) as exc:
        raise FileInjectionError("file-injection implementation source is unavailable") from exc
    if not payload:
        raise FileInjectionError("file-injection implementation source is empty")
    return sha256_bytes(payload)


def _scan_corpus(root: Path, *, excluded_helpers: tuple[str, ...]) -> _CorpusScan:
    _assert_flat_regular_json_directory(root)
    payloads: dict[str, Any] = {}
    endpoints: list[_EndpointRef] = []
    files: list[dict[str, Any]] = []
    excluded_keys = {_identifier_key(value) for value in excluded_helpers}
    for path in sorted(root.glob("*.json"), key=lambda item: item.name):
        relative = path.name
        payload = _read_json_value(path, field=f"corpus file {relative}")
        payloads[relative] = payload
        files.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
        api_mapping, pointer_prefix = _api_mapping(payload, path=path)
        for raw_api_key, raw_record in api_mapping.items():
            api_key = str(raw_api_key)
            if not isinstance(raw_record, Mapping):
                raise FileInjectionError(f"{path}: endpoint {api_key!r} must be an object")
            record = dict(raw_record)
            raw_app = record.get("app_name", path.stem)
            raw_api = record.get("api_name", api_key)
            if not isinstance(raw_app, str) or not raw_app.strip():
                raise FileInjectionError(f"{path}: endpoint {api_key!r} has invalid app_name")
            if not isinstance(raw_api, str) or not raw_api.strip():
                raise FileInjectionError(f"{path}: endpoint {api_key!r} has invalid api_name")
            pointer = f"{pointer_prefix}/{_json_pointer_escape(api_key)}"
            excluded = (
                _identifier_key(raw_app) in excluded_keys
                or _identifier_key(raw_api) in excluded_keys
            )
            endpoints.append(
                _EndpointRef(
                    relative_path=relative,
                    api_key=api_key,
                    json_pointer=pointer,
                    app_name=raw_app,
                    api_name=raw_api,
                    record=record,
                    excluded=excluded,
                )
            )
    if not files:
        raise FileInjectionError(f"no JSON API documentation files found in {root}")
    task_facing_count = sum(not endpoint.excluded for endpoint in endpoints)
    return _CorpusScan(
        root=root,
        payloads=payloads,
        endpoints=tuple(endpoints),
        files=tuple(files),
        corpus_sha256=canonical_json_sha256({"files": files}),
        raw_endpoint_count=len(endpoints),
        task_facing_endpoint_count=task_facing_count,
        excluded_endpoint_count=len(endpoints) - task_facing_count,
    )


def _locate_target(scan: _CorpusScan, *, app_name: str, api_name: str) -> _EndpointRef:
    matches = [
        endpoint
        for endpoint in scan.endpoints
        if endpoint.app_name == app_name and endpoint.api_name == api_name
    ]
    if len(matches) != 1:
        raise FileInjectionError(
            f"target endpoint {app_name}.{api_name} must occur exactly once; got {len(matches)}"
        )
    return matches[0]


def _record_at_pointer(payloads: Mapping[str, Any], target: _EndpointRef) -> dict[str, Any]:
    payload = payloads.get(target.relative_path)
    if payload is None:
        raise FileInjectionError("target source file is absent from copied corpus")
    mapping, _ = _api_mapping(payload, path=Path(target.relative_path))
    record = mapping.get(target.api_key)
    if not isinstance(record, dict):
        raise FileInjectionError("target endpoint is not mutable in the copied corpus")
    return record


def _validate_corpus_relationship(
    source: _CorpusScan,
    derived: _CorpusScan,
    *,
    target: _EndpointRef,
    payload: str | None,
) -> None:
    if [item["path"] for item in source.files] != [item["path"] for item in derived.files]:
        raise FileInjectionError("source and derived corpus file sets differ")
    if (
        source.raw_endpoint_count != derived.raw_endpoint_count
        or source.task_facing_endpoint_count != derived.task_facing_endpoint_count
        or source.excluded_endpoint_count != derived.excluded_endpoint_count
    ):
        raise FileInjectionError("source and derived endpoint counts differ")
    source_payloads = copy.deepcopy(dict(source.payloads))
    derived_payloads = copy.deepcopy(dict(derived.payloads))
    if payload is None:
        if source_payloads != derived_payloads:
            raise FileInjectionError("Benign derived corpus is not an identity copy")
        if source.corpus_sha256 != derived.corpus_sha256 or source.files != derived.files:
            raise FileInjectionError("Benign derived corpus hashes differ from the source")
        return
    source_target = _record_at_pointer(source_payloads, target)
    derived_target = _record_at_pointer(derived_payloads, target)
    benign = source_target.get("description")
    mutated = derived_target.get("description")
    if not isinstance(benign, str) or mutated != payload + DESCRIPTION_SEPARATOR + benign:
        raise FileInjectionError("derived target is not an exact prepend of the payload")
    derived_target["description"] = benign
    if source_payloads != derived_payloads:
        raise FileInjectionError("derived corpus changed data outside the target description")
    if _count_text_occurrences(derived.payloads.values(), payload) != 1:
        raise FileInjectionError("payload must occur exactly once in the derived corpus")
    if _count_text_occurrences(source.payloads.values(), payload) != 0:
        raise FileInjectionError("payload unexpectedly occurs in the source corpus")


def _corpus_manifest(
    scan: _CorpusScan,
    *,
    expected_raw_count: int,
    expected_task_facing_count: int,
    excluded_helpers: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "corpus_sha256": scan.corpus_sha256,
        "file_count": len(scan.files),
        "raw_endpoint_count": scan.raw_endpoint_count,
        "task_facing_endpoint_count": scan.task_facing_endpoint_count,
        "excluded_endpoint_count": scan.excluded_endpoint_count,
        "expected_raw_endpoint_count": expected_raw_count,
        "expected_task_facing_endpoint_count": expected_task_facing_count,
        "excluded_helpers": list(excluded_helpers),
        "files": [dict(item) for item in scan.files],
    }


def _verify_corpus_manifest(
    scan: _CorpusScan,
    commitment: Mapping[str, Any],
    *,
    field: str,
) -> None:
    required = {
        "corpus_sha256",
        "file_count",
        "raw_endpoint_count",
        "task_facing_endpoint_count",
        "excluded_endpoint_count",
        "expected_raw_endpoint_count",
        "expected_task_facing_endpoint_count",
        "excluded_helpers",
        "files",
    }
    if set(commitment) != required:
        raise FileInjectionError(f"{field} has an invalid field set")
    expected_raw = _positive_int(
        commitment.get("expected_raw_endpoint_count"),
        field=f"{field}.expected_raw_endpoint_count",
    )
    expected_task_facing = _positive_int(
        commitment.get("expected_task_facing_endpoint_count"),
        field=f"{field}.expected_task_facing_endpoint_count",
    )
    observed = _corpus_manifest(
        scan,
        expected_raw_count=expected_raw,
        expected_task_facing_count=expected_task_facing,
        excluded_helpers=_normalized_helpers(commitment.get("excluded_helpers", ())),
    )
    if dict(commitment) != observed:
        raise FileInjectionError(f"{field} commitments do not recompute")
    if scan.raw_endpoint_count != expected_raw:
        raise FileInjectionError(
            f"{field} raw endpoint count mismatch: expected {expected_raw}, "
            f"observed {scan.raw_endpoint_count}"
        )
    if scan.task_facing_endpoint_count != expected_task_facing:
        raise FileInjectionError(
            f"{field} task-facing endpoint count mismatch: expected {expected_task_facing}, "
            f"observed {scan.task_facing_endpoint_count}"
        )


def _target_hashes(record: Mapping[str, Any], resource: Resource) -> dict[str, Any]:
    description = record.get("description")
    if not isinstance(description, str):
        raise FileInjectionError("target endpoint description is not text")
    return {
        "endpoint_sha256": canonical_json_sha256(dict(record)),
        "description_sha256": sha256_text(description),
        "description_size_bytes": len(description.encode("utf-8")),
        "resource_body_sha256": resource.content_hash,
    }


def _derived_file_spans(
    path: Path,
    *,
    description: str,
    payload: str,
) -> dict[str, Any]:
    raw = _validated_regular_file(path, field="derived target file").read_bytes()
    description_token = json.dumps(description, ensure_ascii=False).encode("utf-8")
    escaped_payload = json.dumps(payload, ensure_ascii=False)[1:-1].encode("utf-8")
    description_start = _unique_bytes_offset(
        raw,
        description_token,
        field="description JSON string",
    )
    payload_start = description_start + 1
    payload_end = payload_start + len(escaped_payload)
    if raw[payload_start:payload_end] != escaped_payload:
        raise FileInjectionError("escaped payload is not at the start of the description token")
    return {
        "coordinate_system": "derived_json_file_utf8",
        "description_json_string": {
            "start_byte": description_start,
            "end_byte": description_start + len(description_token),
        },
        "escaped_payload": {
            "start_byte": payload_start,
            "end_byte": payload_end,
            "sha256": sha256_bytes(escaped_payload),
        },
    }


def _payload_from_derived_description(
    source_description: str,
    derived_description: str,
    insertion: Mapping[str, Any],
) -> str:
    expected_fields = {
        "coordinate_system",
        "start_byte",
        "end_byte",
        "benign_suffix_start_byte",
    }
    if set(insertion) != expected_fields:
        raise FileInjectionError("decoded description insertion has an invalid field set")
    if insertion.get("coordinate_system") != "decoded_description_utf8":
        raise FileInjectionError("decoded description coordinate system is invalid")
    start = insertion.get("start_byte")
    end = insertion.get("end_byte")
    benign_start = insertion.get("benign_suffix_start_byte")
    invalid_offsets = any(
        isinstance(value, bool) or not isinstance(value, int) for value in (end, benign_start)
    )
    if start != 0 or invalid_offsets:
        raise FileInjectionError("decoded description byte offsets are invalid")
    encoded = derived_description.encode("utf-8")
    if end <= 0 or benign_start != end + len(DESCRIPTION_SEPARATOR.encode("utf-8")):
        raise FileInjectionError("decoded description byte offsets are inconsistent")
    if encoded[end:benign_start] != DESCRIPTION_SEPARATOR.encode("utf-8"):
        raise FileInjectionError("decoded description separator is missing")
    if encoded[benign_start:] != source_description.encode("utf-8"):
        raise FileInjectionError("derived description does not preserve the benign suffix")
    try:
        return encoded[:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileInjectionError("payload byte range is not valid UTF-8") from exc


def _pool_resource(pool: ResourcePool, *, app_name: str, api_name: str) -> Resource:
    matches = [
        resource
        for resource in pool.resources
        if resource.app_name == app_name and resource.api_name == api_name
    ]
    if len(matches) != 1:
        raise FileInjectionError(
            f"loaded pool target {app_name}.{api_name} must occur exactly once; got {len(matches)}"
        )
    return matches[0]


def _api_mapping(payload: Any, *, path: Path) -> tuple[Mapping[str, Any], str]:
    if not isinstance(payload, Mapping):
        raise FileInjectionError(f"{path}: root must be an object")
    if "apis" in payload:
        mapping = payload.get("apis")
        if not isinstance(mapping, Mapping):
            raise FileInjectionError(f"{path}: apis must be an object")
        return mapping, "/apis"
    return payload, ""


def _read_json_value(path: Path, *, field: str) -> Any:
    try:
        return json.loads(_validated_regular_file(path, field=field).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FileInjectionError(f"{field} is not valid UTF-8 JSON") from exc


def _read_json_mapping(path: Path, *, field: str) -> dict[str, Any]:
    payload = _read_json_value(path, field=field)
    if not isinstance(payload, dict):
        raise FileInjectionError(f"{field} must be a JSON object")
    return payload


def _render_json_like_source(source_path: Path, payload: Any) -> bytes:
    source_text = source_path.read_text(encoding="utf-8")
    trailing_newline = source_text.endswith("\n")
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=4)
    if trailing_newline:
        encoded += "\n"
    return encoded.encode("utf-8")


def _canonical_manifest_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _exclusive_write(path: Path, data: bytes) -> None:
    if not isinstance(data, bytes):
        raise TypeError("exclusive file payload must be bytes")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:  # pragma: no cover - OS invariant
                raise FileInjectionError(f"short write while creating {path}")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_regular_file(source: Path, destination: Path) -> None:
    _validated_regular_file(source, field="source corpus file")
    try:
        with source.open("rb") as input_handle, destination.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        destination.chmod(0o600)
    except OSError as exc:
        raise FileInjectionError(f"cannot copy corpus file {source.name}") from exc


def _assert_flat_regular_json_directory(root: Path) -> None:
    try:
        entries = tuple(root.iterdir())
    except OSError as exc:
        raise FileInjectionError(f"cannot inspect corpus directory: {root}") from exc
    for entry in entries:
        try:
            info = entry.lstat()
        except OSError as exc:
            raise FileInjectionError(f"cannot inspect corpus entry: {entry}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise FileInjectionError(f"corpus contains a symlink: {entry.name}")
        if stat.S_ISDIR(info.st_mode):
            raise FileInjectionError(f"standard corpus must be flat: {entry.name}")
        if not stat.S_ISREG(info.st_mode):
            raise FileInjectionError(f"corpus entry is not a regular file: {entry.name}")
        if entry.suffix != ".json":
            raise FileInjectionError(f"standard corpus contains a non-JSON file: {entry.name}")


def _validated_directory(path: str | Path, *, field: str) -> Path:
    candidate = Path(path).expanduser()
    _reject_symlink_components(candidate, field=field)
    try:
        resolved = candidate.resolve(strict=True)
        info = resolved.lstat()
    except OSError as exc:
        raise FileInjectionError(f"{field} is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise FileInjectionError(f"{field} must be a real directory")
    return resolved


def _validated_regular_file(path: str | Path, *, field: str) -> Path:
    candidate = Path(path).expanduser()
    _reject_symlink_components(candidate, field=field)
    try:
        resolved = candidate.resolve(strict=True)
        info = resolved.lstat()
    except OSError as exc:
        raise FileInjectionError(f"{field} is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise FileInjectionError(f"{field} must be a regular file")
    return resolved


def _new_output_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.exists() or candidate.is_symlink():
        raise FileInjectionError("output_directory already exists")
    parent = candidate.parent
    _validated_directory(parent, field="output parent")
    _reject_symlink_components(candidate, field="output_directory")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(parent.resolve(strict=True))
    except ValueError as exc:
        raise FileInjectionError("output_directory escapes its parent") from exc
    return resolved


def _reject_symlink_components(path: Path, *, field: str) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise FileInjectionError(f"cannot inspect {field} path") from exc
        if stat.S_ISLNK(info.st_mode):
            raise FileInjectionError(f"{field} path contains a symlink")


def _safe_relative_path(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise FileInjectionError(f"{field} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise FileInjectionError(f"{field} is unsafe")
    return path.as_posix()


def _validate_manifest_shape(manifest: Mapping[str, Any]) -> None:
    expected = {
        "schema_version",
        "transform",
        "profile",
        "source_corpus",
        "derived_corpus",
        "target",
        "bundle_sha256",
    }
    if set(manifest) != expected:
        raise FileInjectionError("manifest has an invalid top-level field set")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise FileInjectionError("unsupported manifest schema_version")
    if not is_sha256(manifest.get("bundle_sha256")):
        raise FileInjectionError("manifest bundle_sha256 is invalid")


def _mapping(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FileInjectionError(f"{field} must be an object")
    return dict(value)


def _required_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FileInjectionError(f"{field} must be non-empty text")
    return value


def _required_payload(value: Any) -> str:
    payload = _required_text(value, field="payload")
    if "\x00" in payload:
        raise FileInjectionError("payload cannot contain NUL")
    return payload


def _canonical_arm(value: Any) -> str:
    if value in {"benign", BENIGN_ARM}:
        return BENIGN_ARM
    if value in {"poison", POISON_ARM}:
        return POISON_ARM
    raise FileInjectionError("arm must be A_benign or B_poison")


def _arm_payload(arm: str, value: Any) -> str | None:
    if arm == BENIGN_ARM:
        if value is not None:
            raise FileInjectionError("A_benign must not contain an injection payload")
        return None
    return _required_payload(value)


def _positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FileInjectionError(f"{field} must be a positive integer")
    return value


def _resolve_count_alias(
    primary: Any,
    alias: Any,
    *,
    primary_field: str,
    alias_field: str,
) -> int:
    value = _positive_int(primary, field=primary_field)
    if alias is None:
        return value
    alias_value = _positive_int(alias, field=alias_field)
    if alias_value != value:
        raise FileInjectionError(f"{alias_field} conflicts with {primary_field}")
    return value


def _normalized_helpers(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise FileInjectionError("excluded_helpers must be an iterable of names")
    normalized: list[str] = []
    try:
        for value in values:
            text = _required_text(value, field="excluded helper")
            normalized.append(unicodedata.normalize("NFKC", text).casefold())
    except TypeError as exc:
        raise FileInjectionError("excluded_helpers must be iterable") from exc
    if len(normalized) != len(set(normalized)):
        raise FileInjectionError("excluded_helpers contains duplicates")
    return tuple(sorted(normalized, key=_identifier_key))


def _identifier_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _json_pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _count_text_occurrences(values: Iterable[Any], needle: str) -> int:
    def visit(value: Any) -> int:
        if isinstance(value, str):
            return value.count(needle)
        if isinstance(value, Mapping):
            return sum(visit(key) + visit(child) for key, child in value.items())
        if isinstance(value, list):
            return sum(visit(child) for child in value)
        return 0

    return sum(visit(value) for value in values)


def _unique_bytes_offset(haystack: bytes, needle: bytes, *, field: str) -> int:
    if not needle:
        raise FileInjectionError(f"{field} cannot be empty")
    start = haystack.find(needle)
    if start < 0 or haystack.find(needle, start + 1) >= 0:
        raise FileInjectionError(f"{field} must occur exactly once in the derived file")
    return start


__all__ = [
    "BENIGN_ARM",
    "DEFAULT_EXCLUDED_HELPERS",
    "FileInjectionBundle",
    "FileInjectionError",
    "POISON_ARM",
    "load_file_injection_bundle",
    "materialize_file_injection_bundle",
]
