from __future__ import annotations

import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from tau_skill_evolution.artifacts import EvolutionSubmission, FrozenBase, SkillBundle, load_bundle
from tau_skill_evolution.container import ProgramResult
from tau_skill_evolution.core._canonical import canonical_json_sha256, thaw_json
from tau_skill_evolution.generator import (
    CreationFailure,
    GeneratorContextBudgetExhausted,
    RevisionConversation,
    RevisionFailure,
    execute_initial,
    failure_categories,
    generate_initial,
    parse_bundle_response,
    public_feedback_history,
    revise,
)
from tau_skill_evolution.journal import Journal
from tau_skill_evolution.model import SerializedChatTokenCounter, _assistant_response


def _base():
    return FrozenBase(
        ({"page_id": "selected", "title": "Selected policy", "content": "use tool"},),
        {"opening_message": "Help", "clarifications": [], "read_only_observations": []},
    )


def _raw(content="instructions"):
    return {
        "files": [
            {"path": "SKILL.md", "content": content},
            {"path": "scripts/main.py", "content": "this is intentionally invalid Python !!!"},
            {"path": "references/policy.txt", "content": "policy"},
        ]
    }


class EditingSession:
    """Offline learning environment; never runs a model-provided shell command."""

    tool_schemas = [
        {
            "type": "function",
            "function": {
                "name": "public_task_tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    def __init__(self):
        self.candidate = {}
        self.commands = []
        self.tool_calls = []
        self.raw_results = {}
        self.beginnings = []
        self.cleanup_failed = False

    def begin_attempt(self, parent, *, initial, operation_id):
        self.candidate = dict(parent.files)
        self.beginnings.append((parent.bundle_hash, initial, operation_id))

    def terminal(self, command):
        self.commands.append(command)
        operation = json.loads(command)
        if operation[0] == "write":
            self.candidate[operation[1]] = operation[2]
        elif operation[0] == "read_raw":
            return ProgramResult(0, {"stdout": json.dumps(self.raw_results[operation[1]])})
        elif operation[0] == "verbose":
            return ProgramResult(
                None,
                {"stdout": "x" * 40000, "data": "y" * 40000},
                stderr="output exceeded",
                failure="output_limit",
            )
        return ProgramResult(0, {"stdout": "local self-check", "stderr": ""})

    def execute_tool(self, name, arguments, *, operation_id):
        self.tool_calls.append((name, dict(arguments), operation_id))
        return {"status": "completed", "opening_message": "public task response"}

    def snapshot(self):
        return {
            "workspace_hash": canonical_json_sha256(self.candidate),
            "files": dict(self.candidate),
        }

    def record_tool_result(self, operation_id, result):
        path = f"/work/tool-results/{hashlib.sha256(operation_id.encode()).hexdigest()}.json"
        if path in self.raw_results:
            assert self.raw_results[path] == thaw_json(result)
        self.raw_results[path] = thaw_json(result)
        return path

    def submit(self, parent, *, initial, operation_id):
        bundle = SkillBundle(
            self.candidate, parent_hash=parent.parent_hash if initial else parent.bundle_hash
        )
        trace = {"events": [{"type": "tool", "name": item[0]} for item in self.tool_calls]}
        return EvolutionSubmission(
            bundle,
            trace,
            "offline-learning-episode",
            len(self.commands) + len(self.tool_calls),
            initial=initial,
        )


class EditingModel:
    def __init__(self, content="updated"):
        self.content, self.requests = content, []
        self.token_counter = SimpleNamespace(
            count=lambda messages, **kwargs: len(json.dumps([messages, kwargs]))
        )

    def complete(self, messages, **kwargs):
        self.requests.append(copy.deepcopy(messages))
        if len(self.requests) == 1:
            name, arguments = (
                "terminal",
                {"command": json.dumps(["write", "SKILL.md", self.content])},
            )
        else:
            name, arguments = "submit_revision", {}
        return {
            "role": "assistant",
            "content": None,
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": str(len(self.requests)),
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        }


class ToolSequenceModel(EditingModel):
    def __init__(self, actions):
        super().__init__()
        self.actions = iter(actions)
        self.tool_schemas = []

    def complete(self, messages, **kwargs):
        self.requests.append(copy.deepcopy(messages))
        self.tool_schemas.append(copy.deepcopy(kwargs["tools"]))
        name, arguments = next(self.actions)
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": str(len(self.requests)),
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        }


def test_revision_edits_and_executes_in_the_learning_environment_before_submit(tmp_path):
    base, parent = _base(), parse_bundle_response(_raw())
    session = EditingSession()
    model = ToolSequenceModel(
        [
            ("terminal", {"command": json.dumps(["write", "SKILL.md", "first fix"])}),
            ("public_task_tool", {}),
            ("terminal", {"command": json.dumps(["write", "SKILL.md", "complete fix"])}),
            ("public_task_tool", {}),
            ("submit_revision", {}),
        ]
    )
    journal = Journal(tmp_path / "journal")
    report = {"diagnosis": "VERIFIER_SECRET_DETAIL", "test_source": "PRIVATE_TEST_SOURCE"}
    result = revise(
        model, parent, base.public_inputs, base, report, journal=journal, session=session
    )
    assert result.bundle.files["SKILL.md"] == "complete fix"
    assert result.bundle.parent_hash == parent.bundle_hash
    assert result.execution_id == "offline-learning-episode"
    assert result.operation_cursor == 4 and len(session.tool_calls) == 2
    assert len(model.requests) == 5
    assert {item["function"]["name"] for item in model.tool_schemas[0]} == {
        "terminal",
        "submit_revision",
        "public_task_tool",
    }
    assert "public task response" in json.dumps(model.requests[2])
    assert "VERIFIER_SECRET_DETAIL" not in json.dumps(model.requests)
    assert "PRIVATE_TEST_SOURCE" not in json.dumps(model.requests)
    restored = revise(
        model, parent, base.public_inputs, base, report, journal=journal, session=session
    )
    assert restored == result and len(model.requests) == 5 and len(session.tool_calls) == 2
    assert journal.response("revise/submitted")["submission"] == result.to_dict()


def test_revision_recovers_sealed_task_tool_without_repeating_execution(tmp_path):
    class InterruptedJournal(Journal):
        interrupted = False

        def dispatch(self, operation_id, *args, **kwargs):
            result = super().dispatch(operation_id, *args, **kwargs)
            if operation_id == "revise/model-1/tool-0" and not self.interrupted:
                self.interrupted = True
                raise KeyboardInterrupt()
            return result

    base, parent = _base(), parse_bundle_response(_raw())
    model = ToolSequenceModel(
        [
            ("terminal", {"command": json.dumps(["write", "SKILL.md", "fix"])}),
            ("public_task_tool", {}),
            ("submit_revision", {}),
        ]
    )
    journal, session = InterruptedJournal(tmp_path / "journal"), EditingSession()

    def attempt():
        return revise(model, parent, base.public_inputs, base, {}, journal=journal, session=session)

    with pytest.raises(KeyboardInterrupt):
        attempt()
    result = attempt()
    assert result.bundle.files["SKILL.md"] == "fix"
    assert len(session.tool_calls) == 1 and len(model.requests) == 3


def test_unknown_task_tool_stops_without_submitting_or_resending(tmp_path):
    from tau_skill_evolution.journal import UnknownOperation

    class UnknownSession(EditingSession):
        def execute_tool(self, name, arguments, *, operation_id):
            super().execute_tool(name, arguments, operation_id=operation_id)
            raise TimeoutError()

    base, parent = _base(), parse_bundle_response(_raw())
    model = ToolSequenceModel([("public_task_tool", {}), ("submit_revision", {})])
    journal, session = Journal(tmp_path / "journal"), UnknownSession()
    for _ in range(2):
        with pytest.raises(UnknownOperation):
            revise(model, parent, base.public_inputs, base, {}, journal=journal, session=session)
    assert len(session.tool_calls) == len(model.requests) == 1
    assert not journal.completed("revise/submitted")


def test_initial_execution_submits_exact_s0_without_creating_another_package(tmp_path):
    base, initial = _base(), parse_bundle_response(_raw())
    model = ToolSequenceModel([("public_task_tool", {}), ("submit_revision", {})])
    journal, session = Journal(tmp_path / "journal"), EditingSession()
    result = execute_initial(
        model, initial, base.public_inputs, base, journal=journal, session=session
    )
    assert result.initial and result.bundle.to_dict() == initial.to_dict()
    assert result.public_trace["events"][0]["name"] == "public_task_tool"
    assert len(model.requests) == 2 and len(session.tool_calls) == 1
    assert journal.completed("execute_initial/submitted")


def test_initial_execution_rejects_package_edit_before_submit(tmp_path):
    base, initial = _base(), parse_bundle_response(_raw())
    model = EditingModel("modified S0")
    journal = Journal(tmp_path / "journal")
    with pytest.raises(RevisionFailure, match="initial_execution_modified_bundle"):
        execute_initial(
            model, initial, base.public_inputs, base, journal=journal, session=EditingSession()
        )
    assert len(model.requests) == 1 and not journal.completed("execute_initial/submitted")
    assert initial.files["SKILL.md"] == "instructions"


def test_terminal_preview_is_bounded_while_raw_result_remains_readable(tmp_path):
    base, parent = _base(), parse_bundle_response(_raw())
    model = ToolSequenceModel(
        [("terminal", {"command": json.dumps(["verbose"])}), ("submit_revision", {})]
    )
    journal, session = Journal(tmp_path / "journal"), EditingSession()
    result = revise(model, parent, base.public_inputs, base, {}, journal=journal, session=session)
    tool_message = next(item for item in model.requests[1] if item["role"] == "tool")
    preview = json.loads(tool_message["content"])
    assert preview["failure"] == "output_limit" and preview["truncated"]
    assert (
        sum(len(value.encode()) for value in preview["output"].values())
        + len(preview["stderr"].encode())
        <= 8192
    )
    assert len(session.raw_results[preview["raw_path"]]["output"]["stdout"]) == 40000
    assert preview["raw_hash"] == canonical_json_sha256(session.raw_results[preview["raw_path"]])
    assert result.bundle.bundle_hash == parent.bundle_hash


def test_s0_generated_once_and_structure_only_validated(tmp_path):
    base = _base()
    calls = []

    def model(payload):
        calls.append(copy.deepcopy(payload))
        return _raw()

    journal = Journal(tmp_path / "journal")
    bundle = generate_initial(
        model, base.public_inputs, base, journal=journal, artifact_dir=tmp_path / "s0"
    )
    assert load_bundle(tmp_path / "s0") == bundle
    restored = generate_initial(
        lambda _: pytest.fail("S0 cannot be resent"),
        base.public_inputs,
        base,
        journal=journal,
        artifact_dir=tmp_path / "s0",
    )
    assert restored == bundle
    assert len(calls) == 1
    assert calls[0]["phase"] == "create"
    encoded = json.dumps(calls[0])
    for private in (
        "analyzer_reasoning",
        "gold_documents",
        "expected_actions",
        "database_target",
        "ASR",
        "unselected",
    ):
        assert private not in encoded
    assert "previous_bundle" not in calls[0]
    assert "intentionally invalid" in bundle.files["scripts/main.py"]


def test_generator_uses_fresh_messages_and_actual_configured_prompt(tmp_path):
    class Model:
        def __init__(self):
            self.messages = []
            self.token_counter = type("Counter", (), {"count": lambda _, messages: 100})()

        def complete(self, messages, *, seed=None):
            self.messages.append(messages)
            return {"content": json.dumps(_raw())}

    model = Model()
    base = _base()
    journal = Journal(tmp_path)
    generate_initial(
        model, base.public_inputs, base, journal=journal, system_prompt="configured prompt", seed=2
    )
    assert [message["role"] for message in model.messages[0]] == ["system", "user"]
    assert model.messages[0][0]["content"] == "configured prompt"
    with pytest.raises(ValueError, match="differs"):
        generate_initial(model, base.public_inputs, base, journal=journal, system_prompt="changed")
    assert len(model.messages) == 1


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not JSON",
        {"files": []},
        {"files": [{"path": "SKILL.md", "content": ""}]},
        {"files": [{"path": "../bad", "content": "bad"}]},
        {
            "files": [
                {"path": "SKILL.md", "content": "ok"},
                {"path": "SKILL.md", "content": "again"},
            ]
        },
        {"files": [{"path": "SKILL.md", "content": "ok", "mode": "symlink"}]},
        '{"files":[],"files":[]}',
    ],
)
def test_creation_failure_never_retries_or_feedbacks(tmp_path, raw):
    base = _base()
    calls = []

    def model(payload):
        calls.append(payload)
        return raw

    journal = Journal(tmp_path)
    for _ in range(2):
        with pytest.raises(CreationFailure, match="invalid_package"):
            generate_initial(model, base.public_inputs, base, journal=journal)
    assert len(calls) == 1
    assert journal.result("generate_initial")["status"] == "creation_failed"


