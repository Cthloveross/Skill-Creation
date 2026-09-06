from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from r2sp_common import RunStatus
from r2sp_tau_knowledge import batch
from r2sp_tau_knowledge.batch import (
    BatchError,
    EvaluationSpec,
    GenerationSpec,
    ScriptedBatchBackend,
    load_spec,
    replay_batch,
    run_creation,
    run_evaluation,
)
from r2sp_tau_knowledge.batch_constants import MODEL_ID, MODEL_REVISION, UPSTREAM_COMMIT
from r2sp_tau_knowledge.batch_runtime import DIAGNOSTIC_MODEL_ID, DIAGNOSTIC_MODEL_REVISION
from r2sp_tau_knowledge.records import canonical_json_bytes

PROVENANCE = {"execution_mode": "scripted", "source_bundle_sha256": "a" * 64}


def generation(count: int = 3, *, batch_id: str = "fixture") -> GenerationSpec:
    return GenerationSpec.from_dict(
        {
            "schema_version": "r2sp.tau-generation-spec.v2",
            "batch_id": batch_id,
            "dataset": {"name": "tau-knowledge", "commit": UPSTREAM_COMMIT},
            "model": {
                "id": MODEL_ID,
                "revision": MODEL_REVISION,
                "endpoint": "http://127.0.0.1:18138/v1",
                "max_context_tokens": 65536,
            },
            "items": [
                {
                    "skill_id": f"skill-{index:02d}",
                    "acquisition_task_id": f"task_{(index % 3) + 1:03d}",
                    "corpus": "benign",
                    "seed": 100 + index,
                }
                for index in range(count)
            ],
        }
    )


def evaluation(sources, *, missing: bool = False) -> EvaluationSpec:
    trials = []
    for source_index, _source in enumerate(sources):
        for skill_index in (0, 1) if missing else (0,):
            for task, category in (("task_002", "positive"), ("task_034", "negative")):
                trials.append(
                    {
                        "trial_id": f"trial-{source_index}-{skill_index}-{task}",
                        "source_id": f"source-{source_index}",
                        "skill_id": f"skill-{skill_index:02d}",
                        "task_id": task,
                        "category": category,
                        "seed": 300 + source_index,
                    }
                )
    return EvaluationSpec.from_dict(
        {
            "schema_version": "r2sp.tau-evaluation-spec.v2",
            "batch_id": "utility-fixture",
            "dataset": {"name": "tau-knowledge", "commit": UPSTREAM_COMMIT},
            "model": {
                "id": DIAGNOSTIC_MODEL_ID,
                "revision": DIAGNOSTIC_MODEL_REVISION,
                "endpoint": "http://127.0.0.1:18140/v1",
                "max_context_tokens": 65536,
            },
            "sources": [
                {
                    "source_id": f"source-{index}",
                    "root": str(source.root),
                    "complete_sha256": source.complete_sha256,
                }
                for index, source in enumerate(sources)
            ],
            "trials": trials,
        }
    )


class RecordingBackend(ScriptedBatchBackend):
    def __init__(self, phase: str):
        super().__init__()
        self.phase = phase
        self.calls = []
        self.behavior_failure = None
        self.service_failure = None
        self.interrupt = None

    def _record(self, stage: str, item_id: str):
        self.calls.append((stage, item_id))
        if self.service_failure == (stage, item_id):
            raise RuntimeError("synthetic service outage")
        if self.interrupt == (stage, item_id):
            raise KeyboardInterrupt("synthetic process interruption")

    def acquire(self, *, item):
        assert self.phase == "creation", "evaluation must not acquire"
        self._record("acquisition", item["skill_id"])
        outcome = super().acquire(item=item)
        return outcome

    def compile(self, *, item, acquisition):
        assert self.phase == "creation", "evaluation must not compile"
        self._record("compiler", item["skill_id"])
        outcome = super().compile(item=item, acquisition=acquisition)
        if self.behavior_failure == item["skill_id"]:
            return replace(
                outcome,
                status=RunStatus.BEHAVIORAL_FAIL,
                valid=False,
                skill_text="",
                error="empty_skill",
            )
        return outcome

    def deploy(self, *, trial, skill_text, skill_sha256):
        assert self.phase == "evaluation", "creation must never deploy"
        self._record("deployment", trial["trial_id"])
        outcome = super().deploy(trial=trial, skill_text=skill_text, skill_sha256=skill_sha256)
        if self.behavior_failure == trial["trial_id"]:
            return replace(
                outcome,
                status=RunStatus.BEHAVIORAL_FAIL,
                task_success=False,
                official_reward=0.0,
                error="utility_failed",
            )
        return outcome


