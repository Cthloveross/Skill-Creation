"""Offline checks for the independently published benign service lifecycle."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from r2sp_tau_knowledge import batch_services as services


class FakeProcess:
    def __init__(self, *, stall_on_terminate: bool = False) -> None:
        self.alive = True
        self.stall_on_terminate = stall_on_terminate
        self.events: list[str] = []

    def poll(self) -> int | None:
        return None if self.alive else 0

    def terminate(self) -> None:
        self.events.append("terminate")
        if not self.stall_on_terminate:
            self.alive = False

    def kill(self) -> None:
        self.events.append("kill")
        self.alive = False

    def wait(self, timeout: float) -> int:
        self.events.append("wait")
        if self.alive:
            raise subprocess.TimeoutExpired("fake-dense", timeout)
        return 0


@pytest.fixture
def service_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("SIF_PATH", "APPTAINER_EXECUTABLE"):
        path = tmp_path / name
        path.touch()
        monkeypatch.setattr(services, name, path)
    model = tmp_path / "dense-model"
    metadata = model / ".cache/huggingface/download/config.json.metadata"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(services.DENSE_MODEL_REVISION + "\n")
    monkeypatch.setattr(services, "DENSE_MODEL_ROOT", model)
    monkeypatch.setattr(services, "SERVICE_LOG_ROOT", tmp_path / "logs")
    monkeypatch.setattr(services, "_port_available", lambda port: port == 18139)
    return metadata


def test_worker_environment_ignores_credentials_and_loading_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    excluded = ("API_KEY", "HTTP_PROXY", "LD_PRELOAD", "PYTHONHOME", "APPTAINERENV_EXTRA")
    for name in excluded:
        monkeypatch.setenv(name, "untrusted-parent-value")
    monkeypatch.setenv("PYTHONPATH", "/untrusted-parent")
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setenv("SLURMD_NODENAME", "allocated-node")
    base = services._base_subprocess_environment()
    worker = services._worker_environment()
    assert not set(excluded) & base.keys()
    assert not set(excluded) & worker.keys()
    assert "PYTHONPATH" not in base
    assert worker["PYTHONPATH"] == str(services.EXPERIMENT_ROOT.parents[2] / "src")
    assert worker["SLURM_JOB_ID"] == "123"
    assert worker["SLURMD_NODENAME"] == "allocated-node"
    assert worker["PYTHONNOUSERSITE"] == "1"


def test_dense_service_uses_cpu_and_closes_its_owned_process(
    service_assets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = FakeProcess()
    launches = []

    def launch(command, **kwargs):
        launches.append((command, kwargs))
        return process

    health = {
        "status": "ok",
        "model_id": services.DENSE_MODEL_ID,
        "revision": services.DENSE_MODEL_REVISION,
        "dimensions": 1024,
        "device": "cpu",
    }
    monkeypatch.setattr(services.subprocess, "Popen", launch)
    monkeypatch.setattr(
        services.urllib.request,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(json.dumps(health).encode()),
    )
    with services.OwnedDenseService() as service:
        assert service.process is process
        assert service.log_path is not None and service.log_path.is_file()
        command, kwargs = launches[0]
        assert "--nv" not in command
        assert command[command.index("python3") + 1 :][:2] == [
            "-m",
            "r2sp_tau_knowledge.dense_service",
        ]
        assert command[-2:] == ["--port", "18139"]
        assert kwargs["env"]["APPTAINERENV_CUDA_VISIBLE_DEVICES"] == ""
        assert kwargs["env"]["APPTAINERENV_HF_HUB_OFFLINE"] == "1"
        log_handle = kwargs["stdout"]
        assert not log_handle.closed
    assert service.process is None
    assert process.events == ["terminate", "wait"]
    assert log_handle.closed


@pytest.mark.parametrize("failure", ["missing-container", "revision", "busy-port"])
def test_dense_asset_failure_never_launches_a_process(
    failure: str, service_assets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if failure == "missing-container":
        services.SIF_PATH.unlink()
    elif failure == "revision":
        service_assets.write_text("wrong-revision\n")
    else:
        monkeypatch.setattr(services, "_port_available", lambda port: False)

    def forbidden_launch(*args, **kwargs):
        raise AssertionError("asset failure must precede process launch")

    monkeypatch.setattr(services.subprocess, "Popen", forbidden_launch)
    with pytest.raises(services.LiveInfrastructureError):
        services.OwnedDenseService().start()


def test_dense_readiness_timeout_cleans_process_and_log(
    service_assets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = FakeProcess(stall_on_terminate=True)
    handles = []

    def launch(*args, **kwargs):
        handles.append(kwargs["stdout"])
        return process

    monkeypatch.setattr(services.subprocess, "Popen", launch)
    service = services.OwnedDenseService()
    with pytest.raises(services.LiveInfrastructureError, match="readiness timed out"):
        service.start(timeout_seconds=0)
    assert process.events == ["terminate", "wait", "kill", "wait"]
    assert service.process is None
    assert handles[0].closed
    service.close()
    assert process.events == ["terminate", "wait", "kill", "wait"]
