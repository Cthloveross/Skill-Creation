from __future__ import annotations

import copy
import json

import pytest
from tau_skill_evolution.acquisition import (
    READ_ONLY_TOOL_NAMES,
    AcquisitionBudgets,
    _selection,
    collect_base,
)
from tau_skill_evolution.artifacts import normalize_document
from tau_skill_evolution.bank import BankWorkerError
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.model import ModelClientError

DOC = {"page_id": "policy", "title": "Policy", "content": "Tool arguments require a known user ID."}


def decision(
    action, selected=(), *, sufficient=False, evidence=None, conflicts=None, gaps=None, scores=None
):
    return {
        "gaps": ["policy needed"] if gaps is None and not sufficient else (gaps or []),
        "action": action,
        "document_scores": scores
        if scores is not None
        else [
            {"document_id": item, "confidence": 1.0, "reason": "Relevant policy"}
            for item in selected
        ],
        "sufficient": sufficient,
        "evidence": evidence
        if evidence is not None
        else (
            [{"requirement": "bank request", "document_id": "policy", "quote": "known user ID"}]
            if selected
            else []
        ),
        "coverage": {
            category: list(selected)
            for category in ("policies", "tools", "parameters", "preconditions")
        },
        "conflicts": conflicts or [],
    }


class Corpus:
    def __init__(self, documents=None):
        self.documents = documents if documents is not None else [DOC]
        self.calls = []
        self.closed = False

    def search_web(self, query):
        assert not self.closed
        self.calls.append(query)
        return {"results": self.documents}

    def close(self):
        self.closed = True


class Model:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.inputs = []

    def __call__(self, payload):
        self.inputs.append(copy.deepcopy(payload))
        response = copy.deepcopy(next(self.responses))
        if "document_scores" in response:
            scored = {item["document_id"] for item in response["document_scores"]}
            response["document_scores"].extend(
                {"document_id": item["document_id"], "confidence": 0, "reason": "Unrelated fixture"}
                for item in payload["returned_documents"]
                if item["document_id"] not in scored
            )
        return response


def test_private_action_recovery_uses_stable_id_without_repeating_public_model_requests(tmp_path):
    private_results, dispatches = {}, []
    journal = Journal(tmp_path)
    model = Model(
        [
            decision({"kind": "search", "query": "policy"}),
            decision({"kind": "clarify", "question": "Which account?"}, ["policy"]),
            decision({"kind": "freeze"}, ["policy"], sufficient=True),
        ]
    )

    def action_dispatcher(identifier, action):
        dispatches.append((identifier, dict(action)))
        if identifier not in private_results:
            private_results[identifier] = "public clarification"
            # The worker sealed its result; its public pipe closed before returning it.
            raise BankWorkerError("bank_worker_exited")
        return private_results[identifier]

    with pytest.raises(BankWorkerError):
        collect_base(
            model,
            {"opening": "immutable opening"},
            Corpus(),
            {},
            lambda _: None,
            len,
            journal=journal,
            action_dispatcher=action_dispatcher,
        )
    assert journal.status("acquisition/clarify/0") == "NOT_SENT"
    assert len(model.inputs) == 2
    base = collect_base(
        model,
        {"opening": "immutable opening"},
        Corpus(),
        {},
        lambda _: None,
        len,
        journal=journal,
        action_dispatcher=action_dispatcher,
    )
    assert base.stop_reason == "sufficient"
    assert base.public_inputs["opening"] == "immutable opening"
    assert base.public_inputs["clarifications"][0]["result"] == "public clarification"
    assert dispatches[0] == dispatches[1]
    assert len(model.inputs) == 3


def test_received_invalid_private_simulator_response_aborts_before_freezing_or_generation(tmp_path):
    model = Model([decision({"kind": "clarify", "question": "Which account?"})])

    def invalid(_identifier, _action):
        raise ModelClientError("acquisition_received_invalid", "invalid simulator response")

    with pytest.raises(ModelClientError, match="invalid simulator response"):
        collect_base(
            model,
            {"opening": "fixed"},
            Corpus(),
            {},
            lambda _: None,
            len,
            journal=Journal(tmp_path),
            action_dispatcher=invalid,
        )
    assert len(model.inputs) == 1