def create(tmp_path: Path, count: int = 3, *, backend=None, batch_id="fixture"):
    return run_creation(
        generation(count, batch_id=batch_id),
        backend or RecordingBackend("creation"),
        runs_root=tmp_path,
        provenance=PROVENANCE,
    )


def record(result, phase="generation"):
    return json.loads((result.root / f"{phase}.json").read_text())


def test_creation_handles_ten_items_and_multiple_tasks_without_deployment(tmp_path: Path) -> None:
    backend = RecordingBackend("creation")
    spec = generation(10)
    result = run_creation(spec, backend, runs_root=tmp_path, provenance=PROVENANCE)
    assert result.status == "COMPLETE"
    assert result.complete_sha256
    assert backend.acquisition_calls == backend.compiler_calls == 10
    assert backend.deployment_calls == 0
    assert not (result.root / "trials").exists()
    data = record(result)
    assert [cell["skill_id"] for cell in data["cells"]] == [item["skill_id"] for item in spec.items]
    for name, expected in {
        "planned": 10,
        "ready": 10,
        "attempted": 10,
        "failed": 0,
        "skipped": 0,
        "valid": 10,
        "infra_invalid": 0,
        "interrupted": 0,
        "behavioral_fail": 0,
        "upstream_skipped": 0,
    }.items():
        assert data["summary"][name] == expected
    identities = [cell["acquisition"]["runtime_identity"]["execution_id"] for cell in data["cells"]]
    assert len(set(identities)) == 10
    assert replay_batch(result.root, result.complete_sha256)["summary"] == data["summary"]


def test_evaluation_accepts_multiple_sources_tasks_and_a_different_model(tmp_path: Path) -> None:
    sources = [create(tmp_path / "source-a", 1), create(tmp_path / "source-b", 1)]
    spec = evaluation(sources)
    backend = RecordingBackend("evaluation")
    result = run_evaluation(spec, backend, runs_root=tmp_path / "evaluation", provenance=PROVENANCE)
    assert result.status == "COMPLETE"
    assert backend.deployment_calls == 4
    assert backend.acquisition_calls == backend.compiler_calls == 0
    assert not (result.root / "items").exists()
    data = record(result, "evaluation")
    assert data["summary"]["planned"] == data["summary"]["attempted"] == 4
    assert data["summary"]["asr"] is None
    assert {group["model"] for group in data["summary"]["groups"]} == {DIAGNOSTIC_MODEL_ID}
    assert all(group["utility_success_rate"] is None for group in data["summary"]["groups"])
    assert all(row["reset_passed"] for row in data["trials"])
    assert replay_batch(result.root, result.complete_sha256)["summary"] == data["summary"]


def test_failed_skill_remains_in_creation_and_evaluation_denominators(tmp_path: Path) -> None:
    creator = RecordingBackend("creation")
    creator.behavior_failure = "skill-01"
    source = create(tmp_path / "source", 2, backend=creator)
    assert source.status == "COMPLETE"
    assert record(source)["summary"]["planned"] == 2
    assert record(source)["summary"]["ready"] == 1
    assert record(source)["summary"]["failed"] == 1
    assert not (source.root / "items/skill-01/compiler/SKILL.md").exists()
    spec = evaluation([source], missing=True)
    evaluator = RecordingBackend("evaluation")
    evaluator.behavior_failure = spec.trials[0]["trial_id"]
    result = run_evaluation(spec, evaluator, runs_root=tmp_path / "eval", provenance=PROVENANCE)
    assert result.status == "COMPLETE"
    data = record(result, "evaluation")
    summary = data["summary"]
    assert len(data["trials"]) == summary["planned"] == 4
    assert summary["attempted"] == evaluator.deployment_calls == 2
    assert summary["skipped"] == 2
    assert summary["failed"] == 1
    assert summary["task_successes"] == 1
    assert sum(group["valid"] for group in summary["groups"]) == 2
    assert sum(group["planned"] for group in summary["groups"]) == 4
    assert sum(row["status"] == "NOT_RUN_UPSTREAM" for row in data["trials"]) == 2


