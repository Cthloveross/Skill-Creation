#!/usr/bin/env bash
#SBATCH --job-name=tau-benign-qualification
#SBATCH --partition=compsci-gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=512G
#SBATCH --time=02:00:00
#SBATCH --gres=gpu:rtx_pro_6000:4
#SBATCH --output=/usr/xtmp/%u/skill-creation/logs/%x-%j.out
#SBATCH --error=/usr/xtmp/%u/skill-creation/logs/%x-%j.err

set -euo pipefail
[[ $# == 2 ]] || { echo 'expected sealed request path and SHA-256' >&2; exit 2; }
run_user="$(id -un)"
export HF_HOME="/usr/xtmp/${run_user}/.cache/huggingface"
export TORCH_HOME="/usr/xtmp/${run_user}/.cache/torch"
export PIP_CACHE_DIR="/usr/xtmp/${run_user}/.cache/pip"
export XDG_CACHE_HOME="/usr/xtmp/${run_user}/.cache"
export OMP_NUM_THREADS=4
nvidia-smi -L 2>/dev/null || echo 'none'

python3 - "$1" "$2" <<'PY'
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

path = Path(sys.argv[1])
raw = path.read_bytes()
if path.is_symlink() or hashlib.sha256(raw).hexdigest() != sys.argv[2]:
    raise SystemExit("qualification request digest mismatch")
request = json.loads(raw)
if request.get("schema_version") != "r2sp.benign-qualification-job.v1":
    raise SystemExit("unsupported qualification request")
source = request["source"]
bundle_path = Path(source["bundle_path"])
if bundle_path.is_symlink() or hashlib.sha256(bundle_path.read_bytes()).hexdigest() != source["bundle_sha256"]:
    raise SystemExit("source bundle digest mismatch")
with tempfile.TemporaryDirectory(prefix="tau-qualification-", dir=os.environ.get("SLURM_TMPDIR", "/var/tmp")) as directory:
    temporary = Path(directory)
    with tarfile.open(bundle_path, "r:") as archive:
        seen = set()
        for member in archive.getmembers():
            relative = PurePosixPath(member.name)
            if (relative.is_absolute() or len(relative.parts) < 2
                or relative.parts[0] != "Skill-Creation"
                or any(part in {"", ".", ".."} for part in relative.parts)
                or str(relative) != member.name or not member.isfile()
                or member.name in seen):
                raise SystemExit("unsafe source bundle member")
            seen.add(member.name)
            target = temporary.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            if stream is None:
                raise SystemExit("unreadable source bundle member")
            target.write_bytes(stream.read())
            target.chmod(0o555 if member.mode & 0o100 else 0o444)
    root = temporary / "Skill-Creation"
    scripts = root / "experiments/tau-knowledge/preliminary/scripts"
    sys.path.insert(0, str(scripts))
    from batch_source import verified_bundle, verify_checkout
    identity, members = verified_bundle(bundle_path, source["bundle_sha256"])
    if (identity["source_manifest_sha256"] != source["manifest_sha256"]
        or identity["source_tree_sha256"] != source["source_tree_sha256"]):
        raise SystemExit("source manifest identity mismatch")
    verify_checkout(root, members)
    runtime = request["runtime_environment"]
    allowed_runtime = {
        "R2SP_TAU_UPSTREAM_ROOT", "R2SP_TAU_MODEL_ROOT", "R2SP_TAU_DENSE_MODEL_ROOT",
        "R2SP_TAU_SIF_PATH", "R2SP_TAU_SIF_SHA256", "R2SP_TAU_RUNTIME_ROOT",
        "R2SP_TAU_MODEL_SNAPSHOT_SHA256", "R2SP_TAU_DENSE_SNAPSHOT_SHA256", "R2SP_TAU_PYTHON",
    }
    if set(runtime) - allowed_runtime:
        raise SystemExit("unsupported runtime environment key")
    upstream = Path(runtime["R2SP_TAU_UPSTREAM_ROOT"])
    link = root / "experiments/tau-knowledge/preliminary/data/upstream/tau2-bench"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(upstream, target_is_directory=True)
    spec_path = temporary / "creation-spec.json"
    spec_path.write_text(json.dumps(request["spec"], sort_keys=True))
    command = [str(upstream / ".venv/bin/python"), str(scripts / "qualify_batch_runtime.py"),
               "--spec", str(spec_path), "--output", request["output"]]
    if request["compiler_input"] is not None:
        compiler_path = temporary / "compiler-input.json"
        compiler_path.write_text(json.dumps(request["compiler_input"], sort_keys=True))
        command += ["--compiler-input", str(compiler_path)]
    if request["retrieval_queries"] is not None:
        queries_path = temporary / "retrieval-queries.json"
        queries_path.write_text(json.dumps(request["retrieval_queries"], sort_keys=True))
        command += ["--retrieval-queries", str(queries_path)]
    inherited = {
        "PATH", "USER", "LANG", "LC_ALL", "CUDA_VISIBLE_DEVICES", "HF_HOME", "TORCH_HOME",
        "PIP_CACHE_DIR", "XDG_CACHE_HOME", "SLURM_JOB_ID", "SLURM_JOBID", "SLURM_JOB_GPUS",
        "SLURM_STEP_GPUS", "SLURM_CPUS_PER_TASK", "TMPDIR", "SLURM_TMPDIR", "OMP_NUM_THREADS",
    }
    environment = {key: value for key, value in os.environ.items() if key in inherited}
    environment.update(runtime)
    environment.update({
        "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1",
        "R2SP_TAU_SOURCE_BUNDLE": str(bundle_path),
        "R2SP_TAU_SOURCE_BUNDLE_SHA256": source["bundle_sha256"],
    })
    raise SystemExit(subprocess.call(command, cwd=root, env=environment))
PY
