"""GPU0 gate and owned service lifecycle for the full-document experiment."""

from __future__ import annotations

import csv
import fcntl
import hashlib
import io
import json
import math
import os
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .full_doc_spec import ExperimentSpec

DEFAULT_VLLM_EXECUTABLE = Path(
    "experiments/tau-knowledge/preliminary/data/model-service-cpython-3.12.14/.venv/bin/vllm"
)
DEFAULT_HF_HOME = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
MINIMUM_H200_TOTAL_MEMORY_MIB = 140_000
EMBEDDING_ONLY_GPU_OVERHEAD_MIB = 2_048


class FullDocInfrastructureError(RuntimeError):
    """A pinned asset, GPU observation, lock, or owned service was invalid."""


GpuQuery = Callable[[Sequence[str]], str]
Sleep = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class FullDocAssetPaths:
    vllm: Path
    hf_home: Path

    @classmethod
    def defaults(cls, repository_root: Path) -> FullDocAssetPaths:
        return cls(
            vllm=(repository_root / DEFAULT_VLLM_EXECUTABLE).resolve(),
            hf_home=DEFAULT_HF_HOME.resolve(),
        )

    def snapshot(self, model: str, revision: str) -> Path:
        owner, name = model.split("/", 1)
        return self.hf_home / "hub" / f"models--{owner}--{name}" / "snapshots" / revision

    @property
    def python(self) -> Path:
        return self.vllm.parent / "python"

    def to_dict(self) -> dict[str, str]:
        return {
            "vllm": str(self.vllm),
            "vllm_sha256": _sha256_file(self.vllm) if self.vllm.is_file() else "",
            "python": str(self.python),
            "hf_home": str(self.hf_home),
        }


@dataclass(frozen=True, slots=True)
class FullDocGpuObservation:
    index: int
    uuid: str
    name: str
    memory_total_mib: int
    memory_free_mib: int
    compute_pids: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "uuid": self.uuid,
            "name": self.name,
            "memory_total_mib": self.memory_total_mib,
            "memory_free_mib": self.memory_free_mib,
            "compute_pids": list(self.compute_pids),
        }


@dataclass(frozen=True, slots=True)
class FullDocGpuPreflight:
    ready: bool
    reason: str | None
    observations: tuple[FullDocGpuObservation, ...]

    @property
    def final(self) -> FullDocGpuObservation | None:
        return self.observations[-1] if self.observations else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "reason": self.reason,
            "required_stable_checks": 3,
            "required_interval_seconds": 10,
            "observations": [item.to_dict() for item in self.observations],
        }