def test_complete_selection_is_compilable_even_when_acquisition_utility_fails(
    tmp_path: Path,
) -> None:
    class LowUtility(RecordingBackend):
        def acquire(self, *, item):
            return replace(
                super().acquire(item=item),
                status=RunStatus.BEHAVIORAL_FAIL,
                task_success=False,
                official_reward=0.0,
            )

    backend = LowUtility("creation")
    result = create(tmp_path, 1, backend=backend)
    assert result.status == "COMPLETE"
    assert backend.compiler_calls == 1
    assert record(result)["summary"]["ready"] == 1
    assert record(result)["cells"][0]["acquisition"]["task_success"] is False


def test_service_failure_stops_without_seal_and_resume_never_retries_failed_attempt(
    tmp_path: Path,
) -> None:
    failed = RecordingBackend("creation")
    failed.service_failure = ("acquisition", "skill-01")
    result = create(tmp_path, backend=failed)
    assert result.status == "INVALID"
    assert result.complete_sha256 is None
    assert not (result.root / "generation-complete.json").exists()
    assert failed.calls == [
        ("acquisition", "skill-00"),
        ("compiler", "skill-00"),
        ("acquisition", "skill-01"),
    ]
    resumed = RecordingBackend("creation")
    done = run_creation(
        generation(), resumed, runs_root=tmp_path, provenance=PROVENANCE, resume=result.root
    )
    assert done.status == "COMPLETE"
    assert resumed.calls == [("acquisition", "skill-02"), ("compiler", "skill-02")]
    assert record(done)["summary"]["planned"] == 3
    assert record(done)["summary"]["ready"] == 2
    assert record(done)["cells"][1]["acquisition"]["status"] == "INVALID"


@pytest.mark.parametrize("phase", ["acquisition", "compiler"])
def test_resume_keeps_unknown_inflight_outcome_terminal_without_rerunning(
    tmp_path: Path,
    phase: str,
) -> None:
    backend = RecordingBackend("creation")
    backend.interrupt = (phase, "skill-01")
    with pytest.raises(KeyboardInterrupt):
        create(tmp_path, backend=backend)
    root = next(tmp_path.glob("tau-creation-*"))
    first = (root / "items/skill-00/compiler/SKILL.md").read_bytes()
    assert (root / f"items/skill-01/{phase}/started.json").is_file()
    assert not (root / f"items/skill-01/{phase}/result.json").exists()
    resumed = RecordingBackend("creation")
    done = run_creation(
        generation(), resumed, runs_root=tmp_path, provenance=PROVENANCE, resume=root
    )
    assert done.status == "COMPLETE"
    assert resumed.calls == [("acquisition", "skill-02"), ("compiler", "skill-02")]
    assert (root / "items/skill-00/compiler/SKILL.md").read_bytes() == first
    assert record(done)["cells"][1][phase]["status"] == "INTERRUPTED"


def test_evaluation_resume_does_not_rerun_completed_or_inflight_trial(tmp_path: Path) -> None:
    source = create(tmp_path / "source", 2)
    spec = evaluation([source], missing=True)
    backend = RecordingBackend("evaluation")
    backend.interrupt = ("deployment", spec.trials[1]["trial_id"])
    runs_root = tmp_path / "eval"
    with pytest.raises(KeyboardInterrupt):
        run_evaluation(spec, backend, runs_root=runs_root, provenance=PROVENANCE)
    root = next(runs_root.glob("tau-evaluation-*"))
    resumed = RecordingBackend("evaluation")
    done = run_evaluation(spec, resumed, runs_root=runs_root, provenance=PROVENANCE, resume=root)
    assert done.status == "COMPLETE"
    assert resumed.calls == [("deployment", row["trial_id"]) for row in spec.trials[2:]]
    assert record(done, "evaluation")["trials"][1]["status"] == "INTERRUPTED"
    assert record(done, "evaluation")["summary"]["planned"] == 4


