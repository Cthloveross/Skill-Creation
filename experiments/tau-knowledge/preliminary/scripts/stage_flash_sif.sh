#!/usr/bin/env bash
# Prepare the pinned runtime before GPU submission. No model service is started.
set -euo pipefail
run_user="$(id -un)"
runtime_root="/usr/xtmp/${run_user}/skill-creation"
image_directory="${runtime_root}/images"
output="${image_directory}/vllm-qwen38-flash-next-amd64.sif"
source_uri='docker://vllm/vllm-openai@sha256:0aea30240f3e3d9ffae8526643950e170eb5fa07fc427016a9dd90892afa2aa3'
if [[ $# -ne 0 ]]; then
  echo 'Usage: stage_flash_sif.sh (uses the pinned image and shared scratch paths)' >&2
  exit 2
fi
if [[ -e "${output}" || -L "${output}" ]]; then
  echo "Image already exists; validate it with the batch asset validator: ${output}" >&2
  exit 2
fi
mkdir -p "${image_directory}" "/usr/xtmp/${run_user}/.cache/apptainer"
export APPTAINER_CACHEDIR="/usr/xtmp/${run_user}/.cache/apptainer"
export APPTAINER_TMPDIR="${image_directory}"
# Default mksquashfs parallelism can exhaust a login session's memory allowance.
apptainer build --mksquashfs-args '-processors 2 -mem 1G' "${output}" "${source_uri}"
python3 - "${output}" "${source_uri}" <<'PY'
import hashlib
import json
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
    'source_uri': sys.argv[2],
    'path': str(path),
    'sha256': digest.hexdigest(),
    'size_bytes': path.stat().st_size,
    'created_at': datetime.now(timezone.utc).isoformat(),
    'mksquashfs_args': '-processors 2 -mem 1G',
}
with path.with_suffix('.receipt.json').open('x') as stream:
    json.dump(record, stream, indent=2, sort_keys=True)
    stream.write('\n')
print(json.dumps(record, sort_keys=True))
PY