def test_multiround_search_clarify_read_only_and_explicit_freeze(tmp_path):
    corpus = Corpus([DOC, {"page_id": "unused", "title": "Unused", "content": "not selected"}])
    model = Model(
        [
            decision({"kind": "search", "query": "bank policy"}),
            decision({"kind": "clarify", "question": "Which account?"}, ["policy"]),
            decision(
                {
                    "kind": "read_only",
                    "tool": "get_user_information_by_id",
                    "arguments": {"user_id": "u1"},
                },
                ["policy"],
            ),
            decision({"kind": "freeze"}, ["policy"], sufficient=True),
        ]
    )
    base = collect_base(
        model,
        {"opening_message": "Help"},
        corpus,
        {"get_user_information_by_id": lambda user_id: {"user_id": user_id, "balance": 123}},
        lambda question: "Account u1",
        lambda text: len(text.split()),
        journal=Journal(tmp_path),
    )
    assert base.stop_reason == "sufficient"
    assert [item["document_id"] for item in base.documents] == ["policy"]
    assert corpus.closed and corpus.calls == ["bank policy"]
    assert base.public_inputs["clarifications"][0]["result"] == "Account u1"
    assert base.public_inputs["read_only_observations"][0]["result"]["user_id"] == "u1"
    assert model.inputs[-1]["remaining"] == {"search": 29, "clarify": 3, "read_only": 9}
    assert "unused" not in str(base.to_dict())


def test_confidence_filter_keeps_all_potential_documents_at_the_threshold(tmp_path):
    documents = [
        DOC,
        {"page_id": "possible", "title": "Later procedure", "content": "A possible next step."},
        {"page_id": "unrelated", "title": "Other product", "content": "An unrelated product."},
    ]
    scores = [
        {"document_id": "unrelated", "confidence": 0.099, "reason": "Different product."},
        {"document_id": "possible", "confidence": 0.1, "reason": "Potential future branch."},
        {"document_id": "policy", "confidence": 0.9, "reason": "Supports the required rule."},
    ]
    journal = Journal(tmp_path)
    base = collect_base(
        Model(
            [
                decision({"kind": "search", "query": "policy"}),
                decision({"kind": "freeze"}, ["policy"], sufficient=True, scores=scores),
            ]
        ),
        {},
        Corpus(documents),
        {},
        lambda _: "",
        len,
        journal=journal,
    )
    assert [item["document_id"] for item in base.documents] == ["policy", "possible"]
    assert base.stop_reason == "sufficient"
    assert "Potential future branch." not in str(base.to_dict())
    assert journal.response("acquisition/analyzer/1")["document_scores"] == scores


def test_confidence_capacity_skips_an_oversized_file_and_continues_with_whole_documents():
    inventory = {
        item["page_id"]: normalize_document(item)
        for item in [
            DOC,
            {"page_id": "huge", "title": "Large", "content": "X" * 4000},
            {"page_id": "small", "title": "Small", "content": "Useful small reference."},
        ]
    }
    scores = [
        {"document_id": "huge", "confidence": 1, "reason": "Relevant but large."},
        {"document_id": "small", "confidence": 0.2, "reason": "Possible branch."},
        {"document_id": "policy", "confidence": 0.8, "reason": "Required rule."},
    ]
    selected, _, count = _selection(
        decision({"kind": "freeze"}, evidence=[], scores=scores), inventory, len, 600, 0.1
    )
    assert [item["document_id"] for item in selected] == ["policy", "small"]
    assert selected == [inventory["policy"], inventory["small"]]
    assert count <= 600


def test_zero_confidence_threshold_keeps_all_documents_with_stable_tie_order():
    inventory = {
        item["page_id"]: normalize_document(item)
        for item in [DOC, {"page_id": "a", "title": "A", "content": "Additional context."}]
    }
    scores = [
        {"document_id": item, "confidence": 0, "reason": "Low estimated usefulness."}
        for item in ("policy", "a")
    ]
    selected, _, _ = _selection(
        decision({"kind": "freeze"}, evidence=[], scores=scores), inventory, len, 10000, 0
    )
    assert [item["document_id"] for item in selected] == ["a", "policy"]