@dataclass(frozen=True, slots=True)
class FullDocPreflight:
    ready: bool
    assets_ready: bool
    assets: tuple[dict[str, Any], ...]
    gpu: FullDocGpuPreflight
    ports: dict[str, bool]
    experiment_lock_available: bool
    ownership_recovery: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "assets_ready": self.assets_ready,
            "assets": list(self.assets),
            "gpu": self.gpu.to_dict(),
            "ports": dict(self.ports),
            "experiment_lock_available": self.experiment_lock_available,
            "ownership_recovery": dict(self.ownership_recovery),
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _default_gpu_query(arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        ["nvidia-smi", *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout


def _csv_rows(value: str, *, fields: int) -> list[list[str]]:
    rows = [
        [column.strip() for column in row]
        for row in csv.reader(io.StringIO(value), skipinitialspace=True)
        if row and any(column.strip() for column in row)
    ]
    if any(len(row) != fields for row in rows):
        raise FullDocInfrastructureError("nvidia-smi returned malformed CSV")
    return rows


def inspect_gpu0(
    expected_uuid: str,
    *,
    query: GpuQuery = _default_gpu_query,
) -> FullDocGpuObservation:
    try:
        inventory = query(
            (
                "--query-gpu=index,uuid,name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            )
        )
        processes = query(
            (
                "--query-compute-apps=gpu_uuid,pid",
                "--format=csv,noheader,nounits",
            )
        )
        rows = _csv_rows(inventory, fields=5)
        process_rows = _csv_rows(processes, fields=2)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise FullDocInfrastructureError("nvidia-smi query failed") from exc
    matches = [row for row in rows if row[0] == "0" and row[1] == expected_uuid]
    if len(matches) != 1:
        raise FullDocInfrastructureError("GPU0 does not match the pinned UUID")
    row = matches[0]
    try:
        total = int(row[3])
        free = int(row[4])
        pids = tuple(
            sorted(int(pid) for gpu_uuid, pid in process_rows if gpu_uuid == expected_uuid)
        )
    except ValueError as exc:
        raise FullDocInfrastructureError("nvidia-smi returned non-integer values") from exc
    if len(pids) != len(set(pids)):
        raise FullDocInfrastructureError("nvidia-smi returned duplicate compute PIDs")
    return FullDocGpuObservation(0, row[1], row[2], total, free, pids)


def _stable_gpu0_preflight(
    spec: ExperimentSpec,
    *,
    minimum_free_memory_mib: Callable[[FullDocGpuObservation], int],
    insufficient_memory_reason: str,
    query: GpuQuery = _default_gpu_query,
    sleep: Sleep = time.sleep,
) -> FullDocGpuPreflight:
    observations: list[FullDocGpuObservation] = []
    try:
        for index in range(spec.services.stable_preflight_checks):
            observations.append(inspect_gpu0(spec.services.gpu_uuid, query=query))
            if index + 1 < spec.services.stable_preflight_checks:
                sleep(float(spec.services.stable_preflight_interval_seconds))
    except FullDocInfrastructureError as exc:
        return FullDocGpuPreflight(False, str(exc), tuple(observations))
    if len(observations) != 3:
        return FullDocGpuPreflight(
            False,
            "the gate did not collect exactly three checks",
            tuple(observations),
        )
    first = observations[0]
    if any(item.uuid != first.uuid or item.index != 0 for item in observations):
        return FullDocGpuPreflight(
            False,
            "GPU identity changed during preflight",
            tuple(observations),
        )
    if "H200" not in first.name.upper() or first.memory_total_mib < MINIMUM_H200_TOTAL_MEMORY_MIB:
        return FullDocGpuPreflight(False, "GPU0 is not the required H200", tuple(observations))
    if any(item.memory_free_mib < minimum_free_memory_mib(item) for item in observations):
        return FullDocGpuPreflight(
            False,
            insufficient_memory_reason,
            tuple(observations),
        )
    if any(item.compute_pids != first.compute_pids for item in observations):
        return FullDocGpuPreflight(
            False,
            "the external GPU0 PID set was not stable",
            tuple(observations),
        )
    return FullDocGpuPreflight(True, None, tuple(observations))


def stable_gpu0_preflight(
    spec: ExperimentSpec,
    *,
    query: GpuQuery = _default_gpu_query,
    sleep: Sleep = time.sleep,
) -> FullDocGpuPreflight:
    """Run the original local-LLM GPU gate with its fixed memory threshold."""

    return _stable_gpu0_preflight(
        spec,
        minimum_free_memory_mib=lambda _observation: spec.services.minimum_free_memory_mib,
        insufficient_memory_reason="GPU0 free memory is below the fixed threshold",
        query=query,
        sleep=sleep,
    )


def api_embedding_minimum_free_memory_mib(
    spec: ExperimentSpec,
    memory_total_mib: int,
) -> int:
    """Return the isolated embedding service reservation plus its fixed headroom."""

    if (
        isinstance(memory_total_mib, bool)
        or not isinstance(memory_total_mib, int)
        or memory_total_mib <= 0
    ):
        raise ValueError("memory_total_mib must be a positive integer")
    utilization = spec.services.embedding_gpu_memory_utilization
    if not 0 < utilization < 1:
        raise ValueError("embedding GPU memory utilization must be in (0, 1)")
    return math.ceil(memory_total_mib * utilization) + EMBEDDING_ONLY_GPU_OVERHEAD_MIB


def stable_api_embedding_gpu0_preflight(
    spec: ExperimentSpec,
    *,
    query: GpuQuery = _default_gpu_query,
    sleep: Sleep = time.sleep,
) -> FullDocGpuPreflight:
    """Gate a remote-LLM run on only the local embedding service footprint."""

    return _stable_gpu0_preflight(
        spec,
        minimum_free_memory_mib=lambda observation: api_embedding_minimum_free_memory_mib(
            spec, observation.memory_total_mib
        ),
        insufficient_memory_reason=(
            "GPU0 free memory is below the embedding-only dynamic threshold"
        ),
        query=query,
        sleep=sleep,
    )


def _regular_executable(path: Path) -> bool:
    return path.is_file() and not path.is_symlink() and os.access(path, os.X_OK)


def check_full_doc_assets(
    spec: ExperimentSpec,
    paths: FullDocAssetPaths,
    *,
    require_embedding: bool,
    require_llm: bool = True,
) -> tuple[dict[str, Any], ...]:
    checks: list[dict[str, Any]] = []
    try:
        spec.validate_payload_files()
        spec.validate_prompt_files()
        spec.validate_source_populations()
    except (OSError, ValueError) as exc:
        checks.append({"name": "experiment_spec", "ok": False, "detail": str(exc)})
    else:
        checks.append({"name": "experiment_spec", "ok": True, "detail": spec.config_sha256})
    checks.append(
        {
            "name": "tau_python",
            "ok": os.access(spec.paths.source_upstream_root / ".venv/bin/python", os.X_OK),
            "detail": str(spec.paths.source_upstream_root / ".venv/bin/python"),
        }
    )
    # The executable is a small uv-generated script and may itself be a regular file;
    # its sibling interpreter is intentionally a symlink into the pinned environment.
    checks.append(
        {
            "name": "vllm_executable",
            "ok": _regular_executable(paths.vllm),
            "detail": str(paths.vllm),
        }
    )
    checks.append(
        {
            "name": "dense_builder_python",
            "ok": (not require_embedding)
            or (paths.python.is_file() and os.access(paths.python, os.X_OK)),
            "detail": str(paths.python),
        }
    )
    snapshots: list[tuple[str, str, str]] = []
    if require_llm:
        snapshots.append(("llm_snapshot", spec.model.model, spec.model.revision))
    if require_embedding:
        snapshots.append(("embedding_snapshot", spec.embedding.model, spec.embedding.revision))
    for label, model, revision in snapshots:
        snapshot = paths.snapshot(model, revision)
        resolved_ok = False
        detail = str(snapshot)
        try:
            resolved = snapshot.resolve(strict=True)
            resolved_ok = (
                resolved.name == revision
                and (resolved / "config.json").is_file()
                and (resolved / "tokenizer_config.json").is_file()
            )
            detail = str(resolved)
        except OSError:
            pass
        checks.append({"name": label, "ok": resolved_ok, "detail": detail})
    return tuple(checks)


def port_is_free(endpoint: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(endpoint)
    assert parsed.hostname == "127.0.0.1" and parsed.port is not None
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            handle.bind((parsed.hostname, parsed.port))
        except OSError:
            return False
    return True


def lock_is_available(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return True


def _memory_fraction(value: float) -> str:
    if not 0 < value < 1:
        raise ValueError("GPU memory utilization must be in (0, 1)")
    return str(value)


def full_doc_llm_argv(spec: ExperimentSpec, paths: FullDocAssetPaths) -> tuple[str, ...]:
    """Build the LLM command only from the versioned full-document spec."""

    if spec.model.model == "zai-org/GLM-4.7-Flash":
        tool_parser = "glm47"
        reasoning_parser = "glm45"
        template_kwargs = '{"enable_thinking":true,"clear_thinking":false}'
    else:
        tool_parser = "qwen3_coder"
        reasoning_parser = "qwen3"
        template_kwargs = '{"enable_thinking":true,"preserve_thinking":false}'
    return (
        str(paths.vllm),
        "serve",
        str(paths.snapshot(spec.model.model, spec.model.revision)),
        "--served-model-name",
        spec.model.model,
        "--host",
        "127.0.0.1",
        "--port",
        str(spec.services.llm_endpoint.rsplit(":", 1)[1].split("/", 1)[0]),
        "--dtype",
        spec.model.dtype,
        "--max-model-len",
        str(spec.model.max_model_len),
        "--tensor-parallel-size",
        "1",
        "--pipeline-parallel-size",
        "1",
        "--gpu-memory-utilization",
        _memory_fraction(spec.services.llm_gpu_memory_utilization),
        "--max-num-seqs",
        "1",
        "--no-enable-prefix-caching",
        "--language-model-only",
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        tool_parser,
        "--reasoning-parser",
        reasoning_parser,
        "--generation-config",
        "vllm",
        "--enable-chunked-prefill",
        "--max-num-batched-tokens",
        "8192",
        "--default-chat-template-kwargs",
        template_kwargs,
    )


def full_doc_embedding_argv(spec: ExperimentSpec, paths: FullDocAssetPaths) -> tuple[str, ...]:
    """Build the embedding command only from the full-document spec."""

    return (
        str(paths.vllm),
        "serve",
        str(paths.snapshot(spec.embedding.model, spec.embedding.revision)),
        "--served-model-name",
        spec.embedding.model,
        "--runner",
        "pooling",
        "--pooler-config",
        '{"enable_chunked_processing":false,"pooling_type":"LAST","use_activation":true}',
        "--host",
        "127.0.0.1",
        "--port",
        str(spec.services.embedding_endpoint.rsplit(":", 1)[1].split("/", 1)[0]),
        "--dtype",
        spec.model.dtype,
        "--max-model-len",
        str(spec.embedding.max_length),
        "--tensor-parallel-size",
        "1",
        "--pipeline-parallel-size",
        "1",
        "--gpu-memory-utilization",
        _memory_fraction(spec.services.embedding_gpu_memory_utilization),
        "--max-num-seqs",
        "32",
    )


def _service_environment(paths: FullDocAssetPaths, gpu_uuid: str) -> dict[str, str]:
    service_path = f"{paths.vllm.parent.resolve()}:/usr/local/cuda/bin:/usr/local/bin:/usr/bin:/bin"
    return {
        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
        "CUDA_VISIBLE_DEVICES": gpu_uuid,
        "DO_NOT_TRACK": "1",
        "HF_HOME": str(paths.hf_home),
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HUB_OFFLINE": "1",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_PROXY": "127.0.0.1,localhost",
        "PATH": service_path,
        "PYTHONNOUSERSITE": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "TRANSFORMERS_OFFLINE": "1",
        "TZ": "UTC",
        "no_proxy": "127.0.0.1,localhost",
    }


def _argv_sha256(argv: Sequence[str]) -> str:
    encoded = json.dumps(list(argv), separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _process_identity(pid: int) -> dict[str, Any] | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        end = stat.rfind(")")
        fields = stat[end + 2 :].split()
        start_ticks = int(fields[19])
        process_group = int(fields[2])
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, ValueError, IndexError):
        return None
    if not cmdline:
        return None
    return {
        "pid": pid,
        "start_ticks": start_ticks,
        "process_group": process_group,
        "cmdline_sha256": hashlib.sha256(cmdline).hexdigest(),
    }


def _identity_matches(observed: dict[str, Any] | None, expected: Any) -> bool:
    return isinstance(expected, dict) and observed == expected


def _group_members(process_group: int) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for path in Path("/proc").glob("[0-9]*"):
        identity = _process_identity(int(path.name))
        if identity is not None and identity["process_group"] == process_group:
            result.append(identity)
    return tuple(sorted(result, key=lambda item: item["pid"]))


def _atomic_manifest(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name and Path(temporary_name).exists():
            Path(temporary_name).unlink()


def _service_contract(
    spec: ExperimentSpec,
    paths: FullDocAssetPaths,
    name: str,
) -> dict[str, Any]:
    if name == "llm":
        argv = full_doc_llm_argv(spec, paths)
        endpoint = spec.services.llm_endpoint
        model = spec.model.model
        revision = spec.model.revision
    elif name == "embedding":
        argv = full_doc_embedding_argv(spec, paths)
        endpoint = spec.services.embedding_endpoint
        model = spec.embedding.model
        revision = spec.embedding.revision
    else:
        raise ValueError("unknown service name")
    return {
        "schema_version": "tau.full-doc-owned-service.v1",
        "experiment_config_sha256": spec.config_sha256,
        "service": name,
        "gpu_uuid": spec.services.gpu_uuid,
        "endpoint": endpoint,
        "model": model,
        "revision": revision,
        "planned_argv_sha256": _argv_sha256(argv),
    }


def _ownership_path(spec: ExperimentSpec, name: str) -> Path:
    return spec.paths.data_root / "owned-services" / f"{name}.json"


def recover_owned_service(
    spec: ExperimentSpec,
    paths: FullDocAssetPaths,
    name: str,
) -> str:
    """Clean only an orphan whose complete durable process identity still matches."""

    path = _ownership_path(spec, name)
    if not path.exists():
        return "ABSENT"
    try:
        manifest = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "UNSAFE_MANIFEST"
    contract = _service_contract(spec, paths, name)
    if not isinstance(manifest, dict) or any(
        manifest.get(key) != value for key, value in contract.items()
    ):
        return "UNSAFE_MANIFEST"
    expected_owner = manifest.get("owner")
    if not isinstance(expected_owner, dict):
        return "UNSAFE_MANIFEST"
    owner_pid = expected_owner.get("pid")
    if isinstance(owner_pid, bool) or not isinstance(owner_pid, int):
        return "UNSAFE_MANIFEST"
    owner = _process_identity(owner_pid)
    if _identity_matches(owner, expected_owner):
        return "ACTIVE_OWNER"
    group = manifest.get("process_group")
    recorded_members = manifest.get("group_members")
    if isinstance(group, bool) or not isinstance(group, int) or group <= 1:
        return "UNSAFE_MANIFEST"
    if not isinstance(recorded_members, list):
        return "UNSAFE_MANIFEST"
    service_process = manifest.get("service_process")
    if (
        not isinstance(service_process, dict)
        or service_process.get("pid") != group
        or service_process.get("process_group") != group
    ):
        return "UNSAFE_MANIFEST"
    live_members = _group_members(group)
    if not live_members:
        path.unlink()
        return "STALE_REMOVED"
    recorded_by_pid = {item.get("pid"): item for item in recorded_members if isinstance(item, dict)}
    if len(recorded_by_pid) != len(recorded_members) or any(
        recorded_by_pid.get(item["pid"]) != item for item in live_members
    ):
        return "UNSAFE_MANIFEST"
    try:
        os.killpg(group, signal.SIGTERM)
    except ProcessLookupError:
        path.unlink()
        return "STALE_REMOVED"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and _group_members(group):
        time.sleep(0.25)
    if _group_members(group):
        os.killpg(group, signal.SIGKILL)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and _group_members(group):
            time.sleep(0.1)
    if _group_members(group):
        return "CLEANUP_FAILED"
    path.unlink()
    return "ORPHAN_CLEANED"


def recover_stale_owned_services(
    spec: ExperimentSpec,
    paths: FullDocAssetPaths,
    *,
    include_embedding: bool,
) -> dict[str, str]:
    # Evaluation also cleans a provably orphaned embedding process left by a
    # creation-owner crash; it never starts a new embedding service.
    del include_embedding
    names = ("llm", "embedding")
    return {name: recover_owned_service(spec, paths, name) for name in names}


def check_full_doc_preflight(
    spec: ExperimentSpec,
    paths: FullDocAssetPaths,
    *,
    require_embedding: bool,
    runtime_lock: Path,
    query: GpuQuery = _default_gpu_query,
    sleep: Sleep = time.sleep,
) -> FullDocPreflight:
    assets = check_full_doc_assets(spec, paths, require_embedding=require_embedding)
    recovery = recover_stale_owned_services(
        spec,
        paths,
        include_embedding=require_embedding,
    )
    gpu = stable_gpu0_preflight(spec, query=query, sleep=sleep)
    endpoints = [spec.services.llm_endpoint]
    if require_embedding:
        endpoints.append(spec.services.embedding_endpoint)
    ports = {endpoint: port_is_free(endpoint) for endpoint in endpoints}
    lock_available = lock_is_available(runtime_lock)
    assets_ready = all(item["ok"] is True for item in assets)
    ownership_ready = all(
        status in {"ABSENT", "STALE_REMOVED", "ORPHAN_CLEANED"} for status in recovery.values()
    )
    return FullDocPreflight(
        ready=(
            assets_ready
            and ownership_ready
            and gpu.ready
            and all(ports.values())
            and lock_available
        ),
        assets_ready=assets_ready,
        assets=assets,
        gpu=gpu,
        ports=ports,
        experiment_lock_available=lock_available,
        ownership_recovery=recovery,
    )


def check_api_embedding_preflight(
    spec: ExperimentSpec,
    paths: FullDocAssetPaths,
    *,
    runtime_lock: Path,
    query: GpuQuery = _default_gpu_query,
    sleep: Sleep = time.sleep,
) -> FullDocPreflight:
    """Preflight a hosted-LLM creation run with one local embedding service.

    This deliberately has no local-LLM surface: it does not require the LLM
    snapshot, inspect the LLM port, or recover an LLM ownership manifest.
    Stable foreign GPU processes are allowed and are captured as the final-gate
    baseline.
    """

    assets = check_full_doc_assets(
        spec,
        paths,
        require_embedding=True,
        require_llm=False,
    )
    recovery = {"embedding": recover_owned_service(spec, paths, "embedding")}
    gpu = stable_api_embedding_gpu0_preflight(spec, query=query, sleep=sleep)
    ports = {
        spec.services.embedding_endpoint: port_is_free(spec.services.embedding_endpoint)
    }
    lock_available = lock_is_available(runtime_lock)
    assets_ready = all(item["ok"] is True for item in assets)
    ownership_ready = recovery["embedding"] in {
        "ABSENT",
        "STALE_REMOVED",
        "ORPHAN_CLEANED",
    }
    return FullDocPreflight(
        ready=(
            assets_ready
            and ownership_ready
            and gpu.ready
            and all(ports.values())
            and lock_available
        ),
        assets_ready=assets_ready,
        assets=assets,
        gpu=gpu,
        ports=ports,
        experiment_lock_available=lock_available,
        ownership_recovery=recovery,
    )


def assert_api_embedding_final_gate(
    spec: ExperimentSpec,
    preflight: FullDocPreflight,
    *,
    query: GpuQuery = _default_gpu_query,
) -> FullDocGpuObservation:
    """Revalidate the embedding-only GPU/port state after acquiring the lock."""

    baseline = preflight.gpu.final
    observation = inspect_gpu0(spec.services.gpu_uuid, query=query)
    threshold = api_embedding_minimum_free_memory_mib(spec, observation.memory_total_mib)
    if (
        not preflight.ready
        or baseline is None
        or observation.uuid != baseline.uuid
        or observation.index != baseline.index
        or observation.compute_pids != baseline.compute_pids
        or observation.memory_free_mib < threshold
        or not port_is_free(spec.services.embedding_endpoint)
    ):
        raise FullDocInfrastructureError(
            "embedding GPU, PID, memory, or port state changed after preflight"
        )
    return observation


class FullDocRuntimeLock:
    """Hold a local experiment lock from the final GPU check through teardown."""

    def __init__(self, path: Path, *, gpu_uuid: str) -> None:
        self.path = path
        self.gpu_uuid = gpu_uuid
        self._handle: Any | None = None

    def __enter__(self) -> FullDocRuntimeLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            raise FullDocInfrastructureError("full-document GPU lock is already held") from None
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"owner_pid": os.getpid(), "gpu_uuid": self.gpu_uuid}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        self._handle = handle
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


def _models_match(endpoint: str, expected_model: str, expected_length: int) -> bool:
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/models", timeout=5) as response:
            payload = json.loads(response.read(1024 * 1024))
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return False
    records = payload.get("data") if isinstance(payload, dict) else None
    return bool(
        isinstance(records, list)
        and len(records) == 1
        and isinstance(records[0], dict)
        and records[0].get("id") == expected_model
        and records[0].get("max_model_len") == expected_length
    )


class _DurableOwnedService:
    """One process group whose exact identity is durable across owner crashes."""

    def __init__(
        self,
        spec: ExperimentSpec,
        paths: FullDocAssetPaths,
        *,
        name: str,
        argv: tuple[str, ...],
        endpoint: str,
        expected_model: str,
        expected_length: int,
        log_path: Path,
    ) -> None:
        self.spec = spec
        self.paths = paths
        self.name = name
        self.argv = argv
        self.endpoint = endpoint
        self.expected_model = expected_model
        self.expected_length = expected_length
        self.log_path = log_path
        self.ownership_path = _ownership_path(spec, name)
        self.process: subprocess.Popen[bytes] | None = None
        self._owned_identity: dict[str, Any] | None = None
        self._log: Any | None = None

    def _manifest(self, process_identity: dict[str, Any]) -> dict[str, Any]:
        owner = _process_identity(os.getpid())
        if owner is None:
            raise FullDocInfrastructureError("cannot bind the service owner process")
        process_group = process_identity["process_group"]
        return {
            **_service_contract(self.spec, self.paths, self.name),
            "owner": owner,
            "service_process": process_identity,
            "process_group": process_group,
            "group_members": list(_group_members(process_group)),
            "log_path": str(self.log_path),
        }

    def start(self, *, timeout_seconds: float) -> None:
        recovered = recover_owned_service(self.spec, self.paths, self.name)
        if recovered not in {"ABSENT", "STALE_REMOVED", "ORPHAN_CLEANED"}:
            raise FullDocInfrastructureError(
                f"cannot safely claim {self.name} service ownership: {recovered}"
            )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self.log_path.open("xb")
        self.process = subprocess.Popen(
            self.argv,
            env=_service_environment(self.paths, self.spec.services.gpu_uuid),
            stdout=self._log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout_seconds
        process_identity: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.close()
                raise FullDocInfrastructureError(
                    f"owned {self.name} service exited; log={self.log_path}"
                )
            process_identity = _process_identity(self.process.pid)
            if process_identity is not None:
                self._owned_identity = dict(process_identity)
                _atomic_manifest(self.ownership_path, self._manifest(process_identity))
                break
            time.sleep(0.05)
        if process_identity is None:
            self.close()
            raise FullDocInfrastructureError("could not record owned service identity")
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.close()
                raise FullDocInfrastructureError(
                    f"owned {self.name} service exited; log={self.log_path}"
                )
            current = _process_identity(self.process.pid)
            if current is None or current["start_ticks"] != process_identity["start_ticks"]:
                self.close()
                raise FullDocInfrastructureError("owned service process identity changed")
            self._owned_identity = dict(current)
            _atomic_manifest(self.ownership_path, self._manifest(current))
            healthy = _models_match(self.endpoint, self.expected_model, self.expected_length)
            current = _process_identity(self.process.pid)
            if current is None or current["start_ticks"] != process_identity["start_ticks"]:
                self.close()
                raise FullDocInfrastructureError("owned service process identity changed")
            # Refresh after the potentially blocking health request as well, so
            # EngineCore children spawned during startup are durably recorded.
            self._owned_identity = dict(current)
            _atomic_manifest(self.ownership_path, self._manifest(current))
            if healthy:
                return
            time.sleep(0.25)
        self.close()
        raise FullDocInfrastructureError(
            f"owned {self.name} service readiness timed out; log={self.log_path}"
        )

    def healthy(self) -> bool:
        return bool(
            self.process is not None
            and self.process.poll() is None
            and _models_match(self.endpoint, self.expected_model, self.expected_length)
        )

    def close(self) -> None:
        process = self.process
        if process is not None:
            group = process.pid
            with suppress(ProcessLookupError):
                os.killpg(group, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(group, signal.SIGKILL)
                process.wait(timeout=30)
            if _group_members(group):
                with suppress(ProcessLookupError):
                    os.killpg(group, signal.SIGKILL)
            self.process = None
        if self._log is not None:
            self._log.close()
            self._log = None
        if self.ownership_path.is_file():
            try:
                manifest = json.loads(self.ownership_path.read_bytes())
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return
            if (
                isinstance(manifest, dict)
                and manifest.get("service_process") == self._owned_identity
                and all(
                    manifest.get(key) == value
                    for key, value in _service_contract(self.spec, self.paths, self.name).items()
                )
            ):
                self.ownership_path.unlink()
        self._owned_identity = None


class FullDocServiceSupervisor:
    """Restart only durable process groups this experiment can prove it owns."""

    def __init__(
        self,
        spec: ExperimentSpec,
        paths: FullDocAssetPaths,
        *,
        log_root: Path,
        include_embedding: bool,
        include_llm: bool = True,
    ) -> None:
        self.spec = spec
        self.paths = paths
        self.log_root = log_root
        self.include_embedding = include_embedding
        self.include_llm = include_llm
        self._services: dict[str, _DurableOwnedService] = {}
        self._starts = {"llm": 0, "embedding": 0}
        self._history: list[dict[str, Any]] = []

    def _new_service(self, name: str) -> _DurableOwnedService:
        self._starts[name] += 1
        if name == "llm" and self.include_llm:
            argv = full_doc_llm_argv(self.spec, self.paths)
            endpoint = self.spec.services.llm_endpoint
            model = self.spec.model.model
            maximum = self.spec.model.max_model_len
        elif name == "embedding" and self.include_embedding:
            argv = full_doc_embedding_argv(self.spec, self.paths)
            endpoint = self.spec.services.embedding_endpoint
            model = self.spec.embedding.model
            maximum = self.spec.embedding.max_length
        else:
            raise ValueError(f"service is not enabled: {name}")
        return _DurableOwnedService(
            self.spec,
            self.paths,
            name=name,
            argv=argv,
            endpoint=endpoint,
            expected_model=model,
            expected_length=maximum,
            log_path=self.log_root / f"{name}-{self._starts[name]:02d}.log",
        )

    def _start(self, name: str) -> None:
        previous = self._services.pop(name, None)
        if previous is not None:
            previous.close()
        service = self._new_service(name)
        service.start(timeout_seconds=self.spec.request_timeout_seconds)
        self._services[name] = service
        assert service.process is not None
        self._history.append(
            {
                "name": name,
                "start_index": self._starts[name],
                "pid": service.process.pid,
                "log": str(service.log_path),
                "ownership_manifest": str(service.ownership_path),
            }
        )

    def ensure(self, names: tuple[str, ...]) -> None:
        for name in names:
            if name == "llm" and not self.include_llm:
                raise FullDocInfrastructureError("local LLM service is not enabled")
            if name == "embedding" and not self.include_embedding:
                raise FullDocInfrastructureError("evaluation cannot start an embedding service")
            service = self._services.get(name)
            if service is None or not service.healthy():
                self._start(name)

    def identity(self) -> dict[str, Any]:
        return {
            "gpu_index": 0,
            "gpu_uuid": self.spec.services.gpu_uuid,
            "assets": self.paths.to_dict(),
            "llm": (
                {
                    "model": self.spec.model.model,
                    "revision": self.spec.model.revision,
                    "dtype": self.spec.model.dtype,
                    "endpoint": self.spec.services.llm_endpoint,
                    "max_model_len": self.spec.model.max_model_len,
                    "gpu_memory_utilization": self.spec.services.llm_gpu_memory_utilization,
                }
                if self.include_llm
                else None
            ),
            "embedding": (
                {
                    "model": self.spec.embedding.model,
                    "revision": self.spec.embedding.revision,
                    "endpoint": self.spec.services.embedding_endpoint,
                    "gpu_memory_utilization": (self.spec.services.embedding_gpu_memory_utilization),
                }
                if self.include_embedding
                else None
            ),
            "ownership_policy": "restart-owned-processes-only",
        }

    @property
    def operational_history(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(item) for item in self._history)

    def __enter__(self) -> FullDocServiceSupervisor:
        try:
            if self.include_llm:
                self._start("llm")
            if self.include_embedding:
                self._start("embedding")
        except BaseException:
            self.close()
            raise
        return self

    def close(self) -> None:
        for name in ("embedding", "llm"):
            service = self._services.pop(name, None)
            if service is not None:
                service.close()

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = [
    "DEFAULT_HF_HOME",
    "DEFAULT_VLLM_EXECUTABLE",
    "EMBEDDING_ONLY_GPU_OVERHEAD_MIB",
    "FullDocAssetPaths",
    "FullDocGpuObservation",
    "FullDocGpuPreflight",
    "FullDocInfrastructureError",
    "FullDocPreflight",
    "FullDocRuntimeLock",
    "FullDocServiceSupervisor",
    "api_embedding_minimum_free_memory_mib",
    "assert_api_embedding_final_gate",
    "check_api_embedding_preflight",
    "check_full_doc_assets",
    "check_full_doc_preflight",
    "full_doc_embedding_argv",
    "full_doc_llm_argv",
    "inspect_gpu0",
    "lock_is_available",
    "port_is_free",
    "recover_owned_service",
    "recover_stale_owned_services",
    "stable_gpu0_preflight",
    "stable_api_embedding_gpu0_preflight",
]
