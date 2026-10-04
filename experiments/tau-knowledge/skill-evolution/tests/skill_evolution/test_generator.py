from __future__ import annotations

import copy
import json

import pytest
from tau_skill_evolution.artifacts import FrozenBase, load_bundle
from tau_skill_evolution.generator import (
    CreationFailure,
    GeneratorContextBudgetExhausted,
    generate_initial,
    parse_bundle_response,
    public_feedback_history,
    revise,
)
from tau_skill_evolution.journal import Journal
from tau_skill_evolution.model import _assistant_response


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
    calls = []

    def model(payload):
        calls.append(payload)
        response = [
            {"path": path, "content": content}
            for path, content in payload["previous_bundle"]["files"].items()
        ]
        response[0]["content"] += " revised"
        return {"files": response}

    next_bundle = revise(
        model,
        previous,
        base.public_inputs,
        base,
        {"diagnosis": "fix"},
        journal=Journal(tmp_path),
        operation_id="revision/1",
    )
    assert next_bundle.parent_hash == previous.bundle_hash
    assert next_bundle.bundle_hash != previous.bundle_hash
    assert calls[0]["previous_bundle"]["files"] == dict(previous.files)
    assert calls[0]["verification_report"] == {"diagnosis": "fix"}
    assert next_bundle.files["references/policy.txt"] == previous.files["references/policy.txt"]


def test_generator_rejects_public_input_drift_before_dispatch(tmp_path):
    base = _base()
    with pytest.raises(ValueError, match="differ"):
        generate_initial(
            lambda _: pytest.fail("no call"),
            {"opening_message": "different"},
            base,
            journal=Journal(tmp_path),
        )


def test_context_admission_counts_exact_fresh_request_and_preserves_output_reserve(tmp_path):
    counted, requests = [], []

    class Counter:
        basis = "offline_pinned_counter"

        def count(self, messages):
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
    captured = []
    report = {"diagnosis": "new missing requirement", "suite": {"files": {"latest": "CURRENT"}}}
    revise(
        lambda payload: captured.append(payload) or _raw("updated"),
        previous,
        base.public_inputs,
        base,
        report,
        journal=Journal(tmp_path),
        feedback_history=history,
    )
    payload = captured[0]
    assert payload["verification_report"] == report
    assert payload["feedback_history"][0]["diagnosis"] == history[0]["diagnosis"]
    assert payload["feedback_history"][0]["results"][0]["detail"] == "missing public guard"
    assert payload["feedback_history"][1]["passed"] is False
    encoded = json.dumps(payload["feedback_history"])
    assert "OLD_TEST_SOURCE" not in encoded
    assert "PRIVATE_SCORE" not in encoded and "PRIVATE_ACTIONS" not in encoded
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


def test_revision_admission_includes_complete_package_current_tests_and_accumulated_feedback(
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
        def count(self, messages):
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
    assert actual["previous_bundle"]["files"] == dict(previous.files)
    assert actual["verification_report"] == report
    assert actual["feedback_history"] == history


def test_revision_recovery_reuses_response_with_identical_explicit_history(tmp_path):
    base, previous, journal = _base(), parse_bundle_response(_raw()), Journal(tmp_path)
    history = [{"kind": "oracle", "base_hash": base.base_hash, "passed": False, "call": 1}]
    first = revise(
        lambda _: _raw("updated"),
        previous,
        base.public_inputs,
        base,
        {},
        feedback_history=history,
        journal=journal,
    )
    restored = revise(
        lambda _: pytest.fail("sealed revision response cannot be resent"),
        previous,
        base.public_inputs,
        base,
        {},
        feedback_history=history,
        journal=journal,
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
