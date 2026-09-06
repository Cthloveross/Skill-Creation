#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd "${script_dir}/../../../.." && pwd)"
python_binary="${R2SP_BATCH_PYTHON:-${repository_root}/.venv/bin/python}"
[[ -x "${python_binary}" ]] || { echo "project Python is missing: ${python_binary}" >&2; exit 2; }
export PYTHONPATH="${repository_root}/src"
exec "${python_binary}" "${script_dir}/submit_batch.py" evaluate "$@"
