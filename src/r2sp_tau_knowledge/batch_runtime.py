"""Owned model services and fresh workers for benign batch creation and utility.

This module does not call the legacy matrix or attach its sidecar tools. The
only acquisition corpus is the verified, byte-identical official snapshot.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from r2sp_common import RunStatus, RuntimeIdentity

from .batch_compiler import TauSkillCompiler
from .batch_constants import (
    COMPILER_MAX_OUTPUT_TOKENS,
    EXPERIMENT_ROOT,
    MODEL_ID,
    MODEL_REVISION,
    SELECTION_K,
    SIDECAR_TOOLS,
)
from .batch_gpu_gate import GpuGateError, GpuGateLock, GpuObservation, _nvidia_csv, check_gpu_gate
from .batch_model import GenerationConfig, OpenAICompatibleClient
from .batch_outcomes import AcquisitionOutcome, CompilationOutcome, DeploymentOutcome
from .batch_services import (
    APPTAINER_EXECUTABLE,
    DENSE_MODEL_ROOT,
    PINNED_PYTHON,
    RUNTIME_ROOT,
    SIF_PATH,
    LiveInfrastructureError,
    OwnedDenseService,
    _base_subprocess_environment,
    _worker_environment,
)
from .data import load_documents, verify_tracked_snapshot
from .qualification import qualify_model_service
from .records import sha256_json

DIAGNOSTIC_MODEL_ID = "Qwen/Qwen3.8-27B-FP8"
DIAGNOSTIC_MODEL_REVISION = "017b9c7af6b5689d5dd426a76e0bc077eb5ca20a"
_PINNED_MODELS = {MODEL_ID: MODEL_REVISION, DIAGNOSTIC_MODEL_ID: DIAGNOSTIC_MODEL_REVISION}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DEDICATED_BUILD_VERSION = "0.1.dev20073+g8e685d198"
_DEDICATED_BUILD_FILES = {
    "vllm/model_executor/models/registry.py": (
        "f2cb58b659f9b9069141b9df5681feaf384a18ea180090d0b5c78adf6a678d65"
    ),
    "vllm/models/qwen3_8_flash_next/nvidia/model.py": (
        "d900cd6fcacba18f460e00b3f018fbf36fbe6ecc310692b6adb1451f7f53cc17"
    ),
    "vllm/models/qwen3_8_flash_next/nvidia/ple_layer.py": (
        "a71144c1d36e06f22a2da1b1ada900076597fe5e824a911e7ada86249a0993e7"
    ),
}
_FORBIDDEN_TOOLS = {
    "search_web",
    "select_docs",
    "open_page",
    *SIDECAR_TOOLS.values(),
}


def _check_framework_build(
    version: str, *, flash: bool, development_files: dict[str, str] | None = None
) -> str:
    """Gate assets; a recognized build still requires every live service probe."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\+[^\s]+)?", version)
    minimum = (0, 29, 0) if flash else (0, 28, 0)
    if match is not None and tuple(int(part) for part in match.groups()) >= minimum:
        return "release-version"
    # The recipe's pinned image uses setuptools' development version rather
    # than 0.29. Verify its exact architecture sources, not a guessed version.
    if version == _DEDICATED_BUILD_VERSION and development_files == _DEDICATED_BUILD_FILES:
        return "pinned-dedicated-development-build"
    raise LiveInfrastructureError("pre-staged container vLLM build is incompatible")


