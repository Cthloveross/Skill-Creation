#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
experiment_root="$(cd "${script_dir}/.." && pwd)"
upstream_root="${experiment_root}/data/upstream/tau2-bench"
uv_bin="${experiment_root}/data/tools/uv-0.12.9/uv-x86_64-unknown-linux-gnu/uv"
python_bin="${experiment_root}/data/python/cpython-3.12.14-linux-x86_64-gnu/bin/python3.12"

test -x "${uv_bin}"
test -x "${python_bin}"
"${uv_bin}" --version | grep -Eq '^uv 0[.]12[.]9( |$)'
"${python_bin}" -c 'import platform; print(platform.python_version())' | grep -Fqx "3.12.14"
test "$(git -C "${upstream_root}" rev-parse HEAD)" = "fc0055dc4e0a316c3f83133267fbd6faaa770992"
PYTHONPATH="${experiment_root}/../../../src" "${python_bin}" -c \
  'import json; from r2sp_tau_knowledge.data import verify_tracked_snapshot; print(json.dumps(verify_tracked_snapshot(), sort_keys=True))'
"${uv_bin}" sync --project "${upstream_root}" --frozen --extra knowledge --python "${python_bin}"
PYTHONPATH="${experiment_root}/../../../src" "${upstream_root}/.venv/bin/python" -c \
  'import tau2, r2sp_tau_knowledge; print("tau runtime ready")'
