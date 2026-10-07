from types import SimpleNamespace

import pytest
from tau_skill_evolution import codex_runtime
from tau_skill_evolution.codex_provider import OUTPUT_TOKEN_BUDGET_STOP
from tau_skill_evolution.container import ContainerUnavailable
from tau_skill_evolution.journal import UnknownOperation
from tau_skill_evolution.model import ModelClientError
from tau_skill_evolution.skillsbench import SkillsBenchAdapter


def adapter(tmp_path, statistics):
    value = SkillsBenchAdapter.__new__(SkillsBenchAdapter)
    value.task_id = "example"
    value.public_inputs = {"opening": "Make the public deliverable."}
    value.spec = SimpleNamespace(
        provider_settings={"model": "openai.gpt-5.5"},
        values={
            "runtime": {
                "controls": {
                    "agent": {"reasoning_effort": "medium"},
                    "max_input_tokens": 114688,
                }
            }
        },
    )
    value.runner = SimpleNamespace(public_python="/.tau-python/python3")
    value._codex_binary = tmp_path / "codex"
    value._codex_logs = tmp_path / "private" / "codex"
    value._executor_identity = {"framework": "author-codex", "model": "openai.gpt-5.5"}
    value._codex_gateway = SimpleNamespace(
        base_url="http://127.0.0.1:18765/v1",
        statistics=statistics,
        close_public=lambda: statistics.update(closed=True),
    )
    return value


def test_codex_trace_excludes_native_model_messages_and_closes_provider(tmp_path, monkeypatch):
    statistics = {"requests": 2, "output_tokens": 20}
    value = adapter(tmp_path, statistics)

    def execute(*args, **kwargs):
        assert kwargs["instruction"] == "Make the public deliverable."
        assert kwargs["bundle"] is None
        assert kwargs["provider"].relay_command[0] == "/.tau-python/python3"
        return {"termination_reason": "agent_finished", "raw_stdout": "PRIVATE_SKILL_SOURCE"}

    monkeypatch.setattr(codex_runtime, "execute_codex", execute)
    trace = value._execute_codex(None, object())
    assert statistics["closed"]
    assert "PRIVATE_SKILL_SOURCE" not in str(trace)
    assert trace["executor"] == value._executor_identity


@pytest.mark.parametrize(
    "failure, error",
    [
        ({"authentication_status": 401}, ModelClientError),
        ({"unknown_operation": True}, UnknownOperation),
        ({"halted": True, "failure_code": "provider_http_error"}, ModelClientError),
    ],
)
def test_provider_failures_are_not_task_scores(tmp_path, monkeypatch, failure, error):
    statistics = {"requests": 1, "output_tokens": 0, **failure}
    value = adapter(tmp_path, statistics)
    monkeypatch.setattr(
        codex_runtime,
        "execute_codex",
        lambda *a, **k: {
            "termination_reason": "codex_error",
        },
    )
    with pytest.raises(error):
        value._execute_codex(None, object())
    assert statistics["closed"]


def test_valid_execution_can_be_graded_after_budget_stop(tmp_path, monkeypatch):
    statistics = {
        "requests": 2,
        "output_tokens": 20,
        "halted": True,
        "failure_code": "provider_completion_budget_exhausted",
    }
    value = adapter(tmp_path, statistics)
    monkeypatch.setattr(
        codex_runtime,
        "execute_codex",
        lambda *a, **k: {
            "termination_reason": "codex_error",
        },
    )
    assert value._execute_codex(None, object())["termination_reason"] == (
        "provider_completion_budget_exhausted"
    )


@pytest.mark.parametrize("reason", ["codex_error", "codex_runtime_error"])
def test_native_cli_failure_is_not_a_measured_task_failure(tmp_path, monkeypatch, reason):
    statistics = {"requests": 2, "output_tokens": 20}
    value = adapter(tmp_path, statistics)
    monkeypatch.setattr(
        codex_runtime, "execute_codex", lambda *a, **k: {"termination_reason": reason}
    )
    with pytest.raises(ContainerUnavailable):
        value._execute_codex(None, object())
    assert statistics["closed"]


def test_native_output_budget_stop_allows_partial_episode_grade(tmp_path, monkeypatch):
    statistics = {
        "requests": 1,
        "output_tokens": 4096,
        "halted": True,
        "failure_code": OUTPUT_TOKEN_BUDGET_STOP,
        "terminal_stop": {
            "kind": "budget",
            "reason": "max_output_tokens",
            "response_status": "incomplete",
        },
    }
    value = adapter(tmp_path, statistics)
    monkeypatch.setattr(
        codex_runtime, "execute_codex", lambda *a, **k: {"termination_reason": "codex_error"}
    )
    trace = value._execute_codex(None, object())
    assert trace["termination_reason"] == OUTPUT_TOKEN_BUDGET_STOP
    assert trace["assistant_completion_tokens"] == 4096 and statistics["closed"]


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"terminal_stop": None}, ModelClientError),
        ({"terminal_stop": {"kind": "budget", "reason": "interrupted"}}, ModelClientError),
        ({"unknown_operation": True}, UnknownOperation),
        ({"authentication_status": 401}, ModelClientError),
        ({"failure_code": "provider_output_token_limit_exceeded"}, ModelClientError),
    ],
)
def test_budget_tag_does_not_override_other_native_failures(
    tmp_path, monkeypatch, overrides, error
):
    statistics = {
        "requests": 1,
        "output_tokens": 4096,
        "halted": True,
        "failure_code": OUTPUT_TOKEN_BUDGET_STOP,
        "terminal_stop": {
            "kind": "budget",
            "reason": "max_output_tokens",
            "response_status": "incomplete",
        },
        **overrides,
    }
    value = adapter(tmp_path, statistics)
    monkeypatch.setattr(
        codex_runtime, "execute_codex", lambda *a, **k: {"termination_reason": "codex_error"}
    )
    with pytest.raises(error):
        value._execute_codex(None, object())