@pytest.mark.parametrize(
    "scores",
    [
        [],
        [{"document_id": "unseen", "confidence": 1, "reason": "Unknown."}],
        [{"document_id": "policy", "confidence": 0.9, "reason": ""}],
    ]
    + [
        [{"document_id": "policy", "confidence": score, "reason": "Invalid score."}]
        for score in (True, -0.1, 1.1, float("nan"), float("inf"), "0.8")
    ],
)
def test_invalid_or_incomplete_confidence_scores_are_rejected(scores):
    with pytest.raises(ValueError):
        _selection(
            decision({"kind": "freeze"}, evidence=[], scores=scores),
            {"policy": normalize_document(DOC)},
            len,
            10000,
            0.1,
        )


def test_permission_allowlist_rejects_bank_writes_and_unknown_actions():
    with pytest.raises(ValueError, match="forbidden"):
        collect_base(lambda _: None, {}, Corpus(), {"send_money": lambda: None}, lambda _: "", len)
    calls = []
    model = Model(
        [
            decision({"kind": "write", "tool": "send_money"}),
            decision({"kind": "read_only", "tool": "send_money", "arguments": {}}),
            decision({"kind": "read_only", "tool": "get_current_time", "arguments": {}}),
            decision({"kind": "freeze"}),
        ]
    )
    base = collect_base(
        model,
        {},
        Corpus(),
        {"get_current_time": lambda: calls.append(1) or "time"},
        lambda _: "",
        len,
        budgets=AcquisitionBudgets(searches=0, clarifications=0, read_only_queries=1),
    )
    assert calls == [1]
    assert base.stop_reason == "budget_exhausted_incomplete"
    assert len(base.public_inputs["read_only_observations"]) == 1
    assert len(READ_ONLY_TOOL_NAMES) == 7


def test_selection_only_full_text_last_legal_and_never_truncates():
    corpus = Corpus(
        [
            DOC,
            {"page_id": "header", "title": "not full text"},
            {"page_id": "huge", "title": "huge", "content": "X" * 4000},
        ]
    )
    model = Model(
        [
            decision({"kind": "search", "query": "policy"}),
            decision({"kind": "search", "query": "again"}, ["policy"]),
            decision(
                {"kind": "freeze"},
                evidence=[],
                scores=[{"document_id": "huge", "confidence": 1.1, "reason": "Invalid score"}],
            ),
            decision({"kind": "freeze"}, ["header"], evidence=[]),
        ]
    )
    base = collect_base(
        model,
        {},
        corpus,
        {},
        lambda _: "",
        len,
        budgets=AcquisitionBudgets(base_tokens=400, analyzer_steps=4),
    )
    assert base.stop_reason == "budget_exhausted_incomplete"
    assert len(base.documents) == 1
    assert base.documents[0]["content"] == DOC["content"]
    assert base.token_count <= 400
    assert corpus.closed


@pytest.mark.parametrize(
    "conflicts,gaps,evidence",
    [(["contradiction"], [], None), ([], ["missing condition"], None), ([], [], [])],
)
def test_claimed_sufficient_freeze_with_invalid_support_is_corrected_and_continues(
    conflicts, gaps, evidence
):
    model = Model(
        [
            decision({"kind": "search", "query": "policy"}),
            decision(
                {"kind": "freeze"},
                ["policy"],
                sufficient=True,
                conflicts=conflicts,
                gaps=gaps,
                evidence=evidence,
            ),
            decision({"kind": "search", "query": "missing support"}, ["policy"]),
            decision({"kind": "freeze"}, ["policy"], sufficient=True),
        ]
    )
    base = collect_base(model, {}, Corpus(), {}, lambda _: "", len)
    assert base.stop_reason == "sufficient"
    assert len(model.inputs) == 4
    assert model.inputs[2]["observations"][-1]["kind"] == "controller_error"


@pytest.mark.parametrize(
    "invalid_tools",
    [
        [],
        ["uncited"],
        {},
        {"not_applicable": ""},
        {"not_applicable": "   "},
        {"not_applicable": None},
        {"not_applicable": True},
        {"reason": "Advice only"},
        {"not_applicable": "Advice only", "document_ids": ["policy"]},
        [{"not_applicable": "Advice only"}, "policy"],
    ],
)
def test_invalid_coverage_freeze_can_be_repaired_without_another_search(invalid_tools):
    invalid = decision({"kind": "freeze"}, ["policy"], sufficient=True)
    invalid["coverage"]["tools"] = invalid_tools
    model = Model(
        [
            decision({"kind": "search", "query": "policy"}),
            invalid,
            decision({"kind": "freeze"}, ["policy"], sufficient=True),
        ]
    )
    corpus = Corpus()
    base = collect_base(model, {}, corpus, {}, lambda _: "", len)
    error = model.inputs[-1]["observations"][-1]
    assert error["invalid_coverage"] == ["coverage.tools"]
    assert base.stop_reason == "sufficient" and corpus.calls == ["policy"]