def test_single_fenced_package_is_parsed_without_changing_the_role_json_contract(tmp_path):
    from tau_skill_evolution.generator import parse_model_json

    base, journal, calls = _base(), Journal(tmp_path / "journal"), []
    raw = {"content": "\n```json\n" + json.dumps(_raw()) + "\n```\n", "finish_reason": "stop"}

    def model(payload):
        calls.append(payload)
        return raw

    bundle = generate_initial(model, base.public_inputs, base, journal=journal)
    assert bundle == parse_bundle_response(_raw())
    assert generate_initial(model, base.public_inputs, base, journal=journal) == bundle
    assert len(calls) == 1 and journal.response("generate_initial") == raw
    with pytest.raises(ValueError):
        parse_model_json(raw)


def test_known_invalid_submission_can_be_corrected_in_the_same_revision(tmp_path):
    from tau_skill_evolution.artifacts import decode_package_text

    class Session(EditingSession):
        def submit(self, parent, *, initial, operation_id):
            if self.candidate["SKILL.md"] == "invalid candidate":
                decode_package_text(b"\xff", "references/cache.bin")
            return super().submit(parent, initial=initial, operation_id=operation_id)

    model = ToolSequenceModel(
        [
            ("terminal", {"command": json.dumps(["write", "SKILL.md", "invalid candidate"])}),
            ("submit_revision", {}),
            ("terminal", {"command": json.dumps(["write", "SKILL.md", "corrected candidate"])}),
            ("submit_revision", {}),
        ]
    )
    base, parent, journal = _base(), parse_bundle_response(_raw()), Journal(tmp_path)
    result = revise(model, parent, base.public_inputs, base, {}, journal=journal, session=Session())
    assert result.bundle.files["SKILL.md"] == "corrected candidate"
    assert result.bundle.parent_hash == parent.bundle_hash and len(model.requests) == 4
    rejected = journal.response("revise/model-1/tool-0")
    assert rejected["result"]["failure"] == "invalid_package"
    assert "non_utf8_package_file" in rejected["result"]["detail"]
    assert journal.status("revise/model-1/tool-0") == "COMPLETED"
    assert journal.completed("revise/submitted")


