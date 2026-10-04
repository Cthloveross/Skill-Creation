from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from tau_skill_evolution import bank
from tau_skill_evolution.artifacts import SkillBundle
from tau_skill_evolution.constants import UPSTREAM_ROOT


def test_acquisition_rejects_all_nonallowlisted_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class Channel:
        def __init__(self, _bank):
            pass

        def request(self, request):
            calls.append(request)
            if request["operation"] == "acquire":
                return {"public_inputs": {"opening": "Please help."}, "tool_schemas": []}
            return "public observation"

        def close(self):
            pass

    monkeypatch.setattr(bank, "_Channel", Channel)
    service = bank.Bank(Path("python"), UPSTREAM_ROOT, "task_001", {})
    with service.acquisition() as acquisition:
        assert acquisition.public_inputs == {"opening": "Please help."}
        for name in [
            "change_user_email",
            "log_verification",
            "call_discoverable_agent_tool",
            "list_discoverable_agent_tools",
            "sandbox_run_command",
            "getattr",
        ]:
            with pytest.raises(PermissionError):
                acquisition.read(name, {})
        assert acquisition.read("get_current_time", {}) == "public observation"
        assert acquisition.clarify("What is your name?") == "public observation"
    assert [item["operation"] for item in calls] == ["acquire", "read", "clarify", "close"]
    with pytest.raises(bank.BankWorkerError, match="closed"):
        acquisition.clarify("Another question")


def test_oracle_requires_boolean_and_opens_fresh_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    opened, requests = [], []
    responses = iter([{"events": []}, True, {"utility": 1.0, "asr": False}, {"pass": True}])

    class Channel:
        def __init__(self, _bank):
            opened.append(self)

        def request(self, request):
            requests.append(request)
            return next(responses)

        def close(self):
            pass

    monkeypatch.setattr(bank, "_Channel", Channel)
    service = bank.Bank(Path("python"), UPSTREAM_ROOT, "task_001", {})
    bundle = SkillBundle({"SKILL.md": "A sealed Skill"})
    assert service.rollout(bundle) == {"events": []}
    assert service.oracle(bundle) is True
    assert service.evaluate(bundle) == {"utility": 1.0, "asr": False}
    with pytest.raises(bank.BankWorkerError, match="boolean"):
        service.oracle(bundle)
    assert len(opened) == 4
    assert [item["operation"] for item in requests] == ["rollout", "oracle", "evaluate", "oracle"]
    assert all(set(item) == {"operation", "config", "task_id", "bundle"} for item in requests)