def test_completed_resume_has_no_backend_calls_and_requires_same_spec_and_provenance(
    tmp_path: Path,
) -> None:
    source = create(tmp_path, 1)
    backend = RecordingBackend("creation")
    same = run_creation(
        generation(1), backend, runs_root=tmp_path, provenance=PROVENANCE, resume=source.root
    )
    assert same.complete_sha256 == source.complete_sha256
    assert backend.calls == []
    changed = generation(1).to_dict()
    changed["items"][0]["seed"] += 1
    with pytest.raises(BatchError):
        run_creation(
            GenerationSpec.from_dict(changed),
            backend,
            runs_root=tmp_path,
            provenance=PROVENANCE,
            resume=source.root,
        )
    with pytest.raises(BatchError):
        run_creation(
            generation(1),
            backend,
            runs_root=tmp_path,
            provenance={**PROVENANCE, "source_bundle_sha256": "b" * 64},
            resume=source.root,
        )


@pytest.mark.parametrize("mutation", ["changed-skill", "extra-file", "symlink", "deleted-skill"])
def test_sealed_source_changes_are_rejected_by_replay_and_before_evaluation(
    tmp_path: Path,
    mutation: str,
) -> None:
    source = create(tmp_path / "source", 1)
    skill = source.root / "items/skill-00/compiler/SKILL.md"
    if mutation == "changed-skill":
        skill.write_text(skill.read_text() + "Unexpected change.\n")
    elif mutation == "extra-file":
        (source.root / "extra.txt").write_text("Unexpected file")
    elif mutation == "symlink":
        target = tmp_path / "external.md"
        target.write_bytes(skill.read_bytes())
        skill.unlink()
        skill.symlink_to(target)
    else:
        skill.unlink()
    with pytest.raises(BatchError):
        replay_batch(source.root, source.complete_sha256)
    backend = RecordingBackend("evaluation")
    with pytest.raises(BatchError):
        run_evaluation(
            evaluation([source]), backend, runs_root=tmp_path / "eval", provenance=PROVENANCE
        )
    assert backend.calls == []


def test_completion_hash_and_scripted_live_boundary_are_enforced(tmp_path: Path) -> None:
    source = create(tmp_path / "source", 1)
    with pytest.raises(BatchError):
        replay_batch(source.root, "0" * 64)
    with pytest.raises(BatchError, match="scripted and live"):
        run_evaluation(
            evaluation([source]),
            RecordingBackend("evaluation"),
            runs_root=tmp_path / "eval",
            provenance={**PROVENANCE, "execution_mode": "live"},
        )


@pytest.mark.parametrize(
    "change", ["duplicate-id", "poison", "unknown-task", "negative-seed", "bool-seed"]
)
def test_invalid_generation_rows_are_rejected(change: str) -> None:
    value = generation().to_dict()
    row = value["items"][1]
    if change == "duplicate-id":
        row["skill_id"] = value["items"][0]["skill_id"]
    elif change == "poison":
        row["corpus"] = "poison"
    elif change == "unknown-task":
        row["acquisition_task_id"] = "task_999"
    else:
        row["seed"] = True if change == "bool-seed" else -1
    with pytest.raises(ValueError):
        GenerationSpec.from_dict(value)


def test_duplicate_evaluation_trial_and_source_ids_are_rejected(tmp_path: Path) -> None:
    source = create(tmp_path, 1)
    value = evaluation([source]).to_dict()
    value["trials"].append(dict(value["trials"][0]))
    with pytest.raises(ValueError):
        EvaluationSpec.from_dict(value)
    value = evaluation([source]).to_dict()
    value["sources"].append(dict(value["sources"][0]))
    with pytest.raises(ValueError):
        EvaluationSpec.from_dict(value)


