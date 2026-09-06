"""Isolated worker environments and an owned CPU embedding service for benign batches."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .batch_constants import (
    DENSE_MODEL_ID,
    DENSE_MODEL_REVISION,
    EXPERIMENT_ROOT,
    UPSTREAM_ROOT,
)

PINNED_PYTHON = Path(
    os.environ.get("R2SP_TAU_PYTHON", str(UPSTREAM_ROOT / ".venv" / "bin" / "python"))
)

RUNTIME_ROOT = Path(os.environ.get("R2SP_TAU_RUNTIME_ROOT", "/usr/xtmp/tc442/skill-creation"))

APPTAINER_EXECUTABLE = Path(
    os.environ.get(
        "R2SP_TAU_APPTAINER_EXECUTABLE",
        "/bin/apptainer",
    )
)

SIF_PATH = Path(
    os.environ.get(
        "R2SP_TAU_SIF_PATH",
        str(RUNTIME_ROOT / "images" / "vllm-qwen38-flash-next-amd64.sif"),
    )
)

DENSE_MODEL_ROOT = Path(
    os.environ.get(
        "R2SP_TAU_DENSE_MODEL_ROOT",
        str(RUNTIME_ROOT / "models" / "Qwen3-Embedding-0.6B"),
    )
)

SERVICE_LOG_ROOT = Path(
    os.environ.get("R2SP_TAU_SERVICE_LOG_ROOT", str(RUNTIME_ROOT / "logs" / "vllm"))
)

DENSE_ENDPOINT = "http://127.0.0.1:18139"

_SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin"


def _base_subprocess_environment() -> dict[str, str]:
    """Return a deterministic environment with no inherited credentials or hooks."""

    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_PROXY": "127.0.0.1,localhost",
        "PATH": _SYSTEM_PATH,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "TZ": "UTC",
        "no_proxy": "127.0.0.1,localhost",
    }


def _worker_environment() -> dict[str, str]:
    environment = _base_subprocess_environment()
    environment["PYTHONPATH"] = str(EXPERIMENT_ROOT.parents[2] / "src")
    environment["R2SP_TAU_DENSE_ENDPOINT"] = os.environ.get(
        "R2SP_TAU_DENSE_ENDPOINT", DENSE_ENDPOINT
    )
    environment["R2SP_TAU_DENSE_CACHE_ROOT"] = os.environ.get(
        "R2SP_TAU_DENSE_CACHE_ROOT", str(RUNTIME_ROOT / "cache" / "dense")
    )
    for name in ("SLURM_JOB_ID", "SLURMD_NODENAME"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    return environment


class LiveInfrastructureError(RuntimeError):
    pass


def _port_available(port: int = 18138) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            handle.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


class OwnedDenseService:
    """Run the 0.6B embedding model on CPU without exposing it off-node."""

    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None
        self._log_handle: Any | None = None
        self.log_path: Path | None = None

    def start(self, *, timeout_seconds: float = 900.0) -> None:
        if not SIF_PATH.is_file() or not APPTAINER_EXECUTABLE.is_file():
            raise LiveInfrastructureError("dense service container is unavailable")
        if not DENSE_MODEL_ROOT.is_dir():
            raise LiveInfrastructureError("pinned dense model snapshot is unavailable")
        metadata = DENSE_MODEL_ROOT / ".cache" / "huggingface" / "download" / "config.json.metadata"
        try:
            revision = metadata.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError) as exc:
            raise LiveInfrastructureError("dense model revision metadata is unavailable") from exc
        if revision != DENSE_MODEL_REVISION:
            raise LiveInfrastructureError("dense model revision mismatch")
        if not _port_available(18139):
            raise LiveInfrastructureError("port 18139 is already in use")
        SERVICE_LOG_ROOT.mkdir(parents=True, exist_ok=True)
        self.log_path = SERVICE_LOG_ROOT / f"dense-cpu-{uuid.uuid4().hex}.log"
        self._log_handle = self.log_path.open("xb")
        environment = _base_subprocess_environment()
        environment.update(
            {
                "APPTAINERENV_CUDA_VISIBLE_DEVICES": "",
                "APPTAINERENV_HF_HUB_OFFLINE": "1",
                "APPTAINERENV_TRANSFORMERS_OFFLINE": "1",
                "APPTAINERENV_TOKENIZERS_PARALLELISM": "false",
                "APPTAINERENV_PYTHONPATH": str(EXPERIMENT_ROOT.parents[2] / "src"),
                "APPTAINERENV_R2SP_DENSE_CPU_THREADS": os.environ.get(
                    "R2SP_DENSE_CPU_THREADS", "24"
                ),
            }
        )
        command = [
            str(APPTAINER_EXECUTABLE),
            "exec",
            "--cleanenv",
            "--bind",
            "/usr/xtmp:/usr/xtmp",
            "--bind",
            f"{EXPERIMENT_ROOT.parents[2]}:{EXPERIMENT_ROOT.parents[2]}:ro",
            str(SIF_PATH),
            "python3",
            "-m",
            "r2sp_tau_knowledge.dense_service",
            "--model-root",
            str(DENSE_MODEL_ROOT),
            "--port",
            "18139",
        ]
        try:
            self.process = subprocess.Popen(
                command,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                env=environment,
            )
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise LiveInfrastructureError(
                        f"dense service exited during startup; log={self.log_path}"
                    )
                try:
                    with urllib.request.urlopen(DENSE_ENDPOINT + "/health", timeout=5) as response:
                        health = json.loads(response.read())
                    if health == {
                        "status": "ok",
                        "model_id": DENSE_MODEL_ID,
                        "revision": DENSE_MODEL_REVISION,
                        "dimensions": 1024,
                        "device": "cpu",
                    }:
                        return
                except (OSError, urllib.error.URLError, json.JSONDecodeError):
                    pass
                time.sleep(2)
            raise LiveInfrastructureError(f"dense service readiness timed out; log={self.log_path}")
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=30)
        self.process = None
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def __enter__(self) -> OwnedDenseService:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