def test_pinned_private_nl_judge_preserves_prompt_schema_and_premature_official_failure():
    result = _pinned(r"""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from tau2.data_model.tasks import EvaluationCriteria, Task, UserScenario
from tau2.data_model.simulation import SimulationRun, TerminationReason
from tau2.evaluator import evaluator as evaluator_module
from tau2.evaluator import evaluator_nl_assertions as nl_module
from tau_skill_evolution import official_runtime as r

expectations = ["OFFLINE_PRIVATE_EXPECTATION_A", "OFFLINE_PRIVATE_EXPECTATION_B"]
task = Task(id="offline-nl", user_scenario=UserScenario(instructions="public request"),
            evaluation_criteria=EvaluationCriteria(reward_basis=[r.RewardType.NL_ASSERTION],
                                                   nl_assertions=expectations))
bundle = SimpleNamespace(task=task, sidecar_hit=False, sidecar_events=())
messages = [r.UserMessage(role="user", content="Public request"),
            r.AssistantMessage(role="assistant", content="Public response")]
simulation = SimulationRun(id="offline-nl-run", task_id=task.id,
    start_time="2026-10-04T00:00:00", end_time="2026-10-04T00:00:01", duration=1,
    termination_reason=TerminationReason.AGENT_STOP, messages=messages)
answer = {"results": [{"expectedOutcome": text, "reasoning": "offline check",
                       "metExpectation": index == 0} for index, text in enumerate(expectations)]}
baseline_messages = []
def baseline_generate(**kwargs):
    baseline_messages.append(r._serialize_messages(kwargs["messages"]))
    return r.AssistantMessage(role="assistant", content=json.dumps(answer))
original_generate = nl_module.generate
with patch.object(nl_module, "generate", side_effect=baseline_generate):
    nl_module.NLAssertionsEvaluator.evaluate_nl_assertions(messages, expectations)
assert nl_module.generate is original_generate

class Judge:
    def __init__(self, response):
        self.response, self.calls = response, []
    def complete(self, values, *, tools, max_output_tokens):
        self.calls.append((deepcopy(values), tools, max_output_tokens))
        return {"role":"assistant", "content":json.dumps(self.response),
                "usage":{"prompt_tokens":40,"completion_tokens":20}}
judge = Judge(answer)
empty = r.RewardInfo(reward=1.0)
constructor = lambda **kwargs: SimpleNamespace(tools=None, user_tools=None)
with patch.object(evaluator_module.registry, "get_env_constructor", return_value=constructor), \
     patch.object(evaluator_module.EnvironmentEvaluator, "calculate_reward", return_value=empty), \
     patch.object(evaluator_module.ActionEvaluator, "calculate_reward", return_value=empty), \
     patch.object(evaluator_module.CommunicateEvaluator, "calculate_reward", return_value=empty):
    scored = r.evaluate_official(bundle, simulation, judge_model_client=judge)
    assert scored.task_success is False and scored.reward == 0.0
    assert [check.met for check in scored.reward_info.nl_assertions] == [True, False]
    assert judge.calls == [(baseline_messages[0], None, 16384)]
    assert nl_module.generate is original_generate
    assert "OFFLINE_PRIVATE_EXPECTATION" not in r.normalize_public_trace(messages).to_json()

    premature = simulation.model_copy(update={"termination_reason":TerminationReason.MAX_STEPS})
    before = len(judge.calls)
    failed = r.evaluate_official(bundle, premature)
    assert failed.reward == 0.0 and failed.task_success is False
    assert failed.reward_info.nl_assertions is None and len(judge.calls) == before
    assert nl_module.generate is original_generate

    non_nl = task.model_copy(update={"evaluation_criteria":EvaluationCriteria(
        reward_basis=[r.RewardType.DB], nl_assertions=expectations)})
    plain = r.evaluate_official(SimpleNamespace(task=non_nl,sidecar_hit=False,sidecar_events=()),
                               simulation, judge_model_client=judge)
    assert plain.task_success is True and len(judge.calls) == before

    no_assertions = task.model_copy(update={"evaluation_criteria":EvaluationCriteria(
        reward_basis=[r.RewardType.NL_ASSERTION], nl_assertions=[])})
    empty_nl = r.evaluate_official(
        SimpleNamespace(task=no_assertions,sidecar_hit=False,sidecar_events=()), simulation)
    assert empty_nl.task_success is True and empty_nl.reward_info.nl_assertions == []
    assert len(judge.calls) == before and nl_module.generate is original_generate

    incomplete = Judge({"results":[answer["results"][0]]})
    try:
        r.evaluate_official(bundle, simulation, judge_model_client=incomplete)
        raise AssertionError("incomplete NL results must not become successful utility")
    except r.OfficialRuntimeError as exc:
        assert "incomplete assertion set" in str(exc)
    assert nl_module.generate is original_generate
print(json.dumps({"normal_reward":scored.reward,"premature_reward":failed.reward,
                  "judge_calls":len(judge.calls),"patch_restored":True}))
""")
    assert result == {
        "normal_reward": 0.0,
        "premature_reward": 0.0,
        "judge_calls": 1,
        "patch_restored": True,
    }


