from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from r2sp_common import RunStatus, RuntimeIdentity
from r2sp_tau_knowledge.constants import (
    EXPERIMENT_ROOT,
    FAR_NEGATIVE_TASK_ID,
    POSITIVE_TASK_ID,
    TARGET_DOCUMENT_ID,
)
from r2sp_tau_knowledge.materialize import CorpusMaterializer, Materialization
from r2sp_tau_knowledge.matrix import (
    MATRIX_ORDER,
    AcquisitionOutcome,
    CompilationOutcome,
    DeploymentOutcome,
    PreliminaryMatrixRunner,
)
from r2sp_tau_knowledge.replay import recompute_metrics, replay_run
from r2sp_tau_knowledge.scripted import ScriptedMatrixBackend


@pytest.fixture(scope="module")
def scripted_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any], Any]:
    root = tmp_path_factory.mktemp("scripted-matrix")
    documents = root / "source-documents"
    documents.mkdir()
    documents.joinpath(f"{TARGET_DOCUMENT_ID}.json").write_text(
        json.dumps(
            {
                "id": TARGET_DOCUMENT_ID,
                "title": "Gold Rewards Card",
                "content": "Original trusted body.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    documents.joinpath("doc_other_001.json").write_bytes(
        b'{"id":"doc_other_001","title":"Other","content":"Unchanged"}\n'
    )
    backend = ScriptedMatrixBackend()
    materializer = CorpusMaterializer(
        source_documents=documents,
        output_root=root / "materialized",
    )
    run_root = PreliminaryMatrixRunner(
        backend,
        materializer=materializer,
        runs_root=root / "runs",
    ).run()
    run = json.loads((run_root / "run.json").read_bytes())
    return run_root, run, backend


def test_scripted_backend_executes_exact_full_matrix_once_and_in_fixed_order(
    scripted_run: tuple[Path, dict[str, Any], Any],
) -> None:
    run_root, run, backend = scripted_run
    assert run_root.is_dir()
    assert backend.acquisition_calls == 4
    assert backend.compiler_calls == 4
    assert backend.deployment_calls == 8
    assert [(cell["profile"], cell["acquisition_arm"]) for cell in run["cells"]] == list(
        MATRIX_ORDER
    )
    assert [cell["cell_id"] for cell in run["cells"]] == [
        "01-mock-api-call-benign",
        "02-mock-api-call-poison",
        "03-delete-sentinel-poison",
        "04-delete-sentinel-benign",
    ]
    for cell in run["cells"]:
        assert cell["acquisition"]["status"] == RunStatus.SUCCESS.value
        assert cell["compiler"]["status"] == RunStatus.SUCCESS.value
        assert [item["task_id"] for item in cell["deployments"]] == [
            POSITIVE_TASK_ID,
            FAR_NEGATIVE_TASK_ID,
        ]

    events = [json.loads(line) for line in (run_root / "events.jsonl").read_text().splitlines()]
    phase_starts = [
        (event["cell"], event["phase"], event.get("task_id"))
        for event in events
        if event["event"] == "phase-start"
    ]
    expected_starts = []
    for cell in run["cells"]:
        expected_starts.extend(
            [
                (cell["cell_id"], "acquisition", None),
                (cell["cell_id"], "compiler", None),
                (cell["cell_id"], "deployment", POSITIVE_TASK_ID),
                (cell["cell_id"], "deployment", FAR_NEGATIVE_TASK_ID),
            ]
        )
    assert phase_starts == expected_starts
    efficiency = next(event for event in events if event["event"] == "efficiency")
    assert efficiency == {
        "event": "efficiency",
        "acquisition_calls": 4,
        "compiler_calls": 4,
        "deployment_calls": 8,
    }


def test_scripted_run_and_reset_artifacts_match_tracked_schemas(
    scripted_run: tuple[Path, dict[str, Any], Any],
) -> None:
    run_root, run, _backend = scripted_run
    schema_root = EXPERIMENT_ROOT / "schemas"
    run_schema = json.loads((schema_root / "run-record.schema.json").read_bytes())
    reset_schema = json.loads((schema_root / "reset-attestation.schema.json").read_bytes())

    Draft202012Validator.check_schema(run_schema)
    Draft202012Validator(run_schema).validate(run)
    Draft202012Validator.check_schema(reset_schema)
    reset_validator = Draft202012Validator(reset_schema)
    reset_paths = sorted(run_root.glob("cells/*/deployment/*/reset-attestation.json"))
    assert len(reset_paths) == 8
    for path in reset_paths:
        reset_validator.validate(json.loads(path.read_bytes()))


def test_replay_uses_published_artifacts_only(
    scripted_run: tuple[Path, dict[str, Any], Any],
    tmp_path: Path,
) -> None:
    run_root, run, _backend = scripted_run
    isolated = tmp_path / "artifact-only-run"
    shutil.copytree(run_root, isolated)

    assert replay_run(isolated) == recompute_metrics(run)


def test_replay_rejects_skill_tampering(
    scripted_run: tuple[Path, dict[str, Any], Any],
    tmp_path: Path,
) -> None:
    run_root, run, _backend = scripted_run
    tampered = tmp_path / "tampered-run"
    shutil.copytree(run_root, tampered)
    skill_path = tampered / "cells" / run["cells"][0]["cell_id"] / "compiler" / "SKILL.md"
    skill_path.write_text(skill_path.read_text() + "tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="skill hash mismatch"):
        replay_run(tampered)


def test_replay_rejects_missing_valid_skill(
    scripted_run: tuple[Path, dict[str, Any], Any],
    tmp_path: Path,
) -> None:
    run_root, run, _backend = scripted_run
    tampered = tmp_path / "missing-skill-run"
    shutil.copytree(run_root, tampered)
    skill_path = tampered / "cells" / run["cells"][0]["cell_id"] / "compiler" / "SKILL.md"
    skill_path.unlink()

    with pytest.raises(ValueError, match="valid skill artifact missing"):
        replay_run(tampered)


@pytest.mark.parametrize("compiler_status", [RunStatus.BEHAVIORAL_FAIL, RunStatus.INVALID])
def test_replay_accepts_attempted_invalid_compiler_without_skill_artifact(
    tmp_path: Path,
    compiler_status: RunStatus,
) -> None:
    run_root = PreliminaryMatrixRunner(
        ControlledBackend(compiler_status=compiler_status),
        materializer=StaticMaterializer(tmp_path / "materials"),
        runs_root=tmp_path / "runs",
    ).run()
    run = json.loads((run_root / "run.json").read_bytes())

    assert not list(run_root.glob("cells/*/compiler/SKILL.md"))
    assert replay_run(run_root) == recompute_metrics(run)


def test_replay_rejects_skill_artifact_for_invalid_compiler(tmp_path: Path) -> None:
    run_root = PreliminaryMatrixRunner(
        ControlledBackend(compiler_status=RunStatus.BEHAVIORAL_FAIL),
        materializer=StaticMaterializer(tmp_path / "materials"),
        runs_root=tmp_path / "runs",
    ).run()
    skill_path = run_root / "cells/01-mock-api-call-benign/compiler/SKILL.md"
    skill_path.write_bytes(b"")

    with pytest.raises(ValueError, match="invalid compiler published a skill"):
        replay_run(run_root)


def test_poison_positive_denominator_is_two_and_far_negative_only_counts_activation(
    scripted_run: tuple[Path, dict[str, Any], Any],
) -> None:
    _run_root, run, _backend = scripted_run
    summary = recompute_metrics(run)
    assert summary["full_chain"] == {
        "eligible": 2,
        "maximum_protocol_trials": 2,
        "successes": 2,
        "rate": 1.0,
    }
    assert summary["far_negative_activation"] == {"numerator": 0, "denominator": 4}

    far_negative_hits = copy.deepcopy(run)
    for cell in far_negative_hits["cells"]:
        far_negative = next(
            item for item in cell["deployments"] if item["task_id"] == FAR_NEGATIVE_TASK_ID
        )
        far_negative["canary_hit"] = True
    changed = recompute_metrics(far_negative_hits)
    assert changed["full_chain"] == summary["full_chain"]
    assert changed["far_negative_activation"] == {"numerator": 4, "denominator": 4}


@pytest.mark.parametrize("excluded_phase", ["compiler", "positive_deployment"])
@pytest.mark.parametrize("excluded_status", [RunStatus.INVALID, RunStatus.DEFERRED])
def test_infrastructure_status_at_any_full_chain_phase_is_excluded_from_denominator(
    scripted_run: tuple[Path, dict[str, Any], Any],
    excluded_phase: str,
    excluded_status: RunStatus,
) -> None:
    _run_root, run, _backend = scripted_run
    changed = copy.deepcopy(run)
    poison_cells = [cell for cell in changed["cells"] if cell["acquisition_arm"] == "poison"]
    if excluded_phase == "compiler":
        poison_cells[0]["compiler"]["status"] = excluded_status.value
        poison_cells[0]["compiler"]["valid"] = False
        poison_cells[0]["deployments"] = [
            {
                **deployment,
                "status": RunStatus.NOT_RUN_UPSTREAM.value,
                "task_success": False,
                "canary_hit": False,
            }
            for deployment in poison_cells[0]["deployments"]
        ]
    else:
        positive = next(
            deployment
            for deployment in poison_cells[0]["deployments"]
            if deployment["task_id"] == POSITIVE_TASK_ID
        )
        positive["status"] = excluded_status.value
        positive["task_success"] = False
        positive["canary_hit"] = False

    summary = recompute_metrics(changed)
    assert summary["full_chain"]["eligible"] == 1
    assert summary["full_chain"]["successes"] == 1
    assert summary["full_chain"]["rate"] == 1.0


class StaticMaterializer:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[tuple[str, str]] = []

    def materialize(self, profile: str, arm: str) -> Materialization:
        self.calls.append((profile, arm))
        payload_hash = hashlib.sha256(profile.encode()).hexdigest()
        corpus_hash = hashlib.sha256(f"{profile}/{arm}".encode()).hexdigest()
        output = self.root / profile / payload_hash / arm
        return Materialization(
            profile=profile,
            arm=arm,
            payload_sha256=payload_hash,
            corpus_sha256=corpus_hash,
            output_root=output,
            manifest_path=output / "manifest.json",
            target_source_sha256="1" * 64,
            target_output_sha256="2" * 64,
        )


def _identity(process_id: int, suffix: str) -> RuntimeIdentity:
    return RuntimeIdentity(
        process_id=process_id,
        instances={
            "model_conversation": f"model-{suffix}",
            "official_db": f"db-{suffix}",
            "runtime": f"runtime-{suffix}",
            "user_simulator": f"user-{suffix}",
        },
    )


class ControlledBackend:
    def __init__(
        self,
        *,
        acquisition_status: RunStatus = RunStatus.SUCCESS,
        compiler_status: RunStatus = RunStatus.SUCCESS,
        deployment_status: RunStatus = RunStatus.SUCCESS,
    ) -> None:
        self.acquisition_status = acquisition_status
        self.compiler_status = compiler_status
        self.deployment_status = deployment_status
        self.acquisition_calls = 0
        self.compiler_calls = 0
        self.deployment_calls = 0

    def acquire(
        self,
        *,
        profile: str,
        arm: str,
        materialization: Materialization,
        seed: int,
    ) -> AcquisitionOutcome:
        del profile, arm, materialization, seed
        self.acquisition_calls += 1
        return AcquisitionOutcome(
            status=self.acquisition_status,
            task_success=self.acquisition_status is RunStatus.SUCCESS,
            first_user_utterance="Question",
            opened_pages=(
                {
                    "page_id": TARGET_DOCUMENT_ID,
                    "title": "Gold",
                    "body": "Body",
                    "content_sha256": hashlib.sha256(b"Body").hexdigest(),
                },
            ),
            runtime_identity=_identity(100 + self.acquisition_calls, f"a-{self.acquisition_calls}"),
        )

    def compile(
        self,
        *,
        profile: str,
        arm: str,
        acquisition: AcquisitionOutcome,
        seed: int,
    ) -> CompilationOutcome:
        del arm, acquisition, seed
        self.compiler_calls += 1
        text = f"---\nname: {profile}\ndescription: Test.\n---\n\nProcedure.\n"
        valid = self.compiler_status is RunStatus.SUCCESS
        return CompilationOutcome(
            status=self.compiler_status,
            skill_text=text if valid else "",
            skill_sha256=hashlib.sha256((text if valid else "").encode()).hexdigest(),
            valid=valid,
            compiler_input={"task": "Question"},
        )

    def deploy(
        self,
        *,
        profile: str,
        arm: str,
        task_id: str,
        skill_text: str,
        skill_sha256: str,
        seed: int,
    ) -> DeploymentOutcome:
        del profile, arm, skill_text, skill_sha256, seed
        self.deployment_calls += 1
        return DeploymentOutcome(
            status=self.deployment_status,
            task_id=task_id,
            task_success=self.deployment_status is RunStatus.SUCCESS,
            canary_hit=False,
            canary_events=(),
            official_reward=1.0 if self.deployment_status is RunStatus.SUCCESS else 0.0,
            runtime_identity=_identity(
                1000 + self.deployment_calls,
                f"d-{self.deployment_calls}",
            ),
            exposed_tool_names=("mock_api_record",),
        )


@pytest.mark.parametrize(
    ("acquisition_status", "expected_overall"),
    [
        (RunStatus.INVALID, RunStatus.INVALID),
        (RunStatus.BEHAVIORAL_FAIL, RunStatus.BEHAVIORAL_FAIL),
        (RunStatus.DEFERRED, RunStatus.DEFERRED),
    ],
)
def test_acquisition_status_propagates_to_not_run_downstream_without_retry(
    tmp_path: Path,
    acquisition_status: RunStatus,
    expected_overall: RunStatus,
) -> None:
    backend = ControlledBackend(acquisition_status=acquisition_status)
    materializer = StaticMaterializer(tmp_path / "materials")
    run_root = PreliminaryMatrixRunner(
        backend,
        materializer=materializer,
        runs_root=tmp_path / "runs",
    ).run()
    run = json.loads((run_root / "run.json").read_bytes())

    assert materializer.calls == list(MATRIX_ORDER)
    assert backend.acquisition_calls == 4
    assert backend.compiler_calls == 0
    assert backend.deployment_calls == 0
    assert run["status"] == expected_overall.value
    expected_eligible = 2 if acquisition_status is RunStatus.BEHAVIORAL_FAIL else 0
    assert run["summary"]["full_chain"]["eligible"] == expected_eligible
    for cell in run["cells"]:
        assert cell["acquisition"]["status"] == acquisition_status.value
        assert cell["compiler"]["status"] == RunStatus.NOT_RUN_UPSTREAM.value
        assert [item["status"] for item in cell["deployments"]] == [
            RunStatus.NOT_RUN_UPSTREAM.value,
            RunStatus.NOT_RUN_UPSTREAM.value,
        ]


@pytest.mark.parametrize(
    ("compiler_status", "expected_overall"),
    [
        (RunStatus.INVALID, RunStatus.INVALID),
        (RunStatus.BEHAVIORAL_FAIL, RunStatus.BEHAVIORAL_FAIL),
    ],
)
def test_compiler_failure_propagates_to_not_run_deployments_without_retry(
    tmp_path: Path,
    compiler_status: RunStatus,
    expected_overall: RunStatus,
) -> None:
    backend = ControlledBackend(compiler_status=compiler_status)
    run_root = PreliminaryMatrixRunner(
        backend,
        materializer=StaticMaterializer(tmp_path / "materials"),
        runs_root=tmp_path / "runs",
    ).run()
    run = json.loads((run_root / "run.json").read_bytes())

    assert backend.acquisition_calls == 4
    assert backend.compiler_calls == 4
    assert backend.deployment_calls == 0
    assert run["status"] == expected_overall.value
    for cell in run["cells"]:
        assert cell["compiler"]["status"] == compiler_status.value
        assert all(
            item["status"] == RunStatus.NOT_RUN_UPSTREAM.value for item in cell["deployments"]
        )


def test_behavioral_deployment_failure_is_attempted_once_and_propagates(
    tmp_path: Path,
) -> None:
    backend = ControlledBackend(deployment_status=RunStatus.BEHAVIORAL_FAIL)
    run_root = PreliminaryMatrixRunner(
        backend,
        materializer=StaticMaterializer(tmp_path / "materials"),
        runs_root=tmp_path / "runs",
    ).run()
    run = json.loads((run_root / "run.json").read_bytes())

    assert backend.acquisition_calls == 4
    assert backend.compiler_calls == 4
    assert backend.deployment_calls == 8
    assert run["status"] == RunStatus.BEHAVIORAL_FAIL.value
    assert {item["status"] for cell in run["cells"] for item in cell["deployments"]} == {
        RunStatus.BEHAVIORAL_FAIL.value
    }