def test_specs_are_immutable_and_relative_source_roots_resolve_from_spec_file(
    tmp_path: Path,
) -> None:
    source = create(tmp_path / "sources", 1)
    value = evaluation([source]).to_dict()
    value["sources"][0]["root"] = str(source.root.relative_to(tmp_path))
    path = tmp_path / "evaluation.yaml"
    path.write_text(yaml.safe_dump(value))
    spec = load_spec(path, "evaluation")
    assert spec.sources[0]["root"] == str(source.root)
    changed = spec.to_dict()
    changed["model"]["id"] = "unapproved"
    assert spec.model["id"] == DIAGNOSTIC_MODEL_ID


def test_persisted_source_bundle_is_bound_to_declared_hash(tmp_path: Path) -> None:
    bundle = tmp_path / "source.tar"
    bundle.write_bytes(b"opaque test bundle bytes")
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    result = run_creation(
        generation(1),
        RecordingBackend("creation"),
        runs_root=tmp_path / "runs",
        provenance={
            **PROVENANCE,
            "source_bundle_path": str(bundle),
            "source_bundle_sha256": digest,
        },
    )
    assert (result.root / "source/source-bundle.tar").read_bytes() == bundle.read_bytes()
    assert replay_batch(result.root, result.complete_sha256)["status"] == "COMPLETE"


def test_resume_archives_uncommitted_compiler_outputs_without_accepting_or_retrying(
    tmp_path: Path,
) -> None:
    backend = RecordingBackend("creation")
    backend.interrupt = ("compiler", "skill-01")
    with pytest.raises(KeyboardInterrupt):
        create(tmp_path, backend=backend)
    root = next(tmp_path.glob("tau-creation-*"))
    phase = root / "items/skill-01/compiler"
    leftovers = {
        "input.json": b'{"partial":',
        "SKILL.md": b"partial skill",
        "result.json": b'{"status":"SUCCESS"}',
        ".pending-output": b"partial bytes",
    }
    for name, raw in leftovers.items():
        (phase / name).write_bytes(raw)
    resumed = RecordingBackend("creation")
    result = run_creation(
        generation(), resumed, runs_root=tmp_path, provenance=PROVENANCE, resume=root
    )
    assert result.status == "COMPLETE"
    assert resumed.calls == [("acquisition", "skill-02"), ("compiler", "skill-02")]
    assert record(result)["cells"][1]["compiler"]["status"] == "INTERRUPTED"
    assert not (phase / "SKILL.md").exists()
    archived = list((root / "interrupted-artifacts").glob("*/items/skill-01/compiler"))
    assert len(archived) == 1
    assert {path.name: path.read_bytes() for path in archived[0].iterdir()} == leftovers
    assert replay_batch(root, result.complete_sha256)["status"] == "COMPLETE"


@pytest.mark.parametrize("mutation", ["committed-skill", "unrelated-extra"])
def test_partial_resume_rejects_changes_outside_the_uncommitted_phase(
    tmp_path: Path,
    mutation: str,
) -> None:
    backend = RecordingBackend("creation")
    backend.interrupt = ("compiler", "skill-01")
    with pytest.raises(KeyboardInterrupt):
        create(tmp_path, backend=backend)
    root = next(tmp_path.glob("tau-creation-*"))
    target = (
        root / "items/skill-00/compiler/SKILL.md"
        if mutation == "committed-skill"
        else root / "unrelated-extra.json"
    )
    target.write_text("Unexpected mutation")
    resumed = RecordingBackend("creation")
    with pytest.raises(BatchError):
        run_creation(generation(), resumed, runs_root=tmp_path, provenance=PROVENANCE, resume=root)
    assert resumed.calls == []


