"""Re-run the unchanged ready004 fixture using a credential-free environment.

Only this launcher and public machine summaries are publication candidates.
The full fixture JSON and process log remain mode 0600 and private.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


EVIDENCE = Path(__file__).resolve().parent
EXPERIMENT = EVIDENCE.parents[2]
REPO = EXPERIMENT.parents[2]
SOURCE = EXPERIMENT / "src/tau_skill_evolution"
OLD_FIXTURE = (
    EXPERIMENT
    / "runs/readiness-skillsbench-native-controller-20261008-004/evidence"
    / "full-controller-context-native-codex-real-grader-fixture.py"
)
FIXTURE = EVIDENCE / OLD_FIXTURE.name
EXPECTED_FIXTURE_HASH = "da2863ac492e78927b152054b929062b8da4f19b4103c2b0159e773e3dbde53a"
MODES = sys.argv[1:] or ["observed", "predispatch"]
assert MODES and all(mode in {"observed", "predispatch"} for mode in MODES)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def source_hashes() -> dict[str, str]:
    paths = [
        p
        for p in SOURCE.rglob("*")
        if p.is_file() and p.suffix in {".py", ".json", ".txt", ".md", ".html"}
        and "__pycache__" not in p.parts
    ]
    paths.append(EXPERIMENT / "tests/skill_evolution/test_workflow.py")
    paths.append(EXPERIMENT / "runtime/skillsbench-docker-dialogue-parser-v4-lock.json")
    return {p.relative_to(EXPERIMENT).as_posix(): digest(p) for p in sorted(paths)}


def docker_inventory(env: dict[str, str]) -> list[dict[str, str]]:
    completed = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{json .}}"],
        env=env, cwd=REPO, capture_output=True, text=True, check=True,
    )
    return [
        {key: entry[key] for key in ("ID", "Names", "Image", "Status")}
        for entry in map(json.loads, completed.stdout.splitlines())
    ]


def public_fixture(raw: dict, mode: str, raw_path: Path) -> dict:
    keys = (
        "scenario", "context_mode", "status", "paid_model_calls", "real_model_scores",
        "model_source", "official_grader", "fixture_base_hash", "fixture_source_initial_hash",
        "fixture_initial_hash", "fixture_adaptation", "source_commit", "max_episodes",
        "max_surrogate_retries", "max_oracles", "budget_scope", "source_hashes_at_start",
        "source_hashes_at_finish", "fixture_script_sha256", "fresh_package_checks",
        "real_official_grader_calls", "scripted_Codex_requests", "core_calls",
        "raw_controller_sha256", "local_model_requests", "shared_dependency_and_service",
        "fixed_suite_reused", "candidate_legal_attachments_and_cache_exercised",
        "oracle_best_independent_full_hash_match", "generator_verifier_separate_clients",
        "fresh_environment_separation", "container_residuals", "cleanup_calls",
        "unique_cleanup_verified", "cleanup_verified", "source_unchanged_during_execution",
        "limitations", "code_path",
    )
    public = {key: raw[key] for key in keys if key in raw}
    public.update(
        workflow_gate_exercised=False,
        cleanup_failure_injected=False,
        close_failure_gate_acceptance="NOT_EXERCISED_BY_THIS_DOCKER_FIXTURE",
        raw_private_evidence_sha256=digest(raw_path),
        raw_private_evidence_mode=oct(raw_path.stat().st_mode & 0o777),
    )
    public["limitations"] = [
        *public.get("limitations", []),
        "The entry point is run_author_evolution and adapter.evaluate; Workflow._learning and its persistent close-failure gate are not executed.",
        "Successful unique Docker cleanup is observed; this fixture does not inject cleanup failure or validate the failure boundary.",
        "Any official reward below describes deterministic scripted fixture execution, not model performance.",
    ]
    result = raw.get("result", {})
    public["result"] = {
        "stop_reason": result.get("stop_reason"),
        "author_counters": result.get("author_counters"),
        "final_bundle_hash": result.get("final_bundle_hash"),
        "versions": [
            {key: value.get(key) for key in ("bundle_hash", "parent_hash")}
            for value in result.get("versions", [])
        ],
        "oracle_history": [
            {key: value.get(key) for key in (
                "phase", "status", "bundle_hash", "parent_hash", "passed",
                "canonical_reward", "resolved_reward", "tests_passed", "total_tests",
            )}
            for value in result.get("oracle_history", [])
        ],
    }
    independent = raw.get("independent_evaluation", {})
    public["independent_evaluation"] = {
        key: independent.get(key) for key in (
            "status", "utility", "reward", "execution_termination_reason", "official_checks",
        )
    }
    write_json(EVIDENCE / f"full-controller-context-{mode}-public.json", public)
    return public


assert digest(OLD_FIXTURE) == EXPECTED_FIXTURE_HASH
if FIXTURE.exists():
    assert digest(FIXTURE) == EXPECTED_FIXTURE_HASH
else:
    shutil.copyfile(OLD_FIXTURE, FIXTURE)
home = Path(tempfile.mkdtemp(prefix="native-crosscheck-empty-home-", dir="/tmp"))
home.chmod(0o700)
# The installed Compose plugin is a binary under the user's home. Expose only
# that executable to Docker's clean HOME, never the user's Docker config.
compose_binary = Path("/home/tc442/.docker/cli-plugins/docker-compose")
plugin_dir = home / ".docker/cli-plugins"
plugin_dir.mkdir(parents=True, mode=0o700)
(plugin_dir / "docker-compose").symlink_to(compose_binary)
environment = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": str(home),
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONPATH": str(EXPERIMENT / "src"),
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONUNBUFFERED": "1",
}
compose_version = subprocess.run(
    ["docker", "compose", "version"], env=environment, cwd=REPO,
    capture_output=True, text=True, check=True,
).stdout.strip()
started = datetime.now(timezone.utc).isoformat()
before = source_hashes()
manifest = json.loads((SOURCE / "author/VERIFIER_SOURCE.json").read_text())
author_matches = {
    relative: digest(SOURCE / "author" / relative) == entry["sha256"]
    for relative, entry in manifest["files"].items()
}
docker_before = docker_inventory(environment)
summaries = []
try:
    for mode in MODES:
        raw_path = EVIDENCE / f"full-controller-context-{mode}-private.json"
        public_path = EVIDENCE / f"full-controller-context-{mode}-public.json"
        log_path = EVIDENCE / f"full-controller-context-{mode}.private.log"
        assert not any(path.exists() for path in (raw_path, public_path, log_path))
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as log:
            completed = subprocess.run(
                [str(REPO / ".venv/bin/python"), str(FIXTURE)],
                cwd=REPO,
                env={**environment, "TAU_NATIVE_CONTEXT_FIXTURE": mode},
                stdout=log, stderr=subprocess.STDOUT,
            )
        raw_path.chmod(0o600)
        public = public_fixture(json.loads(raw_path.read_text()), mode, raw_path)
        summary = {
            "mode": mode,
            "process_returncode": completed.returncode,
            "fixture_status": public.get("status"),
            "paid_model_calls": public.get("paid_model_calls"),
            "public_evidence_sha256": digest(public_path),
            "private_process_log_sha256": digest(log_path),
            "private_process_log_mode": oct(log_path.stat().st_mode & 0o777),
            "cleanup_verified": public.get("cleanup_verified"),
            "source_unchanged_during_execution": public.get("source_unchanged_during_execution"),
        }
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
        if completed.returncode or public.get("status") != "PASS":
            break
finally:
    after = source_hashes()
    docker_after = docker_inventory(environment)
    new_containers = [
        item for item in docker_after
        if item["ID"] not in {entry["ID"] for entry in docker_before}
    ]
    proof = {
        "scenario": "current_v6_free_native_docker_crosscheck",
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if len(summaries) == len(MODES) and all(
            row["process_returncode"] == 0 and row["fixture_status"] == "PASS"
            and row["cleanup_verified"] and row["source_unchanged_during_execution"]
            for row in summaries
        ) and before == after and not new_containers and all(author_matches.values()) else "FAIL",
        "model_source": "MODEL_SCRIPTED",
        "paid_model_calls": 0,
        "real_model_scores": "NOT_MEASURED",
        "credential_controls": {
            "child_environment_is_explicit_allowlist": True,
            "empty_temporary_home_used": True,
            "real_credential_environment_variables_forwarded": False,
            "key_env_auth_or_credential_files_read_by_launcher": False,
            "fake_local_fixture_key_set_by_original_fixture": True,
            "only_installed_compose_executable_linked_into_empty_home": True,
            "real_docker_config_or_auth_copied": False,
        },
        "compose_version": compose_version,
        "compose_binary_sha256": digest(compose_binary),
        "fixture_source": str(OLD_FIXTURE.relative_to(REPO)),
        "fixture_source_sha256_at_start": EXPECTED_FIXTURE_HASH,
        "fixture_source_sha256_at_finish": digest(OLD_FIXTURE),
        "copied_fixture_sha256": digest(FIXTURE),
        "fixture_copy_is_byte_identical": digest(FIXTURE) == EXPECTED_FIXTURE_HASH,
        "launcher_sha256": digest(Path(__file__)),
        "source_hashes_at_start": before,
        "source_hashes_at_finish": after,
        "source_unchanged_during_execution": before == after,
        "author_original_file_count": len(author_matches),
        "author_original_files_match_pinned_manifest": all(author_matches.values()),
        "author_source_sha256": digest(SOURCE / "author/VERIFIER_SOURCE.json"),
        "docker_inventory_before": docker_before,
        "docker_inventory_after": docker_after,
        "new_container_residuals": new_containers,
        "workflow_gate_exercised": False,
        "cleanup_failure_injected": False,
        "close_failure_gate_acceptance": "NOT_EXERCISED_BY_THIS_DOCKER_FIXTURE",
        "modes": summaries,
    }
    write_json(EVIDENCE / "native-docker-crosscheck-public.json", proof)
    print(json.dumps({key: proof[key] for key in (
        "scenario", "status", "paid_model_calls", "source_unchanged_during_execution",
        "author_original_file_count", "author_original_files_match_pinned_manifest",
        "new_container_residuals", "workflow_gate_exercised",
    )}), flush=True)
assert proof["status"] == "PASS"