def test_recommendation_freezes_with_evidence_and_explicit_inapplicable_categories():
    ready = decision(
        {"kind": "freeze"},
        ["policy"],
        sufficient=True,
        evidence=[{"requirement": "Highest cash-back earning rate", "document_id": "policy"}],
    )
    ready["coverage"].update(
        {
            "tools": {"not_applicable": "The user requests a recommendation, not a bank action."},
            "parameters": {"not_applicable": "No bank call or its arguments are needed."},
            "preconditions": {
                "not_applicable": "This general rate comparison has no eligibility gate."
            },
        }
    )
    corpus = Corpus([{**DOC, "content": "Card A has the highest cash-back rate at 10%."}])
    model = Model([decision({"kind": "search", "query": "cash-back rates"}), ready])
    base = collect_base(
        model, {"opening": "Which card has the highest cash back?"}, corpus, {}, lambda _: "", len
    )
    assert base.stop_reason == "sufficient"
    assert len(model.inputs) == 2 and corpus.calls == ["cash-back rates"]
    assert base.evidence[0]["document_id"] == "policy"


def test_unknown_coverage_category_rejects_freeze_and_reports_the_same_validation():
    invalid = decision({"kind": "freeze"}, ["policy"], sufficient=True)
    invalid["coverage"]["extra"] = {"not_applicable": "Unused category"}
    model = Model(
        [
            decision({"kind": "search", "query": "policy"}),
            invalid,
            decision({"kind": "freeze"}, ["policy"], sufficient=True),
        ]
    )
    base = collect_base(model, {}, Corpus(), {}, lambda _: "", len)
    assert base.stop_reason == "sufficient"
    assert model.inputs[-1]["observations"][-1]["invalid_coverage"] == ["coverage.extra"]


def test_explicit_incomplete_freeze_continues_then_freezes_when_search_budget_is_spent():
    model = Model(
        [
            decision({"kind": "search", "query": "first"}),
            decision({"kind": "freeze"}, ["policy"]),
            decision({"kind": "search", "query": "missing procedure"}, ["policy"]),
            decision({"kind": "freeze"}, ["policy"]),
        ]
    )
    corpus = Corpus()
    base = collect_base(
        model,
        {},
        corpus,
        {},
        lambda _: "",
        len,
        budgets=AcquisitionBudgets(searches=2, clarifications=0, read_only_queries=0),
    )
    assert corpus.calls == ["first", "missing procedure"]
    assert model.inputs[2]["observations"][-1]["kind"] == "controller_error"
    assert base.stop_reason == "budget_exhausted_incomplete"
    assert [item["document_id"] for item in base.documents] == ["policy"]


def test_exhausted_search_does_not_stop_an_available_clarification():
    model = Model(
        [
            decision({"kind": "search", "query": "first"}),
            decision({"kind": "search", "query": "exhausted"}, ["policy"]),
            decision({"kind": "clarify", "question": "Account ID?"}, ["policy"]),
            decision({"kind": "freeze"}, ["policy"], sufficient=True),
        ]
    )
    base = collect_base(
        model,
        {},
        Corpus(),
        {},
        lambda _: "u1",
        len,
        budgets=AcquisitionBudgets(searches=1, clarifications=1, read_only_queries=0),
    )
    assert model.inputs[2]["observations"][-1]["error"] == "search budget exhausted"
    assert base.stop_reason == "sufficient"
    assert base.public_inputs["clarifications"][0]["result"] == "u1"


