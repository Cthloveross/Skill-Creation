#!/usr/bin/env bash
set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(git -C "$HERE" rev-parse --show-toplevel)
SB="$ROOT/experiments/tau-knowledge/skill-evolution"
CFG="$SB/configs/skillsbench.yaml"
R2SP="$ROOT/.venv/bin/r2sp"
PY="$ROOT/.venv/bin/python"
PINNED_CODEX_DIR=${PINNED_CODEX_DIR:-/home/tc442/.local/skillsbench-codex-0.160.1}
export PATH="$PINNED_CODEX_DIR:$PATH"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

usage() {
  cat <<'USAGE'
Usage: operator.sh COMMAND

Review/preparation:
  verify                 Check audit snapshots, 85x9 matrix, tools, and pinned Codex.
  prepare-data           Prepare pinned source, nine corpora, all indices, and matrix.
  prepare-docker         Build/check all 85 task environments (PREP_JOBS defaults to 8).

Required gates and controls:
  preflight-all          Save a fresh 85-task preflight at $ALL_PREFLIGHT.
  check-preflight        Check the saved source-bound 85-task preflight without model calls.
  smoke                  Run the paid payload smoke at $SMOKE_RUN, then check its evidence.
  check-smoke            Check an already completed $SMOKE_RUN without model calls.
  noskill                Evaluate all 85 NoSkill controls in $RUN_DIR, then check coverage.
  check-noskill          Check NoSkill coverage in $RUN_DIR without model calls.
  gates                   Require verify + all-task preflight + smoke + 85 NoSkill results.

Primary matrix:
  matrix                 Launch all frozen 765 Skill cells after all gates pass.
  resume                 Relaunch nonzero/incomplete launcher cells in the same $RUN_DIR.
  report                 Rebuild report.json/REPORT.md deterministically.

Required environment for paid operations:
  RUN_DIR                 One empty primary-run path; NoSkill and the 765 cells share it.
  AWS_BEARER_TOKEN_BEDROCK_FILE
                          Private atomically refreshed token JSON for preflight/smoke/NoSkill.
  TOKEN_DIR               Private directory of <AWS-account-id>.json token files for matrix.
  ACCOUNT_IDS             Optional comma-separated account IDs; otherwise TOKEN_DIR is scanned.
  MAX_CONCURRENT          Matrix concurrency (default 16).

Gate paths and smoke defaults:
  ALL_PREFLIGHT           Default: $RUN_DIR/preflight-all.json
  SMOKE_RUN               Required smoke run directory, separate from RUN_DIR.
  SMOKE_TASK              Default: manufacturing-codebook-normalization
  SMOKE_ARM               Default: data-exfil-http-5

Task-specific credentials are passed only through the scoped environment variables described
in HANDOFF.md. This script never reads key.env and never stores credential values.
USAGE
}

need_project() {
  test -x "$R2SP" || fail "missing $R2SP; run make setup"
  test -x "$PY" || fail "missing $PY; run make setup"
}

need_run_dir() {
  test -n "${RUN_DIR:-}" || fail "set RUN_DIR to the primary trial directory"
  RUN_DIR=$(realpath -m "$RUN_DIR")
  ALL_PREFLIGHT=${ALL_PREFLIGHT:-$RUN_DIR/preflight-all.json}
}

need_smoke_dir() {
  test -n "${SMOKE_RUN:-}" || fail "set SMOKE_RUN to a separate smoke trial directory"
  SMOKE_RUN=$(realpath -m "$SMOKE_RUN")
  SMOKE_TASK=${SMOKE_TASK:-manufacturing-codebook-normalization}
  SMOKE_ARM=${SMOKE_ARM:-data-exfil-http-5}
  test "$SMOKE_RUN" != "${RUN_DIR:-}" || fail "SMOKE_RUN must differ from RUN_DIR"
}

need_single_token() {
  test -n "${AWS_BEARER_TOKEN_BEDROCK_FILE:-}" || \
    fail "set AWS_BEARER_TOKEN_BEDROCK_FILE to a private refreshed token JSON"
  test -f "$AWS_BEARER_TOKEN_BEDROCK_FILE" || fail "Bedrock token file does not exist"
  "$PY" - "$SB" "$AWS_BEARER_TOKEN_BEDROCK_FILE" <<'PY'
import os, pathlib, stat, sys
sb, path = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
info = path.lstat()
if path.is_symlink() or not stat.S_ISREG(info.st_mode):
    raise SystemExit("Bedrock token path must be a regular file, not a symlink")
if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
    raise SystemExit("Bedrock token file must be owned by the current user with mode 0600")
sys.path.insert(0, str(sb / "src"))
from tau_skill_evolution.credentials import read_token_file
read_token_file(path)
PY
}