@pytest.mark.parametrize(
    "raw",
    [
        'Explanation\n```json\n{"files": []}\n```',
        '```json\n{"files": []}\n```\nExplanation',
        '```json\n{"files": []}\n```\n```json\n{"files": []}\n```',
        '```json\n{"files": [], "files": []}\n```',
        '```json\n{"files": [{"path": "SKILL.md", "content": "ok", "content": "other"}]}\n```',
        '```json\n{"files": [{"path": "../SKILL.md", "content": "ok"}]}\n```',
        '```json\n{"files": [{"path": "SKILL.md", "content": "ok"}]} trailing\n```',
        {"content": '```json\n{"files": []}\n```', "finish_reason": "length"},
    ],
)
def test_fenced_creation_rejects_ambiguous_or_unsafe_answers_without_retry(tmp_path, raw):
    base, journal, calls = _base(), Journal(tmp_path / "journal"), []

    def model(payload):
        calls.append(payload)
        return raw

    for _ in range(2):
        with pytest.raises(CreationFailure, match="invalid_package"):
            generate_initial(model, base.public_inputs, base, journal=journal)
    assert len(calls) == 1


def test_unknown_s0_request_is_terminal_and_not_resent(tmp_path):
    base = _base()
    calls = []

    def model(payload):
        calls.append(payload)
        raise TimeoutError()

    journal = Journal(tmp_path)
    for _ in range(2):
        with pytest.raises(CreationFailure, match="generation_result_unknown"):
            generate_initial(model, base.public_inputs, base, journal=journal)
    assert len(calls) == 1