def test_adapter_supplied_read_only_allowlist_is_enforced_and_schemas_are_filtered():
    model = Model(
        [
            decision({"kind": "read_only", "tool": "write_file", "arguments": {}}),
            decision({"kind": "read_only", "tool": "inspect_public", "arguments": {"item": "a"}}),
            decision({"kind": "freeze"}),
        ]
    )
    base = collect_base(
        model,
        {},
        Corpus(),
        {"inspect_public": lambda item: {"item": item}},
        lambda _: "",
        len,
        allowed_read_only_tool_names=("inspect_public",),
        tool_schemas=[{"name": "inspect_public"}, {"name": "write_file"}],
        budgets=AcquisitionBudgets(searches=0, clarifications=0, read_only_queries=1),
    )
    assert model.inputs[0]["tool_schemas"] == [{"name": "inspect_public"}]
    assert model.inputs[1]["observations"][-1]["error"] == "forbidden read-only tool"
    assert base.public_inputs["read_only_observations"][0]["result"] == {"item": "a"}
    with pytest.raises(ValueError, match="forbidden"):
        collect_base(
            Model([]),
            {},
            Corpus(),
            {"inspect_public": lambda: None},
            lambda _: "",
            len,
            allowed_read_only_tool_names=(),
        )


def test_bank_initial_clock_consumes_one_read_and_resume_does_not_repeat_it(tmp_path):
    calls = []
    journal = Journal(tmp_path)
    model = Model(
        [
            decision({"kind": "search", "query": "policy"}),
            decision({"kind": "freeze"}, ["policy"], sufficient=True),
        ]
    )
    base = collect_base(
        model,
        {},
        Corpus(),
        {"get_current_time": lambda: calls.append(1) or "2026-10-04"},
        lambda _: "",
        len,
        journal=journal,
    )
    assert calls == [1] and model.inputs[0]["remaining"]["read_only"] == 9
    assert model.inputs[0]["public_inputs"]["read_only_observations"][0]["result"] == "2026-10-04"
    restored = collect_base(
        lambda _: pytest.fail("no repeated Analyzer"),
        {},
        Corpus(),
        {"get_current_time": lambda: pytest.fail("no repeated clock")},
        lambda _: "",
        len,
        journal=journal,
    )
    assert restored == base


def test_skillsbench_discovers_inputs_without_bank_clock_clarification_or_exec(tmp_path):
    names = ("list_input_directory", "read_input_file")
    calls = []
    journal = Journal(tmp_path)
    model = Model(
        [
            decision({"kind": "clarify", "question": "Unavailable"}),
            decision({"kind": "read_only", "tool": "get_current_time", "arguments": {}}),
            decision({"kind": "read_only", "tool": "terminal", "arguments": {"command": "ls"}}),
            decision({"kind": "read_only", "tool": names[0], "arguments": {"path": "/root"}}),
            decision(
                {
                    "kind": "read_only",
                    "tool": names[1],
                    "arguments": {"path": "/root/input.txt"},
                }
            ),
            decision({"kind": "search", "query": "procedure"}),
            decision({"kind": "freeze"}, ["policy"], sufficient=True),
        ]
    )
    tools = {
        names[0]: lambda path: (
            calls.append((names[0], path))
            or {"entries": [{"name": "input.txt", "path": path + "/input.txt", "kind": "file"}]}
        ),
        names[1]: lambda path: (
            calls.append((names[1], path))
            or {"path": path, "content": "provided data", "encoding": "utf-8"}
        ),
    }
    public = {"opening": "Analyze the supplied data", "workspace": {"directory": "/root"}}
    base = collect_base(
        model,
        public,
        Corpus(),
        tools,
        lambda _: pytest.fail("cannot clarify"),
        len,
        allowed_read_only_tool_names=names,
        tool_schemas=[{"name": name} for name in (*names, "get_current_time", "terminal")],
        budgets=AcquisitionBudgets(clarifications=0, read_only_queries=10),
        journal=journal,
    )
    assert model.inputs[0]["allowed_read_only_tools"] == list(names)
    assert model.inputs[0]["tool_schemas"] == [{"name": name} for name in names]
    assert model.inputs[0]["remaining"]["read_only"] == 10
    assert model.inputs[-1]["remaining"]["read_only"] == 8
    assert calls == [(names[0], "/root"), (names[1], "/root/input.txt")]
    assert base.public_inputs["clarifications"] == ()
    assert base.public_inputs["read_only_observations"][1]["result"]["content"] == ("provided data")
    assert base.stop_reason == "sufficient"
    assert journal.response("acquisition/read_only/1")["result"]["content"] == "provided data"
    restored = collect_base(
        lambda _: pytest.fail("received Analyzer response must not be requested again"),
        public,
        Corpus(),
        {name: lambda **_: pytest.fail("frozen observation must be reused") for name in names},
        lambda _: pytest.fail("cannot clarify"),
        len,
        allowed_read_only_tool_names=names,
        tool_schemas=[{"name": name} for name in (*names, "get_current_time", "terminal")],
        budgets=AcquisitionBudgets(clarifications=0, read_only_queries=10),
        journal=journal,
    )
    assert restored == base and len(calls) == 2