verify_bundle() {
  need_project
  command -v docker >/dev/null || fail "docker CLI is missing"
  docker compose version >/dev/null || fail "docker compose is missing"
  docker info >/dev/null || fail "Docker daemon is unavailable"
  test "$(command -v codex || true)" = "$PINNED_CODEX_DIR/codex" || \
    fail "pinned Codex is not first on PATH: $PINNED_CODEX_DIR/codex"
  test "$(sha256sum "$PINNED_CODEX_DIR/codex" | cut -d' ' -f1)" = \
    f34a4d2301892ae96c90097786bfe5dc269f187b6f69faf42a7b357b8c081e35 || \
    fail "pinned Codex binary hash differs"
  "$PY" - "$ROOT" "$HERE" <<'PY'
import hashlib, json, pathlib, sys
root, bundle = map(pathlib.Path, sys.argv[1:])
manifest = json.loads((bundle / "MANIFEST.json").read_text())
if manifest.get("schema") != "skillsbench.full-85-v8-handoff.v2":
    raise SystemExit("handoff manifest schema differs")
if manifest.get("namespace") != "skillsbench.skill-evolution.v8":
    raise SystemExit("handoff namespace differs")
for item in manifest["entries"]:
    snapshot = bundle / item["snapshot"]
    canonical = root / item["canonical_source"]
    for label, path in (("snapshot", snapshot), ("canonical", canonical)):
        if not path.is_file():
            raise SystemExit(f"missing {label}: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise SystemExit(f"{label} hash differs: {path}")
commitment = manifest.get("source_commitment") or {}
if commitment.get("schema") != "skillsbench.runtime-source-commitment.v1" or not commitment.get(
    "canonical_files"
):
    raise SystemExit("handoff source commitment is missing or invalid")
sys.path.insert(0, str(root / "experiments/tau-knowledge/skill-evolution/src"))
from tau_skill_evolution.spec import load_spec
spec = load_spec(root / "experiments/tau-knowledge/skill-evolution/configs/skillsbench.yaml")
if spec.identity["identity_hash"] != commitment.get("spec_identity_hash"):
    raise SystemExit("canonical runtime/spec identity differs from the handoff commitment")
for item in commitment.get("canonical_files", []):
    path = root / item["path"]
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
        raise SystemExit(f"canonical operator dependency differs: {path}")
matrix = json.loads((bundle / "snapshots/skillsbench-dymal4-matrix.json").read_text())
conditions = json.loads((bundle / "snapshots/skillsbench-dymal4-conditions.json").read_text())
if matrix.get("namespace") != "skillsbench.skill-evolution.v8":
    raise SystemExit("matrix namespace differs")
cells = matrix.get("cells", [])
tasks = {cell["task_id"] for cell in cells}
arms = {cell["condition_id"] for cell in cells}
expected = {
    "benign", "credential-abuse-5", "credential-abuse-10",
    "data-exfil-http-5", "data-exfil-http-10", "file-delete-5",
    "file-delete-10", "cpu-hijack-5", "cpu-hijack-10",
}
if len(tasks) != 85 or arms != expected or len(cells) != 765:
    raise SystemExit(f"bad frozen population: tasks={len(tasks)} arms={len(arms)} cells={len(cells)}")
if len(conditions.get("arms", {})) != 9:
    raise SystemExit("condition snapshot does not contain nine conditions")
print("handoff snapshots: OK; tasks=85 arms=9 cells=765")
PY
  printf 'pinned Codex: %s\n' "$(codex --version)"
}

handoff_binding() {
  "$PY" - "$SB" "$HERE" <<'PY'
import hashlib, pathlib, sys
sb, bundle = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(sb / "src"))
from tau_skill_evolution.spec import load_spec
spec = load_spec(sb / "configs/skillsbench.yaml")
print(spec.identity["identity_hash"])
print(hashlib.sha256((bundle / "MANIFEST.json").read_bytes()).hexdigest())
PY
}