def _rebind_file_inventory_for_semantic_test(root: Path) -> None:
    """Keep byte hashes consistent so the test reaches semantic validation."""

    def inventory(excluded):
        return [
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size_bytes": path.stat().st_size,
            }
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.relative_to(root).as_posix() not in excluded
        ]

    checkpoint = root / "checkpoint-index.json"
    value = json.loads(checkpoint.read_text())
    value["artifacts"] = inventory({"checkpoint-index.json", "evaluation-complete.json"})
    checkpoint.write_bytes(canonical_json_bytes(value))
    complete = root / "evaluation-complete.json"
    value = json.loads(complete.read_text())
    value["artifacts"] = inventory({"evaluation-complete.json"})
    complete.write_bytes(canonical_json_bytes(value))


@pytest.mark.parametrize("mutation", ["trajectory-task", "reset-evidence"])
def test_replay_checks_semantics_even_when_file_inventory_hashes_agree(
    tmp_path: Path,
    mutation: str,
) -> None:
    source = create(tmp_path / "source", 1)
    spec = evaluation([source])
    result = run_evaluation(
        spec, RecordingBackend("evaluation"), runs_root=tmp_path / "eval", provenance=PROVENANCE
    )
    phase = result.root / "trials" / spec.trials[0]["trial_id"] / "deployment"
    if mutation == "trajectory-task":
        path = phase / "official-trajectory.json"
        value = json.loads(path.read_text())
        value["task_id"] = "task_034"
    else:
        path = phase / "reset-attestation.json"
        value = json.loads(path.read_text())
        value["evidence"]["loaded_skill_hash"] = "0" * 64
    path.write_bytes(canonical_json_bytes(value))
    _rebind_file_inventory_for_semantic_test(result.root)
    with pytest.raises(BatchError):
        replay_batch(result.root)


def test_resume_recovers_started_file_published_before_checkpoint_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write = batch._atomic

    def crash_after_started(path, value, **kwargs):
        write(path, value, **kwargs)
        if str(path).endswith("items/skill-01/acquisition/started.json"):
            raise KeyboardInterrupt("crash between started publication and checkpoint")

    monkeypatch.setattr(batch, "_atomic", crash_after_started)
    with pytest.raises(KeyboardInterrupt):
        create(tmp_path)
    monkeypatch.setattr(batch, "_atomic", write)
    root = next(tmp_path.glob("tau-creation-*"))
    resumed = RecordingBackend("creation")
    result = run_creation(
        generation(), resumed, runs_root=tmp_path, provenance=PROVENANCE, resume=root
    )
    assert result.status == "COMPLETE"
    assert resumed.calls == [("acquisition", "skill-02"), ("compiler", "skill-02")]
    assert record(result)["cells"][1]["acquisition"]["status"] == "INTERRUPTED"


def test_resume_recovers_skip_result_published_before_checkpoint_without_running_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class IncompleteSelection(RecordingBackend):
        def acquire(self, *, item):
            outcome = super().acquire(item=item)
            return (
                replace(
                    outcome,
                    status=RunStatus.BEHAVIORAL_FAIL,
                    opened_pages=(),
                    selection_complete=False,
                )
                if item["skill_id"] == "skill-01"
                else outcome
            )

    write = batch._atomic

    def crash_after_skip(path, value, **kwargs):
        write(path, value, **kwargs)
        if str(path).endswith("items/skill-01/compiler/result.json"):
            assert value["status"] == "NOT_RUN_UPSTREAM"
            raise KeyboardInterrupt("crash between skip result and checkpoint")

    monkeypatch.setattr(batch, "_atomic", crash_after_skip)
    with pytest.raises(KeyboardInterrupt):
        create(tmp_path, backend=IncompleteSelection("creation"))
    monkeypatch.setattr(batch, "_atomic", write)
    root = next(tmp_path.glob("tau-creation-*"))
    resumed = RecordingBackend("creation")
    result = run_creation(
        generation(), resumed, runs_root=tmp_path, provenance=PROVENANCE, resume=root
    )
    assert result.status == "COMPLETE"
    assert resumed.calls == [("acquisition", "skill-02"), ("compiler", "skill-02")]
    assert record(result)["cells"][1]["compiler"]["status"] == "NOT_RUN_UPSTREAM"
    assert record(result)["summary"]["planned"] == 3
    assert record(result)["summary"]["ready"] == 2
