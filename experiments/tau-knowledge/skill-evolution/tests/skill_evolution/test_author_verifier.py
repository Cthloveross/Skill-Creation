import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from tau_skill_evolution.artifacts import FrozenBase
from tau_skill_evolution.author_verifier import AuthorSkillsBenchVerifier, author_source
from tau_skill_evolution.container import ProcessResult
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.model import InputTokenBudgetExceeded, ModelClientError


class Model:
    def __init__(self, marker="public"):
        self.marker = marker
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        command = (
            "mkdir -p /root/verifier; printf '%s\\n' "
            f"'def test_{self.marker}(): assert True' > /root/verifier/test_outputs.py"
        )
        return {
            "content": json.dumps(
                {
                    "analysis": "Inspect public outputs",
                    "plan": "Write tests",
                    "commands": [{"keystrokes": command, "duration": 0.1}],
                    "task_complete": True,
                }
            ),
            "finish_reason": "stop",
        }


class Runner:
    def __init__(self, root):
        self.root = root
        self.root.mkdir(parents=True)
        self.container_name = "learning-main"
        self.public_open = True
        self.learning_workspace = object()
        self.task_directory = root / "task"
        (self.task_directory / "environment").mkdir(parents=True)
        self.calls = []

    def phase_remaining(self):
        return 7200

    def author_exec(self, command, *, cwd=None, env=None, timeout_sec=None):
        self.calls.append(command)
        command = command.replace("/root/verifier", str(self.root / "verifier"))
        command = command.replace("/app/environment/doc", str(self.root / "docs"))
        command = command.replace("python3", sys.executable)
        result = subprocess.run(
            ["/bin/bash", "-c", command],
            cwd=self.root,
            env=env,
            capture_output=True,
            timeout=timeout_sec,
        )
        return ProcessResult(result.returncode, result.stdout, result.stderr)


def verifier(tmp_path, model=None):
    runner = Runner(tmp_path / "container")
    model = model or Model()
    journal = Journal(tmp_path / "journal", identity={"task": "test"})
    instance = AuthorSkillsBenchVerifier(
        model,
        runner,
        journal=journal,
        token_counter=lambda text: len(text) // 4 + 1,
        logs_dir=tmp_path / "logs",
    )
    return instance, runner, model


def test_direct_author_lifecycle_accepts_author_checks_and_consumes_generation_run(tmp_path):
    instance, runner, model = verifier(tmp_path)
    base = FrozenBase((), {"opening": "Write a public output."})
    suite = instance.create_suite(base.public_inputs, base, {"execution_id": "submission"})
    before = len(runner.calls)
    report = instance.verify(base.public_inputs, base, {"execution_id": "submission"}, suite)
    assert report.passed
    assert report.author_result["source"] == "script"
    assert len(runner.calls) == before
    assert len(model.calls) == 1
    assert suite.obligations == ()
    assert model.calls[0][1]["max_output_tokens"] is None
    assert "independent verification agent" in model.calls[0][0][0]["content"]
    assert "submit_tests" not in model.calls[0][0][0]["content"]


def test_completed_author_generation_replays_without_model_or_terminal(tmp_path):
    instance, runner, model = verifier(tmp_path)
    base = FrozenBase((), {"opening": "Write output."})
    first = instance.create_suite(base.public_inputs, base, {}, operation_id="initial")
    counts = len(runner.calls), len(model.calls)
    second = instance.create_suite(base.public_inputs, base, {}, operation_id="initial")
    assert second == first
    assert counts == (len(runner.calls), len(model.calls))


def test_restart_consumes_sealed_generation_result_and_restores_author_history(tmp_path):
    instance, runner, model = verifier(tmp_path)
    suite = instance.create_suite({"opening": "Task"}, {}, {}, operation_id="initial")
    before = len(runner.calls)
    resumed = AuthorSkillsBenchVerifier(
        model,
        runner,
        journal=instance.journal,
        token_counter=instance.token_counter,
        logs_dir=instance.logs_dir,
    )
    assert resumed.author._generation_count == 1
    report = resumed.verify({"opening": "Task"}, {}, {}, suite, operation_id="first-check")
    assert report.passed and len(runner.calls) == before
    resumed_again = AuthorSkillsBenchVerifier(
        model,
        runner,
        journal=instance.journal,
        token_counter=instance.token_counter,
        logs_dir=instance.logs_dir,
    )
    resumed_again.verify({"opening": "Task"}, {}, {}, suite, operation_id="second-check")
    assert len(runner.calls) > before
    assert len(model.calls) == 1