save_preflight() {
  local output=$1
  shift
  mkdir -p "$(dirname "$output")"
  local temporary="${output}.tmp.$$"
  local before_file="${temporary}.binding-before"
  local after_file="${temporary}.binding-after"
  local -a binding_before binding_after
  handoff_binding > "$before_file"
  mapfile -t binding_before < "$before_file"
  set +e
  "$R2SP" preflight --experiment skillsbench --runtime docker --config "$CFG" "$@" \
    > "$temporary"
  local status=$?
  set -e
  handoff_binding > "$after_file"
  mapfile -t binding_after < "$after_file"
  rm -f "$before_file" "$after_file"
  if test "${#binding_before[@]}" -ne 2 || test "${#binding_after[@]}" -ne 2 || \
     test "${binding_before[0]}" != "${binding_after[0]}" || \
     test "${binding_before[1]}" != "${binding_after[1]}"; then
    rm -f "$temporary"
    fail "handoff manifest or experiment identity changed while preflight was running"
  fi
  mv "$temporary" "$output"
  "$PY" - "$output" "${binding_before[0]}" "${binding_before[1]}" <<'PY'
import datetime, json, pathlib, sys
p, spec_identity, manifest_digest = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
try:
    value = json.loads(p.read_text())
except Exception as exc:
    raise SystemExit(f"invalid preflight JSON {p}: {exc}")
value["handoff_gate"] = {
    "schema": "skillsbench.full-85-v8-preflight.v1",
    "runtime": "docker",
    "spec_identity_hash": spec_identity,
    "handoff_manifest_sha256": manifest_digest,
    "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
print(f"preflight ready={value.get('ready')} record={p}")
PY
  return "$status"
}

check_all_preflight() {
  need_run_dir
  "$PY" - "$SB" "$HERE" "$ALL_PREFLIGHT" <<'PY'
import hashlib, json, pathlib, sys
sb, bundle, p = map(pathlib.Path, sys.argv[1:])
if not p.is_file():
    raise SystemExit(f"missing all-task preflight: {p}")
value = json.loads(p.read_text())
sys.path.insert(0, str(sb / "src"))
from tau_skill_evolution.spec import load_spec
spec = load_spec(sb / "configs/skillsbench.yaml")
expected_binding = {
    "schema": "skillsbench.full-85-v8-preflight.v1",
    "runtime": "docker",
    "spec_identity_hash": spec.identity["identity_hash"],
    "handoff_manifest_sha256": hashlib.sha256((bundle / "MANIFEST.json").read_bytes()).hexdigest(),
}
binding = value.get("handoff_gate") or {}
if any(binding.get(name) != expected for name, expected in expected_binding.items()):
    raise SystemExit("all-task preflight is not bound to the current handoff/spec/runtime")
checks = value.get("checks", [])
environments = [x for x in checks if str(x.get("name", "")).startswith("skillsbench_environment:")]
if value.get("namespace") != "skillsbench.skill-evolution.v8" or value.get("ready") is not True:
    raise SystemExit("all-task preflight is not ready for v8")
expected_names = {f"skillsbench_environment:{task}" for task in spec.tasks}
observed_names = [str(item.get("name")) for item in environments]
if (
    len(observed_names) != len(expected_names)
    or set(observed_names) != expected_names
    or not all(x.get("ok") is True for x in environments)
):
    raise SystemExit(f"preflight covers {len(environments)}/85 task environments")
print(f"all-task preflight gate: PASS ({len(environments)}/85 environments)")
PY
}

check_smoke() {
  need_run_dir
  need_smoke_dir
  "$R2SP" report --experiment skillsbench --runtime docker --config "$CFG" \
    --run-dir "$SMOKE_RUN"
  "$PY" - "$SB" "$SMOKE_RUN" "$SMOKE_TASK" "$SMOKE_ARM" <<'PY'
import json, pathlib, re, sys
sb, run, task, arm = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3], sys.argv[4]
sys.path.insert(0, str(sb / "src"))
from tau_skill_evolution.artifacts import load_bundle
from tau_skill_evolution.skillsbench_attack import adapted_payload
from tau_skill_evolution.skillsbench_attack_runtime import parse_condition, static_attack_persistence
condition = parse_condition(arm)
if not condition.poisoned:
    raise SystemExit("smoke arm must be one of the eight injected conditions")
cell_root = run / "cells" / task / arm
base_path = cell_root / "base"
report_path = run / "report.json"
if not base_path.is_file() or not report_path.is_file():
    raise SystemExit("smoke lacks sealed base or report")
base = json.loads(base_path.read_text())
full_payload_documents = 0
for document in base.get("documents", []):
    content = document.get("content", "")
    match = re.match(r"# ([^\r\n]+)", content)
    if match and adapted_payload(condition.profile, match.group(1)).rstrip("\n") in content:
        full_payload_documents += 1
if full_payload_documents < 1:
    raise SystemExit("smoke B* contains no complete active payload")
report = json.loads(report_path.read_text())
matching = [c for c in report.get("cases", []) if c.get("task_id") == task and c.get("condition") == arm]
if len(matching) != 1:
    raise SystemExit("smoke report lacks the unique requested cell")
case = matching[0]
creation = case.get("creation", {})
initial_hash = creation.get("initial_bundle_hash")
if creation.get("status") != "CREATED" or not initial_hash:
    raise SystemExit("smoke did not seal S0")
initial = load_bundle(cell_root / "initial")
static = static_attack_persistence(initial, condition.profile)
if static.get("status") != "DETECTED" or static.get("rate") != 1.0:
    raise SystemExit(f"S0 lacks complete static payload anchors: {static}")
versions = {v.get("bundle_hash") for v in case.get("versions", [])}
evaluations = case.get("evaluations", {})
if not versions or set(evaluations) != versions:
    raise SystemExit("smoke does not have one independent evaluation per sealed content version")
for digest in versions:
    result = evaluations[digest]
    if result.get("status") != "MEASURED" or result.get("asr_status") != "MEASURED":
        raise SystemExit(f"version {digest} lacks measured utility or dynamic attack outcome")
if not case.get("verifications"):
    raise SystemExit("smoke lacks Verifier evidence")
if int(case.get("oracle_calls") or 0) < 1:
    raise SystemExit("smoke lacks a completed fresh oracle call")
unknown = []
for state in cell_root.glob("journal/*/state.json"):
    try:
        if json.loads(state.read_text()).get("status") == "UNKNOWN":
            unknown.append(str(state))
    except (OSError, ValueError):
        unknown.append(str(state))
if unknown:
    raise SystemExit(f"smoke has UNKNOWN journal operations: {len(unknown)}")
print(
    "payload smoke gate: PASS; "
    f"full_payload_documents={full_payload_documents} versions={len(versions)} "
    f"oracle_calls={case.get('oracle_calls')} stop={case.get('stop_reason')}"
)
PY
}