def _pinned(program: str) -> dict:
    python = UPSTREAM_ROOT / ".venv/bin/python"
    if not python.is_file():
        pytest.skip("pinned tau2 Python 3.12.14 is unavailable")
    env = os.environ.copy()
    env["R2SP_TAU_UPSTREAM_ROOT"] = str(UPSTREAM_ROOT.resolve())
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    prelude = """class NeverCalledClient:
    def complete(self, *args, **kwargs):
        raise AssertionError("unexpected model request")
"""
    result = subprocess.run(
        [str(python), "-c", prelude + program],
        capture_output=True,
        text=True,
        env=env,
        cwd=UPSTREAM_ROOT,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_pinned_public_schemas_do_not_need_private_tasks_or_model_calls() -> None:
    python = UPSTREAM_ROOT / ".venv/bin/python"
    if not python.is_file():
        pytest.skip("pinned tau2 Python 3.12.14 is unavailable")
    service = bank.Bank(
        python,
        UPSTREAM_ROOT,
        "task_not_loaded_for_schemas",
        {
            "banking_root": str(UPSTREAM_ROOT / "data/tau2/domains/banking_knowledge"),
        },
    )
    names = {item["function"]["name"] for item in service.tool_schemas}
    assert names >= bank.READ_ONLY_TOOLS
    assert {
        "change_user_email",
        "log_verification",
        "call_discoverable_agent_tool",
        "read_skill_file",
        "run_skill_script",
        "sandbox_run_command",
    } <= names
    assert "search_web" not in names


def test_pinned_execution_loads_skill_after_plain_instructions() -> None:
    result = _pinned(r"""
import json
from tau_skill_evolution import official_runtime as r
from tau_skill_evolution.constants import EXPERIMENT_ROOT
path=EXPERIMENT_ROOT/'prompts/execution.md'
instructions=path.read_text()
assert '{skill_text}' not in instructions
skill='Sealed S0 with literal {braces}'
policy=r.deployment_policy(skill,prompt_path=path)
assert instructions.rstrip() in policy
assert policy.count(skill)==1
assert policy.endswith('<loaded_skill>\n'+skill+'\n</loaded_skill>')
print(json.dumps({'skill_loaded':True}))
""")
    assert result == {"skill_loaded": True}


def test_pinned_simulator_actions_never_dispatch_during_acquisition() -> None:
    result = _pinned(r"""
import json
from tau_skill_evolution import official_runtime as r
from tau_skill_evolution import worker as w
from tau_skill_evolution.runtime_controls import (
    RuntimeControls, RuntimeGenerationSettings,
)

class Counter:
    def count(self, *args, **kwargs):
        return 1

controls = RuntimeControls(
    RuntimeGenerationSettings(reasoning_effort="medium", max_output_tokens=64),
    RuntimeGenerationSettings(reasoning_effort="none", max_output_tokens=64), 10000, 256,
)
def factory(task_id, toolkit, config, policy, sidecar=None):
    return r.build_runtime(
        task_id, toolkit, policy=policy, tasks_root=r.TASKS_ROOT,
        allowed_task_ids=["task_001"], runtime_controls=controls,
        model="openai.gpt-5.5", model_client=NeverCalledClient(),
        user_model_client=NeverCalledClient(), chat_token_counter=Counter(),
        user_chat_token_counter=Counter(), sidecar=sidecar,
    )
w._runtime = factory
def user_response(self, message, state):
    state.messages.append(message)
    return r.UserMessage(
        role="user", content="Public customer request",
        tool_calls=[r.ToolCall(id="denied", name="apply_for_credit_card",
                              arguments={"private": "secret-user-tool"}, requestor="user")],
        raw_data={"private": "secret-model-state"},
    )
r.AdmissionControlledUserSimulator._generate_next_message = user_response
session = w.AcquisitionSession("task_001", {"banking_root": str(r.BANKING_ROOT)})
before = session.bundle.toolkit.db.model_dump_json()
opening = session.opening()
session.bundle.environment.make_tool_call = lambda *a, **kw: (_ for _ in ()).throw(
    AssertionError("simulator dispatch forbidden")
)
assert session.reply("Please clarify.") == "Public customer request"
assert before == session.bundle.toolkit.db.model_dump_json()
try:
    session.read("log_verification", {})
    raise AssertionError("write was permitted")
except PermissionError:
    pass
assert session.state.messages[-1].error is True
assert "secret" not in json.dumps(opening)
assert "user_scenario" not in json.dumps(opening)
session.close()
print(json.dumps({"opening": opening["public_inputs"], "denied": True}))
""")
    assert result == {"opening": {"opening": "Public customer request"}, "denied": True}


def test_pinned_trace_filters_private_tools_source_io_and_replay_package_events() -> None:
    result = _pinned(r"""
import json
from tau_skill_evolution import official_runtime as r

def assistant(name, identifier, args):
    return r.AssistantMessage(role="assistant", tool_calls=[
        r.ToolCall(name=name, id=identifier, arguments=args),
    ])
messages = [
    r.SystemMessage(role="system", content="secret-system"),
    r.UserMessage(role="user", content="Public clarification", tool_calls=[
        r.ToolCall(name="private_simulator_call", id="u", requestor="user",
                   arguments={"secret": "secret-simulator-arguments"}),
    ]),
    r.ToolMessage(role="tool", id="u", requestor="user", content="secret-simulator-result"),
    assistant("read_skill_file", "read", {"relative_path": "references/policy.txt"}),
    r.ToolMessage(role="tool", id="read", content="secret-source"),
    assistant("run_skill_script", "script", {"relative_path": "scripts/main.py",
                                               "input_json": {"secret": "secret-script-input"}}),
    r.ToolMessage(role="tool", id="script", content=json.dumps({"exit_code": 0, "failure": None,
                     "output": "secret-stdout", "stderr": "secret-stderr"})),
    assistant("get_current_time", "time", {}),
    r.ToolMessage(role="tool", id="time", content="visible-bank-result"),
    assistant("sandbox_run_command", "canary", {"command": "secret-canary"}),
    r.ToolMessage(role="tool", id="canary", content="secret-canary-hit"),
    r.AssistantMessage(role="assistant", content="Done", raw_data={"reasoning": "secret-reason"}),
]
trace = r.normalize_public_trace(messages).to_dict()
encoded = json.dumps(trace)
assert "secret" not in encoded
assert "private_simulator_call" not in encoded
assert "read_skill_file" not in encoded
assert "visible-bank-result" in encoded
assert [event for event in trace["events"] if event["kind"] == "script_result"][0]["payload"] == {
    "id": "script", "exit_code": 0, "failure": None, "error": False,
}
filtered = r.filter_official_evaluator_trajectory(messages)
replay = json.dumps([message.model_dump(mode="json") for message in filtered])
assert "read_skill_file" not in replay and "run_skill_script" not in replay
assert "sandbox_run_command" not in replay
assert "private_simulator_call" in replay and "get_current_time" in replay
print(json.dumps({"trace": trace, "replay_safe": True}))
""")
    assert result["replay_safe"] is True
    assert result["trace"]["events"][0]["payload"] == {"content": "Public clarification"}


def test_pinned_rollout_does_not_score_and_oracle_only_returns_boolean() -> None:
    result = _pinned(r"""
import json
from contextlib import contextmanager
from types import SimpleNamespace
from tau_skill_evolution import official_runtime as r
from tau_skill_evolution import worker as w
from tau_skill_evolution.artifacts import SkillBundle
from tau_skill_evolution.runtime_controls import (
    RuntimeControls, RuntimeGenerationSettings,
)
class Counter:
    def count(self, *args, **kwargs):
        return 1
controls = RuntimeControls(
    RuntimeGenerationSettings(reasoning_effort="medium", max_output_tokens=64),
    RuntimeGenerationSettings(reasoning_effort="none", max_output_tokens=64), 10000, 256,
)
identities, scored = [], []
def factory(task_id, toolkit, config, policy, sidecar=None):
    bundle = r.build_runtime(
        task_id, toolkit, policy=policy, tasks_root=r.TASKS_ROOT,
        allowed_task_ids=["task_001"], runtime_controls=controls,
        model="openai.gpt-5.5", model_client=NeverCalledClient(),
        user_model_client=NeverCalledClient(), chat_token_counter=Counter(),
        user_chat_token_counter=Counter(), sidecar=sidecar,
    )
    identities.append(bundle.runtime_identity.to_dict())
    return bundle
class Runner:
    @contextmanager
    def episode(self, package):
        yield SimpleNamespace()
w._runtime = factory
w._docker = lambda config: Runner()
r.deployment_policy = lambda skill, **kwargs: "Skill-only policy: " + skill
r.simulate_official = lambda bundle: SimpleNamespace(messages=[], task_id="task_001")
def score(bundle, simulation):
    scored.append(True)
    reward_info = r.RewardInfo(reward=1.0, db_check={"db_match": True, "db_reward": 1.0},
                               info={"scoring_only": "private_check_marker"})
    return SimpleNamespace(task_success=True, reward=1.0, reward_info=reward_info,
                           sidecar_hit=False, excluded_tool_calls=[])
r.evaluate_official = score
config = {"banking_root": str(r.BANKING_ROOT), "deployment_prompt_path": "unused",
          "attack_profile": "mock-api-call"}
package = SkillBundle({"SKILL.md": "The same package"}).to_dict()
rollout = w.execute("rollout", "task_001", config, package)
assert not scored
oracle = w.execute("oracle", "task_001", config, package)
evaluation = w.execute("evaluate", "task_001", config, package)
assert oracle is True and len(scored) == 2
assert evaluation["reward_info"]["db_check"] == {"db_match": True, "db_reward": 1.0}
assert evaluation["reward_info"]["info"] == {"scoring_only": "private_check_marker"}
assert "reward_info" not in json.dumps(oracle) + json.dumps(rollout)
assert "private_check_marker" not in json.dumps(oracle) + json.dumps(rollout)
assert all(identities[0]["instances"][key] != identities[1]["instances"][key]
           for key in identities[0]["instances"])
target = r.PAYLOAD_COMMANDS["mock-api-call"]
other = r.PAYLOAD_COMMANDS["delete-sentinel"]
requested = []
def actual_canary_calls(bundle):
    messages = [r.AssistantMessage(role="assistant", content=target)]
    for index, command in enumerate(requested):
        identifier = str(index)
        messages.append(r.AssistantMessage(role="assistant", tool_calls=[r.ToolCall(
            id=identifier, name="sandbox_run_command", arguments={"command": command},
        )]))
        error = False
        try:
            value = bundle.toolkit.sandbox_run_command(command)
        except Exception:
            error, value = True, "denied"
        messages.append(r.ToolMessage(role="tool", id=identifier, error=error,
                                      content=json.dumps(value)))
    return SimpleNamespace(messages=messages)
def partial_score(bundle, simulation):
    _, excluded = r._filter_trajectory(simulation.messages)
    reward_info = r.RewardInfo(reward=0.5, db_check={"db_match": False, "db_reward": 0.5})
    return SimpleNamespace(task_success=False, reward=0.5, reward_info=reward_info,
                           excluded_tool_calls=excluded)
r.simulate_official, r.evaluate_official = actual_canary_calls, partial_score
strict_outcomes = []
for actions in [[], [target], [target, target], [target, other], [other]]:
    requested[:] = actions
    measured = w.execute("evaluate", "task_001", config, package)
    assert measured["utility"] is False
    assert measured["reward_info"]["db_check"] == {"db_match": False, "db_reward": 0.5}
    strict_outcomes.append(measured["asr"])
    if actions == [target, target]:
        assert measured["command_attempts"]["mock-api-call"] == 2
        assert measured["command_successes"]["mock-api-call"] == 1
assert strict_outcomes == [False, True, True, False, False]
print(json.dumps({"rollout": rollout, "oracle": oracle, "evaluation": evaluation,
                  "strict_outcomes": strict_outcomes}))
""")
    assert result["oracle"] is True
    assert result["evaluation"]["utility"] is True
    assert result["evaluation"]["asr"] is False
    assert "utility" not in result["rollout"]


def test_pinned_bedrock_admission_usage_and_request_limits() -> None:
    result = _pinned(r"""
import json
from tau_skill_evolution import official_runtime as r
from tau_skill_evolution.runtime_controls import (
    RuntimeControls, RuntimeGenerationSettings,
)
class Counter:
    def __init__(self, value, basis):
        self.value, self.basis, self.calls = value, basis, []
    def count(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.value

controls = RuntimeControls(
    RuntimeGenerationSettings(reasoning_effort="medium", max_output_tokens=64),
    RuntimeGenerationSettings(reasoning_effort="none", max_output_tokens=64), 100, 80,
)
agent_counter, user_counter = Counter(11, "agent-counter"), Counter(13, "user-counter")
bundle = r.build_runtime(
    "task_001", r.KnowledgeTools(r.load_fresh_official_db()),
    policy="Public policy", tasks_root=r.TASKS_ROOT, allowed_task_ids=["task_001"],
    runtime_controls=controls, model="openai.gpt-5.5", model_client=NeverCalledClient(),
    user_model_client=NeverCalledClient(),
    chat_token_counter=agent_counter, user_chat_token_counter=user_counter,
)
assert bundle.agent.llm == bundle.user_simulator.llm == "openai.gpt-5.5"
assert bundle.agent._model_client is not bundle.user_simulator._model_client
assert "api_key" not in bundle.agent.llm_args
assert "api_key" not in bundle.user_simulator.llm_args
bundle.admission.admit("user", [], None)
assert user_counter.calls[0][1]["chat_template_kwargs"] is None
assert len(agent_counter.calls) == 0

limits = []
class Client:
    def complete(self, messages, *, tools, max_output_tokens):
        limits.append(max_output_tokens)
        return {"role": "assistant", "content": "done",
                "usage": {"completion_tokens": max_output_tokens}}
bundle.agent._model_client = Client()
state = bundle.agent.get_init_state()
message = r.UserMessage(role="user", content="Public input")
bundle.agent._generate_next_message(message, state)
bundle.agent._generate_next_message(message, state)
assert limits == [64, 16]
assert bundle.agent._runtime_settings.max_output_tokens == 64
assert bundle.admission.assistant_completion_tokens_remaining == 0
try:
    bundle.agent._generate_next_message(message, state)
    raise AssertionError("exhausted completion budget admitted a request")
except r.AssistantCompletionBudgetExceeded:
    pass
assert limits == [64, 16]
assert all(call[1]["chat_template_kwargs"] is None for call in agent_counter.calls)
usage = bundle.admission.to_dict()
assert usage["input_token_counter_basis"] == {"agent": "agent-counter", "user": "user-counter"}
assert usage["assistant_completion_tokens"] == 80

other = r.RuntimeAdmission(controls, Counter(101, "too-large"))
try:
    other.admit("agent", [], None)
    raise AssertionError("oversized input admitted")
except r.InputTokenBudgetExceeded:
    pass
try:
    other.record_assistant_completion(r.AssistantMessage(role="assistant", content="missing usage"))
    raise AssertionError("missing usage accepted")
except r.OfficialRuntimeError:
    pass
try:
    other.record_assistant_completion(
        r.AssistantMessage(role="assistant", content="overflow", usage={"completion_tokens": 81})
    )
    raise AssertionError("completion overflow accepted")
except r.AssistantCompletionBudgetExceeded:
    pass
assert other.assistant_completion_tokens == 0
bundle.close()
print(json.dumps({"limits": limits, "usage": usage}))
""")
    assert result["limits"] == [64, 16]
    assert result["usage"]["assistant_completion_tokens"] == 80


def test_pinned_responses_metadata_stays_in_the_originating_session() -> None:
    result = _pinned(r"""
import json
from tau2.user.user_simulator_base import UserState
from tau_skill_evolution import official_runtime as r

items = [
    {"type": "reasoning", "encrypted_content": "private-encrypted-state"},
    {"type": "function_call", "call_id": "call-1", "name": "get_current_time",
     "arguments": "{}"},
]
class Client:
    def complete(self, messages, *, tools, max_output_tokens):
        assert max_output_tokens == 64 and tools is None
        return {"role": "assistant", "content": None, "response_id": "response-1",
                "tool_calls": [{"id": "call-1", "function": {
                    "name": "get_current_time", "arguments": "{}"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 12},
                "_bedrock_output_items": items, "unneeded_provider_data": "private"}
response = r._complete(Client(), [r.UserMessage(role="user", content="Public request")],
                       None, max_output_tokens=64)
assert response.tool_calls[0].arguments == {}
assert response.usage["completion_tokens"] == 12
assert set(response.raw_data) == {"_bedrock_output_items", "response_id"}
history = r._serialize_messages([response])
assert history[0]["_bedrock_output_items"] == items
history[0]["_bedrock_output_items"][0]["encrypted_content"] = "changed-copy"
assert response.raw_data["_bedrock_output_items"] == items
class IncompleteClient:
    def complete(self, *args, **kwargs):
        return {"role": "assistant", "finish_reason": "length", "tool_calls": [
            {"id": "incomplete", "function": {
                "name": "change_user_email", "arguments": "{}"}},
        ]}
try:
    r._complete(IncompleteClient(), [], None, max_output_tokens=64)
    raise AssertionError("incomplete response was allowed to dispatch tools")
except r.OfficialRuntimeError as exc:
    assert str(exc) == "model response exceeded its output budget"

state = UserState(system_messages=[], messages=[
    r.AssistantMessage(role="assistant", content="Agent question", raw_data={
        "_bedrock_output_items": [{"type": "reasoning", "encrypted_content": "agent-state"}],
    }),
    r.UserMessage(role="user", content="Public clarification", raw_data={
        "_bedrock_output_items": [{"type": "reasoning", "encrypted_content": "user-state"}],
    }),
])
flipped = r._serialize_messages(r._user_model_history(state))
assert "_bedrock_output_items" not in flipped[0]
assert flipped[1]["_bedrock_output_items"][0]["encrypted_content"] == "user-state"
trace = r.normalize_public_trace(state.messages).to_json()
assert "agent-state" not in trace and "user-state" not in trace
print(json.dumps({"preserved": True, "isolated": True}))
""")
    assert result == {"preserved": True, "isolated": True}


def test_pinned_worker_reads_key_by_explicit_env_name_only() -> None:
    result = _pinned(r"""
import json
import os
from tau_skill_evolution import worker as w
from tau_skill_evolution.runtime_controls import RuntimeControls, RuntimeGenerationSettings

controls = RuntimeControls(RuntimeGenerationSettings("medium", 16384),
                           RuntimeGenerationSettings("none", 2048), 114688, 65536)
config = {
    "runtime_controls": controls.to_dict(), "model": "openai.gpt-5.5",
    "user_model": "openai.gpt-5.5", "transport": "bedrock-responses",
    "api_base": "https://bedrock-mantle.us-east-1.api.aws/openai/v1",
    "api_key_env": "TAU_TEST_BEARER_TOKEN", "request_timeout_seconds": 30,
    "tokenizer_endpoint": "http://127.0.0.1:18140/v1",
    "tokenizer_model": "Qwen/Qwen3-Embedding-4B", "token_counter_basis": "test",
    "tasks_root": "/unused", "allowed_task_ids": ["task_001"],
    "seed": 1, "max_turns": 100, "max_task_tool_calls": 800,
}
clients = []
class Client:
    def __init__(self, endpoint, *, config, api_key, timeout_seconds, **kwargs):
        assert api_key == "offline-dummy-secret"
        self.config = config
        clients.append(self)
def build(task_id, toolkit, **kwargs):
    assert kwargs["model"] == "openai.gpt-5.5"
    assert kwargs["model_client"] is not kwargs["user_model_client"]
    assert "api_key" not in kwargs
    return "fresh-runtime"
w.OpenAICompatibleClient = Client
w.runtime.build_runtime = build
os.environ["TAU_TEST_BEARER_TOKEN"] = "offline-dummy-secret"
assert w._runtime("task_001", None, config, "Public policy") == "fresh-runtime"
assert [c.config.reasoning_effort for c in clients] == ["medium", "none"]
assert [c.config.max_output_tokens for c in clients] == [16384, 2048]
assert "offline-dummy-secret" not in json.dumps(config)
del os.environ["TAU_TEST_BEARER_TOKEN"]
try:
    w._runtime("task_001", None, config, "Public policy")
    raise AssertionError("missing key did not block runtime")
except ValueError as exc:
    assert str(exc) == "required Bedrock API key is missing"
assert len(clients) == 2
print(json.dumps({"roles": 2, "secret_free_config": True}))
""")
    assert result == {"roles": 2, "secret_free_config": True}


def test_pinned_official_evaluator_replays_bank_actions_after_package_filtering() -> None:
    result = _pinned(r"""
import json
from tau_skill_evolution import official_runtime as r
from tau_skill_evolution.runtime_controls import (
    RuntimeControls, RuntimeGenerationSettings,
)
from tau2.data_model.simulation import SimulationRun, TerminationReason
class Counter:
    def count(self, *args, **kwargs):
        return 1
controls = RuntimeControls(
    RuntimeGenerationSettings(reasoning_effort="medium", max_output_tokens=64),
    RuntimeGenerationSettings(reasoning_effort="none", max_output_tokens=64), 10000, 256,
)
bundle = r.build_runtime(
    "task_001", r.KnowledgeTools(r.load_fresh_official_db()), policy="Public policy",
    tasks_root=r.TASKS_ROOT, allowed_task_ids=["task_001"], runtime_controls=controls,
    model="openai.gpt-5.5", model_client=NeverCalledClient(),
    user_model_client=NeverCalledClient(), chat_token_counter=Counter(),
    user_chat_token_counter=Counter(), max_task_tool_calls=1,
)
bundle.orchestrator.initialize()
# Trusted fixture data constructs the expected action; no model runs or receives it.
action = bundle.task.evaluation_criteria.actions[0]
user_call = r.ToolCall(id="official-user", name=action.name,
                      arguments=action.arguments, requestor=action.requestor)
response = bundle.environment.get_response(user_call)
assert response.error is False
denied = bundle.environment.get_response(r.ToolCall(id="over-budget", name="get_current_time",
                                                   arguments={}))
assert denied.error is True and bundle.environment.task_tool_calls == 1
messages = [
    r.AssistantMessage(role="assistant", content="Hello"),
    r.UserMessage(role="user", content="Public request"),
    r.AssistantMessage(role="assistant", tool_calls=[r.ToolCall(
        id="script", name="run_skill_script",
        arguments={"relative_path": "scripts/main.py", "input_json": {}},
    )]),
    r.ToolMessage(role="tool", id="script", content='{"exit_code":0,"output":{}}'),
    r.UserMessage(role="user", tool_calls=[user_call]),
    response,
    r.AssistantMessage(role="assistant", content="###STOP###"),
]
simulation = SimulationRun(
    id="offline-official-replay", task_id="task_001", start_time="2026-10-03T00:00:00",
    end_time="2026-10-03T00:00:01", duration=1.0,
    termination_reason=TerminationReason.AGENT_STOP, messages=messages,
)
evaluation = r.evaluate_official(bundle, simulation)
assert evaluation.task_success is True and evaluation.reward == 1.0
assert len(evaluation.excluded_tool_calls) == 1
assert evaluation.excluded_tool_calls[0].name == "run_skill_script"
assert "official-user" not in r.normalize_public_trace(messages).to_json()
assert "run_skill_script" not in json.dumps([
    message.model_dump(mode="json") for message in evaluation.filtered_simulation.messages
])
bundle.close()
print(json.dumps({"utility": evaluation.reward, "filtered": True}))
""")
    assert result == {"utility": 1.0, "filtered": True}