def validate_batch_model(model: Any) -> dict[str, Any]:
    """Accept only a pinned local model; endpoints cannot redirect requests off-node."""
    if not isinstance(model, dict) or set(model) != {
        "id",
        "revision",
        "endpoint",
        "max_context_tokens",
    }:
        raise ValueError("batch model requires id, revision, endpoint, max_context_tokens")
    if (
        not isinstance(model.get("id"), str)
        or model["id"] not in _PINNED_MODELS
        or model.get("revision") != _PINNED_MODELS[model["id"]]
    ):
        raise ValueError("batch model is not an allowed pinned model revision")
    if (
        isinstance(model["max_context_tokens"], bool)
        or not isinstance(model["max_context_tokens"], int)
        or model["max_context_tokens"] != 65536
    ):
        raise ValueError("batch model context is fixed at 65536 tokens")
    if not isinstance(model["endpoint"], str):
        raise ValueError("batch model endpoint must be a string")
    parsed = urllib.parse.urlsplit(model["endpoint"])
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path.rstrip("/") != "/v1"
        or parsed.query
        or parsed.fragment
        or parsed.port is None
        or parsed.port == 18139
    ):
        raise ValueError("batch model endpoint must be a distinct localhost HTTP /v1 service")
    return dict(model)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_validator() -> Any:
    path = EXPERIMENT_ROOT / "scripts" / "validate_runtime_assets.py"
    spec = importlib.util.spec_from_file_location("_tau_batch_asset_validation", path)
    if spec is None or spec.loader is None:
        raise LiveInfrastructureError("runtime asset validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _diagnostic_snapshot(root: Path) -> dict[str, Any]:
    """Validate the diagnostic revision against its downloaded artifact metadata."""
    if root.is_symlink() or not root.is_dir():
        raise LiveInfrastructureError("diagnostic model snapshot is unavailable")
    index_path = root / "model.safetensors.index.json"
    index = json.loads(index_path.read_bytes())
    shard_names = sorted(set(index.get("weight_map", {}).values()))
    if not shard_names or any(
        not isinstance(name, str)
        or re.fullmatch(r"model-\d{5}-of-\d{5}\.safetensors", name) is None
        for name in shard_names
    ):
        raise LiveInfrastructureError("diagnostic model shard inventory is invalid")
    records = []
    names = [
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "model.safetensors.index.json",
    ]
    for name in names + shard_names:
        path = root / name
        metadata = root / ".cache" / "huggingface" / "download" / f"{name}.metadata"
        if path.is_symlink() or not path.is_file() or not metadata.is_file():
            raise LiveInfrastructureError(f"diagnostic model artifact is missing: {name}")
        lines = metadata.read_text().splitlines()
        if len(lines) < 2 or lines[0] != DIAGNOSTIC_MODEL_REVISION:
            raise LiveInfrastructureError(f"diagnostic model revision mismatch: {name}")
        digest = _hash_file(path)
        # Large-file metadata stores the content SHA-256; small metadata files
        # may instead carry a Git blob SHA-1, which is checked with Git framing.
        expected = lines[1]
        if _SHA256.fullmatch(expected):
            valid = digest == expected
        elif re.fullmatch(r"[0-9a-f]{40}", expected):
            raw = path.read_bytes()
            valid = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() == expected
        else:
            valid = False
        if not valid:
            raise LiveInfrastructureError(f"diagnostic model artifact digest mismatch: {name}")
        records.append({"path": name, "sha256": digest, "size_bytes": path.stat().st_size})
    return {
        "root": str(root),
        "revision": DIAGNOSTIC_MODEL_REVISION,
        "snapshot_sha256": sha256_json(records),
        "weight_shards": len(shard_names),
    }


def validate_batch_assets(*, phase: str, model: dict[str, Any]) -> dict[str, Any]:
    """Read and validate all assets before any service starts; never download."""
    model = validate_batch_model(model)
    if phase not in {"creation", "evaluation"}:
        raise ValueError("batch phase must be creation or evaluation")
    model_root = Path(
        os.environ.get(
            "R2SP_TAU_MODEL_ROOT", str(RUNTIME_ROOT / "models" / model["id"].split("/")[-1])
        )
    )
    if SIF_PATH.is_symlink() or not SIF_PATH.is_file():
        raise LiveInfrastructureError(f"pre-staged model SIF is unavailable: {SIF_PATH}")
    if not APPTAINER_EXECUTABLE.is_file() or not os.access(APPTAINER_EXECUTABLE, os.X_OK):
        raise LiveInfrastructureError("Apptainer is unavailable")
    if not PINNED_PYTHON.is_file() or not os.access(PINNED_PYTHON, os.X_OK):
        raise LiveInfrastructureError("pinned Tau Python is unavailable")
    sif_hash = _hash_file(SIF_PATH)
    expected = os.environ.get("R2SP_TAU_SIF_SHA256")
    if expected is not None and (_SHA256.fullmatch(expected) is None or sif_hash != expected):
        raise LiveInfrastructureError("pre-staged SIF hash mismatch")
    validator = _asset_validator()
    main = (
        validator._validate_main_model(model_root)
        if model["id"] == MODEL_ID
        else _diagnostic_snapshot(model_root)
    )
    assets = {
        "model": main,
        "sif": {"path": str(SIF_PATH), "sha256": sif_hash},
        "dataset": verify_tracked_snapshot(),
    }
    if phase == "creation":
        assets["dense_model"] = validator._validate_dense_model(DENSE_MODEL_ROOT)
    for name, variable in (
        ("model", "R2SP_TAU_MODEL_SNAPSHOT_SHA256"),
        ("dense_model", "R2SP_TAU_DENSE_SNAPSHOT_SHA256"),
    ):
        expected_snapshot = os.environ.get(variable)
        if (
            name in assets
            and expected_snapshot is not None
            and (
                _SHA256.fullmatch(expected_snapshot) is None
                or assets[name]["snapshot_sha256"] != expected_snapshot
            )
        ):
            raise LiveInfrastructureError(f"sealed {name} snapshot hash mismatch")
    version_result = subprocess.run(
        [
            str(APPTAINER_EXECUTABLE),
            "exec",
            "--cleanenv",
            str(SIF_PATH),
            "python3",
            "-c",
            "import importlib.metadata as m; print(m.version('vllm'))",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=_base_subprocess_environment(),
    )
    version = version_result.stdout.strip()
    development_files = None
    if version == _DEDICATED_BUILD_VERSION:
        inspection = subprocess.run(
            [
                str(APPTAINER_EXECUTABLE),
                "exec",
                "--cleanenv",
                str(SIF_PATH),
                "python3",
                "-c",
                "import hashlib,importlib.metadata as m,json,sys; "
                "d=m.distribution('vllm'); "
                "print(json.dumps({p:hashlib.sha256(d.locate_file(p).read_bytes()).hexdigest() "
                "for p in json.loads(sys.argv[1])},sort_keys=True))",
                json.dumps(list(_DEDICATED_BUILD_FILES)),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=_base_subprocess_environment(),
        )
        development_files = json.loads(inspection.stdout)
    assets["sif"]["framework_asset_check"] = _check_framework_build(
        version, flash=model["id"] == MODEL_ID, development_files=development_files
    )
    if development_files is not None:
        assets["sif"]["development_source_sha256"] = development_files
    assets["sif"]["vllm_version"] = version
    return assets


def _allocation(gpu_indices: tuple[int, ...] | None) -> tuple[str, list[dict[str, Any]]]:
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if visible is None:
        if os.environ.get("SLURM_JOB_ID") or gpu_indices is None:
            raise GpuGateError("CUDA_VISIBLE_DEVICES allocation is required")
        visible = ",".join(str(index) for index in gpu_indices)
    tokens = visible.split(",")
    if not tokens or any(not token.strip() for token in tokens) or len(set(tokens)) != len(tokens):
        raise GpuGateError("GPU allocation must contain distinct device identifiers")
    if gpu_indices is not None and visible != ",".join(str(index) for index in gpu_indices):
        raise GpuGateError("explicit GPU indices must match CUDA_VISIBLE_DEVICES exactly")
    result = subprocess.run(
        [
            "nvidia-smi",
            "--id",
            visible,
            "--query-gpu=index,uuid,name,memory.total",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    rows = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        fields = [part.strip() for part in line.split(",")]
        if len(fields) != 4:
            raise GpuGateError("GPU allocation attestation is malformed")
        rows.append(
            {
                "index": int(fields[0]),
                "uuid": fields[1],
                "name": fields[2],
                "memory_total_mib": int(fields[3]),
            }
        )
    if len(rows) != len(tokens) or len({row["uuid"] for row in rows}) != len(rows):
        raise GpuGateError("GPU allocation does not resolve to distinct available devices")
    return visible, rows


def _observe_allocated_gpus(indices: tuple[int, ...]) -> GpuObservation:
    """An unavailable process inventory is a gate failure, never evidence of idle GPUs."""
    free: dict[int, int] = {}
    identifiers: dict[str, int] = {}
    for row in _nvidia_csv(["--query-gpu=index,uuid,memory.free"]):
        if len(row) != 3:
            raise GpuGateError("GPU observation is malformed")
        index = int(row[0])
        if index in indices:
            identifiers[row[1]] = index
            free[index] = int(row[2])
    if set(free) != set(indices):
        raise GpuGateError("an allocated GPU disappeared")
    processes: dict[int, list[int]] = {index: [] for index in indices}
    for row in _nvidia_csv(["--query-compute-apps=gpu_uuid,pid"]):
        if len(row) != 2:
            raise GpuGateError("GPU process inventory is malformed")
        if row[0] in identifiers:
            processes[identifiers[row[0]]].append(int(row[1]))
    return GpuObservation(free, {index: tuple(pids) for index, pids in processes.items()})


class _OwnedBatchService:
    def __init__(
        self, *, model: dict[str, Any], assets: dict[str, Any], visible: str, gpu_count: int
    ) -> None:
        self.model, self.assets, self.visible, self.gpu_count = model, assets, visible, gpu_count
        self.process: subprocess.Popen[bytes] | None = None
        self.log: Any = None
        self.log_path: Path | None = None

    def __enter__(self) -> _OwnedBatchService:
        port = urllib.parse.urlsplit(self.model["endpoint"]).port
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise LiveInfrastructureError("batch model endpoint is already occupied") from exc
        logs = RUNTIME_ROOT / "logs" / "batch"
        logs.mkdir(parents=True, exist_ok=True)
        self.log_path = logs / f"service-{uuid.uuid4().hex}.log"
        self.log = self.log_path.open("xb")
        cache = RUNTIME_ROOT / "cache" / "batch-service"
        for name in ("huggingface", "triton", "xdg"):
            (cache / name).mkdir(parents=True, exist_ok=True)
        environment = _base_subprocess_environment()
        # Preserve the scheduler's CUDA namespace byte-for-byte. Physical
        # indices observed for locks must never replace this allocation.
        environment.update(
            {
                "CUDA_VISIBLE_DEVICES": self.visible,
                "APPTAINERENV_CUDA_VISIBLE_DEVICES": self.visible,
                "APPTAINERENV_HF_HUB_OFFLINE": "1",
                "APPTAINERENV_TRANSFORMERS_OFFLINE": "1",
                "APPTAINERENV_TOKENIZERS_PARALLELISM": "false",
                "APPTAINERENV_NCCL_IB_DISABLE": "1",
                "APPTAINERENV_NCCL_SOCKET_IFNAME": "lo",
                "APPTAINERENV_GLOO_SOCKET_IFNAME": "lo",
                "APPTAINERENV_HF_HOME": str(cache / "huggingface"),
                "APPTAINERENV_TRITON_CACHE_DIR": str(cache / "triton"),
                "APPTAINERENV_XDG_CACHE_HOME": str(cache / "xdg"),
            }
        )
        if self.model["id"] == MODEL_ID:
            environment["APPTAINERENV_VLLM_PLE_CPU_OFFLOAD"] = "1"
        command = [
            str(APPTAINER_EXECUTABLE),
            "exec",
            "--cleanenv",
            "--nv",
            "--bind",
            "/usr/xtmp:/usr/xtmp",
            str(SIF_PATH),
            "vllm",
            "serve",
            self.assets["model"]["root"],
            "--served-model-name",
            self.model["id"],
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--max-model-len",
            str(self.model["max_context_tokens"]),
            "--tensor-parallel-size",
            str(self.gpu_count),
            "--distributed-executor-backend",
            "mp",
            "--gpu-memory-utilization",
            "0.9",
            "--max-num-seqs",
            "1",
            "--max-num-batched-tokens",
            "8192",
            "--no-enable-prefix-caching",
            "--no-enable-flashinfer-autotune",
            "--language-model-only",
            "--enable-auto-tool-choice",
            "--tool-call-parser",
            "qwen3_xml",
            "--reasoning-parser",
            "qwen3",
            "--generation-config",
            "vllm",
            "--default-chat-template-kwargs",
            '{"enable_thinking":true,"preserve_thinking":false}',
        ]
        try:
            self.process = subprocess.Popen(
                command,
                stdout=self.log,
                stderr=subprocess.STDOUT,
                env=environment,
                start_new_session=True,
            )
            deadline = time.monotonic() + 2700
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise LiveInfrastructureError(f"batch service exited; log={self.log_path}")
                try:
                    with urllib.request.urlopen(self.model["endpoint"] + "/models", timeout=5) as r:
                        records = json.loads(r.read()).get("data")
                    if (
                        isinstance(records, list)
                        and len(records) == 1
                        and records[0].get("id") == self.model["id"]
                        and records[0].get("max_model_len") == self.model["max_context_tokens"]
                    ):
                        return self
                except (OSError, urllib.error.URLError, json.JSONDecodeError):
                    pass
                time.sleep(2)
            raise LiveInfrastructureError(f"batch service timed out; log={self.log_path}")
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=30)
        self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None

    def __exit__(self, *_exc: object) -> None:
        self.close()


class BatchBackend:
    """Only verified benign acquisition and banking utility deployment."""

    def __init__(self, *, phase: str, model: dict[str, Any]) -> None:
        self.phase = phase
        self.model = validate_batch_model(model)
        self.metrics: list[dict[str, Any]] = []
        self.client = OpenAICompatibleClient(
            model["endpoint"],
            config=GenerationConfig(
                model=model["id"],
                revision=model["revision"],
                max_output_tokens=COMPILER_MAX_OUTPUT_TOKENS,
            ),
            timeout_seconds=900,
        )
        self.compiler = TauSkillCompiler(
            self.client, include_public_trace=True, max_generation_tokens=COMPILER_MAX_OUTPUT_TOKENS
        )

    def _worker(self, request: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        response: dict[str, Any] = {}
        worker_module = (
            "r2sp_tau_knowledge.batch_compile_worker"
            if request["mode"] == "batch-benign-compile"
            else "r2sp_tau_knowledge.batch_official_worker"
        )
        with tempfile.TemporaryDirectory(prefix="tau-benign-batch-") as directory:
            root = Path(directory)
            request_path, response_path = root / "request.json", root / "response.json"
            request_path.write_text(json.dumps(request, ensure_ascii=False))
            environment = _worker_environment()
            if self.phase == "evaluation":
                environment.pop("R2SP_TAU_DENSE_ENDPOINT", None)
                environment.pop("R2SP_TAU_DENSE_CACHE_ROOT", None)
            try:
                completed = subprocess.run(
                    [
                        str(PINNED_PYTHON),
                        "-m",
                        worker_module,
                        "--request",
                        str(request_path),
                        "--response",
                        str(response_path),
                    ],
                    cwd=directory,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=43200,
                )
                if completed.returncode not in {0, 2} or not response_path.is_file():
                    raise LiveInfrastructureError(f"batch worker exited {completed.returncode}")
                response = json.loads(response_path.read_bytes())
                if response.get("status") == "INVALID":
                    raise LiveInfrastructureError(response.get("error", "batch worker invalid"))
                return response
            finally:
                trajectory = response.get("official_trajectory", {})
                usage_records = [
                    message["usage"]
                    for message in trajectory.get("messages", [])
                    if isinstance(message.get("usage"), dict)
                ]
                usage = {}
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    values = [record.get(key) for record in usage_records]
                    usage[key] = (
                        sum(values)
                        if values
                        and all(
                            isinstance(value, int) and not isinstance(value, bool) and value >= 0
                            for value in values
                        )
                        else None
                    )
                self.metrics.append(
                    {
                        "phase": request["mode"],
                        "task_id": request["task_id"],
                        "duration_seconds": time.monotonic() - started,
                        "termination_reason": trajectory.get("termination_reason"),
                        "usage": usage,
                        "usage_message_count": len(usage_records),
                    }
                )

    def acquire(self, *, item: dict[str, Any]) -> AcquisitionOutcome:
        if self.phase != "creation" or item.get("corpus") != "benign":
            raise ValueError("batch acquisition requires creation phase and the benign corpus")
        response = self._worker(
            {
                "mode": "batch-benign-acquisition",
                "model": self.model,
                "task_id": item["acquisition_task_id"],
                "seed": item["seed"],
                "simulation_id": f"batch-acquire-{uuid.uuid4().hex}",
                "corpus": "benign",
            }
        )
        pages = tuple(response.get("opened_pages", []))
        ids = [page.get("page_id") for page in pages]
        valid = (
            response.get("selection_complete") is True
            and len(ids) == SELECTION_K
            and all(isinstance(page_id, str) and page_id for page_id in ids)
            and len(set(ids)) == SELECTION_K
        )
        return AcquisitionOutcome(
            status=RunStatus.SUCCESS if valid else RunStatus.BEHAVIORAL_FAIL,
            task_success=response["task_success"],
            first_user_utterance=response["first_user_utterance"],
            opened_pages=pages,
            selection_complete=valid,
            public_trace=response["public_trace"],
            search_evidence=tuple(response["search_events"]),
            runtime_identity=RuntimeIdentity.from_dict(response["runtime_identity"]),
            official_reward=response["official_reward"],
            error=None if valid else "selection_incomplete",
        )

    def compile(
        self, *, item: dict[str, Any], acquisition: AcquisitionOutcome
    ) -> CompilationOutcome:
        if self.phase != "creation" or item.get("corpus") != "benign":
            raise ValueError("batch compilation requires a benign creation item")
        response = self._worker(
            {
                "mode": "batch-benign-compile",
                "model": self.model,
                "task_id": item["acquisition_task_id"],
                "item": item,
                "acquisition": {
                    "first_user_utterance": acquisition.first_user_utterance,
                    "opened_pages": list(acquisition.opened_pages),
                    "selection_complete": acquisition.selection_complete,
                    "public_trace": acquisition.public_trace,
                },
            }
        )
        self.metrics.append(
            {
                "phase": "compilation-model-response",
                "skill_id": item["skill_id"],
                "worker_pid": response["worker_pid"],
                "execution_id": response["execution_id"],
                "model_response": response["model_response"],
            }
        )
        return CompilationOutcome(
            status=RunStatus(response["status"]),
            skill_text=response["skill_text"],
            skill_sha256=response["skill_sha256"],
            valid=response["valid"],
            compiler_input=response["compiler_input"],
            error=response["error"],
        )

    def _compile_in_process(
        self, *, item: dict[str, Any], acquisition: AcquisitionOutcome
    ) -> CompilationOutcome:
        """Execute only inside a fresh compiler worker (or a mocked unit test)."""
        if self.phase != "creation" or item.get("corpus") != "benign":
            raise ValueError("batch compilation requires a benign creation item")
        official = {document.page_id: document.to_page_mapping() for document in load_documents()}
        if (
            not acquisition.selection_complete
            or len(acquisition.opened_pages) != SELECTION_K
            or len({page.get("page_id") for page in acquisition.opened_pages}) != SELECTION_K
            or any(official.get(page.get("page_id")) != page for page in acquisition.opened_pages)
        ):
            raise ValueError("batch compiler requires complete original benign documents")
        inputs = {
            "first_user_utterance": acquisition.first_user_utterance,
            "opened_pages": acquisition.opened_pages,
            "public_trace": acquisition.public_trace,
        }
        started = time.monotonic()
        self.client.last_response_metadata = {}
        try:
            payload = self.compiler.build_payload(**inputs)
            artifact = self.compiler.compile(seed=item["seed"], **inputs)
        finally:
            self.metrics.append(
                {
                    "phase": "compilation",
                    "skill_id": item["skill_id"],
                    "duration_seconds": time.monotonic() - started,
                    "model_response": dict(self.client.last_response_metadata),
                }
            )
        status = RunStatus.SUCCESS if artifact.valid else RunStatus.BEHAVIORAL_FAIL
        if (
            not artifact.valid
            and artifact.failure
            and artifact.failure.startswith("model_")
            and artifact.failure != "model_finish_reason_length"
        ):
            status = RunStatus.INVALID
        return CompilationOutcome(
            status=status,
            skill_text=artifact.text,
            skill_sha256=artifact.skill_sha256,
            valid=artifact.valid,
            compiler_input=payload,
            error=artifact.failure,
        )

    def deploy(
        self, *, trial: dict[str, Any], skill_text: str, skill_sha256: str
    ) -> DeploymentOutcome:
        if self.phase != "evaluation":
            raise ValueError("batch deployment requires the independent evaluation phase")
        response = self._worker(
            {
                "mode": "batch-utility-deployment",
                "model": self.model,
                "task_id": trial["task_id"],
                "seed": trial["seed"],
                "simulation_id": f"batch-deploy-{uuid.uuid4().hex}",
                "skill_text": skill_text,
                "skill_sha256": skill_sha256,
            }
        )
        exposed = tuple(response["exposed_tool_names"])
        if (
            set(exposed) & _FORBIDDEN_TOOLS
            or response.get("canary_events")
            or response.get("canary_hit")
        ):
            raise LiveInfrastructureError("utility deployment exposed a forbidden tool")
        return DeploymentOutcome(
            status=RunStatus.SUCCESS if response["task_success"] else RunStatus.BEHAVIORAL_FAIL,
            task_id=trial["task_id"],
            task_success=response["task_success"],
            canary_hit=False,
            canary_events=(),
            official_reward=response["official_reward"],
            runtime_identity=RuntimeIdentity.from_dict(response["runtime_identity"]),
            exposed_tool_names=exposed,
            official_trajectory=response["official_trajectory"],
            sidecar_trajectory=(),
            error=None if response["task_success"] else "utility_failed",
        )


class BatchRuntime:
    """Context manager owning creation's main+dense or evaluation's main only."""

    def __init__(
        self, *, phase: str, model: dict[str, Any], gpu_indices: tuple[int, ...] | None = None
    ) -> None:
        if phase not in {"creation", "evaluation"}:
            raise ValueError("phase must be creation or evaluation")
        self.phase, self.model, self.gpu_indices = phase, validate_batch_model(model), gpu_indices
        self.backend = BatchBackend(phase=phase, model=self.model)
        self.metadata: dict[str, Any] = {
            "phase": phase,
            "model": self.model,
            "call_metrics": self.backend.metrics,
        }
        self._stack = ExitStack()

    def __enter__(self) -> BatchRuntime:
        started = time.monotonic()
        try:
            assets = validate_batch_assets(phase=self.phase, model=self.model)
            self.metadata["assets"] = assets
            visible, devices = _allocation(self.gpu_indices)
            flash = self.model["id"] == MODEL_ID
            required = 4 if flash else 2
            if len(devices) != required:
                raise GpuGateError(f"selected model requires exactly {required} allocated GPUs")
            if flash and any("RTX PRO 6000" not in row["name"].upper() for row in devices):
                raise GpuGateError("Flash-Next requires allocated RTX Pro 6000 GPUs")
            self.metadata["allocation"] = {"cuda_visible_devices": visible, "devices": devices}
            indices = tuple(row["index"] for row in devices)
            minimum = 90000 if flash else 22000
            first_gate = check_gpu_gate(
                indices=indices, minimum_free_mib=minimum, observer=_observe_allocated_gpus
            )
            if not first_gate.passed:
                raise GpuGateError(first_gate.reason)
            # One lock per physical UUID also prevents overlapping allocations
            # with different tuple orderings from bypassing local ownership.
            for row in sorted(devices, key=lambda row: row["uuid"]):
                label = hashlib.sha256(row["uuid"].encode()).hexdigest()
                self._stack.enter_context(
                    GpuGateLock(
                        RUNTIME_ROOT / "locks" / f"gpu-{label}.lock", indices=(row["index"],)
                    )
                )
            final_gate = check_gpu_gate(
                indices=indices,
                minimum_free_mib=minimum,
                checks=1,
                interval_seconds=0,
                observer=_observe_allocated_gpus,
            )
            if not final_gate.passed:
                raise GpuGateError(final_gate.reason)
            self.metadata["gpu_gate"] = final_gate.to_dict()
            service = self._stack.enter_context(
                _OwnedBatchService(
                    model=self.model, assets=assets, visible=visible, gpu_count=len(devices)
                )
            )
            self.metadata["service_log"] = str(service.log_path)
            self.metadata["qualification"] = qualify_model_service(
                self.model["endpoint"],
                model_id=self.model["id"],
                model_revision=self.model["revision"],
                max_context_tokens=self.model["max_context_tokens"],
                include_creation=self.phase == "creation",
            )
            if self.phase == "creation":
                dense = self._stack.enter_context(OwnedDenseService())
                self.metadata["dense_service_log"] = str(dense.log_path)
            self.metadata["startup_seconds"] = time.monotonic() - started
            return self
        except BaseException:
            self._stack.close()
            raise

    def __exit__(self, *_exc: object) -> None:
        self._stack.close()


__all__ = ["BatchBackend", "BatchRuntime", "validate_batch_assets", "validate_batch_model"]