def test_author_diagnosis_restores_sealed_tests_and_keeps_measured_failure(tmp_path):
    class DiagnoseModel(Model):
        def complete(self, messages, **kwargs):
            response = super().complete(messages, **kwargs)
            value = json.loads(response["content"])
            if len(self.calls) == 1:
                value["commands"][0]["keystrokes"] = value["commands"][0]["keystrokes"].replace(
                    "assert True", "assert False"
                )
            else:
                value["commands"][0]["keystrokes"] += (
                    "; printf 'Current output failed the public check' "
                    "> /root/verifier/diagnosis.md"
                )
            response["content"] = json.dumps(value)
            return response

    instance, runner, model = verifier(tmp_path, DiagnoseModel())
    suite = instance.create_suite({"opening": "Task"}, {}, {})
    report = instance.verify({"opening": "Task"}, {}, {}, suite)
    assert not report.passed and not report.program_error
    assert report.author_result["tests_failed"] == 1
    assert report.diagnosis == "Current output failed the public check"
    assert (runner.root / "verifier/test_outputs.py").read_text() == suite.files[
        "tests/test_outputs.py"
    ]
    assert len(model.calls) == 2


def test_no_script_returns_author_failure_evidence_without_a_synthetic_suite(tmp_path):
    class EmptyModel(Model):
        def complete(self, messages, **kwargs):
            value = super().complete(messages, **kwargs)
            parsed = json.loads(value["content"])
            parsed["commands"] = []
            value["content"] = json.dumps(parsed)
            return value

    instance, _runner, _model = verifier(tmp_path, EmptyModel())
    with pytest.raises(RuntimeError) as caught:
        instance.create_suite({"opening": "Task"}, {}, {})
    assert caught.value.source == "no_script"
    assert caught.value.author_result["total_tests"] == 0


def test_author_boundary_audit_invalidates_skill_inspection(tmp_path):
    class BoundaryModel(Model):
        def complete(self, messages, **kwargs):
            value = super().complete(messages, **kwargs)
            parsed = json.loads(value["content"])
            parsed["commands"][0]["keystrokes"] += "; ls /app/environment/skills"
            value["content"] = json.dumps(parsed)
            return value

    instance, _runner, _model = verifier(tmp_path, BoundaryModel())
    with pytest.raises(RuntimeError) as caught:
        instance.create_suite({"opening": "Task"}, {}, {})
    assert caught.value.source == "script_error"
    assert "verification boundary" in caught.value.author_result["error"]


def test_model_post_timeout_is_bound_to_current_remaining_budget(tmp_path):
    class TimedModel(Model):
        timeout_seconds = 900

        def complete(self, messages, **kwargs):
            assert self.timeout_seconds == 30
            return super().complete(messages, **kwargs)

    instance, runner, model = verifier(tmp_path, TimedModel())
    runner.phase_remaining = lambda: 30
    instance.create_suite({"opening": "Task"}, {}, {})
    assert model.timeout_seconds == 900


@pytest.mark.parametrize(
    "error",
    [UnknownOperation("lost response"), ModelClientError("http_error", "auth failed", status=401)],
)
def test_author_cannot_swallow_fatal_model_error_or_continue_tools(tmp_path, error):
    class FailedModel:
        calls = 0

        def complete(self, *args, **kwargs):
            self.calls += 1
            raise error

    instance, runner, model = verifier(tmp_path, FailedModel())
    with pytest.raises(type(error)):
        instance.create_suite({"opening": "Task"}, {}, {}, operation_id="fatal")
    after = len(runner.calls)
    with pytest.raises((UnknownOperation, ModelClientError)):
        instance.create_suite({"opening": "Task"}, {}, {}, operation_id="fatal")
    assert len(runner.calls) == after
    assert model.calls == 1


def test_run_bound_factory_does_not_mix_concurrent_clients(tmp_path):
    def run(marker):
        instance, runner, model = verifier(tmp_path / marker, Model(marker))
        suite = instance.create_suite({"opening": marker}, {}, {})
        return suite, model.calls

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["one", "two"]))
    for marker, (suite, calls) in zip(["one", "two"], results, strict=True):
        assert f"test_{marker}" in suite.files["tests/test_outputs.py"]
        assert len(calls) == 1


def test_vendored_core_is_hash_verified():
    source = author_source()
    assert source["commit"] == "4380d4bff673dd6e1d58e5babeb2aaa0fe527119"
    assert len(source["files"]) >= 16


def test_author_cannot_swallow_input_admission_or_expired_deadline(tmp_path):
    instance, runner, model = verifier(tmp_path)
    instance.max_input_tokens = 1
    with pytest.raises(InputTokenBudgetExceeded):
        instance.create_suite({"opening": "Task"}, {}, {})
    assert not model.calls
    expired, runner, model = verifier(tmp_path / "expired")
    runner.phase_remaining = lambda: 0
    with pytest.raises(TimeoutError, match="learning_timeout"):
        expired.create_suite({"opening": "Task"}, {}, {})
    assert not model.calls and not runner.calls