def test_search_budget_and_analyzer_bound_stop_with_incomplete_base():
    corpus = Corpus()
    model = Model(
        [
            decision({"kind": "search", "query": "one"}),
            decision({"kind": "search", "query": "two"}, ["policy"]),
        ]
    )
    base = collect_base(
        model,
        {},
        corpus,
        {},
        lambda _: "",
        len,
        budgets=AcquisitionBudgets(searches=1, clarifications=0, read_only_queries=0),
    )
    assert corpus.calls == ["one"]
    assert base.stop_reason == "budget_exhausted_incomplete"
    assert len(base.documents) == 1
    invalid = Model([{}, {}, {}])
    base = collect_base(
        invalid, {}, Corpus(), {}, lambda _: "", len, budgets=AcquisitionBudgets(analyzer_steps=3)
    )
    assert base.stop_reason == "budget_exhausted_incomplete"
    assert not base.documents


def test_simulator_tool_result_rejected_in_public_clarification():
    model = Model(
        [decision({"kind": "clarify", "question": "What ID?"}), decision({"kind": "freeze"})]
    )
    base = collect_base(
        model,
        {},
        Corpus(),
        {},
        lambda _: {"text": "u1", "tool_calls": [{"name": "write_bank"}]},
        len,
        budgets=AcquisitionBudgets(analyzer_steps=2),
    )
    observation = base.public_inputs["clarifications"][0]
    assert observation["status"] == "error"
    assert "result" not in observation
    assert "tool_calls" not in str(base.to_dict())


@pytest.mark.parametrize("status", [401, 403])
def test_clarification_authentication_failure_stops_before_another_analyzer_request(
    tmp_path, status
):
    model = Model([decision({"kind": "clarify", "question": "Account ID?"})])
    corpus = Corpus()
    journal = Journal(tmp_path)

    def denied(_):
        raise ModelClientError(
            "authentication_failed", "Bedrock authentication failed", status=status
        )

    with pytest.raises(UnknownOperation):
        collect_base(model, {}, corpus, {}, denied, len, journal=journal)
    assert len(model.inputs) == 1 and corpus.closed
    assert journal.authentication_failure() == status
    assert not journal.completed("acquisition/clarify/0")
    operations = [
        json.loads(path.read_text())["operation_id"] for path in tmp_path.glob("*/request.json")
    ]
    assert set(operations) == {
        "acquisition/analyzer/0",
        "acquisition/clarify/0",
    }


def test_acquisition_resume_replays_all_calls_and_freezes_same_base(tmp_path):
    journal = Journal(tmp_path)
    responses = [
        decision({"kind": "search", "query": "policy"}),
        decision({"kind": "clarify", "question": "ID?"}, ["policy"]),
        decision({"kind": "freeze"}, ["policy"], sufficient=True),
    ]
    base = collect_base(
        Model(responses),
        {"opening_message": "Help"},
        Corpus(),
        {},
        lambda _: "u1",
        len,
        journal=journal,
    )
    restored_corpus = Corpus()
    restored = collect_base(
        lambda _: pytest.fail("Analyzer cannot repeat sealed call"),
        {"opening_message": "Help"},
        restored_corpus,
        {},
        lambda _: pytest.fail("Clarification cannot repeat"),
        len,
        journal=journal,
    )
    assert restored == base
    assert restored_corpus.calls == [] and restored_corpus.closed


def test_fake_quote_cannot_replace_previous_legal_selection():
    model = Model(
        [
            decision({"kind": "search", "query": "policy"}),
            decision({"kind": "search", "query": "again"}, ["policy"]),
            decision(
                {"kind": "freeze"},
                ["policy"],
                sufficient=True,
                evidence=[{"requirement": "policy", "document_id": "policy", "quote": "invented"}],
            ),
        ]
    )
    base = collect_base(
        model, {}, Corpus(), {}, lambda _: "", len, budgets=AcquisitionBudgets(analyzer_steps=3)
    )
    assert base.stop_reason == "budget_exhausted_incomplete"
    assert base.evidence[0]["quote"] == "known user ID"


