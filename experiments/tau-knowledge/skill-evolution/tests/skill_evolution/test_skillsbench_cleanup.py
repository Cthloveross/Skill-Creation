"""Public command cleanup preserves execution failures and retained staging."""

from __future__ import annotations

import json
import os
import subprocess
from types import SimpleNamespace

import pytest
from tau_skill_evolution.constants import EXPERIMENT_ROOT
from tau_skill_evolution.container import ProcessResult, _public_workspace, _remove_runtime_staging
from tau_skill_evolution.skillsbench import SkillsBenchAdapter
from tau_skill_evolution.skillsbench_runtime import SkillsBenchRunner


def public_runner(transport):
    runner = SkillsBenchRunner.__new__(SkillsBenchRunner)
    runner.use_bwrap = False
    runner.container_name = None
    runner.verifier_artifacts = None
    runner.public_workspace_mode = True
    runner.config = {"environment": {"cpus": 1, "memory_mb": 1024}, "verifier": {"timeout_sec": 60}}
    runner.timeout, runner.output_limit = 60, 65536
    runner.transport = transport
    runner._docker_lock = lambda: {
        "images": {"runtime": {"digest": "sha256:" + "a" * 64, "verifier_python": "python3"}}
    }
    runner._command = runner._docker_command
    return runner


@pytest.mark.parametrize("failure", [None, "timeout", "output_limit"])
@pytest.mark.parametrize("already_absent", [False, True])
def test_public_command_uses_one_explicit_removal_without_masking_execution(
    tmp_path, failure, already_absent
):
    calls = []
    original = ProcessResult(0 if failure is None else -9, b"output", b"diagnostic", failure)

    def run(command, **_kwargs):
        calls.append(command)
        if command[:2] == ["docker", "run"]:
            return original
        return (
            ProcessResult(1, stderr=b"No such container: already removed")
            if already_absent
            else ProcessResult(0)
        )

    runner = public_runner(SimpleNamespace(run=run))
    package, work = tmp_path / "bundle", tmp_path / "work"
    package.mkdir()
    work.mkdir()
    result = runner._raw(package, work, ["/bin/bash", "-c", "true"])
    assert result == original
    assert len(calls) == 2 and "--rm" not in calls[0]
    name = calls[0][calls[0].index("--name") + 1]
    assert calls[1] == ["docker", "rm", "--force", "--volumes", name]


@pytest.mark.parametrize("failure", [None, "timeout", "output_limit"])
def test_true_cleanup_failure_returns_original_context_and_retains_public_workspace(failure):
    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        return (
            ProcessResult(-9, b"partial output", b"original detail", failure)
            if command[:2] == ["docker", "run"]
            else ProcessResult(1, stderr=b"daemon refused removal")
        )

    runner = public_runner(SimpleNamespace(run=run))
    with _public_workspace(
        runner,
        {"opening": "Public task"},
        {},
        test_files={
            "tests/test_public.py": "from pathlib import Path\n"
            "def test_inputs():\n    assert Path('/bundle/public_inputs.json').is_file()\n"
        },
        terminal_callback=runner._public_terminal,
    ) as session:
        staging = session.package.parent
        result = session.terminal("true")
        assert result.failure == "cleanup_failed" and session.cleanup_failed
        assert f"original_failure={failure}" in result.stderr
        assert "daemon refused removal" in result.stderr and "original detail" in result.stderr
        assert result.output["stdout"] == "partial output" and result.exit_code == -9
    try:
        assert staging.is_dir() and (staging / "work/tests/test_public.py").is_file()
        assert len(calls) == 2
    finally:
        _remove_runtime_staging(runner, str(staging))


def test_cleanup_failure_detail_stays_inside_combined_output_limit(tmp_path):
    def run(command, **_kwargs):
        return (
            ProcessResult(-9, b"x" * 1024, failure="output_limit")
            if command[:2] == ["docker", "run"]
            else ProcessResult(1, stderr=b"daemon denied removal")
        )

    runner = public_runner(SimpleNamespace(run=run))
    runner.output_limit = 1024
    package, work = tmp_path / "bundle", tmp_path / "work"
    package.mkdir()
    work.mkdir()
    result = runner._raw(package, work, ["/bin/bash", "-c", "true"])
    assert result.failure == "cleanup_failed"
    assert len(result.stdout) + len(result.stderr) == 1024
    assert b"original_failure=output_limit" in result.stderr
    assert b"daemon denied removal" in result.stderr and result.stdout


@pytest.mark.skipif(
    os.environ.get("TAU_RUN_SKILLSBENCH_DOCKER_INTEGRATION") != "1",
    reason="actual public-command Docker cleanup requires explicit opt-in",
)
@pytest.mark.parametrize("failure", [None, "timeout", "output_limit"])
def test_real_public_commands_preserve_limits_and_remove_every_container(tmp_path, failure):
    runner = SkillsBenchRunner(
        EXPERIMENT_ROOT,
        "dialogue-parser",
        demo=False,
        runtime_lock_path=EXPERIMENT_ROOT
        / "runtime/skillsbench-docker-dialogue-parser-v2-20261006-lock.json",
    )
    runner._docker_lock()
    calls = []
    original = runner.transport.run

    def run(command, **kwargs):
        calls.append(list(command))
        return original(command, **kwargs)

    runner.transport.run = run
    runner.timeout = 0.5 if failure == "timeout" else 10
    runner.output_limit = 1024 if failure == "output_limit" else 65536
    command = {
        None: "printf 'normal command'",
        "timeout": "sleep 30",
        "output_limit": "python3 -c 'import os; os.write(1, b\"x\"*1000000)'",
    }[failure]
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=EXPERIMENT_ROOT),
        "dialogue-parser",
        demo=False,
        artifact_root=tmp_path / "public-artifacts",
    )
    adapter.runner = runner
    public = tmp_path / "public"
    public.mkdir()
    (public / "input.txt").write_text("public cleanup fixture")
    trace = adapter._seal_public_workspace({"/app": public})
    with runner.public_verifier_session({"opening": "Public task"}, {}, trace) as session:
        staging = session.package.parent
        results = [session.terminal(command) for _ in range(2 if failure is None else 1)]
        assert all(result.failure == failure for result in results), results
        assert not session.cleanup_failed
    runs = [call for call in calls if call[:2] == ["docker", "run"]]
    removals = [call for call in calls if call[:2] == ["docker", "rm"]]
    names = [call[call.index("--name") + 1] for call in runs]
    assert len(removals) == len(runs) == len(results)
    assert all("--rm" not in call for call in runs)
    assert [call[-1] for call in removals] == names
    for name in names:
        probe = subprocess.run(["docker", "inspect", name], capture_output=True)
        assert probe.returncode != 0 and b"no such" in probe.stderr.lower()
    assert not staging.exists()
    (tmp_path / "cleanup-evidence.json").write_text(
        json.dumps(
            {
                "failure": failure,
                "containers": names,
                "commands": calls,
                "results": [result.to_dict() for result in results],
            },
            indent=2,
        )
        + "\n"
    )