check_noskill() {
  need_run_dir
  "$R2SP" report --experiment skillsbench --runtime docker --config "$CFG" \
    --run-dir "$RUN_DIR"
  "$PY" - "$RUN_DIR/report.json" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
report = json.loads(p.read_text())
benign = [c for c in report.get("cases", []) if c.get("condition") == "benign"]
measured = [c for c in benign if (c.get("no_skill_evaluation") or {}).get("status") == "MEASURED"]
if len(benign) != 85 or len(measured) != 85:
    raise SystemExit(f"NoSkill coverage is {len(measured)}/85 (benign cases={len(benign)})")
print("NoSkill gate: PASS (85/85 measured once on benign task environments)")
PY
}

command=${1:-}
case "$command" in
  verify)
    verify_bundle
    ;;
  prepare-data)
    verify_bundle
    "$PY" "$SB/scripts/prepare_skillsbench.py" --config "$CFG" --source --pool
    "$PY" "$SB/scripts/prepare_skillsbench.py" --config "$CFG" \
      --injected-pools --all-indices --freeze-matrix
    verify_bundle
    ;;
  prepare-docker)
    verify_bundle
    "$PY" "$SB/scripts/prepare_skillsbench.py" --config "$CFG" \
      --docker --all-tasks --jobs "${PREP_JOBS:-8}" \
      --runtime-lock "$SB/runtime/skillsbench-docker-{task_id}-v4-lock.json"
    ;;
  preflight-all)
    verify_bundle
    need_run_dir
    need_single_token
    save_preflight "$ALL_PREFLIGHT"
    check_all_preflight
    ;;
  check-preflight)
    verify_bundle
    check_all_preflight
    ;;
  smoke)
    verify_bundle
    need_run_dir
    need_smoke_dir
    need_single_token
    mkdir -p "$(dirname "$SMOKE_RUN")"
    save_preflight "${SMOKE_RUN}-preflight.json" --task "$SMOKE_TASK"
    "$R2SP" run --experiment skillsbench --runtime docker --config "$CFG" \
      --task "$SMOKE_TASK" --arm "$SMOKE_ARM" --run-dir "$SMOKE_RUN"
    check_smoke
    ;;
  check-smoke)
    verify_bundle
    check_smoke
    ;;
  noskill)
    verify_bundle
    need_run_dir
    need_single_token
    check_all_preflight
    mkdir -p "$RUN_DIR"
    "$R2SP" evaluate --experiment skillsbench --runtime docker --config "$CFG" \
      --run-dir "$RUN_DIR" --arm benign --no-skill
    check_noskill
    ;;
  check-noskill)
    verify_bundle
    check_noskill
    ;;
  gates)
    verify_bundle
    check_all_preflight
    check_smoke
    check_noskill
    ;;
  matrix)
    verify_bundle
    need_run_dir
    need_smoke_dir
    test -n "${TOKEN_DIR:-}" || fail "set TOKEN_DIR for the parallel matrix launcher"
    test -d "$TOKEN_DIR" || fail "TOKEN_DIR does not exist"
    check_all_preflight
    check_smoke
    check_noskill
    args=(
      "$PY" "$SB/scripts/launch_matrix.py"
      --experiment skillsbench --runtime docker --config "$CFG"
      --run-dir "$RUN_DIR" --token-dir "$TOKEN_DIR"
      --max-concurrent "${MAX_CONCURRENT:-16}" --r2sp "$R2SP"
    )
    if test -n "${ACCOUNT_IDS:-}"; then args+=(--accounts "$ACCOUNT_IDS"); fi
    "${args[@]}"
    ;;
  resume)
    verify_bundle
    need_run_dir
    need_smoke_dir
    test -n "${TOKEN_DIR:-}" || fail "set TOKEN_DIR for the parallel matrix launcher"
    test -f "$RUN_DIR/launcher-status.json" || fail "launcher-status.json is missing"
    check_all_preflight
    check_smoke
    check_noskill
    resume_mode=$("$PY" - "$RUN_DIR/launcher-status.json" "$RUN_DIR/resume-cells.json" <<'PY'
import json, pathlib, sys
source, target = map(pathlib.Path, sys.argv[1:])
status = json.loads(source.read_text())
cells = [key for key, value in status.get("cells", {}).items() if value.get("exit_code") != 0]
target.write_text(json.dumps(cells, indent=2) + "\n")
launches = status.get("launches") or []
latest = launches[-1] if isinstance(launches, list) and launches else {}
unfinished_report = (
    latest.get("status") in {"RUNNING", "REPORTING"}
    and latest.get("finished_at") is None
)
print("cells" if cells else "report-only" if unfinished_report else "none")
PY
    )
    if test "$resume_mode" = cells; then
      args=(
        "$PY" "$SB/scripts/launch_matrix.py"
        --experiment skillsbench --runtime docker --config "$CFG"
        --run-dir "$RUN_DIR" --token-dir "$TOKEN_DIR"
        --max-concurrent "${MAX_CONCURRENT:-16}" --r2sp "$R2SP"
        --cells-file "$RUN_DIR/resume-cells.json"
      )
      if test -n "${ACCOUNT_IDS:-}"; then args+=(--accounts "$ACCOUNT_IDS"); fi
      "${args[@]}"
    elif test "$resume_mode" = report-only; then
      "$PY" "$SB/scripts/launch_matrix.py" \
        --experiment skillsbench --runtime docker --config "$CFG" \
        --run-dir "$RUN_DIR" --token-dir "$TOKEN_DIR" --r2sp "$R2SP" \
        --report-only
    else
      printf 'No nonzero or unfinished launcher cells.\n'
    fi
    ;;
  report)
    verify_bundle
    need_run_dir
    "$R2SP" report --experiment skillsbench --runtime docker --config "$CFG" \
      --run-dir "$RUN_DIR"
    ;;
  -h|--help|help|'')
    usage
    ;;
  *)
    usage >&2
    fail "unknown command: $command"
    ;;
esac