def test_search_context_has_one_full_text_copy_and_journal_preserves_raw_return(tmp_path):
    model = Model(
        [
            decision({"kind": "search", "query": "policy"}),
            decision({"kind": "freeze"}, ["policy"], sufficient=True),
        ]
    )
    journal = Journal(tmp_path)
    collect_base(model, {}, Corpus(), {}, lambda _: "", len, journal=journal)
    payload = model.inputs[-1]
    assert json.dumps(payload).count(DOC["content"]) == 1
    assert payload["observations"] == [
        {"kind": "search", "query": "policy", "status": "ok", "returned_document_ids": ["policy"]}
    ]
    assert journal.response("acquisition/search/0")["result"]["results"] == [DOC]


def test_request_input_budget_freezes_last_legal_selection_before_model_dispatch(tmp_path):
    class GrowingCorpus(Corpus):
        def search_web(self, query):
            self.calls.append(query)
            return {
                "results": [DOC]
                if len(self.calls) == 1
                else [{"page_id": "huge", "title": "huge", "content": "X" * 20000}]
            }

    corpus = GrowingCorpus()
    model = Model(
        [
            decision({"kind": "search", "query": "policy"}),
            decision({"kind": "search", "query": "more"}, ["policy"]),
        ]
    )
    journal = Journal(tmp_path)
    base = collect_base(
        model,
        {},
        corpus,
        {},
        lambda _: "",
        lambda text: 20001 if "huge" in text else len(text),
        journal=journal,
        system_prompt="analyzer",
        input_token_limit=10000,
        budgets=AcquisitionBudgets(base_tokens=400),
    )
    assert base.stop_reason == "budget_exhausted_incomplete"
    assert [document["document_id"] for document in base.documents] == ["policy"]
    assert base.evidence[0]["quote"] == "known user ID"
    assert len(model.inputs) == 2 and corpus.closed
    operations = [
        json.loads(path.read_text())["operation_id"] for path in tmp_path.glob("*/request.json")
    ]
    assert "acquisition/analyzer/2" not in operations


@pytest.mark.parametrize("fail_initial_count", [False, True])
def test_tokenizer_error_is_not_budget_exhaustion_or_unknown_dispatch(tmp_path, fail_initial_count):
    def counter(text):
        value = json.loads(text)
        if fail_initial_count or isinstance(value, dict) and "input" in value:
            raise RuntimeError("tokenizer unavailable")
        return len(text)

    corpus = Corpus()
    journal = Journal(tmp_path)
    with pytest.raises(RuntimeError, match="tokenizer unavailable"):
        collect_base(
            lambda _: pytest.fail("must not send"),
            {},
            corpus,
            {},
            lambda _: "",
            counter,
            journal=journal,
        )
    assert not list(tmp_path.glob("*/request.json")) and corpus.closed


def test_large_unrelated_hit_does_not_hide_short_required_document(tmp_path):
    huge = {"page_id": "huge", "title": "Unrelated long result", "content": "irrelevant " * 20000}
    model = Model(
        [
            decision({"kind": "search", "query": "policy"}),
            decision({"kind": "freeze"}, ["policy"], sufficient=True),
            decision({"kind": "freeze"}, ["policy"], sufficient=True),
        ]
    )
    journal = Journal(tmp_path / "journal")
    base = collect_base(
        model,
        {"opening": "Help"},
        Corpus([DOC, huge]),
        {},
        None,
        lambda text: len(text.split()),
        system_prompt="analyzer",
        input_token_limit=1000,
        journal=journal,
    )
    assert [doc["document_id"] for doc in base.documents] == ["policy"]
    assert all("irrelevant " * 20000 not in str(request) for request in model.inputs)
    summary = journal.response("acquisition-summary")
    assert summary["unreviewable_document_ids"] == ["huge"]
    assert summary["counters"]["search"] == 1


