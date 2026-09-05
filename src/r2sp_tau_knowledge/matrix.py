"""Dataset-specific four-cell preliminary matrix orchestration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from r2sp_common import (
    ResetEvidence,
    RunStatus,
    RuntimeIdentity,
    attest_reset,
    fingerprint_code_roots,
)

from .constants import (
    ACQUISITION_TASK_ID,
    EXPERIMENT_ROOT,
    FAR_NEGATIVE_TASK_ID,
    MODEL_SEED,
    POSITIVE_TASK_ID,
    TARGET_DOCUMENT_ID,
)
from .materialize import CorpusMaterializer, Materialization
from .records import ImmutableRunWriter

MATRIX_ORDER = (
    ("mock-api-call", "benign"),
    ("mock-api-call", "poison"),
    ("delete-sentinel", "poison"),
    ("delete-sentinel", "benign"),
)


@dataclass(frozen=True)
class AcquisitionOutcome:
    status: RunStatus
    task_success: bool
    first_user_utterance: str | None
    opened_pages: tuple[dict[str, str], ...] = ()
    public_trace: dict[str, Any] = field(default_factory=dict)
    search_evidence: tuple[dict[str, Any], ...] = ()
    runtime_identity: RuntimeIdentity | None = None
    official_reward: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class CompilationOutcome:
    status: RunStatus
    skill_text: str
    skill_sha256: str
    valid: bool
    compiler_input: dict[str, Any]
    error: str | None = None


@dataclass(frozen=True)
class DeploymentOutcome:
    status: RunStatus
    task_id: str
    task_success: bool
    canary_hit: bool
    canary_events: tuple[dict[str, Any], ...]
    official_reward: float | None
    runtime_identity: RuntimeIdentity
    exposed_tool_names: tuple[str, ...]
    official_trajectory: dict[str, Any] = field(default_factory=dict)
    sidecar_trajectory: tuple[dict[str, Any], ...] = ()
    error: str | None = None


class MatrixBackend(Protocol):
    def acquire(
        self, *, profile: str, arm: str, materialization: Materialization, seed: int
    ) -> AcquisitionOutcome: ...

    def compile(
        self, *, profile: str, arm: str, acquisition: AcquisitionOutcome, seed: int
    ) -> CompilationOutcome: ...

    def deploy(
        self,
        *,
        profile: str,
        arm: str,
        task_id: str,
        skill_text: str,
        skill_sha256: str,
        seed: int,
    ) -> DeploymentOutcome: ...


def tau_code_fingerprint() -> dict[str, Any]:
    fingerprint = fingerprint_code_roots(
        {
            "common": EXPERIMENT_ROOT.parents[2] / "src" / "r2sp_common",
            "tau": EXPERIMENT_ROOT.parents[2] / "src" / "r2sp_tau_knowledge",
            "tau_scripts": EXPERIMENT_ROOT / "scripts",
        },
        include_suffixes=(".py", ".sh"),
    )
    return fingerprint.to_dict()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _status(value: RunStatus) -> str:
    return value.value


class PreliminaryMatrixRunner:
    def __init__(
        self,
        backend: MatrixBackend,
        *,
        materializer: CorpusMaterializer | None = None,
        runs_root: Path = EXPERIMENT_ROOT / "runs",
        seed: int = MODEL_SEED,
    ) -> None:
        self.backend = backend
        self.materializer = materializer or CorpusMaterializer()
        self.runs_root = Path(runs_root)
        self.seed = seed

    def run(self) -> Path:
        materializations = {
            (profile, arm): self.materializer.materialize(profile, arm)
            for profile, arm in MATRIX_ORDER
        }
        commitment = {
            "matrix": [list(cell) for cell in MATRIX_ORDER],
            "payloads": {
                profile: materializations[(profile, arm)].payload_sha256
                for profile, arm in MATRIX_ORDER
            },
            "corpora": {
                f"{profile}/{arm}": value.corpus_sha256
                for (profile, arm), value in materializations.items()
            },
            "seed": self.seed,
            "code": tau_code_fingerprint()["digest"],
        }
        writer = ImmutableRunWriter(commitment, runs_root=self.runs_root)
        cells: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        try:
            for index, (profile, arm) in enumerate(MATRIX_ORDER, start=1):
                cell_id = f"{index:02d}-{profile}-{arm}"
                events.append({"event": "phase-start", "phase": "acquisition", "cell": cell_id})
                acquisition = self.backend.acquire(
                    profile=profile,
                    arm=arm,
                    materialization=materializations[(profile, arm)],
                    seed=self.seed,
                )
                writer.write_json(
                    f"cells/{cell_id}/acquisition/public-trace.json", acquisition.public_trace
                )
                writer.write_json(
                    f"cells/{cell_id}/acquisition/search-evidence.json",
                    list(acquisition.search_evidence),
                )
                opened_ids = [page["page_id"] for page in acquisition.opened_pages]
                acquisition_record = {
                    "status": _status(acquisition.status),
                    "task_id": ACQUISITION_TASK_ID,
                    "task_success": acquisition.task_success,
                    "first_user_utterance": acquisition.first_user_utterance,
                    "opened_pages": list(acquisition.opened_pages),
                    "opened_page_ids": opened_ids,
                    "target_page_opened": TARGET_DOCUMENT_ID in opened_ids,
                    "official_reward": acquisition.official_reward,
                    "runtime_identity": (
                        acquisition.runtime_identity.to_dict()
                        if acquisition.runtime_identity is not None
                        else None
                    ),
                    "error": acquisition.error,
                }
                events.append(
                    {
                        "event": "phase-end",
                        "phase": "acquisition",
                        "cell": cell_id,
                        "status": _status(acquisition.status),
                    }
                )

                compilation: CompilationOutcome | None = None
                deployments: list[dict[str, Any]] = []
                acquisition_ready = (
                    acquisition.status is RunStatus.SUCCESS
                    and acquisition.task_success
                    and bool(acquisition.opened_pages)
                    and acquisition.first_user_utterance is not None
                    and acquisition.runtime_identity is not None
                )
                if acquisition_ready:
                    events.append({"event": "phase-start", "phase": "compiler", "cell": cell_id})
                    compilation = self.backend.compile(
                        profile=profile,
                        arm=arm,
                        acquisition=acquisition,
                        seed=self.seed,
                    )
                    writer.write_json(
                        f"cells/{cell_id}/compiler/input.json", compilation.compiler_input
                    )
                    if compilation.skill_text:
                        writer.write_text(
                            f"cells/{cell_id}/compiler/SKILL.md", compilation.skill_text
                        )
                    events.append(
                        {
                            "event": "phase-end",
                            "phase": "compiler",
                            "cell": cell_id,
                            "status": _status(compilation.status),
                        }
                    )
                compiler_record = (
                    {
                        "status": _status(compilation.status),
                        "valid": compilation.valid,
                        "skill_sha256": compilation.skill_sha256,
                        "source_page_ids": opened_ids,
                        "error": compilation.error,
                    }
                    if compilation is not None
                    else {
                        "status": RunStatus.NOT_RUN_UPSTREAM.value,
                        "valid": False,
                        "skill_sha256": None,
                        "source_page_ids": opened_ids,
                        "error": "acquisition_not_eligible",
                    }
                )

                compiler_ready = (
                    compilation is not None
                    and compilation.status is RunStatus.SUCCESS
                    and compilation.valid
                    and bool(compilation.skill_text)
                    and compilation.skill_sha256 == _sha256_text(compilation.skill_text)
                )
                for task_id in (POSITIVE_TASK_ID, FAR_NEGATIVE_TASK_ID):
                    if not compiler_ready:
                        deployments.append(
                            {
                                "task_id": task_id,
                                "status": RunStatus.NOT_RUN_UPSTREAM.value,
                                "task_success": False,
                                "canary_hit": False,
                                "reset_passed": False,
                                "error": "compiler_not_eligible",
                            }
                        )
                        continue
                    assert compilation is not None
                    events.append(
                        {
                            "event": "phase-start",
                            "phase": "deployment",
                            "cell": cell_id,
                            "task_id": task_id,
                        }
                    )
                    deployment = self.backend.deploy(
                        profile=profile,
                        arm=arm,
                        task_id=task_id,
                        skill_text=compilation.skill_text,
                        skill_sha256=compilation.skill_sha256,
                        seed=self.seed,
                    )
                    reset = attest_reset(
                        ResetEvidence(
                            acquisition_runtime=acquisition.runtime_identity,
                            deployment_runtime=deployment.runtime_identity,
                            generated_skill_hash=compilation.skill_sha256,
                            loaded_skill_hash=compilation.skill_sha256,
                            temporary_pool_destroyed=True,
                            search_index_destroyed=True,
                            acquisition_conversation_destroyed=True,
                            acquisition_memory_destroyed=True,
                            deployment_resource_pool_attached=False,
                            deployment_memory_enabled=False,
                            deployment_memory_empty=True,
                            exposed_tool_names=deployment.exposed_tool_names,
                            forbidden_tool_names=("search_web", "open_page"),
                            acquisition_material_present=False,
                        )
                    )
                    deployment_record = {
                        "task_id": task_id,
                        "status": _status(deployment.status),
                        "task_success": deployment.task_success,
                        "official_reward": deployment.official_reward,
                        "canary_hit": deployment.canary_hit,
                        "canary_events": list(deployment.canary_events),
                        "reset_passed": reset.passed,
                        "runtime_identity": deployment.runtime_identity.to_dict(),
                        "exposed_tool_names": list(deployment.exposed_tool_names),
                        "error": deployment.error,
                    }
                    deployments.append(deployment_record)
                    writer.write_json(
                        f"cells/{cell_id}/deployment/{task_id}/official-trajectory.json",
                        deployment.official_trajectory,
                    )
                    writer.write_json(
                        f"cells/{cell_id}/deployment/{task_id}/sidecar-trajectory.json",
                        list(deployment.sidecar_trajectory),
                    )
                    writer.write_json(
                        f"cells/{cell_id}/deployment/{task_id}/reset-attestation.json",
                        {
                            **reset.to_dict(),
                            "acquisition_runtime": acquisition.runtime_identity.to_dict(),
                            "deployment_runtime": deployment.runtime_identity.to_dict(),
                        },
                    )
                    events.append(
                        {
                            "event": "phase-end",
                            "phase": "deployment",
                            "cell": cell_id,
                            "task_id": task_id,
                            "status": _status(deployment.status),
                        }
                    )
                cells.append(
                    {
                        "cell_id": cell_id,
                        "profile": profile,
                        "acquisition_arm": arm,
                        "payload_sha256": materializations[(profile, arm)].payload_sha256,
                        "corpus_sha256": materializations[(profile, arm)].corpus_sha256,
                        "acquisition": acquisition_record,
                        "compiler": compiler_record,
                        "deployments": deployments,
                    }
                )
                events.append({"event": "progress", "completed_cells": index, "total_cells": 4})

            provisional = {
                "schema_version": 1,
                "run_id": writer.run_id,
                "status": RunStatus.SUCCESS.value,
                "created_at": writer.created_at.isoformat().replace("+00:00", "Z"),
                "commitment_sha256": writer.commitment_sha256,
                "code_fingerprint": tau_code_fingerprint(),
                "cells": cells,
            }
            from .replay import recompute_metrics

            summary = recompute_metrics(provisional)
            provisional["status"] = summary["overall_status"]
            provisional["summary"] = summary
            events.extend(
                (
                    {"event": "result", "summary": summary},
                    {
                        "event": "efficiency",
                        "acquisition_calls": 4,
                        "compiler_calls": sum(
                            cell["compiler"]["status"] != RunStatus.NOT_RUN_UPSTREAM.value
                            for cell in cells
                        ),
                        "deployment_calls": sum(
                            deployment["status"] != RunStatus.NOT_RUN_UPSTREAM.value
                            for cell in cells
                            for deployment in cell["deployments"]
                        ),
                    },
                )
            )
            writer.write_json("run.json", provisional)
            writer.write_json("summary.json", summary)
            writer.write_text(
                "events.jsonl",
                "".join(
                    json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in events
                ),
            )
            return writer.publish()
        except Exception:
            writer.abort()
            raise
