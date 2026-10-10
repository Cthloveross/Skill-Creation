#!/usr/bin/env python3
"""Prepare a local SkillsBench environment from a clone, without model credentials."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager, suppress
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tau_skill_evolution.artifacts import atomic_json  # noqa: E402
from tau_skill_evolution.core._canonical import canonical_json_bytes  # noqa: E402
from tau_skill_evolution.retrieval import embedding_argv  # noqa: E402
from tau_skill_evolution.skillsbench_attack import (  # noqa: E402
    MATRIX_MANIFEST,
    validate_matrix_manifest,
)
from tau_skill_evolution.spec import load_spec  # noqa: E402

SETUP = Path("data/skillsbench/setup")
SCHEMA = "skillsbench.local-build.v1"


def _hash(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _build_directory(identity: str) -> Path:
    if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
        raise ValueError("skillsbench_local_source_identity_invalid")
    return SETUP / "builds" / identity


def _lock_template(identity: str) -> Path:
    return _build_directory(identity) / "runtime/skillsbench-docker-{task_id}-v4-lock.json"


def _local_values(values: dict, gpu: str, identity: str) -> dict:
    values = json.loads(json.dumps(values))
    values["embedding"]["gpu_uuid"] = gpu
    values["source"]["runtime_lock"] = _lock_template(identity).as_posix()
    return values


def check_binding(root: Path = ROOT) -> dict:
    """Check frozen local files only; runtime readiness still requires preflight."""
    binding = json.loads((root / SETUP / "binding.json").read_text())
    return _validate_binding(binding, root)


def _validate_binding(binding: dict, root: Path) -> dict:
    if (
        binding.get("schema") != SCHEMA
        or binding.get("status") != "PREPARED"
        or binding.get("prepared") is not True
        or binding.get("ready") is not False
    ):
        raise ValueError("skillsbench_local_binding_invalid")
    canonical = load_spec(root / "configs/skillsbench.yaml")
    identity = canonical.identity["identity_hash"]
    if binding.get("canonical_identity_hash") != identity:
        raise ValueError("skillsbench_local_source_changed; prepare a new local build identity")
    config_path = _build_directory(identity) / "skillsbench.yaml"
    if binding.get("config_path") != config_path.as_posix():
        raise ValueError("skillsbench_local_config_path_invalid")
    config = root / config_path
    if binding.get("config_sha256") != _hash(config):
        raise ValueError("skillsbench_local_config_changed")
    local = load_spec(config)
    if local.values != _local_values(canonical.values, binding["gpu"], identity):
        raise ValueError("skillsbench_local_config_has_unapproved_changes")
    if binding.get("identity_hash") != local.identity["identity_hash"]:
        raise ValueError("skillsbench_local_runtime_changed")
    if binding.get("matrix_sha256") != _hash(root / MATRIX_MANIFEST):
        raise ValueError("skillsbench_local_matrix_changed")
    expected = [str(_lock_template(identity)).replace("{task_id}", task) for task in local.tasks]
    records = binding.get("runtime_locks", [])
    if [record["path"] for record in records] != expected:
        raise ValueError("skillsbench_local_locks_incomplete")
    for record in records:
        if _hash(root / record["path"]) != record["sha256"]:
            raise ValueError("skillsbench_local_runtime_changed")
    return binding


def _run(command: list[str], path: Path) -> None:
    print(f"Preparing: {path.name}", flush=True)
    with path.open("wb") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def _resolve_gpu(gpu: str) -> str:
    if not re.fullmatch(r"(?:[0-9]+|GPU-[A-Za-z0-9-]+)", gpu):
        raise ValueError("--gpu must name one GPU index or UUID")
    if executable := shutil.which("nvidia-smi"):
        result = subprocess.run(
            [executable, "--id", gpu, "--query-gpu=uuid", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
        )
        resolved = result.stdout.strip()
        if not re.fullmatch(r"GPU-[A-Za-z0-9-]+", resolved):
            raise ValueError("nvidia-smi did not resolve one GPU UUID")
        return resolved
    return gpu


def _embedding_available(endpoint: str, model: str) -> bool:
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/models", timeout=5) as response:
            result = json.load(response)
    except urllib.error.URLError:
        return False
    if model not in [entry["id"] for entry in result.get("data", [])]:
        raise ValueError("existing embedding service exposes the wrong model")
    return True


@contextmanager
def _embedding_service(spec, log_path: Path, *, startup_timeout: float = 600):
    settings = spec.values["embedding"]
    if _embedding_available(settings["endpoint"], settings["model"]):
        yield "existing_service"
        return
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            embedding_argv(spec),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": settings["gpu_uuid"]},
        )
        try:
            deadline = time.monotonic() + startup_timeout
            while not _embedding_available(settings["endpoint"], settings["model"]):
                if process.poll() is not None:
                    raise RuntimeError(f"embedding service exited; inspect {log_path}")
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"embedding startup timed out; inspect {log_path}")
                time.sleep(0.5)
            yield "owned_temporary_service"
        finally:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=10)
            # The leader may have exited while a backend still owns this process group.
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


def bootstrap(gpu: str, jobs: int, root: Path = ROOT) -> dict:
    if jobs < 1:
        raise ValueError("--jobs must be positive")
    os.environ.setdefault("HF_HOME", str(root.parents[2] / "data/huggingface"))
    setup = root / SETUP
    setup.mkdir(parents=True, exist_ok=True)
    with (setup / ".bootstrap.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        gpu = _resolve_gpu(gpu)
        canonical = load_spec(root / "configs/skillsbench.yaml")
        canonical_identity = canonical.identity["identity_hash"]
        if (setup / "binding.json").exists():
            previous = json.loads((setup / "binding.json").read_text())
            if not isinstance(previous, dict) or previous.get("schema") != SCHEMA:
                raise ValueError("skillsbench_local_binding_invalid")
            if previous.get("canonical_identity_hash") == canonical_identity:
                binding = check_binding(root)
                if binding["gpu"] != gpu:
                    raise ValueError("skillsbench_local_gpu_changed; use the existing GPU identity")
                return {**binding, "reused": True}
        build_path = _build_directory(canonical_identity)
        build = root / build_path
        build.mkdir(parents=True, exist_ok=True)
        config_path = build_path / "skillsbench.yaml"
        locks = _lock_template(canonical_identity)
        frozen_matrix = (root / MATRIX_MANIFEST).read_bytes()
        if canonical_json_bytes(json.loads(frozen_matrix)) != frozen_matrix:
            raise ValueError("committed SkillsBench matrix is not canonically encoded")
        logs = Path(tempfile.mkdtemp(prefix="logs-", dir=build))
        evidence = []

        def run(name: str, command: list[str]) -> None:
            path = logs / f"{len(evidence) + 1:02d}-{name}.log"
            _run(command, path)
            evidence.append(path)

        with tempfile.TemporaryDirectory(prefix="candidate-", dir=build) as temporary:
            candidate = Path(temporary) / "skillsbench.yaml"
            candidate.write_text(
                yaml.safe_dump(_local_values(canonical.values, gpu, canonical_identity))
            )
            local = load_spec(candidate)
            embedding = root / "data/embedding/.venv"
            uv = shutil.which("uv")
            if uv is None or shutil.which("docker") is None:
                raise RuntimeError("install uv and Docker Engine/Compose before bootstrap")
            run("docker", ["docker", "info"])
            run("compose", ["docker", "compose", "version"])
            codex = os.environ.get(
                "PINNED_CODEX_DIR", str(root.parents[2] / "data/tools/codex-0.160.1")
            )
            run(
                "codex",
                [sys.executable, str(root / "scripts/install_codex.py"), "--destination", codex],
            )
            run(
                "embedding-venv",
                [uv, "venv", "--allow-existing", "--python", "3.12", str(embedding)],
            )
            python = str(embedding / "bin/python")
            run(
                "embedding-dependencies",
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    python,
                    "-r",
                    str(root / "runtime/embedding-requirements.txt"),
                ],
            )
            run(
                "embedding-model",
                [
                    python,
                    "-c",
                    "import sys; from huggingface_hub import snapshot_download; "
                    "snapshot_download(sys.argv[1], revision=sys.argv[2])",
                    local.values["embedding"]["model"],
                    local.values["embedding"]["revision"],
                ],
            )
            prepare = [
                sys.executable,
                str(root / "scripts/prepare_skillsbench.py"),
                "--config",
                str(candidate),
            ]
            service_log = logs / "embedding-service.log"
            with _embedding_service(local, service_log) as service:
                run("source-and-pool", [*prepare, "--source", "--pool"])
                run("injected-pools-and-indices", [*prepare, "--injected-pools", "--all-indices"])
                # Validate the committed matrix; never rewrite it to accept different vectors.
                validate_matrix_manifest(local)
                if (root / MATRIX_MANIFEST).read_bytes() != frozen_matrix:
                    raise ValueError("frozen SkillsBench matrix changed during preparation")
            if service_log.exists():
                evidence.append(service_log)
            run(
                "task-images",
                [
                    *prepare,
                    "--docker",
                    "--all-tasks",
                    "--jobs",
                    str(jobs),
                    "--runtime-lock",
                    str(root / locks),
                ],
            )
            if load_spec(canonical.path).identity["identity_hash"] != canonical_identity:
                raise ValueError("canonical SkillsBench identity changed during preparation")
            runtime_locks = []
            for task in local.tasks:
                path = root / str(locks).replace("{task_id}", task)
                runtime_locks.append({"path": str(path.relative_to(root)), "sha256": _hash(path)})
            os.replace(candidate, root / config_path)
            local = load_spec(root / config_path)
            binding = {
                "schema": SCHEMA,
                "status": "PREPARED",
                "prepared": True,
                "ready": False,
                "canonical_identity_hash": canonical_identity,
                "config_path": config_path.as_posix(),
                "config_sha256": _hash(root / config_path),
                "identity_hash": local.identity["identity_hash"],
                "gpu": gpu,
                "matrix_sha256": _hash(root / MATRIX_MANIFEST),
                "runtime_locks": runtime_locks,
                "embedding_service": service,
                "evidence": [
                    {"path": str(path.relative_to(root)), "sha256": _hash(path)}
                    for path in evidence
                ],
            }
            _validate_binding(binding, root)
            atomic_json(setup / "binding.json", binding)
            return binding


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", help="GPU index or UUID used for the pinned embedding service")
    parser.add_argument("--jobs", type=int, default=8, help="Parallel official task image builds")
    parser.add_argument(
        "--check", action="store_true", help="Check the existing local binding only"
    )
    args = parser.parse_args()
    if not args.check and args.gpu is None:
        parser.error("--gpu is required for preparation")
    try:
        result = check_binding() if args.check else bootstrap(args.gpu, args.jobs)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"SkillsBench preparation failed: {exc}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