def test_last_decision_is_reserved_for_review_not_an_unreviewed_search(tmp_path):
    corpus = Corpus()
    model = Model([decision({"kind": "search", "query": "policy"})])
    journal = Journal(tmp_path / "journal")
    base = collect_base(
        model,
        {},
        corpus,
        {},
        None,
        lambda text: len(text.split()),
        budgets=AcquisitionBudgets(analyzer_steps=1),
        journal=journal,
    )
    assert corpus.calls == [] and base.documents == ()
    assert model.inputs[0]["final_review"]
    assert journal.response("acquisition-summary")["stop_detail"] == "analyzer_steps_exhausted"


def test_packing_prioritizes_supporting_citations_without_discarding_selection(tmp_path):
    docs = {
        doc["document_id"]: doc
        for doc in [
            normalize_document(DOC),
            normalize_document({"page_id": "high", "title": "Possible", "content": "possible"}),
        ]
    }
    raw = decision(
        {"kind": "freeze"},
        ["policy"],
        sufficient=True,
        scores=[
            {"document_id": "high", "confidence": 1.0, "reason": "possible"},
            {"document_id": "policy", "confidence": 0.9, "reason": "necessary"},
        ],
    )
    selected, evidence, count = _selection(raw, docs, lambda text: len(json.loads(text)), 1, 0.1)
    assert [doc["document_id"] for doc in selected] == ["policy"]
    assert evidence[0]["document_id"] == "policy" and count == 1


def test_capacity_dropped_evidence_cannot_freeze_as_sufficient(tmp_path):
    extra = {"page_id": "z_extra", "title": "Second requirement", "content": "Another rule."}
    incomplete = decision({"kind": "freeze"}, ["policy"], gaps=["Second rule still missing"])
    claimed = decision(
        {"kind": "freeze"},
        ["policy"],
        sufficient=True,
        scores=[
            {"document_id": identifier, "confidence": 1, "reason": "Necessary rule"}
            for identifier in ("policy", "z_extra")
        ],
        evidence=[
            {"requirement": "First rule", "document_id": "policy"},
            {"requirement": "Second rule", "document_id": "z_extra"},
        ],
    )
    model = Model([decision({"kind": "search", "query": "rules"}), claimed, incomplete])
    journal = Journal(tmp_path)

    def counter(text):
        value = json.loads(text)
        return len(value) if isinstance(value, list) else 0

    base = collect_base(
        model,
        {},
        Corpus([DOC, extra]),
        {},
        None,
        counter,
        budgets=AcquisitionBudgets(base_tokens=1, analyzer_steps=3),
        journal=journal,
    )
    assert base.stop_reason == "budget_exhausted_incomplete"
    assert len(model.inputs) == 3
    assert [document["document_id"] for document in base.documents] == ["policy"]
    assert any(
        item.get("dropped_citations") == ["z_extra"]
        for item in journal.response("acquisition-summary")["observations"]
    )


def test_batch_admission_counts_final_review_metadata_before_dispatch(tmp_path):
    from tau_skill_evolution.generator import model_messages
    from tau_skill_evolution.model import SerializedChatTokenCounter

    budgets = AcquisitionBudgets(
        searches=1, clarifications=0, read_only_queries=0, base_tokens=400, analyzer_steps=3
    )
    calibration = Model(
        [
            decision({"kind": "search", "query": "policy"}),
            decision({"kind": "freeze"}, ["policy"], sufficient=True),
        ]
    )
    collect_base(
        calibration, {}, Corpus(), {}, None, len, budgets=budgets, system_prompt="analyzer"
    )
    counter = SerializedChatTokenCounter(len)
    limit = counter.count(model_messages(calibration.inputs[-1], "analyzer")) - 1
    model = Model([decision({"kind": "search", "query": "policy"}), decision({"kind": "freeze"})])

    def admitted(payload):
        assert counter.count(model_messages(payload, "analyzer")) <= limit
        return model(payload)

    journal = Journal(tmp_path)
    base = collect_base(
        admitted,
        {},
        Corpus(),
        {},
        None,
        len,
        budgets=budgets,
        system_prompt="analyzer",
        input_token_limit=limit,
        journal=journal,
    )
    assert base.stop_reason == "budget_exhausted_incomplete"
    assert base.documents == ()
    assert all(not payload["returned_documents"] for payload in model.inputs)
    assert journal.response("acquisition-summary")["unreviewable_document_ids"] == ["policy"]
