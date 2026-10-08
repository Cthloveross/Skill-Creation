"""Run the published controller hooks with local task files and simulated GT.

Only Verifier/provider outcomes and the source audit are fixture inputs. Counters,
checklists, schema checks, interventions, export and selection remain author code.
"""

import asyncio
import json
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest
from tau_skill_evolution.author_verifier import _RUN, _Run, author_module


class LocalEnvironment:
    def __init__(self, root):
        self.root = root
        self.environment_dir = root / "task/environment"
        self.environment_dir.mkdir(parents=True)
        (self.environment_dir.parent / "task.toml").write_text("[agent]\ntimeout_sec=15\n")
        self.calls = []

    async def exec(self, command, timeout_sec=None, **kwargs):
        mapped = command.replace("/app/environment", str(self.root / "app/environment"))
        mapped = mapped.replace("/root/", str(self.root / "root") + "/")
        mapped = mapped.replace("python3", sys.executable)
        result = subprocess.run(
            ["/bin/bash", "-c", mapped],
            capture_output=True,
            text=True,
            cwd=self.root / "root",
            env={"PATH": "/usr/bin:/bin", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
            timeout=timeout_sec,
        )
        self.calls.append(command)
        stdout = result.stdout.replace(str(self.root / "app/environment"), "/app/environment")
        return SimpleNamespace(
            return_code=result.returncode,
            stdout=stdout.replace(str(self.root / "root"), "/root"),
            stderr=result.stderr,
        )


class VerifierOutcome:
    def __init__(self, value):
        self.value = value
        self._generation_count = 0
        self.generation_flags = []

    async def verify(self, **kwargs):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value

    async def generate_and_run(self, *, adversarial_recheck, **kwargs):
        self._generation_count += 1
        self.generation_flags.append(adversarial_recheck)
        return await self.verify()


def result(*, passed=False, source="script"):
    model = author_module("evolution.models")
    return model.VerificationResult(
        estimated_success=passed,
        source=source,
        total_tests=1,
        tests_passed=int(passed),
        tests_failed=int(not passed),
        diagnosis="Offline fixture; no model call.",
        test_details=[{"name": "test_numeric_value", "status": "PASSED" if passed else "FAILED"}],
    )


@pytest.fixture
def native_controller(tmp_path):
    module = author_module("agents.terminus_2.harbor_terminus_2_evolution")

    class Controller(module.HarborTerminus2Evolution):
        async def _audit_exported_evolved_skills(self, *args, **kwargs):
            return []

        async def _run_gt_oracle_check(self, *args, oracle_label, **kwargs):
            self.gt_calls.append(oracle_label)
            reward = self.gt_results.popleft()
            if isinstance(reward, Exception):
                raise reward
            return {
                "passed": reward == 1,
                "reward": reward,
                "pass_rate": reward,
                "tests_passed": int(reward * 100),
                "total_tests": 100,
                "test_details": [],
            }

    token = _RUN.set(_Run(SimpleNamespace(), "offline-native-constructor"))
    try:
        agent = Controller(logs_dir=tmp_path / "logs", model_name="offline", timeout_multiplier=5)
    finally:
        _RUN.reset(token)
    agent.logs_dir.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    skill = tmp_path / "app/environment/skills/evo-fixture"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: evo-fixture\ndescription: Produce a reusable fixture.\n---\n"
        "Run scripts/main.py.\n"
    )
    (skill / "scripts").mkdir()
    (skill / "scripts/main.py").write_text("print('fixture')\n")
    verifier = root / "verifier"
    verifier.mkdir()
    (verifier / "test_outputs.py").write_text("def test_numeric_value(): assert False\n")
    (root / "progress.md").write_text("# Progress\n- [x] P1: Skill\n- [x] P2: execute\n")
    environment = LocalEnvironment(tmp_path)
    agent._instruction = "Produce a fixture through the existing evo-fixture Skill."
    agent._environment = environment
    agent._skill_dirs = [Path("/app/environment/skills")]
    agent._surrogate_tests_locked = True
    outcome = VerifierOutcome(result())
    agent._verifier = agent._independent_verifier = outcome
    agent.gt_calls, agent.gt_results = [], deque()
    assert agent._max_host_interventions == 5
    assert agent._max_surrogate_retries == 15
    assert agent._max_episodes == 120
    try:
        yield agent, environment, outcome, root
    finally:
        if agent._best_gt_snapshot:
            shutil.rmtree(agent._best_gt_snapshot["skills_dir"], ignore_errors=True)