def test_incomplete_bedrock_response_cannot_seal_s0_even_with_complete_json(tmp_path):
    raw = _assistant_response(
        {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": json.dumps(_raw())}],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 32768},
        }
    )
    base, journal, calls = _base(), Journal(tmp_path / "journal"), []

    def model(payload):
        calls.append(payload)
        return raw

    for _ in range(2):
        with pytest.raises(CreationFailure, match="invalid_package"):
            generate_initial(
                model,
                base.public_inputs,
                base,
                journal=journal,
                artifact_dir=tmp_path / "s0",
            )
    assert raw["finish_reason"] == "length"
    assert len(calls) == 1 and not (tmp_path / "s0").exists()
    assert journal.response("generate_initial") == raw
    assert journal.result("generate_initial") == {
        "status": "creation_failed",
        "reason": "invalid_package",
    }


@pytest.mark.parametrize("finish_reason", ["length", "tool_calls", "content_filter", None])
def test_role_json_requires_normal_finish_when_finish_reason_is_present(finish_reason):
    with pytest.raises(ValueError, match="did not finish normally"):
        parse_bundle_response({"content": json.dumps(_raw()), "finish_reason": finish_reason})
    with pytest.raises(ValueError, match="did not finish normally"):
        parse_bundle_response(
            {"content": "```json\n" + json.dumps(_raw()) + "\n```", "finish_reason": finish_reason}
        )


def test_analyzer_rejects_complete_json_from_an_incomplete_response():
    from tau_skill_evolution.acquisition import _decision

    decision = {
        "gaps": ["policy"],
        "action": {"kind": "search", "query": "policy"},
        "evidence": [],
        "document_scores": [],
        "sufficient": False,
        "coverage": {},
        "conflicts": [],
    }
    raw = _assistant_response(
        {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": json.dumps(decision)}],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 8192},
        }
    )
    with pytest.raises(ValueError, match="did not finish normally"):
        _decision(raw)


def test_revision_inherits_entire_previous_package_with_parent_hash(tmp_path):
    base = _base()
    previous = parse_bundle_response(_raw())
    model = EditingModel(previous.files["SKILL.md"] + " revised")
    next_bundle = revise(
        model,
        previous,
        base.public_inputs,
        base,
        {"diagnosis": "fix"},
        journal=Journal(tmp_path),
        operation_id="revision/1",
        session=EditingSession(),
    )
    assert next_bundle.bundle.parent_hash == previous.bundle_hash
    assert next_bundle.bundle.bundle_hash != previous.bundle_hash
    packet = json.loads(model.requests[0][1]["content"])
    assert packet["parent_bundle_hash"] == previous.bundle_hash
    assert packet["paths"]["candidate"] == "/work/candidate"
    assert "previous_bundle" not in packet
    assert json.loads(model.requests[0][1]["content"])["verification_feedback"] == {
        "passed": False,
        "failure_categories": [],
    }
    assert (
        next_bundle.bundle.files["references/policy.txt"] == previous.files["references/policy.txt"]
    )


def test_generator_rejects_public_input_drift_before_dispatch(tmp_path):
    base = _base()
    with pytest.raises(ValueError, match="differ"):
        generate_initial(
            lambda _: pytest.fail("no call"),
            {"opening_message": "different"},
            base,
            journal=Journal(tmp_path),
        )


def test_revision_retains_own_usage_for_opaque_reasoning_admission(tmp_path):
    class UsageModel(EditingModel):
        def complete(self, messages, **kwargs):
            result = super().complete(messages, **kwargs)
            result["usage"] = {
                "output_tokens": 12,
                "output_tokens_details": {"reasoning_tokens": 7},
            }
            result["_bedrock_output_items"] = [
                {"type": "reasoning", "summary": [], "encrypted_content": "private-state"}
            ]
            return result

    base = _base()
    model = UsageModel()
    revise(
        model,
        parse_bundle_response(_raw()),
        base.public_inputs,
        base,
        {},
        journal=Journal(tmp_path),
        session=EditingSession(),
    )
    assistant = next(item for item in model.requests[1] if item["role"] == "assistant")
    assert assistant["usage"]["output_tokens_details"]["reasoning_tokens"] == 7
    assert assistant["_bedrock_output_items"][0]["encrypted_content"] == "private-state"
    assert "private-state" not in json.dumps(model.requests[0])


def test_context_admission_counts_exact_fresh_request_and_preserves_output_reserve(tmp_path):
    counted, requests = [], []

    class Counter:
        basis = "offline_pinned_counter"

        def count(self, messages, **kwargs):
            counted.append(copy.deepcopy(messages))
            return 157632

    class Model:
        token_counter = Counter()

        def complete(self, messages, *, seed=None):
            requests.append(copy.deepcopy(messages))
            return _raw()

    base = _base()
    journal = Journal(tmp_path)
    generate_initial(Model(), base.public_inputs, base, journal=journal)
    assert counted == requests
    record = json.loads(next(tmp_path.glob("*/request.json")).read_text())
    assert record["payload"]["context_admission"] == {
        "checked": True,
        "context_window": 272000,
        "context_fraction": 0.7,
        "reserved_output_tokens": 32768,
        "max_input_tokens": 157632,
        "input_tokens": 157632,
        "basis": "offline_pinned_counter",
    }


