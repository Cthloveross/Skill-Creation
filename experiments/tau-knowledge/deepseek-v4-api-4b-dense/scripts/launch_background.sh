#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
EXPERIMENT_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
REPOSITORY_ROOT=$(cd -- "${EXPERIMENT_ROOT}/../../.." && pwd)
BACKGROUND_ROOT="${EXPERIMENT_ROOT}/runs/background"
LOCK_PATH="${BACKGROUND_ROOT}/launcher.lock"
PID_PATH="${BACKGROUND_ROOT}/pipeline.pid"
LOG_PATH="${BACKGROUND_ROOT}/pipeline.log"
LAUNCHER_PATH="${BACKGROUND_ROOT}/launcher.json"
STATE_PATH="${BACKGROUND_ROOT}/pipeline-state.json"
PYTHON_BIN=${PYTHON_BIN:-"${REPOSITORY_ROOT}/.venv/bin/python"}
RUNTIME_PROFILE=deepseek-v4-flash-formal-v1

mkdir -p -- "${BACKGROUND_ROOT}"
umask 077

if [[ ! -x "${PYTHON_BIN}" ]]; then
    printf 'Python interpreter is not executable: %s\n' "${PYTHON_BIN}" >&2
    exit 1
fi

if [[ -f "${PID_PATH}" ]]; then
    existing_pid=$(tr -d '[:space:]' < "${PID_PATH}")
    if [[ "${existing_pid}" =~ ^[0-9]+$ ]] && kill -0 "${existing_pid}" 2>/dev/null; then
        printf 'Pipeline already running with PID %s\n' "${existing_pid}"
        exit 0
    fi
fi

nohup setsid --fork --wait \
    flock -n "${LOCK_PATH}" \
    "${PYTHON_BIN}" "${SCRIPT_DIR}/run_experiment.py" pipeline \
    --runtime-profile "${RUNTIME_PROFILE}" \
    --wait-for-gpu \
    --poll-seconds 30 \
    --state-path "${STATE_PATH}" \
    >> "${LOG_PATH}" 2>&1 < /dev/null &

pipeline_pid=""
for _attempt in $(seq 1 50); do
    pipeline_pid=$("${PYTHON_BIN}" - "${STATE_PATH}" "${SCRIPT_DIR}/run_experiment.py" "${RUNTIME_PROFILE}" <<'PY'
import json
import pathlib
import sys

state_path = pathlib.Path(sys.argv[1])
runner = str(pathlib.Path(sys.argv[2]).resolve())
profile = sys.argv[3]
try:
    state = json.loads(state_path.read_bytes())
    pid = state.get("pipeline_pid")
    command = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
except (OSError, TypeError, ValueError, json.JSONDecodeError):
    raise SystemExit(0)
decoded = [item.decode("utf-8", "strict") for item in command if item]
if isinstance(pid, int) and runner in decoded and "pipeline" in decoded and profile in decoded:
    print(pid)
PY
    )
    if [[ "${pipeline_pid}" =~ ^[0-9]+$ ]] && kill -0 "${pipeline_pid}" 2>/dev/null; then
        break
    fi
    pipeline_pid=""
    sleep 0.1
done
if [[ -z "${pipeline_pid}" ]]; then
    printf 'Background API pipeline failed to publish a live PID; inspect %s\n' "${LOG_PATH}" >&2
    exit 1
fi
printf '%s\n' "${pipeline_pid}" > "${PID_PATH}"

started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '{"pipeline_pid":%s,"runtime_profile":"%s","log":"%s","pipeline_state":"%s","started_at":"%s","status":"STARTED"}\n' \
    "${pipeline_pid}" "${RUNTIME_PROFILE}" "${LOG_PATH}" "${STATE_PATH}" "${started_at}" > "${LAUNCHER_PATH}"
printf 'Started DeepSeek formal pipeline PID %s; log: %s\n' "${pipeline_pid}" "${LOG_PATH}"