def submit(agent, environment, episode=1, *, complete=True, commands=()):
    parsed = agent._parser.parse_response(
        json.dumps(
            {
                "analysis": "fixture",
                "plan": "fixture",
                "commands": list(commands),
                "task_complete": complete,
            }
        )
    )
    return asyncio.run(agent._check_episode_exit(episode, parsed, environment, "fixture output"))


@pytest.mark.parametrize(
    "locked,outcome,unchecked,trigger",
    [
        (True, RuntimeError("fixture verifier failure"), False, "locked_rerun_exception"),
        (True, "no_script", False, "locked_no_script"),
        (False, RuntimeError("fixture generation failure"), False, "verifier_exception"),
        (False, "script_error", False, "verifier_script_error"),
        (True, False, False, "surrogate_fail"),
        (True, True, True, "surrogate_pass_checklist_fail"),
    ],
)
def test_native_six_retry_events_have_published_counts(
    native_controller, locked, outcome, unchecked, trigger
):
    agent, environment, verifier, root = native_controller
    agent._surrogate_tests_locked = locked
    verifier.value = (
        outcome
        if isinstance(outcome, Exception)
        else result(
            passed=outcome is True, source=outcome if isinstance(outcome, str) else "script"
        )
    )
    if unchecked:
        (root / "progress.md").write_text("- [ ] P2: execute\n")
    exit_result = submit(agent, environment)
    assert not exit_result.should_exit
    assert agent._surrogate_retry_count == 1 and agent._host_intervention_count == 0
    assert agent._intervention_history[-1]["trigger"] == trigger
    assert not agent.gt_calls


def test_native_r15_uses_fifteen_failures_then_terminal_gt(native_controller):
    agent, environment, _, _ = native_controller
    for episode in range(1, 16):
        assert not submit(agent, environment, episode).should_exit
        assert agent._surrogate_retry_count == episode
    agent.gt_results.append(0.25)
    terminal = submit(agent, environment, 16)
    assert terminal.should_exit and terminal.exit_reason == "max_surrogate_retries"
    assert agent._surrogate_retry_count == 15 and agent._host_intervention_count == 0
    assert len(agent.gt_calls) == 1 and agent._best_gt_snapshot["reward"] == 0.25


def test_native_checklist_blocks_once_then_runs_gt(native_controller):
    agent, environment, verifier, root = native_controller
    verifier.value = result(passed=True)
    (root / "progress.md").write_text("- [ ] P2: execute\n")
    first = submit(agent, environment)
    assert not first.should_exit and not agent.gt_calls
    agent.gt_results.append(1.0)
    second = submit(agent, environment, 2)
    assert second.should_exit and second.exit_reason == "gt_oracle_pass"
    assert agent._surrogate_retry_count == 1 and agent._host_intervention_count == 1
    assert len(agent.gt_calls) == 1


def test_native_oracle_failure_unlocks_tests_after_returning_generator(native_controller):
    agent, environment, verifier, _ = native_controller
    verifier.value = result(passed=True)
    agent.gt_results.extend([0.75, 1.0])
    first = submit(agent, environment)
    assert not first.should_exit and not agent._surrogate_tests_locked
    assert agent._adversarial_surrogate_recheck
    assert verifier.generation_flags == []
    second = submit(agent, environment, 2)
    assert second.should_exit and verifier.generation_flags == [True]
    assert agent._host_intervention_count == 2 and agent._surrogate_retry_count == 0


def test_native_active_command_executes_without_spending_retry_or_gt(native_controller):
    agent, environment, _, root = native_controller
    command = author_module("agents.terminus_2.harbor_terminus_2_evolution").Command(
        keystrokes="printf 'executed\\n' > /root/fixture.txt\n", duration_sec=0.1
    )
    output = asyncio.run(agent._execute_commands(environment, [command]))
    parsed = agent._parser.parse_response(
        json.dumps(
            {
                "analysis": "fixture",
                "plan": "fixture",
                "task_complete": False,
                "commands": [{"keystrokes": command.keystrokes, "duration": 0.1}],
            }
        )
    )
    exit_result = asyncio.run(agent._check_episode_exit(1, parsed, environment, output))
    assert not exit_result.should_exit and (root / "fixture.txt").read_text() == "executed\n"
    assert agent._surrogate_retry_count == agent._host_intervention_count == 0
