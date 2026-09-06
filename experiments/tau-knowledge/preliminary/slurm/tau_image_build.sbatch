#!/usr/bin/env bash
#SBATCH --job-name=tau-flash-image
#SBATCH --partition=compsci
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=/usr/xtmp/%u/skill-creation/logs/%x-%j.out
#SBATCH --error=/usr/xtmp/%u/skill-creation/logs/%x-%j.err

# Package an already downloaded official rootfs; no network fetch occurs here.
set -euo pipefail
[[ $# == 2 ]] || { echo 'expected staged rootfs and output SIF paths' >&2; exit 2; }
staged_rootfs="$1"
output_sif="$2"
[[ -d "${staged_rootfs}/.singularity.d" && ! -e "${output_sif}" ]] || exit 2
run_user="$(id -un)"
export HF_HOME="/usr/xtmp/${run_user}/.cache/huggingface"
export TORCH_HOME="/usr/xtmp/${run_user}/.cache/torch"
export PIP_CACHE_DIR="/usr/xtmp/${run_user}/.cache/pip"
export APPTAINER_CACHEDIR="/usr/xtmp/${run_user}/.cache/apptainer"
export APPTAINER_TMPDIR="/usr/xtmp/${run_user}/skill-creation/images"
nvidia-smi -L 2>/dev/null || echo 'none'
compression_args="-processors ${SLURM_CPUS_PER_TASK} -mem 4G -comp zstd -Xcompression-level 1"
apptainer build --mksquashfs-args "${compression_args}" "${output_sif}" "${staged_rootfs}"
apptainer exec --cleanenv "${output_sif}" python3 -c \
  'import importlib.metadata as m; print(m.version("vllm"))'
python3 - "${output_sif}" "${staged_rootfs}" "${compression_args}" <<'PY'
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
digest = hashlib.sha256()
with path.open('rb') as stream:
    for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
        digest.update(block)
record = {
    'schema_version': 'r2sp.runtime-image-receipt.v1',
    'source_uri': 'docker://vllm/vllm-openai@sha256:0aea30240f3e3d9ffae8526643950e170eb5fa07fc427016a9dd90892afa2aa3',
    'staged_rootfs': sys.argv[2],
    'path': str(path), 'sha256': digest.hexdigest(),
    'size_bytes': path.stat().st_size,
    'created_at': datetime.now(timezone.utc).isoformat(),
    'mksquashfs_args': sys.argv[3],
    'slurm_job_id': os.environ['SLURM_JOB_ID'],
    'network_downloads': False,
}
with path.with_suffix('.receipt.json').open('x') as stream:
    json.dump(record, stream, indent=2, sort_keys=True)
    stream.write('\n')
print(json.dumps(record, sort_keys=True))
PY