def test_null_wire_output_limit_retains_context_reserve_for_creation_and_revision(tmp_path):
    class Model(EditingModel):
        config = SimpleNamespace(max_input_tokens=157632, max_output_tokens=None)

        def __init__(self):
            super().__init__()
            self.options = []

        def complete(self, messages, **kwargs):
            self.options.append(kwargs)
            if kwargs.get("tools") is None:
                return _raw()
            return super().complete(messages, **kwargs)

    base, model = _base(), Model()
    journal = Journal(tmp_path)
    parent = generate_initial(model, base.public_inputs, base, journal=journal)
    revised = revise(
        model,
        parent,
        base.public_inputs,
        base,
        {},
        journal=journal,
        session=EditingSession(),
    )
    assert revised.bundle.parent_hash == parent.bundle_hash
    assert len(model.options) == 3
    assert all("max_output_tokens" not in options for options in model.options)
    requests = [json.loads(path.read_text()) for path in tmp_path.glob("*/request.json")]
    admissions = [
        request["payload"]["context_admission"]
        for request in requests
        if "context_admission" in request["payload"]
    ]
    assert len(admissions) == 3
    assert all(item["reserved_output_tokens"] == 32768 for item in admissions)
    assert all(item["max_input_tokens"] == 157632 for item in admissions)


def test_context_overflow_never_dispatches_or_marks_unknown_s0(tmp_path):
    class Counter:
        def count(self, messages):
            return 157633

    class Model:
        token_counter = Counter()

        def complete(self, *args, **kwargs):
            pytest.fail("over-budget S0 cannot reach the model")

    base, journal = _base(), Journal(tmp_path)
    for _ in range(2):
        with pytest.raises(GeneratorContextBudgetExhausted) as raised:
            generate_initial(Model(), base.public_inputs, base, journal=journal)
        assert raised.value.input_tokens == 157633
        assert raised.value.max_input_tokens == 157632
    assert not journal.completed("generate_initial")
    assert not list(tmp_path.glob("*/request.json"))


@pytest.mark.parametrize("observed, accepted", [(100, True), (157633, False)])
def test_context_admission_records_breakdown_before_accept_or_reject(tmp_path, observed, accepted):
    base, journal, calls = _base(), Journal(tmp_path), []

    def model(payload):
        calls.append(payload)
        return _raw()

    def create():
        return generate_initial(
            model,
            base.public_inputs,
            base,
            journal=journal,
            token_counter=SerializedChatTokenCounter(lambda _: observed),
        )

    if accepted:
        create()
    else:
        with pytest.raises(GeneratorContextBudgetExhausted):
            create()
    records = list((tmp_path / "context-admissions").glob("*.json"))
    assert len(records) == 1 and len(calls) == int(accepted)
    admission = json.loads(records[0].read_text())
    assert admission["operation_id"] == "generate_initial" and admission["accepted"] is accepted
    assert admission["input_tokens"] == observed
    assert admission["estimate_breakdown"] == {
        "total_tokens": observed,
        "visible_tokens": observed,
        "reasoning_reserve": 0,
        "basis": "responses_input_estimate_with_reasoning_reserve",
    }


def test_real_model_interface_requires_context_counter_but_callable_fixture_is_unchecked(tmp_path):
    class Model:
        def complete(self, *args, **kwargs):
            pytest.fail("missing counter cannot reach the model")

    base, journal = _base(), Journal(tmp_path)
    with pytest.raises(ValueError, match="context_counter_required"):
        generate_initial(Model(), base.public_inputs, base, journal=journal)
    generate_initial(lambda _: _raw(), base.public_inputs, base, journal=journal)
    record = json.loads(next(tmp_path.glob("*/request.json")).read_text())
    assert record["payload"]["context_admission"]["checked"] is False
    assert "input_tokens" not in record["payload"]["context_admission"]


def test_revision_history_preserves_public_evidence_without_old_tests_or_oracle_details(tmp_path):
    base = _base()
    previous = parse_bundle_response(_raw())
    history = [
        {
            "kind": "verification",
            "base_hash": base.base_hash,
            "bundle_hash": previous.bundle_hash,
            "test_version": 0,
            "test_hash": "old-test-hash",
            "passed": False,
            "pass_rate": 0.5,
            "diagnosis": "public requirement missing",
            "recommendations": ["add guard"],
            "suite": {"files": {"tests/test_old.py": "OLD_TEST_SOURCE"}},
            "results": [
                {
                    "nodeid": "test_guard",
                    "stage": "call",
                    "outcome": "failed",
                    "detail": "missing public guard",
                    "hidden": "PRIVATE_SCORE",
                }
            ],
            "utility": "PRIVATE_SCORE",
        },
        {
            "kind": "oracle",
            "base_hash": base.base_hash,
            "bundle_hash": previous.bundle_hash,
            "call": 1,
            "passed": False,
            "score": "PRIVATE_SCORE",
            "expected_actions": "PRIVATE_ACTIONS",
        },
    ]
    model = EditingModel()
    report = {"diagnosis": "new missing requirement", "suite": {"files": {"latest": "CURRENT"}}}
    revise(
        model,
        previous,
        base.public_inputs,
        base,
        report,
        journal=Journal(tmp_path),
        feedback_history=history,
        session=EditingSession(),
    )
    payload = json.loads(model.requests[0][1]["content"])
    assert payload["verification_feedback"] == {"passed": False, "failure_categories": []}
    assert payload["feedback_history"][0]["failure_categories"] == []
    assert payload["feedback_history"][1]["passed"] is False
    encoded = json.dumps(model.requests)
    for forbidden in (
        "OLD_TEST_SOURCE",
        "CURRENT",
        "PRIVATE_SCORE",
        "PRIVATE_ACTIONS",
        "missing public guard",
        "test_guard",
        "public requirement missing",
    ):
        assert forbidden not in encoded
    assert history[0]["suite"]["files"]["tests/test_old.py"] == "OLD_TEST_SOURCE"


