"""Tamper-evident, resumable records for the full-document experiment.

This module is intentionally independent from the preliminary hybrid runner.
The only matrix accepted here is the ordered matrix committed by an
``ExperimentSpec`` and copied verbatim into ``commitment.json``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypeAlias

from .compiler import validate_skill_text
from .full_doc_spec import (
    FULL_DOC_SCHEMA_VERSION,
    ExperimentSpec,
    FullDocCell,
    canonical_spec_identity_sha256,
    spec_identity,
)

ArtifactValue: TypeAlias = bytes | str | Mapping[str, Any] | list[Any]
CellKey: TypeAlias = tuple[str, str]
BeginState: TypeAlias = Literal["STARTED", "TERMINAL", "INTERRUPTED_FINALIZED"]

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_CREATION_KIND = "tau-hybrid-full-doc-creation"
_EVALUATION_KIND = "tau-hybrid-full-doc-evaluation"


class FullDocRecordError(RuntimeError):
    """A run is incomplete, structurally invalid, or has been modified."""


class InterruptedCellError(FullDocRecordError):
    """A previously started cell cannot be sampled a second time."""


def _evaluable_skill_error(text: object) -> str | None:
    """Return only hard execution-gate failures; format is diagnosed separately."""

    if not isinstance(text, str) or not text.strip():
        return "empty"
    if "\x00" in text:
        return "nul"
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return "utf8"
    return None


def _validate_creation_skill_binding(
    record: Mapping[str, Any], skill_text: str | None
) -> tuple[bool | None, str | None]:
    """Bind the execution gate and format diagnosis to the exact Skill bytes."""

    if record.get("status") == "INTERRUPTED":
        if skill_text is not None:
            raise FullDocRecordError("an interrupted cell cannot contain SKILL.md")
        return None, None
    compiler = record.get("compiler")
    if not isinstance(compiler, Mapping) or compiler.get("called") is not True:
        raise FullDocRecordError("creation record is missing compiler gate evidence")
    if skill_text is None:
        if (
            compiler.get("evaluable") is not False
            or compiler.get("format_valid") is not False
            or compiler.get("skill_sha256") is not None
        ):
            raise FullDocRecordError("non-evaluable compiler claims do not match artifacts")
        return None, None
    execution_error = _evaluable_skill_error(skill_text)
    if execution_error is not None:
        raise FullDocRecordError(f"sealed SKILL.md is non-evaluable: {execution_error}")
    format_error = validate_skill_text(skill_text)
    digest = sha256_bytes(skill_text.encode("utf-8"))
    if (
        compiler.get("evaluable") is not True
        or compiler.get("format_valid") is not (format_error is None)
        or compiler.get("format_error") != format_error
        or compiler.get("skill_sha256") != digest
    ):
        raise FullDocRecordError("compiler execution/format claims do not match SKILL.md")
    return format_error is None, format_error


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FullDocRecordError("artifact is not canonical JSON") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_utf8_exact(path: Path, label: str) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise FullDocRecordError(f"{label} is not readable UTF-8") from exc


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _safe_relative(value: str | Path) -> Path:
    relative = Path(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise FullDocRecordError("artifact path must be a safe relative path")
    return relative


def _write_new(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = -1
    temporary_name = ""
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        # Hard-link publication is atomic and cannot replace an existing file.
        os.link(temporary_name, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name)


def _write_new_or_resume_identical(path: Path, value: bytes) -> None:
    try:
        _write_new(path, value)
    except FileExistsError:
        try:
            observed = path.read_bytes()
        except OSError as exc:
            raise FullDocRecordError(f"existing artifact is unreadable: {path.name}") from exc
        if observed != value:
            raise FullDocRecordError(
                f"existing artifact differs from resumed output: {path.name}"
            ) from None


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FullDocRecordError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise FullDocRecordError(f"{label} must be a JSON object")
    if raw != canonical_json_bytes(value):
        raise FullDocRecordError(f"{label} is not canonical JSON")
    return value


def _run_id(prefix: str, identity_sha256: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{prefix}-{stamp}-{identity_sha256[:12]}"


def _cell_identity(cell: FullDocCell) -> dict[str, Any]:
    return {
        "ordinal": cell.ordinal,
        "task_id": cell.task_id,
        "arm": cell.arm,
        "condition": cell.condition,
        "profile": cell.profile,
        "poison_percent": cell.poison_percent,
        "materialization_key": cell.materialization_key,
        "model_seed": cell.model_seed,
        "user_seed": cell.user_seed,
    }


def _json_mapping(value: Mapping[str, Any] | None, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    try:
        result = json.loads(
            json.dumps(dict(value), ensure_ascii=False, sort_keys=True, allow_nan=False)
        )
    except (TypeError, ValueError) as exc:
        raise FullDocRecordError(f"{label} is not JSON serializable") from exc
    if not isinstance(result, dict):  # pragma: no cover - dict round-trip invariant
        raise FullDocRecordError(f"{label} must remain a JSON object")
    return result


def _creation_commitment(
    spec: ExperimentSpec,
    run_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cells = [_cell_identity(cell) for cell in spec.cells]
    if len(cells) != 60 or spec.expected_creation_records != 60:
        raise FullDocRecordError("full-document creation matrix must contain exactly 60 cells")
    return {
        "schema_version": spec.schema_version,
        "kind": _CREATION_KIND,
        "experiment_identity": spec_identity(spec),
        "experiment_identity_sha256": canonical_spec_identity_sha256(spec),
        "run_identity": _json_mapping(run_identity, "run_identity"),
        "trial_count": spec.expected_creation_records,
        "cells": cells,
    }


def _validate_creation_commitment_for_spec(
    commitment: Mapping[str, Any],
    spec: ExperimentSpec,
    *,
    expected_run_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    observed_identity = commitment.get("run_identity")
    if not isinstance(observed_identity, Mapping):
        raise FullDocRecordError("creation commitment run_identity is missing")
    run_identity = _json_mapping(observed_identity, "sealed run_identity")
    if expected_run_identity is not None:
        expected = _json_mapping(expected_run_identity, "expected_run_identity")
        if run_identity != expected:
            raise FullDocRecordError("creation run_identity does not match the expected runtime")
    if dict(commitment) != _creation_commitment(spec, run_identity):
        raise FullDocRecordError("creation commitment does not match the supplied spec")
    return run_identity


def _cell_map(commitment: Mapping[str, Any]) -> dict[CellKey, dict[str, Any]]:
    raw = commitment.get("cells")
    if not isinstance(raw, list) or len(raw) != 60:
        raise FullDocRecordError("sealed commitment must contain exactly 60 ordered cells")
    result: dict[CellKey, dict[str, Any]] = {}
    for ordinal, value in enumerate(raw):
        if not isinstance(value, dict):
            raise FullDocRecordError("sealed cell identity is malformed")
        task_id = value.get("task_id")
        arm = value.get("arm")
        if (
            value.get("ordinal") != ordinal
            or not isinstance(task_id, str)
            or not isinstance(arm, str)
            or value.get("condition") != arm
            or Path(task_id).name != task_id
            or Path(arm).name != arm
        ):
            raise FullDocRecordError("sealed cell identity is invalid")
        key = (task_id, arm)
        if key in result:
            raise FullDocRecordError("sealed cell identities are not unique")
        result[key] = dict(value)
    return result


def _cell_relative(identity: Mapping[str, Any]) -> Path:
    return Path("cells") / str(identity["task_id"]) / str(identity["arm"])


def _marker_relative(identity: Mapping[str, Any]) -> Path:
    filename = f"{int(identity['ordinal']):03d}-{identity['task_id']}-{identity['arm']}.json"
    return Path("started") / filename


def _normalize_record(
    value: Mapping[str, Any], identity: Mapping[str, Any], *, phase: str
) -> dict[str, Any]:
    try:
        record = json.loads(json.dumps(dict(value), ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise FullDocRecordError("cell record is not JSON serializable") from exc
    required = {
        "schema_version": FULL_DOC_SCHEMA_VERSION,
        "phase": phase,
        "ordinal": identity["ordinal"],
        "task_id": identity["task_id"],
        "arm": identity["arm"],
        "condition": identity["condition"],
    }
    for key, expected in required.items():
        if key in record and record[key] != expected:
            raise FullDocRecordError(f"cell record {key} conflicts with its commitment")
        record[key] = expected
    status = record.get("status")
    if not isinstance(status, str) or not status:
        raise FullDocRecordError("cell record requires a non-empty terminal status")
    return record


def _encode_artifact(value: ArtifactValue) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return canonical_json_bytes(value)


def _publish_artifact_directory(
    destination: Path,
    artifacts: Mapping[str, ArtifactValue],
) -> None:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"terminal cell already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent)
    )
    try:
        for name, value in artifacts.items():
            relative = _safe_relative(name)
            path = temporary / relative
            try:
                path.relative_to(temporary)
            except ValueError as exc:  # pragma: no cover - guarded by _safe_relative
                raise FullDocRecordError("artifact path escapes its cell") from exc
            _write_new(path, _encode_artifact(value))
        _fsync_directory(temporary)
        os.rename(temporary, destination)
        _fsync_directory(destination.parent)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _remove_owned_staging(
    root: Path,
    cells: Mapping[CellKey, Mapping[str, Any]],
) -> None:
    """Remove only unpublished temp directories created by this writer."""

    for identity in cells.values():
        parent = root / "cells" / str(identity["task_id"])
        if not parent.exists():
            continue
        prefix = f".{identity['arm']}.staging-"
        for candidate in parent.iterdir():
            if not candidate.name.startswith(prefix):
                continue
            if candidate.is_symlink() or not candidate.is_dir():
                raise FullDocRecordError("owned cell staging path has an invalid type")
            shutil.rmtree(candidate)
        _fsync_directory(parent)


def _assert_no_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise FullDocRecordError("run root may not be a symlink")
    for item in root.rglob("*"):
        if item.is_symlink():
            raise FullDocRecordError("run artifacts may not contain symlinks")


def _inventory(root: Path, *, exclude: frozenset[str] = frozenset()) -> dict[str, str]:
    _assert_no_symlinks(root)
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative not in exclude:
            result[relative] = sha256_file(path)
    return result


def _seal_tree(
    root: Path,
    *,
    kind: str,
    trial_count: int,
    required_artifacts: Mapping[str, str],
) -> tuple[dict[str, Any], str]:
    inventory = _inventory(root, exclude=frozenset({"complete.json"}))
    required_hashes: dict[str, str] = {}
    for field, relative in required_artifacts.items():
        expected = inventory.get(relative)
        if expected is None:
            raise FullDocRecordError(f"required artifact hash mismatch: {relative}")
        required_hashes[field] = expected
    complete = {
        "schema_version": FULL_DOC_SCHEMA_VERSION,
        "kind": kind,
        "status": "COMPLETE",
        "trial_count": trial_count,
        **dict(required_hashes),
        "sealed_files": inventory,
        "sealed_files_sha256": sha256_bytes(canonical_json_bytes(inventory)),
    }
    complete_bytes = canonical_json_bytes(complete)
    _write_new(root / "complete.json", complete_bytes)
    for path in sorted(root.rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)
    return complete, sha256_bytes(complete_bytes)


def _verify_sealed_tree(
    root: Path,
    *,
    kind: str,
    expected_complete_sha256: str | None = None,
) -> tuple[dict[str, Any], str]:
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise FullDocRecordError("sealed run does not exist") from exc
    if not resolved.is_dir() or root.is_symlink():
        raise FullDocRecordError("sealed run must be a real directory")
    _assert_no_symlinks(resolved)
    complete_path = resolved / "complete.json"
    complete = _read_json(complete_path, "complete.json")
    complete_bytes = complete_path.read_bytes()
    complete_sha256 = sha256_bytes(complete_bytes)
    if expected_complete_sha256 is not None and complete_sha256 != expected_complete_sha256:
        raise FullDocRecordError("complete.json hash does not match the expected binding")
    common_fields = {
        "schema_version",
        "kind",
        "status",
        "trial_count",
        "sealed_files",
        "sealed_files_sha256",
    }
    kind_fields = {
        _CREATION_KIND: {"commitment_sha256", "skills_sha256"},
        _EVALUATION_KIND: {"creation_binding_sha256", "metrics_sha256"},
    }
    if set(complete) != common_fields | kind_fields[kind]:
        raise FullDocRecordError("complete.json fields do not match the fixed schema")
    if (
        complete.get("schema_version") != FULL_DOC_SCHEMA_VERSION
        or complete.get("kind") != kind
        or complete.get("status") != "COMPLETE"
        or complete.get("trial_count") != 60
    ):
        raise FullDocRecordError("complete.json identity is invalid")
    sealed_files = complete.get("sealed_files")
    if not isinstance(sealed_files, dict) or not sealed_files:
        raise FullDocRecordError("sealed-file inventory is missing")
    if any(
        not isinstance(path, str)
        or _safe_relative(path).as_posix() != path
        or not isinstance(digest, str)
        or _HEX64.fullmatch(digest) is None
        for path, digest in sealed_files.items()
    ):
        raise FullDocRecordError("sealed-file inventory is malformed")
    if complete.get("sealed_files_sha256") != sha256_bytes(canonical_json_bytes(sealed_files)):
        raise FullDocRecordError("sealed-file inventory hash mismatch")
    observed = _inventory(resolved, exclude=frozenset({"complete.json"}))
    if observed != sealed_files:
        raise FullDocRecordError("sealed artifacts were added, removed, or modified")
    return complete, complete_sha256


def _validate_matrix_layout(
    root: Path,
    cells: Mapping[CellKey, Mapping[str, Any]],
) -> None:
    """Reject cells and started markers outside the sealed matrix."""

    cells_root = root / "cells"
    started_root = root / "started"
    if not cells_root.is_dir() or cells_root.is_symlink():
        raise FullDocRecordError("cells directory is missing")
    if not started_root.is_dir() or started_root.is_symlink():
        raise FullDocRecordError("started-marker directory is missing")
    expected_directories = {
        (root / _cell_relative(identity)).resolve(strict=False) for identity in cells.values()
    }
    observed_directories: set[Path] = set()
    for task_entry in cells_root.iterdir():
        if not task_entry.is_dir() or task_entry.is_symlink():
            raise FullDocRecordError("cells directory contains an unexpected entry")
        for arm_entry in task_entry.iterdir():
            if not arm_entry.is_dir() or arm_entry.is_symlink():
                raise FullDocRecordError("task directory contains an unexpected entry")
            observed_directories.add(arm_entry.resolve(strict=False))
    if observed_directories != expected_directories:
        raise FullDocRecordError("terminal cell layout does not match the sealed matrix")
    expected_markers = {
        (root / _marker_relative(identity)).resolve(strict=False) for identity in cells.values()
    }
    observed_markers = set()
    for marker in started_root.iterdir():
        if not marker.is_file() or marker.is_symlink():
            raise FullDocRecordError("started directory contains an unexpected entry")
        observed_markers.add(marker.resolve(strict=False))
    if observed_markers != expected_markers:
        raise FullDocRecordError("started-marker layout does not match the sealed matrix")


def _validate_cell_tree(
    root: Path,
    identity: Mapping[str, Any],
    *,
    phase: str,
) -> dict[str, Any]:
    directory = root / _cell_relative(identity)
    if not directory.is_dir() or directory.is_symlink():
        raise FullDocRecordError("terminal cell directory is missing")
    record = _read_json(directory / "record.json", "cell record")
    normalized = _normalize_record(record, identity, phase=phase)
    if normalized != record:
        raise FullDocRecordError("cell record omitted its sealed identity")
    return record


@dataclass(frozen=True, slots=True)
class SealedCreation:
    root: Path
    commitment: dict[str, Any]
    complete: dict[str, Any]
    complete_sha256: str
    commitment_sha256: str
    skills_sha256: str
    skills: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class SealedEvaluation:
    root: Path
    binding: dict[str, Any]
    complete: dict[str, Any]
    complete_sha256: str
    metrics: dict[str, Any]


class _ResumableWriter:
    phase: str
    kind: str

    def _initialize_state(
        self,
        *,
        root: Path,
        commitment: Mapping[str, Any],
        commitment_filename: str,
    ) -> None:
        self.root = root
        self.commitment = dict(commitment)
        self.commitment_filename = commitment_filename
        self.cells = _cell_map(commitment)
        self._claimed_this_process: set[CellKey] = set()
        self._complete = False

    def _identity(self, task_id: str, arm: str) -> dict[str, Any]:
        try:
            return self.cells[(task_id, arm)]
        except KeyError as exc:
            raise FullDocRecordError("cell is outside the sealed full-document matrix") from exc

    def _marker(self, identity: Mapping[str, Any]) -> Path:
        return self.root / _marker_relative(identity)

    def _destination(self, identity: Mapping[str, Any]) -> Path:
        return self.root / _cell_relative(identity)

    def _marker_document(self, identity: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": FULL_DOC_SCHEMA_VERSION,
            "phase": self.phase,
            "ordinal": identity["ordinal"],
            "task_id": identity["task_id"],
            "arm": identity["arm"],
            "condition": identity["condition"],
            "state": "STARTED",
        }

    def begin_cell(self, task_id: str, arm: str) -> BeginState:
        """Claim a cell once, or terminalize a stale claim without rerunning it."""

        if self._complete:
            raise FullDocRecordError(f"{self.phase} run is already complete")
        identity = self._identity(task_id, arm)
        destination = self._destination(identity)
        marker = self._marker(identity)
        if destination.exists():
            _validate_cell_tree(self.root, identity, phase=self.phase)
            return "TERMINAL"
        key = (task_id, arm)
        if marker.exists():
            observed = _read_json(marker, "cell started marker")
            if observed != self._marker_document(identity):
                raise FullDocRecordError("cell started marker identity mismatch")
            if key in self._claimed_this_process:
                raise FullDocRecordError("cell is already active in this process")
            self._publish_interrupted(identity)
            return "INTERRUPTED_FINALIZED"
        _write_new(marker, canonical_json_bytes(self._marker_document(identity)))
        self._claimed_this_process.add(key)
        return "STARTED"

    def _publish_interrupted(self, identity: Mapping[str, Any]) -> None:
        record = _normalize_record(
            {
                "status": "INTERRUPTED",
                "error": "cell was started but had no terminal publication at process recovery",
            },
            identity,
            phase=self.phase,
        )
        _publish_artifact_directory(
            self._destination(identity),
            {"record.json": record},
        )

    def recover_interrupted_cells(self) -> tuple[CellKey, ...]:
        """Finalize all stale markers; recovered cells can never be sampled again."""

        recovered: list[CellKey] = []
        for identity in self.cells.values():
            destination = self._destination(identity)
            marker = self._marker(identity)
            if destination.exists():
                _validate_cell_tree(self.root, identity, phase=self.phase)
                continue
            if not marker.exists():
                continue
            observed = _read_json(marker, "cell started marker")
            if observed != self._marker_document(identity):
                raise FullDocRecordError("cell started marker identity mismatch")
            self._publish_interrupted(identity)
            recovered.append((str(identity["task_id"]), str(identity["arm"])))
        return tuple(recovered)

    def terminal_cell_keys(self) -> tuple[CellKey, ...]:
        result: list[CellKey] = []
        for identity in self.cells.values():
            if self._destination(identity).is_dir():
                _validate_cell_tree(self.root, identity, phase=self.phase)
                result.append((str(identity["task_id"]), str(identity["arm"])))
        return tuple(result)

    def _ensure_claimed_for_publish(self, identity: Mapping[str, Any]) -> None:
        key = (str(identity["task_id"]), str(identity["arm"]))
        destination = self._destination(identity)
        if destination.exists():
            raise FileExistsError(f"terminal cell already exists: {key[0]}/{key[1]}")
        marker = self._marker(identity)
        if not marker.exists():
            state = self.begin_cell(*key)
            if state != "STARTED":  # pragma: no cover - guarded by the checks above
                raise InterruptedCellError(f"cell cannot be published: {key[0]}/{key[1]}")
            return
        if key not in self._claimed_this_process:
            raise InterruptedCellError(
                f"stale started cell must be finalized, not retried: {key[0]}/{key[1]}"
            )


class CreationRunWriter(_ResumableWriter):
    """Atomically publish 60 creation trials, then seal every artifact."""

    phase = "creation"
    kind = _CREATION_KIND

    def __init__(
        self,
        spec: ExperimentSpec,
        *,
        run_identity: Mapping[str, Any] | None = None,
        runs_root: Path | None = None,
    ) -> None:
        commitment = _creation_commitment(spec, run_identity)
        identity_sha256 = commitment["experiment_identity_sha256"]
        base = Path(runs_root or spec.paths.runs_root / "creation").resolve()
        base.mkdir(parents=True, exist_ok=True)
        root = base / _run_id("full-doc-create", identity_sha256)
        root.mkdir(mode=0o700)
        _write_new(root / "commitment.json", canonical_json_bytes(commitment))
        self.spec = spec
        self._initialize_state(
            root=root,
            commitment=commitment,
            commitment_filename="commitment.json",
        )

    @classmethod
    def resume(
        cls,
        spec: ExperimentSpec,
        root: Path,
        *,
        run_identity: Mapping[str, Any] | None = None,
    ) -> CreationRunWriter:
        requested_root = Path(root)
        resolved = requested_root.resolve(strict=True)
        if requested_root.is_symlink():
            raise FullDocRecordError("creation run root may not be a symlink")
        if (resolved / "complete.json").exists():
            raise FullDocRecordError("sealed creation must be verified, not resumed")
        commitment = _read_json(resolved / "commitment.json", "creation commitment")
        _validate_creation_commitment_for_spec(
            commitment,
            spec,
            expected_run_identity=_json_mapping(run_identity, "run_identity"),
        )
        instance = cls.__new__(cls)
        instance.spec = spec
        instance._initialize_state(
            root=resolved,
            commitment=commitment,
            commitment_filename="commitment.json",
        )
        _remove_owned_staging(instance.root, instance.cells)
        instance.recover_interrupted_cells()
        return instance

    def publish_cell(
        self,
        task_id: str,
        arm: str,
        artifacts: Mapping[str, ArtifactValue],
    ) -> Path:
        identity = self._identity(task_id, arm)
        self._ensure_claimed_for_publish(identity)
        if "record.json" not in artifacts:
            raise FullDocRecordError("creation cell artifacts must include record.json")
        record_value = artifacts["record.json"]
        if not isinstance(record_value, Mapping):
            raise FullDocRecordError("record.json must be supplied as a mapping")
        normalized = _normalize_record(record_value, identity, phase=self.phase)
        prepared = dict(artifacts)
        prepared["record.json"] = normalized
        skill_value = prepared.get("SKILL.md")
        if skill_value is not None:
            if not isinstance(skill_value, str):
                raise FullDocRecordError("SKILL.md must be UTF-8 text")
            execution_error = _evaluable_skill_error(skill_value)
            if execution_error is not None:
                raise FullDocRecordError(f"non-evaluable SKILL.md supplied: {execution_error}")
        _validate_creation_skill_binding(normalized, skill_value)
        raw_value = prepared.get("compiler/raw-output.txt")
        if skill_value is not None:
            if not isinstance(raw_value, (bytes, str)):
                raise FullDocRecordError("evaluable SKILL.md requires compiler raw output")
            raw_bytes = raw_value if isinstance(raw_value, bytes) else raw_value.encode("utf-8")
            if raw_bytes != skill_value.encode("utf-8"):
                raise FullDocRecordError("SKILL.md must preserve exact compiler raw output")
        if any(Path(name).name == "SKILL.md" and name != "SKILL.md" for name in prepared):
            raise FullDocRecordError("SKILL.md must be at the fixed cell path")
        destination = self._destination(identity)
        _publish_artifact_directory(destination, prepared)
        self._claimed_this_process.discard((task_id, arm))
        return destination

    def _skills_index(self) -> list[dict[str, Any]]:
        skills: list[dict[str, Any]] = []
        for identity in self.cells.values():
            directory = self._destination(identity)
            record = _validate_cell_tree(self.root, identity, phase=self.phase)
            skill_path = directory / "SKILL.md"
            if skill_path.is_file():
                skill_text = _read_utf8_exact(skill_path, "SKILL.md")
                execution_error = _evaluable_skill_error(skill_text)
                if execution_error is not None:
                    raise FullDocRecordError(f"sealed SKILL.md is non-evaluable: {execution_error}")
                format_valid, format_error = _validate_creation_skill_binding(record, skill_text)
                raw_path = directory / "compiler" / "raw-output.txt"
                if not raw_path.is_file() or raw_path.read_bytes() != skill_path.read_bytes():
                    raise FullDocRecordError("SKILL.md differs from compiler raw output")
                status = "EVALUABLE"
                relative: str | None = skill_path.relative_to(self.root).as_posix()
                digest: str | None = sha256_file(skill_path)
            else:
                if any(path.name == "SKILL.md" for path in directory.rglob("*")):
                    raise FullDocRecordError("SKILL.md exists outside its fixed cell path")
                status = "INTERRUPTED" if record.get("status") == "INTERRUPTED" else "NOT_EVALUABLE"
                relative = None
                digest = None
                format_valid, format_error = _validate_creation_skill_binding(record, None)
            skills.append(
                {
                    "ordinal": identity["ordinal"],
                    "task_id": identity["task_id"],
                    "arm": identity["arm"],
                    "condition": identity["condition"],
                    "profile": identity["profile"],
                    "status": status,
                    "evaluable": status == "EVALUABLE",
                    "format_valid": format_valid,
                    "format_error": format_error,
                    "path": relative,
                    "sha256": digest,
                    "record_path": (directory / "record.json").relative_to(self.root).as_posix(),
                    "record_sha256": sha256_file(directory / "record.json"),
                }
            )
        return skills

    def seal(self) -> SealedCreation:
        if self._complete or (self.root / "complete.json").exists():
            raise FullDocRecordError("creation run is already sealed")
        if len(self.terminal_cell_keys()) != 60:
            raise FullDocRecordError("cannot seal creation before all 60 cells are terminal")
        _validate_matrix_layout(self.root, self.cells)
        skills = self._skills_index()
        if len(skills) != 60:
            raise FullDocRecordError("skills index must contain exactly 60 entries")
        skills_bytes = canonical_json_bytes({"skills": skills})
        _write_new_or_resume_identical(self.root / "skills.json", skills_bytes)
        commitment_sha256 = sha256_file(self.root / "commitment.json")
        skills_sha256 = sha256_bytes(skills_bytes)
        complete, complete_sha256 = _seal_tree(
            self.root,
            kind=self.kind,
            trial_count=60,
            required_artifacts={
                "commitment_sha256": "commitment.json",
                "skills_sha256": "skills.json",
            },
        )
        self._complete = True
        return SealedCreation(
            root=self.root,
            commitment=dict(self.commitment),
            complete=complete,
            complete_sha256=complete_sha256,
            commitment_sha256=commitment_sha256,
            skills_sha256=skills_sha256,
            skills=tuple(skills),
        )


def verify_creation_run(
    path: Path,
    spec: ExperimentSpec,
    *,
    expected_complete_sha256: str | None = None,
    expected_run_identity: Mapping[str, Any] | None = None,
) -> SealedCreation:
    root = Path(path).resolve(strict=True)
    complete, complete_sha256 = _verify_sealed_tree(
        root,
        kind=_CREATION_KIND,
        expected_complete_sha256=expected_complete_sha256,
    )
    commitment = _read_json(root / "commitment.json", "creation commitment")
    _validate_creation_commitment_for_spec(
        commitment,
        spec,
        expected_run_identity=expected_run_identity,
    )
    commitment_sha256 = sha256_file(root / "commitment.json")
    if complete.get("commitment_sha256") != commitment_sha256:
        raise FullDocRecordError("creation commitment hash mismatch")
    cells = _cell_map(commitment)
    _validate_matrix_layout(root, cells)
    skills_document = _read_json(root / "skills.json", "skills index")
    skills_raw = skills_document.get("skills")
    if not isinstance(skills_raw, list) or len(skills_raw) != 60:
        raise FullDocRecordError("skills index must contain exactly 60 entries")
    expected_index: list[dict[str, Any]] = []
    for identity in cells.values():
        record = _validate_cell_tree(root, identity, phase="creation")
        marker = _read_json(root / _marker_relative(identity), "cell started marker")
        expected_marker = {
            "schema_version": FULL_DOC_SCHEMA_VERSION,
            "phase": "creation",
            "ordinal": identity["ordinal"],
            "task_id": identity["task_id"],
            "arm": identity["arm"],
            "condition": identity["condition"],
            "state": "STARTED",
        }
        if marker != expected_marker:
            raise FullDocRecordError("cell started marker identity mismatch")
        directory = root / _cell_relative(identity)
        skill_path = directory / "SKILL.md"
        if skill_path.is_file():
            skill_text = _read_utf8_exact(skill_path, "SKILL.md")
            execution_error = _evaluable_skill_error(skill_text)
            if execution_error is not None:
                raise FullDocRecordError(f"sealed SKILL.md is non-evaluable: {execution_error}")
            format_valid, format_error = _validate_creation_skill_binding(record, skill_text)
            raw_path = directory / "compiler" / "raw-output.txt"
            if not raw_path.is_file() or raw_path.read_bytes() != skill_path.read_bytes():
                raise FullDocRecordError("SKILL.md differs from compiler raw output")
            status = "EVALUABLE"
            skill_relative: str | None = skill_path.relative_to(root).as_posix()
            skill_sha256: str | None = sha256_file(skill_path)
        else:
            if any(candidate.name == "SKILL.md" for candidate in directory.rglob("*")):
                raise FullDocRecordError("SKILL.md exists outside its fixed cell path")
            status = "INTERRUPTED" if record.get("status") == "INTERRUPTED" else "NOT_EVALUABLE"
            skill_relative = None
            skill_sha256 = None
            format_valid, format_error = _validate_creation_skill_binding(record, None)
        expected_index.append(
            {
                "ordinal": identity["ordinal"],
                "task_id": identity["task_id"],
                "arm": identity["arm"],
                "condition": identity["condition"],
                "profile": identity["profile"],
                "status": status,
                "evaluable": status == "EVALUABLE",
                "format_valid": format_valid,
                "format_error": format_error,
                "path": skill_relative,
                "sha256": skill_sha256,
                "record_path": (directory / "record.json").relative_to(root).as_posix(),
                "record_sha256": sha256_file(directory / "record.json"),
            }
        )
    if skills_raw != expected_index:
        raise FullDocRecordError("skills index order, identity, path, status, or hash is invalid")
    skills_sha256 = sha256_file(root / "skills.json")
    if complete.get("skills_sha256") != skills_sha256:
        raise FullDocRecordError("skills index hash mismatch")
    return SealedCreation(
        root=root,
        commitment=commitment,
        complete=complete,
        complete_sha256=complete_sha256,
        commitment_sha256=commitment_sha256,
        skills_sha256=skills_sha256,
        skills=tuple(dict(item) for item in skills_raw),
    )


def _evaluation_binding(spec: ExperimentSpec, creation: SealedCreation) -> dict[str, Any]:
    _validate_creation_commitment_for_spec(creation.commitment, spec)
    return {
        "schema_version": spec.schema_version,
        "kind": _EVALUATION_KIND,
        "experiment_identity_sha256": canonical_spec_identity_sha256(spec),
        "trial_count": spec.expected_evaluation_records,
        "cells": list(creation.commitment["cells"]),
        "creation_run": str(creation.root),
        "creation_complete_sha256": creation.complete_sha256,
        "creation_commitment_sha256": creation.commitment_sha256,
        "creation_skills_sha256": creation.skills_sha256,
    }


class EvaluationRunWriter(_ResumableWriter):
    """Atomically publish 60 fresh evaluations bound to one creation seal."""

    phase = "evaluation"
    kind = _EVALUATION_KIND

    def __init__(
        self,
        spec: ExperimentSpec,
        creation: SealedCreation,
        *,
        runs_root: Path | None = None,
    ) -> None:
        if spec.expected_evaluation_records != 60:
            raise FullDocRecordError("full-document evaluation matrix must contain 60 cells")
        creation = verify_creation_run(
            creation.root,
            spec,
            expected_complete_sha256=creation.complete_sha256,
        )
        binding = _evaluation_binding(spec, creation)
        base = Path(runs_root or spec.paths.runs_root / "evaluation").resolve()
        base.mkdir(parents=True, exist_ok=True)
        root = base / _run_id("full-doc-evaluate", binding["experiment_identity_sha256"])
        root.mkdir(mode=0o700)
        _write_new(root / "creation-binding.json", canonical_json_bytes(binding))
        self.spec = spec
        self.creation = creation
        self._initialize_state(
            root=root,
            commitment=binding,
            commitment_filename="creation-binding.json",
        )

    @classmethod
    def resume(
        cls,
        spec: ExperimentSpec,
        creation: SealedCreation,
        root: Path,
    ) -> EvaluationRunWriter:
        creation = verify_creation_run(
            creation.root,
            spec,
            expected_complete_sha256=creation.complete_sha256,
        )
        requested_root = Path(root)
        resolved = requested_root.resolve(strict=True)
        if requested_root.is_symlink():
            raise FullDocRecordError("evaluation run root may not be a symlink")
        if (resolved / "complete.json").exists():
            raise FullDocRecordError("sealed evaluation must be verified, not resumed")
        binding = _read_json(resolved / "creation-binding.json", "creation binding")
        if binding != _evaluation_binding(spec, creation):
            raise FullDocRecordError("evaluation binding does not match creation and spec")
        instance = cls.__new__(cls)
        instance.spec = spec
        instance.creation = creation
        instance._initialize_state(
            root=resolved,
            commitment=binding,
            commitment_filename="creation-binding.json",
        )
        _remove_owned_staging(instance.root, instance.cells)
        instance.recover_interrupted_cells()
        return instance

    def publish_cell(
        self,
        task_id: str,
        arm: str,
        record: Mapping[str, Any],
        *,
        artifacts: Mapping[str, ArtifactValue] | None = None,
    ) -> Path:
        identity = self._identity(task_id, arm)
        self._ensure_claimed_for_publish(identity)
        prepared = dict(artifacts or {})
        if "record.json" in prepared:
            raise FullDocRecordError("evaluation record must use the record argument")
        prepared["record.json"] = _normalize_record(record, identity, phase=self.phase)
        destination = self._destination(identity)
        _publish_artifact_directory(destination, prepared)
        self._claimed_this_process.discard((task_id, arm))
        return destination

    def complete(
        self,
        metrics: Mapping[str, Any],
        *,
        report_markdown: str | None = None,
    ) -> SealedEvaluation:
        if self._complete or (self.root / "complete.json").exists():
            raise FullDocRecordError("evaluation run is already sealed")
        if len(self.terminal_cell_keys()) != 60:
            raise FullDocRecordError("cannot seal evaluation before all 60 cells are terminal")
        _validate_matrix_layout(self.root, self.cells)
        metrics_value = json.loads(
            json.dumps(dict(metrics), ensure_ascii=False, sort_keys=True, allow_nan=False)
        )
        _write_new_or_resume_identical(
            self.root / "metrics.json", canonical_json_bytes(metrics_value)
        )
        if report_markdown is not None:
            if not isinstance(report_markdown, str):
                raise TypeError("report_markdown must be text")
            _write_new_or_resume_identical(self.root / "report.md", report_markdown.encode("utf-8"))
        complete, complete_sha256 = _seal_tree(
            self.root,
            kind=self.kind,
            trial_count=60,
            required_artifacts={
                "creation_binding_sha256": "creation-binding.json",
                "metrics_sha256": "metrics.json",
            },
        )
        self._complete = True
        return SealedEvaluation(
            root=self.root,
            binding=dict(self.commitment),
            complete=complete,
            complete_sha256=complete_sha256,
            metrics=metrics_value,
        )


def verify_evaluation_run(
    path: Path,
    spec: ExperimentSpec,
    creation: SealedCreation,
    *,
    expected_complete_sha256: str | None = None,
) -> SealedEvaluation:
    creation = verify_creation_run(
        creation.root,
        spec,
        expected_complete_sha256=creation.complete_sha256,
    )
    root = Path(path).resolve(strict=True)
    complete, complete_sha256 = _verify_sealed_tree(
        root,
        kind=_EVALUATION_KIND,
        expected_complete_sha256=expected_complete_sha256,
    )
    binding = _read_json(root / "creation-binding.json", "creation binding")
    if binding != _evaluation_binding(spec, creation):
        raise FullDocRecordError("evaluation binding does not match creation and spec")
    if complete.get("creation_binding_sha256") != sha256_file(root / "creation-binding.json"):
        raise FullDocRecordError("evaluation creation binding hash mismatch")
    cells = _cell_map(binding)
    _validate_matrix_layout(root, cells)
    records: list[dict[str, Any]] = []
    for cell in spec.cells:
        identity = cells[(cell.task_id, cell.arm)]
        records.append(_validate_cell_tree(root, identity, phase="evaluation"))
        marker = _read_json(root / _marker_relative(identity), "cell started marker")
        expected_marker = {
            "schema_version": FULL_DOC_SCHEMA_VERSION,
            "phase": "evaluation",
            "ordinal": identity["ordinal"],
            "task_id": identity["task_id"],
            "arm": identity["arm"],
            "condition": identity["condition"],
            "state": "STARTED",
        }
        if marker != expected_marker:
            raise FullDocRecordError("cell started marker identity mismatch")
    metrics = _read_json(root / "metrics.json", "evaluation metrics")
    if complete.get("metrics_sha256") != sha256_file(root / "metrics.json"):
        raise FullDocRecordError("evaluation metrics hash mismatch")
    # Import locally to keep the writer/runner modules acyclic at import time.
    from .full_doc_experiment import (  # noqa: PLC0415
        compute_full_doc_metrics,
        render_metrics_markdown,
    )

    try:
        expected_metrics = compute_full_doc_metrics(spec, records)
        expected_report = render_metrics_markdown(expected_metrics).encode("utf-8")
    except (KeyError, TypeError, ValueError) as exc:
        raise FullDocRecordError("sealed evaluation records cannot be summarized") from exc
    if metrics != expected_metrics:
        raise FullDocRecordError("evaluation metrics do not match the sealed cell records")
    try:
        observed_report = (root / "report.md").read_bytes()
    except OSError as exc:
        raise FullDocRecordError("evaluation report is unreadable") from exc
    if observed_report != expected_report:
        raise FullDocRecordError("evaluation report does not match the sealed cell records")
    return SealedEvaluation(
        root=root,
        binding=binding,
        complete=complete,
        complete_sha256=complete_sha256,
        metrics=metrics,
    )


__all__ = [
    "BeginState",
    "CreationRunWriter",
    "EvaluationRunWriter",
    "FullDocRecordError",
    "InterruptedCellError",
    "SealedCreation",
    "SealedEvaluation",
    "canonical_json_bytes",
    "sha256_bytes",
    "sha256_file",
    "verify_creation_run",
    "verify_evaluation_run",
]
