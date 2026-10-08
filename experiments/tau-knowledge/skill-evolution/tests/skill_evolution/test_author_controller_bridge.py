"""Native author-agent transport fixtures; no model account or Docker is contacted."""

import asyncio
import contextlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from harbor.models.agent.context import AgentContext
from tau_skill_evolution.author_controller import AuthorControllerBridge
from tau_skill_evolution.author_verifier import _RUN, _BoundLLM, author_module, author_source
from tau_skill_evolution.container import ContainerUnavailable, ProcessResult
from tau_skill_evolution.core._canonical import canonical_json_sha256
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.model import InputTokenBudgetExceeded, ModelClientError


class Model:
    def __init__(self, role, error=None):
        self.role, self.error, self.calls = role, error, []
        self.timeout_seconds, self.request_deadline = 300, None

    def complete(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.error:
            raise self.error
        return {
            "content": json.dumps(
                {
                    "analysis": self.role,
                    "plan": "One public command",
                    "commands": [{"keystrokes": "echo public", "duration": 0.1}],
                    "task_complete": True,
                }
            ),
            "finish_reason": "stop",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }


class Runner:
    def __init__(self, root):
        self.task_directory = root / "task"
        (self.task_directory / "environment").mkdir(parents=True)
        self.learning_workspace, self.public_open, self.container_name = (
            object(),
            True,
            "fixture-main",
        )
        self.output_limit, self.failure, self.calls = 65536, None, []
        self.output = b"public output"
        self.transport = SimpleNamespace(run=self.copy)

    def phase_remaining(self):
        return 7200

    def author_exec(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return ProcessResult(
            124 if self.failure == "timeout" else -1 if self.failure else 0,
            self.output if command == "echo public" else b"",
            b"",
            self.failure,
        )

    def copy(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if not command[-1].startswith(self.container_name + ":"):
            (Path(command[-1]) / "evo-current").mkdir(exist_ok=True)
        return ProcessResult(0)


def bridge(tmp_path, generator=None):
    runner = Runner(tmp_path / "main")
    generator, verifier = generator or Model("generator"), Model("verifier")
    stored = []
    instance = AuthorControllerBridge(
        generator,
        verifier,
        runner,
        Journal(tmp_path / "journal"),
        operation_id="native-controller",
        environment_dir=tmp_path / "private-task/environment",
        token_counter=lambda text: len(text) // 4 + 1,
        record_tool_result=lambda operation, value: stored.append(value) or "/work/fixture.json",
    )
    return instance, runner, generator, verifier, stored


def test_real_pinned_controller_constructor_and_independent_role_factories(tmp_path):
    instance, _runner, generator, verifier, _stored = bridge(tmp_path)
    native = author_module("agents.terminus_2.harbor_terminus_2_evolution").HarborTerminus2Evolution
    agent = instance.build_agent(native, logs_dir=tmp_path / "logs", model_name="fixture")
    assert agent._llm.run.owner.model is generator
    assert agent._check_episode_exit.__func__ is native._check_episode_exit
    assert agent.run.__func__ is native.run

    async def probe(_instruction, _environment, _context):
        agent._llm.call("Generator history")
        skills = author_module("agents.terminus_2.harbor_terminus_2_skills")
        created = skills.HarborTerminus2WithSkills(logs_dir=tmp_path / "verifier-logs")
        assert created._llm.run.owner.model is verifier
        assert "_execute_commands" in created.__dict__
        created._llm.call("Verifier public-only history")

    agent.run = probe
    asyncio.run(instance.run(agent, "Public task", AgentContext()))
    assert len(generator.calls) == len(verifier.calls) == 1
    assert "Generator history" not in str(verifier.calls)
    assert "Verifier public-only history" not in str(generator.calls)
    requests = [json.loads(p.read_text()) for p in instance.journal.root.glob("*/request.json")]
    assert {r["payload"]["role"] for r in requests} == {"generator", "verifier"}
    assert all(r["payload"]["max_output_tokens"] is None for r in requests)
    assert _RUN.get() is None


def test_real_pinned_term_agent_runs_command_with_original_loop(tmp_path):
    instance, runner, generator, _verifier, stored = bridge(tmp_path)
    native = author_module("agents.terminus_2.harbor_terminus_2_skills").HarborTerminus2WithSkills
    agent = instance.build_agent(
        native,
        logs_dir=tmp_path / "logs",
        model_name="fixture",
        max_episodes=1,
        max_output_tokens=None,
    )
    asyncio.run(instance.setup(agent))
    context = AgentContext()
    asyncio.run(instance.run(agent, "Write a public result", context))
    assert len(generator.calls) == 1
    assert any(command == "echo public" for command, _ in runner.calls)
    assert stored and context.metadata is not None


@pytest.mark.parametrize("failure", ["timeout", "output_limit"])
def test_known_terminal_limits_keep_full_host_result_and_bounded_model_preview(tmp_path, failure):
    instance, runner, _generator, _verifier, stored = bridge(tmp_path)
    runner.failure, runner.output = failure, b"x" * 25000
    host = asyncio.run(instance.environment.exec("echo public"))
    assert host.stdout == "x" * 25000
    assert "terminal limit: " + failure in host.stderr
    assert stored == []  # Host/Verifier raw output is never copied into Generator observations.
    assert instance.terminal_results[-1]["actor"] == "host"
    native = author_module("agents.terminus_2.harbor_terminus_2_skills")
    agent = instance.build_agent(native.HarborTerminus2WithSkills, logs_dir=tmp_path / "logs")
    output = asyncio.run(
        agent._execute_commands(instance.environment, [native.Command("echo public", 0.1)])
    )
    assert output.count("x") <= 8192
    assert "terminal preview truncated" in output
    assert stored[-1]["stdout"] == "x" * 25000
    assert instance.terminal_results[-1]["actor"] == "generator"
    assert instance.terminal_results[-1]["raw_hash"] == canonical_json_sha256(stored[-1])
    instance.check()


def test_fatal_unknown_is_shared_even_if_author_catches_it(tmp_path):
    model = Model(
        "generator", ModelClientError("codex_plan_quota_unavailable", "Quota stopped", status=403)
    )
    instance, runner, _generator, verifier, _stored = bridge(tmp_path, model)
    native = author_module("agents.terminus_2.harbor_terminus_2_evolution").HarborTerminus2Evolution
    agent = instance.build_agent(native, logs_dir=tmp_path / "logs")

    async def swallowing_author(_instruction, _environment, _context):
        with contextlib.suppress(Exception):
            agent._llm.call("Generator")
        with contextlib.suppress(Exception):
            _BoundLLM("fixture").call("Verifier must not dispatch")

    agent.run = swallowing_author
    with pytest.raises((UnknownOperation, ModelClientError)):
        asyncio.run(instance.run(agent, "Task", AgentContext()))
    assert len(model.calls) == 1 and verifier.calls == [] and runner.calls == []


def test_unavailable_environment_is_fatal_not_a_test_program_error(tmp_path):
    instance, runner, *_ = bridge(tmp_path)
    runner.failure = "container_unavailable"
    with pytest.raises(ContainerUnavailable):
        asyncio.run(instance.environment.exec("echo public"))
    with pytest.raises(ContainerUnavailable):
        instance.check()


def test_directory_copy_uses_original_harbor_layout_and_hashes_contents(tmp_path):
    instance, runner, *_ = bridge(tmp_path)
    data = tmp_path / "files"
    data.mkdir()
    (data / "SKILL.md").write_text("public skill")
    asyncio.run(instance.environment.upload_dir(data, "/app/environment/skills/evo-current"))
    copied = runner.calls[-1][0]
    assert copied == [
        "docker",
        "cp",
        str(data) + "/.",
        "fixture-main:/app/environment/skills/evo-current",
    ]
    record = json.loads(
        next(
            p
            for p in instance.journal.root.glob("*/request.json")
            if "-copy-" in json.loads(p.read_text())["operation_id"]
        ).read_text()
    )
    assert record["payload"]["source_hash"] is not None
    destination = tmp_path / "download"
    asyncio.run(
        instance.environment.download_dir("/app/environment/skills/evo-current", destination)
    )
    assert (destination / "evo-current").is_dir()
    (data / "escape").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="special_file"):
        asyncio.run(instance.environment.upload_dir(data, "/app/environment/skills/evo-current"))


def test_vendored_core_is_hash_verified():
    source = author_source()
    assert source["commit"] == "4380d4bff673dd6e1d58e5babeb2aaa0fe527119"
    assert len(source["files"]) >= 16


def test_author_controller_discovers_original_skill_creator_resources():
    from tau_skill_evolution.author_verifier import author_module

    source = author_source()
    resources = [
        key for key in source["files"] if key.startswith("coevo/meta_skills/skill-creator/")
    ]
    assert len(resources) == 18
    controller = author_module("agents.terminus_2.harbor_terminus_2_evolution")
    agent = controller.HarborTerminus2Evolution.__new__(controller.HarborTerminus2Evolution)
    root = agent._find_meta_skills_dir()
    assert root is not None
    assert (root / "skill-creator/SKILL.md").is_file()
    assert (root / "skill-creator/scripts/quick_validate.py").is_file()
    assert (root / "skill-creator/references/schemas.md").is_file()
    assert (root / "skill-creator/LICENSE.txt").is_file()


def bound_llm(instance, role="generator"):
    token = _RUN.set(instance.runs[role])
    try:
        return _BoundLLM("fixture")
    finally:
        _RUN.reset(token)


def restart_bridge(instance):
    return AuthorControllerBridge(
        instance.runs["generator"].owner.model,
        instance.runs["verifier"].owner.model,
        instance.runner,
        instance.journal,
        operation_id=instance.runs["generator"].operation_id.removesuffix("/generator"),
        environment_dir=instance.environment.environment_dir,
        token_counter=lambda text: len(text) // 4 + 1,
    )


def test_bound_model_timeout_uses_remaining_budget_and_restores_client(tmp_path):
    class TimedModel(Model):
        def complete(self, messages, **kwargs):
            assert self.timeout_seconds == 30
            return super().complete(messages, **kwargs)

    model = TimedModel("generator")
    instance, runner, *_ = bridge(tmp_path, model)
    runner.phase_remaining = lambda: 30
    bound_llm(instance).call("Public task")
    assert model.timeout_seconds == 300


def test_provider_context_is_preserved_without_corrupting_output_token_counts(tmp_path):
    class ContextModel(Model):
        def complete(self, messages, **kwargs):
            return {
                **super().complete(messages, **kwargs),
                "context_budget": {
                    "context_window": 258400,
                    "input_tokens": 185730,
                    "output_tokens": 2096,
                    "reserve_tokens": 32768,
                },
            }

    instance, *_ = bridge(tmp_path, ContextModel("generator"))
    model = bound_llm(instance)
    model.call("Public task")
    assert model.last_context_budget["input_tokens"] == 185730
    output = [{"role": "assistant", "content": "done"}]
    assert model.count_tokens(output) == instance.runs["generator"].owner.token_counter(
        json.dumps(output, ensure_ascii=False)
    )
    assert model.count_tokens(output) < 100
    resumed = bound_llm(restart_bridge(instance))
    resumed.call("Public task")
    assert resumed.last_context_budget == model.last_context_budget


def test_known_generator_admission_stop_allows_native_host_finalization(tmp_path):
    instance, runner, generator, verifier, _ = bridge(tmp_path)
    run = instance.runs["generator"]
    run.owner.max_input_tokens = 1
    stopped = []
    run.owner.on_input_budget_stop = stopped.append
    with pytest.raises(InputTokenBudgetExceeded) as original:
        bound_llm(instance).call("Public input")
    assert run.input_budget_stop is original.value and run.fatal is None
    assert stopped == [original.value]
    with pytest.raises(InputTokenBudgetExceeded) as repeated:
        bound_llm(instance).call("Do not dispatch")
    assert repeated.value is original.value
    asyncio.run(instance.environment.exec("echo public"))
    bound_llm(instance, "verifier").call("Separate verifier session")
    assert not generator.calls and len(runner.calls) == len(verifier.calls) == 1


def test_capacity_exception_after_received_response_remains_fatal(tmp_path):
    error = InputTokenBudgetExceeded(185730, 148112)

    class InvalidModel(Model):
        def complete_journaled(self, journal, operation, payload, messages, **kwargs):
            def normalize(*_args):
                raise error

            return journal.dispatch_raw(
                operation, payload, lambda: None, lambda _: (200, b"received"), normalize
            )

    instance, runner, *_ = bridge(tmp_path, InvalidModel("generator"))
    run = instance.runs["generator"]
    stopped = []
    run.owner.on_input_budget_stop = stopped.append
    with pytest.raises(InputTokenBudgetExceeded):
        bound_llm(instance).call("Public task")
    assert instance.journal.status("native-controller/generator-model-0") == "RECEIVED_INVALID"
    assert run.fatal is error and run.input_budget_stop is None and not stopped
    with pytest.raises(InputTokenBudgetExceeded):
        asyncio.run(instance.environment.exec("Must not execute"))
    assert not runner.calls


@pytest.mark.parametrize("failure", ["input", "deadline"])
def test_bound_admission_stops_before_model_and_terminal_dispatch(tmp_path, failure):
    instance, runner, generator, verifier, _ = bridge(tmp_path)
    if failure == "input":
        instance.runs["generator"].owner.max_input_tokens = 1
        error = InputTokenBudgetExceeded
    else:
        runner.phase_remaining = lambda: 0
        error = TimeoutError
    with pytest.raises(error):
        bound_llm(instance).call("This public input exceeds the fixture limit")
    with pytest.raises(error):
        asyncio.run(instance.environment.exec("echo public"))
    assert generator.calls == verifier.calls == runner.calls == []


@pytest.mark.parametrize(
    "error",
    [
        UnknownOperation("lost response"),
        ModelClientError("http_error", "authentication failed", status=401),
        ModelClientError("codex_plan_turn_failed", "inference turn failed"),
    ],
)
def test_bound_fatal_response_never_replays_or_dispatches_another_role(tmp_path, error):
    model = Model("generator", error)
    instance, runner, _, verifier, _ = bridge(tmp_path, model)
    with pytest.raises((UnknownOperation, ModelClientError)):
        bound_llm(instance).call("Public task")
    with pytest.raises((UnknownOperation, ModelClientError)):
        bound_llm(instance, "verifier").call("Must stop")
    with pytest.raises((UnknownOperation, ModelClientError)):
        asyncio.run(instance.environment.exec("echo public"))
    resumed = restart_bridge(instance)
    with pytest.raises((UnknownOperation, ModelClientError)):
        bound_llm(resumed).call("Public task")
    assert len(model.calls) == 1 and verifier.calls == runner.calls == []


def test_completed_bound_model_and_command_resume_from_journal(tmp_path):
    instance, runner, generator, _, _ = bridge(tmp_path)
    first = bound_llm(instance).call("Public task")
    output = asyncio.run(instance.environment.exec("echo public"))
    counts = len(generator.calls), len(runner.calls)
    resumed = restart_bridge(instance)
    assert bound_llm(resumed).call("Public task") == first
    resumed_output = asyncio.run(resumed.environment.exec("echo public"))
    assert resumed_output == output
    assert counts == (len(generator.calls), len(runner.calls))


def test_bound_factories_keep_concurrent_task_and_role_clients_separate(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    def run(marker):
        instance, _, generator, verifier, _ = bridge(tmp_path / marker)
        bound_llm(instance).call("Generator " + marker)
        bound_llm(instance, "verifier").call("Verifier " + marker)
        return generator.calls, verifier.calls

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["one", "two"]))
    for marker, (generator, verifier) in zip(["one", "two"], results, strict=True):
        assert len(generator) == len(verifier) == 1
        assert "Generator " + marker in str(generator)
        assert "Verifier " + marker in str(verifier)
        assert "Verifier " not in str(generator) and "Generator " not in str(verifier)


def test_actual_cleanup_failure_is_fatal_and_keeps_sealed_evidence(tmp_path):
    instance, runner, generator, verifier, _ = bridge(tmp_path)
    runner.failure = "cleanup_failed"
    with pytest.raises(ContainerUnavailable, match="cleanup_failed"):
        asyncio.run(instance.environment.exec("echo public"))
    with pytest.raises(ContainerUnavailable, match="cleanup_failed"):
        bound_llm(instance).call("Must stop")
    records = [
        instance.journal.response(json.loads(path.read_text())["operation_id"])
        for path in instance.journal.root.glob("*/request.json")
    ]
    assert any(record.get("failure") == "cleanup_failed" for record in records)
    assert generator.calls == verifier.calls == []