def test_history_from_another_frozen_task_is_rejected_before_dispatch(tmp_path):
    base = _base()
    with pytest.raises(ValueError, match="this_frozen_base"):
        revise(
            lambda _: pytest.fail("cross-task feedback cannot reach the model"),
            parse_bundle_response(_raw()),
            base.public_inputs,
            base,
            {},
            journal=Journal(tmp_path),
            feedback_history=[{"kind": "oracle", "base_hash": "other", "passed": False}],
        )
    with pytest.raises(ValueError, match="pass_fail_only"):
        public_feedback_history(
            [{"kind": "oracle", "base_hash": base.base_hash, "passed": 0.5}], base.base_hash
        )


def test_revision_admission_includes_fixed_evidence_parent_hash_and_safe_feedback(
    tmp_path,
):
    base = _base()
    previous = parse_bundle_response(_raw())
    report = {"suite": {"files": {"tests/test_current.py": "CURRENT_TEST"}}, "diagnosis": "fix"}
    history = [
        {
            "kind": "oracle",
            "base_hash": base.base_hash,
            "bundle_hash": previous.bundle_hash,
            "call": 1,
            "passed": False,
        }
    ]
    counted = []

    class Counter:
        def count(self, messages, **kwargs):
            counted.append(copy.deepcopy(messages))
            return 157633

    with pytest.raises(GeneratorContextBudgetExhausted):
        revise(
            lambda _: pytest.fail("an oversized revision cannot dispatch"),
            previous,
            base.public_inputs,
            base,
            report,
            feedback_history=history,
            journal=Journal(tmp_path),
            token_counter=Counter(),
            system_prompt="SYSTEM_AUTHORING",
        )
    assert counted[0][0] == {"role": "system", "content": "SYSTEM_AUTHORING"}
    actual = json.loads(counted[0][1]["content"])
    assert actual["parent_bundle_hash"] == previous.bundle_hash
    assert actual["frozen_base"] == base.to_dict()
    assert "previous_bundle" not in actual and "public_inputs" not in actual
    assert actual["verification_feedback"] == {"passed": False, "failure_categories": []}
    assert "CURRENT_TEST" not in json.dumps(counted)
    assert actual["feedback_history"] == history


@pytest.mark.parametrize("output_limit", [32768, None])
def test_fifteen_revisions_send_fixed_evidence_once_and_only_new_feedback(tmp_path, output_limit):
    class Model(EditingModel):
        config = SimpleNamespace(max_input_tokens=157632, max_output_tokens=output_limit)

        def complete(self, messages, **kwargs):
            if output_limit is None:
                assert "max_output_tokens" not in kwargs
            else:
                assert kwargs["max_output_tokens"] == output_limit
            self.requests.append(copy.deepcopy(messages))
            return {
                "role": "assistant",
                "content": None,
                "finish_reason": "tool_calls",
                "usage": {"output_tokens": 8, "output_tokens_details": {"reasoning_tokens": 2}},
                "_bedrock_output_items": [
                    {"type": "reasoning", "summary": [], "encrypted_content": "own-history"}
                ],
                "tool_calls": [
                    {
                        "id": f"edit-{len(self.requests)}",
                        "function": {
                            "name": "terminal",
                            "arguments": json.dumps(
                                {
                                    "command": json.dumps(
                                        ["write", "SKILL.md", f"revision {len(self.requests)}"]
                                    )
                                }
                            ),
                        },
                    },
                    {
                        "id": f"submit-{len(self.requests)}",
                        "function": {"name": "submit_revision", "arguments": "{}"},
                    },
                ],
            }

    base = FrozenBase(
        ({"page_id": "large", "title": "Fixed evidence", "content": "EVIDENCE " * 4000},),
        {"opening": "fixed public task", "files": [{"path": "input.csv", "bytes": 10}]},
        token_count=32000,
    )
    parent = parse_bundle_response(_raw())
    initial = parent
    journal, conversation, runner = Journal(tmp_path), RevisionConversation(), EditingSession()
    model, history = Model(), []
    for attempt in range(1, 16):
        history.append(
            {"kind": "oracle", "base_hash": base.base_hash, "passed": False, "call": attempt}
        )
        # A reverted content hash still identifies the active clone accurately.
        if attempt == 10:
            parent = initial
        active_hash = parent.bundle_hash
        submission = revise(
            model,
            parent,
            base.public_inputs,
            base,
            {},
            journal=journal,
            operation_id=f"revision/{attempt}",
            session=runner,
            conversation=conversation,
            feedback_history=history,
        )
        parent = submission.bundle
        updates = [
            json.loads(item["content"]) for item in model.requests[-1] if item["role"] == "user"
        ]
        assert len(updates) == attempt
        assert updates[-1]["parent_bundle_hash"] == active_hash
        assert updates[-1]["feedback_history"] == public_feedback_history(
            [history[-1]], base.base_hash
        )
        assert sum("frozen_base" in item for item in updates) == 1
        assert all(
            "previous_bundle" not in item and "public_inputs" not in item for item in updates
        )
        assert len(json.dumps(model.requests[-1])) < 157632
    assert len(model.requests) == conversation.turns == conversation.feedback_cursor == 15
    assert conversation.fixed_inputs_hash is not None
    rewritten = copy.deepcopy(history)
    rewritten[0]["passed"] = True
    with pytest.raises(ValueError, match="feedback_history_changed"):
        revise(
            model,
            parent,
            base.public_inputs,
            base,
            {},
            journal=journal,
            operation_id="revision/16",
            session=runner,
            conversation=conversation,
            feedback_history=rewritten,
        )
    assert all(
        item["_bedrock_output_items"][0]["encrypted_content"] == "own-history"
        for item in conversation.messages
        if item["role"] == "assistant"
    )
    changed = FrozenBase(base.documents, {"opening": "changed"}, token_count=32000)
    with pytest.raises(ValueError, match="fixed_inputs_changed"):
        revise(
            model,
            parent,
            changed.public_inputs,
            changed,
            {},
            journal=journal,
            operation_id="revision/16",
            session=runner,
            conversation=conversation,
            feedback_history=[],
        )
    assert len(model.requests) == 15