def test_known_diagnosis_error_preserves_original_measured_failure(tmp_path):
    class FailingModel(Model):
        def complete(self, *args, **kwargs):
            value = super().complete(*args, **kwargs)
            value["content"] = value["content"].replace("assert True", "assert False")
            return value

    instance, runner, _model = verifier(tmp_path, FailingModel())
    suite = instance.create_suite({"opening": "Task"}, {}, {})

    async def fail(*args, **kwargs):
        raise ValueError("local diagnostic failure")

    instance.author.diagnose_failures = fail
    report = instance.verify({"opening": "Task"}, {}, {}, suite)
    assert not report.passed and not report.program_error
    assert report.author_result["tests_failed"] == 1
    assert report.stage_failures[0]["reason"] == "author_diagnosis_error"
    assert report.diagnosis == ""
    assert (runner.root / "verifier/test_outputs.py").read_text() == suite.files[
        "tests/test_outputs.py"
    ]


def test_nonempty_syntax_error_script_never_locks_a_suite(tmp_path):
    class InvalidModel(Model):
        def complete(self, *args, **kwargs):
            value = super().complete(*args, **kwargs)
            value["content"] = value["content"].replace("assert True", "invalid ! syntax")
            return value

    instance, _runner, _model = verifier(tmp_path, InvalidModel())
    with pytest.raises(RuntimeError) as caught:
        instance.create_suite({"opening": "Task"}, {}, {})
    assert caught.value.source == "script_error"
    assert "SyntaxError" in caught.value.author_result["raw_output"]


def test_author_public_environment_changes_are_sealed_and_replay_does_not_snapshot(tmp_path):
    instance, runner, _model = verifier(tmp_path)
    snapshots = []

    def snapshot():
        value = {"/root/public-output.txt": "before" if not snapshots else "after"}
        snapshots.append(value)
        return value

    runner.public_environment_manifest = snapshot
    suite = instance.create_suite({"opening": "Task"}, {}, {}, operation_id="audit")
    record = instance.journal.response("audit-author-generation")
    changes = record["public_environment_changes"]
    assert changes["changed_paths"] == ["/root/public-output.txt"]
    assert changes["before_hash"] != changes["after_hash"]
    assert len(snapshots) == 2
    assert instance.create_suite({"opening": "Task"}, {}, {}, operation_id="audit") == suite
    assert len(snapshots) == 2


def test_original_self_verifier_fallback_filename_remains_supported(tmp_path):
    class FallbackModel(Model):
        def complete(self, *args, **kwargs):
            value = super().complete(*args, **kwargs)
            value["content"] = value["content"].replace("test_outputs.py", "check_output.py")
            return value

    instance, _runner, _model = verifier(tmp_path, FallbackModel())
    suite = instance.create_suite({"opening": "Task"}, {}, {})
    assert "test_public" in suite.files["tests/test_outputs.py"]
    assert instance.verify({"opening": "Task"}, {}, {}, suite).passed


def test_valid_partial_script_uses_author_count_gate_and_keeps_agent_error_audit(tmp_path):
    class TwoTests(Model):
        def complete(self, *args, **kwargs):
            value = super().complete(*args, **kwargs)
            parsed = json.loads(value["content"])
            parsed["commands"][0]["keystrokes"] += (
                "; printf '%s\\n' 'def test_second(): assert True' "
                ">> /root/verifier/test_outputs.py"
            )
            value["content"] = json.dumps(parsed)
            return value

    instance, _runner, model = verifier(tmp_path, TwoTests())
    generate = instance.author.generate_and_run

    async def partial(*args, **kwargs):
        result = await generate(*args, **kwargs)
        assert result.total_tests == result.tests_passed == 2
        result.estimated_success = False
        result.error = "Known agent timeout after a valid partial test script"
        result.diagnosis = "Stale failure text"
        return result

    instance.author.generate_and_run = partial
    suite = instance.create_suite({"opening": "Task"}, {}, {})
    report = instance.verify({"opening": "Task"}, {}, {}, suite)
    assert report.passed and not report.program_error
    assert report.pass_rate == 1 and report.diagnosis == ""
    assert report.author_result["error"] == "Known agent timeout after a valid partial test script"
    assert report.author_result["estimated_success"] is False
    assert report.stage_failures[0]["reason"] == "author_agent_error"
    assert len(model.calls) == 1


@pytest.mark.parametrize("reward", ["2", "-0.1"])
def test_author_finite_reward_admission_does_not_change_default_range_or_dependency_checks(reward):
    from tau_skill_evolution.skillsbench_runtime import _validate_grader_warmup

    with pytest.raises(RuntimeError, match="reward_invalid"):
        _validate_grader_warmup(0, reward, None, "")
    _validate_grader_warmup(0, reward, None, "", allow_finite_reward=True)
    with pytest.raises(RuntimeError, match="dependency_or_collection_error"):
        _validate_grader_warmup(
            1,
            reward,
            None,
            "ModuleNotFoundError: No module named 'missing_grader_dependency'",
            allow_finite_reward=True,
        )
    with pytest.raises(RuntimeError, match="reward_invalid"):
        _validate_grader_warmup(0, "nan", None, "", allow_finite_reward=True)
