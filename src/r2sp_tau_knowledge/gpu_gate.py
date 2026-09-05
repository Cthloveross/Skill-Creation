"""Fail-closed ownership gate for the fixed two-GPU live service."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import EXPERIMENT_ROOT


class GpuGateError(RuntimeError):
    pass


@dataclass(frozen=True)
class GpuObservation:
    free_mib: dict[int, int]
    compute_processes: dict[int, tuple[int, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "free_mib": {str(key): value for key, value in sorted(self.free_mib.items())},
            "compute_processes": {
                str(key): list(value) for key, value in sorted(self.compute_processes.items())
            },
        }


@dataclass(frozen=True)
class GpuGateResult:
    passed: bool
    reason: str | None
    observations: tuple[GpuObservation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "observations": [item.to_dict() for item in self.observations],
        }


def _nvidia_csv(arguments: list[str]) -> list[list[str]]:
    try:
        result = subprocess.run(
            ["nvidia-smi", *arguments, "--format=csv,noheader,nounits"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GpuGateError("nvidia-smi unavailable or failed") from exc
    return [
        [field.strip() for field in line.split(",")]
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def observe_gpus(indices: tuple[int, ...] = (0, 6)) -> GpuObservation:
    gpu_rows = _nvidia_csv(["--query-gpu=index,uuid,memory.free"])
    uuid_to_index: dict[str, int] = {}
    free: dict[int, int] = {}
    for row in gpu_rows:
        if len(row) != 3:
            raise GpuGateError("unexpected GPU query output")
        index = int(row[0])
        if index in indices:
            uuid_to_index[row[1]] = index
            free[index] = int(row[2])
    if set(free) != set(indices):
        raise GpuGateError("one or more required physical GPUs are unavailable")

    processes: dict[int, list[int]] = {index: [] for index in indices}
    try:
        rows = _nvidia_csv(["--query-compute-apps=gpu_uuid,pid"])
    except GpuGateError:
        rows = []
    for row in rows:
        if len(row) != 2 or row[0] not in uuid_to_index:
            continue
        try:
            processes[uuid_to_index[row[0]]].append(int(row[1]))
        except ValueError as exc:
            raise GpuGateError("unexpected compute-process query output") from exc
    return GpuObservation(
        free_mib=free,
        compute_processes={key: tuple(sorted(value)) for key, value in processes.items()},
    )


def check_gpu_gate(
    *,
    indices: tuple[int, ...] = (0, 6),
    minimum_free_mib: int = 23000,
    checks: int = 2,
    interval_seconds: float = 10.0,
    owned_pids: frozenset[int] = frozenset(),
    observer: Callable[[tuple[int, ...]], GpuObservation] = observe_gpus,
    sleeper: Callable[[float], None] = time.sleep,
) -> GpuGateResult:
    if checks < 1 or interval_seconds < 0 or minimum_free_mib <= 0:
        raise ValueError("GPU gate settings are invalid")
    observations: list[GpuObservation] = []
    for check_index in range(checks):
        observation = observer(indices)
        observations.append(observation)
        for index in indices:
            foreign = set(observation.compute_processes[index]) - set(owned_pids)
            if foreign:
                return GpuGateResult(
                    False, f"GPU {index} has foreign compute processes", tuple(observations)
                )
            if observation.free_mib[index] < minimum_free_mib:
                return GpuGateResult(
                    False, f"GPU {index} has insufficient free memory", tuple(observations)
                )
        if check_index + 1 < checks:
            sleeper(interval_seconds)
    return GpuGateResult(True, None, tuple(observations))


class GpuGateLock:
    """Non-blocking local lock held from final gate check through service teardown."""

    def __init__(
        self,
        path: Path = EXPERIMENT_ROOT / "data" / "gpu-0-6.lock",
        *,
        indices: tuple[int, ...] = (0, 6),
    ) -> None:
        if len(indices) != 2 or len(set(indices)) != 2 or any(index < 0 for index in indices):
            raise ValueError("indices must contain two distinct non-negative GPU indices")
        self.path = Path(path)
        self.indices = indices
        self._handle: Any | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise GpuGateError("GPU gate lock is already held") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"owner_pid": os.getpid(), "gpus": list(self.indices)}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        self._handle = handle

    def close(self) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None

    def __enter__(self) -> GpuGateLock:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