def test_revision_recovery_reuses_response_with_identical_explicit_history(tmp_path):
    base, previous, journal = _base(), parse_bundle_response(_raw()), Journal(tmp_path)
    history = [{"kind": "oracle", "base_hash": base.base_hash, "passed": False, "call": 1}]
    first = revise(
        EditingModel(),
        previous,
        base.public_inputs,
        base,
        {},
        feedback_history=history,
        journal=journal,
        session=EditingSession(),
    )
    restored = revise(
        lambda _: pytest.fail("sealed revision response cannot be resent"),
        previous,
        base.public_inputs,
        base,
        {},
        feedback_history=history,
        journal=journal,
        session=EditingSession(),
    )
    assert restored == first


def test_model_output_must_fit_reserved_context_and_client_input_cap_is_respected(tmp_path):
    class Counter:
        def count(self, messages):
            return 501

    class Model:
        token_counter = Counter()
        config = type("Config", (), {"max_input_tokens": 500, "max_output_tokens": 32768})()

        def complete(self, *args, **kwargs):
            pytest.fail("client input cap must be checked before dispatch")

    base, journal = _base(), Journal(tmp_path)
    with pytest.raises(GeneratorContextBudgetExhausted) as raised:
        generate_initial(Model(), base.public_inputs, base, journal=journal)
    assert raised.value.max_input_tokens == 500
    with pytest.raises(ValueError, match="output_exceeds_context_reserve"):
        generate_initial(
            Model(), base.public_inputs, base, journal=journal, reserved_output_tokens=100
        )


def test_author_categories_are_fixed_and_do_not_expose_instance_values():
    raw = {
        "results": [
            {
                "nodeid": "test_output_numeric_unit_123",
                "outcome": "failed",
                "detail": "expected 42 got 7",
                "exception": "AssertionError",
            }
        ]
    }
    assert failure_categories(raw) == [
        "artifact/interface compliance",
        "numeric, formula, or unit consistency",
    ]
    assert "42" not in str(failure_categories(raw))
    with pytest.raises(ValueError, match="unknown_failure_category"):
        failure_categories({"failure_categories": ["expected 42"]})


def test_revision_unknown_request_is_not_reissued_and_parent_remains_safe(tmp_path):
    class UnknownModel(EditingModel):
        def complete(self, messages, **kwargs):
            self.requests.append(messages)
            raise TimeoutError()

    from tau_skill_evolution.journal import UnknownOperation

    model, base, runner = UnknownModel(), _base(), EditingSession()
    parent, journal = parse_bundle_response(_raw()), Journal(tmp_path / "journal")
    for _ in range(2):
        with pytest.raises(UnknownOperation):
            revise(model, parent, base.public_inputs, base, {}, journal=journal, session=runner)
    assert len(model.requests) == 1 and parent.files["SKILL.md"] == "instructions"
    assert not journal.completed("revise/submitted")


def test_generator_turn_budget_is_shared_across_revisions(tmp_path):
    base, parent = _base(), parse_bundle_response(_raw())
    conversation, journal, runner = (
        RevisionConversation(),
        Journal(tmp_path / "journal"),
        EditingSession(),
    )
    first = revise(
        EditingModel("first"),
        parent,
        base.public_inputs,
        base,
        {},
        journal=journal,
        session=runner,
        conversation=conversation,
        max_turns=3,
        operation_id="first",
    )
    assert conversation.turns == 2
    with pytest.raises(RevisionFailure, match="generator_turn_budget_exhausted") as error:
        revise(
            EditingModel("unsealed"),
            first.bundle,
            base.public_inputs,
            base,
            {},
            journal=journal,
            session=runner,
            conversation=conversation,
            max_turns=3,
            operation_id="second",
        )
    assert error.value.dispatched and not journal.completed("second/submitted")
    assert first.bundle.files["SKILL.md"] == "first"
    assert conversation.turns == 3
    restored_conversation = RevisionConversation()
    with pytest.raises(RevisionFailure, match="generator_turn_budget_exhausted"):
        revise(
            lambda _: pytest.fail("ended attempt cannot dispatch again"),
            first.bundle,
            base.public_inputs,
            base,
            {},
            journal=journal,
            session=runner,
            conversation=restored_conversation,
            max_turns=3,
            operation_id="second",
        )
    assert restored_conversation.turns == 3


@pytest.mark.parametrize("initial", [False, True])
def test_known_output_budget_stop_retains_response_and_never_continues_or_resends(
    tmp_path, initial
):
    class BudgetModel(EditingModel):
        def complete(self, messages, **kwargs):
            self.requests.append(copy.deepcopy(messages))
            return {
                "role": "assistant",
                "content": "incomplete response",
                "finish_reason": "length",
                "usage": {
                    "output_tokens": 32768,
                    "output_tokens_details": {"reasoning_tokens": 30000},
                },
                "_bedrock_output_items": [
                    {
                        "type": "reasoning",
                        "summary": [],
                        "encrypted_content": "own-opaque-continuation",
                    }
                ],
            }

    base, parent, model = _base(), parse_bundle_response(_raw()), BudgetModel()
    journal, session, conversation = Journal(tmp_path), EditingSession(), RevisionConversation()
    operation = "execute_initial" if initial else "revise"

    def attempt(state):
        options = {"journal": journal, "session": session, "conversation": state}
        if initial:
            return execute_initial(model, parent, base.public_inputs, base, **options)
        return revise(model, parent, base.public_inputs, base, {}, **options)

    with pytest.raises(RevisionFailure, match="generator_output_budget_exhausted") as error:
        attempt(conversation)
    assert error.value.dispatched and conversation.turns == 1
    assistant = next(item for item in conversation.messages if item["role"] == "assistant")
    assert assistant["usage"]["output_tokens"] == 32768
    assert assistant["_bedrock_output_items"][0]["encrypted_content"] == "own-opaque-continuation"
    assert journal.response(operation + "/model-0")["finish_reason"] == "length"
    assert journal.completed(operation + "/ended") and not journal.dispatched(
        operation + "/model-1"
    )
    assert not journal.completed(operation + "/submitted") and session.commands == []
    restored = RevisionConversation()
    with pytest.raises(RevisionFailure, match="generator_output_budget_exhausted"):
        attempt(restored)
    assert len(model.requests) == 1 and restored.messages == conversation.messages
    assert parent.files["SKILL.md"] == "instructions"


