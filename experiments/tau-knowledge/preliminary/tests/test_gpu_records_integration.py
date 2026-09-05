from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest

from r2sp_tau_knowledge.gpu_gate import (
    GpuGateLock,
    GpuGateResult,
    GpuObservation,
    check_gpu_gate,
)
from r2sp_tau_knowledge.records import ImmutableRunWriter


def _load_run_script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_preliminary.py"
    spec = importlib.util.spec_from_file_location("tau_run_preliminary_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gpu_gate_uses_two_observations_and_fake_sleep_without_real_delay() -> None:
    observation = GpuObservation(
        free_mib={0: 24000, 6: 25000},
        compute_processes={0: (), 6: ()},
    )
    observed_indices: list[tuple[int, ...]] = []
    sleeps: list[float] = []

    def observer(indices: tuple[int, ...]) -> GpuObservation:
        observed_indices.append(indices)
        return observation

    result = check_gpu_gate(observer=observer, sleeper=sleeps.append)
    assert result == GpuGateResult(True, None, (observation, observation))
    assert observed_indices == [(0, 6), (0, 6)]
    assert sleeps == [10.0]


@pytest.mark.parametrize(
    ("observation", "reason"),
    [
        (
            GpuObservation(
                free_mib={0: 24000, 6: 25000},
                compute_processes={0: (991,), 6: ()},
            ),
            "GPU 0 has foreign compute processes",
        ),
        (
            GpuObservation(
                free_mib={0: 22999, 6: 25000},
                compute_processes={0: (), 6: ()},
            ),
            "GPU 0 has insufficient free memory",
        ),
    ],
)
def test_gpu_gate_fails_closed_on_first_bad_observation_without_sleep(
    observation: GpuObservation,
    reason: str,
) -> None:
    sleeps: list[float] = []
    result = check_gpu_gate(observer=lambda _indices: observation, sleeper=sleeps.append)
    assert result.passed is False
    assert result.reason == reason
    assert result.observations == (observation,)
    assert sleeps == []


def test_deferred_gpu_preflight_writes_side_evidence_but_no_formal_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_run_script()
    observation = GpuObservation(
        free_mib={0: 22000, 6: 25000},
        compute_processes={0: (), 6: ()},
    )
    gate = GpuGateResult(False, "GPU 0 has insufficient free memory", (observation,))
    monkeypatch.setattr(module, "EXPERIMENT_ROOT", tmp_path / "experiment")
    monkeypatch.setattr(module, "check_gpu_gate", lambda **_kwargs: gate)
    formal_runs = tmp_path / "formal-runs"
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_preliminary.py", "--mode", "live", "--runs-root", str(formal_runs)],
    )

    assert module.main() == 3
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "DEFERRED"
    evidence = Path(output["evidence"])
    assert evidence.is_file()
    assert evidence.parent == tmp_path / "experiment" / "data" / "deferred"
    assert json.loads(evidence.read_bytes())["status"] == "DEFERRED"
    assert not formal_runs.exists()


def test_gpu_lock_records_the_selected_physical_pair(tmp_path: Path) -> None:
    path = tmp_path / "gpu-2-4.lock"
    with GpuGateLock(path, indices=(2, 4)):
        evidence = json.loads(path.read_bytes())
        assert evidence == {"owner_pid": os.getpid(), "gpus": [2, 4]}


def test_run_writer_publishes_once_and_refuses_same_committed_run_id(tmp_path: Path) -> None:
    now = datetime(2026, 9, 4, 12, 30, tzinfo=timezone.utc)
    commitment = {"matrix": "fixed", "seed": 20260904}
    writer = ImmutableRunWriter(commitment, runs_root=tmp_path, now=now)
    writer.write_json("nested/result.json", {"status": "SUCCESS"})
    with pytest.raises(FileExistsError):
        writer.write_json("nested/result.json", {"status": "INVALID"})
    destination = writer.publish()

    assert json.loads((destination / "nested" / "result.json").read_bytes()) == {
        "status": "SUCCESS"
    }
    with pytest.raises(RuntimeError, match="already published"):
        writer.publish()
    with pytest.raises(RuntimeError, match="already published"):
        writer.write_json("late-artifact.json", {"status": "INVALID"})
    with pytest.raises(FileExistsError, match="run already exists"):
        ImmutableRunWriter(commitment, runs_root=tmp_path, now=now)


@pytest.mark.parametrize("unsafe", ["../escape.json", "/absolute.json"])
def test_run_writer_rejects_unsafe_artifact_paths(tmp_path: Path, unsafe: str) -> None:
    writer = ImmutableRunWriter({"safe": True}, runs_root=tmp_path)
    try:
        with pytest.raises(ValueError, match="safe relative path"):
            writer.write_json(unsafe, {})
    finally:
        writer.abort()