def test_no_runtime_cannot_fall_back_to_single_response_revision(tmp_path):
    base = _base()
    with pytest.raises(RevisionFailure, match="learning_runtime_required") as error:
        revise(
            EditingModel(),
            parse_bundle_response(_raw()),
            base.public_inputs,
            base,
            {},
            journal=Journal(tmp_path / "journal"),
        )
    assert not error.value.dispatched


@pytest.mark.parametrize("interrupt_before_end", [False, True])
def test_revision_cleanup_failure_aborts_before_submit_and_survives_replay(
    tmp_path, interrupt_before_end
):
    class CleanupSession(EditingSession):
        def terminal(self, command):
            self.commands.append(command)
            return ProgramResult(None, failure="cleanup_failed")

    class CleanupModel(EditingModel):
        def complete(self, messages, **kwargs):
            self.requests.append(copy.deepcopy(messages))
            return {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "terminal",
                        "function": {"name": "terminal", "arguments": '{"command":"check"}'},
                    },
                    {"id": "submit", "function": {"name": "submit_revision", "arguments": "{}"}},
                ],
            }

    class InterruptedJournal(Journal):
        interrupted = False

        def dispatch(self, operation_id, *args, **kwargs):
            if interrupt_before_end and operation_id == "revise/ended" and not self.interrupted:
                self.interrupted = True
                raise InterruptedError("local interruption before sealing terminal failure")
            return super().dispatch(operation_id, *args, **kwargs)

    base, parent = _base(), parse_bundle_response(_raw())
    model, runner = CleanupModel(), CleanupSession()
    journal = InterruptedJournal(tmp_path / "journal")

    def attempt():
        return revise(model, parent, base.public_inputs, base, {}, journal=journal, session=runner)

    if interrupt_before_end:
        with pytest.raises(InterruptedError):
            attempt()
        assert journal.completed("revise/model-0/tool-0")
        assert not journal.completed("revise/ended")
    with pytest.raises(RevisionFailure, match="cleanup_failed") as error:
        attempt()
    assert error.value.dispatched
    assert runner.cleanup_failed
    assert len(model.requests) == len(runner.commands) == 1
    assert not journal.completed("revise/model-0/tool-1")
    assert not journal.completed("revise/submitted")
    assert parent.files["SKILL.md"] == "instructions"
    with pytest.raises(RevisionFailure, match="cleanup_failed"):
        attempt()
    assert len(model.requests) == len(runner.commands) == 1


def test_revision_recovers_received_raw_response_without_repeating_post(tmp_path):
    class RawModel(EditingModel):
        posts = 0
        interrupted = False

        def complete_journaled(self, journal, operation_id, payload, messages, **kwargs):
            response = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "submit", "function": {"name": "submit_revision", "arguments": "{}"}}
                ],
            }

            def send(_):
                self.posts += 1
                return 200, json.dumps(response).encode()

            def normalize(status, body):
                if not self.interrupted:
                    self.interrupted = True
                    raise KeyboardInterrupt()
                return json.loads(body)

            return journal.dispatch_raw(operation_id, payload, lambda: None, send, normalize)

    base, parent = _base(), parse_bundle_response(_raw())
    model, journal, runner = RawModel(), Journal(tmp_path / "journal"), EditingSession()
    with pytest.raises(KeyboardInterrupt):
        revise(model, parent, base.public_inputs, base, {}, journal=journal, session=runner)
    assert journal.status("revise/model-0") == "UNKNOWN"
    assert journal.received("revise/model-0")
    result = revise(model, parent, base.public_inputs, base, {}, journal=journal, session=runner)
    assert model.posts == 1 and result.bundle.bundle_hash == parent.bundle_hash


def test_unknown_terminal_result_takes_priority_over_expired_deadline(tmp_path, monkeypatch):
    from tau_skill_evolution.journal import UnknownOperation

    class UnknownSession(EditingSession):
        def terminal(self, command):
            self.commands.append(command)
            raise TimeoutError()

    base, parent = _base(), parse_bundle_response(_raw())
    model, runner, journal = EditingModel(), UnknownSession(), Journal(tmp_path / "journal")
    monkeypatch.setattr("tau_skill_evolution.generator.time.time", lambda: 0)
    with pytest.raises(UnknownOperation):
        revise(model, parent, base.public_inputs, base, {}, journal=journal, session=runner)
    monkeypatch.setattr("tau_skill_evolution.generator.time.time", lambda: 10000)
    with pytest.raises(UnknownOperation):
        revise(model, parent, base.public_inputs, base, {}, journal=journal, session=runner)
    assert len(model.requests) == len(runner.commands) == 1
    assert not journal.completed("revise/ended")
