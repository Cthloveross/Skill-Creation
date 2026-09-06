from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from r2sp_tau_knowledge.batch_compiler import (
    TauSkillCompiler,
    sanitize_acquisition_trace,
    validate_skill_text,
)
from r2sp_tau_knowledge.batch_constants import SELECTION_K

VALID_SKILL = """---
name: banking-card-help
description: Help with banking card questions.
---
# Procedure

Read the supplied task and use the banking tools.
"""


class RecordingClient:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or {"content": VALID_SKILL}
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        seed: int | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "messages": [dict(message) for message in messages],
                "tools": tools,
                "seed": seed,
                "max_output_tokens": max_output_tokens,
            }
        )
        return dict(self.response)


def _page(page_id: str, body: str, *, title: str | None = None) -> dict[str, str]:
    return {
        "page_id": page_id,
        "title": title or page_id,
        "body": body,
        "content_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def _selection(*pages: dict[str, str]) -> list[dict[str, str]]:
    """Supply the current exact-ten contract while retaining duplicate test inputs."""
    selected = list(pages)
    unique_count = len({page["page_id"] for page in selected})
    selected.extend(
        _page(f"filler-{index}", "Reference body") for index in range(SELECTION_K - unique_count)
    )
    return selected


def _compiler(
    tmp_path: Path,
    client: RecordingClient,
    *,
    include_public_trace: bool = False,
    max_input_tokens: int = 32768,
    chars_per_token: int = 4,
) -> TauSkillCompiler:
    prompt = tmp_path / "compiler.md"
    prompt.write_text("Compile only the allowed evidence.", encoding="utf-8")
    return TauSkillCompiler(
        client,
        include_public_trace=include_public_trace,
        max_input_tokens=max_input_tokens,
        chars_per_token=chars_per_token,
        prompt_path=prompt,
    )


def test_default_payload_is_exact_allowlist_and_first_open_order_is_deduplicated(
    tmp_path: Path,
) -> None:
    client = RecordingClient()
    compiler = _compiler(tmp_path, client)
    first = _page("page-a", "first body")
    second = _page("page-b", "second body")
    duplicate = _page("page-a", "later duplicate body", title="changed title")
    selected = _selection(first, second, duplicate)
    trace = {"events": [{"hidden_scenario": "must not leak"}]}

    payload = compiler.build_payload(
        first_user_utterance="Which card fits me?",
        opened_pages=selected,
        public_trace=trace,
    )

    assert payload == {
        "task": "Which card fits me?",
        "documents_actually_read": [first, second, *selected[3:]],
    }
    assert "public_trace" not in payload
    assert "hidden_scenario" not in json.dumps(payload)


@pytest.mark.parametrize(
    "hidden_name",
    [
        "scenario",
        "required_documents",
        "gold_actions",
        "reward_breakdown",
        "db_snapshot",
        "task_id",
        "task_success",
        "official_result",
    ],
)
def test_hidden_fields_are_not_accepted_by_compiler_api(
    tmp_path: Path,
    hidden_name: str,
) -> None:
    compiler = _compiler(tmp_path, RecordingClient())
    arguments: dict[str, Any] = {
        "first_user_utterance": "Question",
        "opened_pages": [_page("page-a", "body")],
        hidden_name: {"secret": True},
    }
    with pytest.raises(TypeError):
        compiler.build_payload(**arguments)


def test_public_trace_is_explicitly_opt_in(tmp_path: Path) -> None:
    compiler = _compiler(tmp_path, RecordingClient(), include_public_trace=True)
    trace = {
        "events": [
            {
                "sequence": 0,
                "actor": "assistant",
                "kind": "tool_call",
                "payload": {"name": "search_web", "query": "cash back card"},
            }
        ]
    }
    payload = compiler.build_payload(
        first_user_utterance="Question",
        opened_pages=_selection(_page("page-a", "body")),
        public_trace=trace,
    )
    assert "public_trace" not in payload
    assert payload["acquisition_trace"]["events"][0]["payload"] == {
        "name": "search_web",
        "query": "cash back card",
    }

    with pytest.raises(ValueError, match="public_trace is required"):
        compiler.build_payload(
            first_user_utterance="Question",
            opened_pages=_selection(),
        )


def test_acquisition_trace_preserves_decisions_but_redacts_retrieval_evidence() -> None:
    unselected_body = "UNSELECTED-DOCUMENT-BODY-MUST-NOT-LEAK"
    selected_body = "SELECTED-DOCUMENT-BODY-MUST-APPEAR-ONLY-IN-DOCUMENTS"
    trace = {
        "schema_version": "r2sp.public-trace.v1",
        "task_id": "task_001",
        "task_success": True,
        "reward": 1.0,
        "events": [
            {
                "sequence": 41,
                "actor": "user",
                "kind": "message",
                "payload": {
                    "content": "I need a card recommendation.",
                    "hidden_scenario": "HIDDEN-SCENARIO-MARKER",
                },
            },
            {
                "sequence": 44,
                "actor": "assistant",
                "kind": "message",
                "payload": {
                    "content": "I will compare the relevant terms.",
                    "tool_calls": [
                        {
                            "id": "search-1",
                            "name": "search_web",
                            "arguments": {
                                "query": "annual fee cash back",
                                "gold_actions": "GOLD-ACTIONS-MARKER",
                            },
                            "requestor": "assistant",
                        },
                        {
                            "id": "time-1",
                            "name": "get_current_time",
                            "arguments": {},
                            "requestor": "assistant",
                        },
                    ],
                    "raw_data": {"evaluator_secret": "RAW-EVALUATOR-MARKER"},
                },
            },
            {
                "sequence": 45,
                "actor": "tool",
                "kind": "tool_result",
                "payload": {
                    "id": "search-1",
                    "requestor": "assistant",
                    "content": json.dumps(
                        {
                            "results": [
                                {
                                    "page_id": "not-selected",
                                    "title": "Unselected",
                                    "body": unselected_body,
                                },
                                {
                                    "page_id": "page-a",
                                    "title": "Selected",
                                    "body": selected_body,
                                },
                            ]
                        }
                    ),
                    "official_result": "OFFICIAL-RESULT-MARKER",
                },
            },
            {
                "sequence": 46,
                "actor": "tool",
                "kind": "tool_result",
                "payload": {
                    "id": "time-1",
                    "requestor": "assistant",
                    "content": json.dumps(
                        {
                            "time": "2026-09-05T12:00:00Z",
                            "reward_breakdown": "REWARD-MARKER",
                        }
                    ),
                },
            },
            {
                "sequence": 50,
                "actor": "assistant",
                "kind": "message",
                "payload": {
                    "tool_calls": [
                        {
                            "id": "select-1",
                            "name": "select_docs",
                            "arguments": {
                                "page_ids": ["page-a", "page-b", "page-c", "page-d", "page-e"]
                            },
                            "requestor": "assistant",
                        }
                    ]
                },
            },
            {
                "sequence": 51,
                "actor": "tool",
                "kind": "tool_result",
                "payload": {
                    "id": "select-1",
                    "requestor": "assistant",
                    "content": json.dumps(
                        {
                            "documents": [
                                {"page_id": "page-a", "body": selected_body},
                                {"page_id": "page-b", "body": "another selected body"},
                            ]
                        }
                    ),
                },
            },
            {
                "sequence": 52,
                "actor": "runtime",
                "kind": "evaluator",
                "payload": {"task_success": True, "gold": "RUNTIME-GOLD-MARKER"},
            },
        ],
    }

    clean = sanitize_acquisition_trace(trace)
    encoded = json.dumps(clean, ensure_ascii=False, sort_keys=True)

    assert clean["schema_version"] == "r2sp.compiler-acquisition-trace.v1"
    assert [event["sequence"] for event in clean["events"]] == list(range(len(clean["events"])))
    assert "I need a card recommendation." in encoded
    assert "I will compare the relevant terms." in encoded
    assert "annual fee cash back" in encoded
    assert all(page_id in encoded for page_id in ("page-a", "page-b", "page-c", "page-d", "page-e"))
    assert "2026-09-05T12:00:00Z" in encoded
    assert "search_web output redacted" in encoded
    assert "select_docs output redacted" in encoded
    assert unselected_body not in encoded
    assert selected_body not in encoded
    for marker in (
        "HIDDEN-SCENARIO-MARKER",
        "GOLD-ACTIONS-MARKER",
        "RAW-EVALUATOR-MARKER",
        "OFFICIAL-RESULT-MARKER",
        "REWARD-MARKER",
        "RUNTIME-GOLD-MARKER",
    ):
        assert marker not in encoded

    trace["events"][0]["payload"]["content"] = "mutated after sanitization"
    assert "mutated after sanitization" not in json.dumps(clean)


def test_selected_bodies_enter_only_through_exact_document_allowlist(tmp_path: Path) -> None:
    compiler = _compiler(tmp_path, RecordingClient(), include_public_trace=True)
    selected_body = "EXACT-SELECTED-BODY"
    trace = {
        "events": [
            {
                "sequence": 0,
                "actor": "assistant",
                "kind": "tool_call",
                "payload": {
                    "name": "select_docs",
                    "page_ids": [f"page-{index}" for index in range(SELECTION_K)],
                },
            },
            {
                "sequence": 1,
                "actor": "tool",
                "kind": "tool_result",
                "payload": {"documents": [{"page_id": "page-0", "body": selected_body}]},
            },
        ]
    }
    pages = [
        _page(f"page-{index}", selected_body if index == 0 else str(index))
        for index in range(SELECTION_K)
    ]

    payload = compiler.build_payload(
        first_user_utterance="Question",
        opened_pages=pages,
        public_trace=trace,
    )
    encoded = json.dumps(payload, ensure_ascii=False)

    assert len(payload["documents_actually_read"]) == SELECTION_K
    assert encoded.count(selected_body) == 1
    assert payload["acquisition_trace"]["events"][0]["payload"]["page_ids"] == [
        f"page-{index}" for index in range(SELECTION_K)
    ]


def test_sanitized_trace_counts_against_compiler_input_budget(tmp_path: Path) -> None:
    compiler = _compiler(
        tmp_path,
        RecordingClient(),
        include_public_trace=True,
        max_input_tokens=2500,
        chars_per_token=1,
    )
    trace = {
        "events": [
            {
                "sequence": 0,
                "actor": "assistant",
                "kind": "message",
                "payload": {"content": "x" * 5000},
            }
        ]
    }

    compiler.build_payload(
        first_user_utterance="Question",
        opened_pages=_selection(_page("page-a", "body")),
        public_trace={"events": []},
    )
    with pytest.raises(ValueError, match="exceeds fixed input budget"):
        compiler.build_payload(
            first_user_utterance="Question",
            opened_pages=_selection(_page("page-a", "body")),
            public_trace=trace,
        )


def test_compile_sends_only_allowlisted_payload_and_records_first_source_ids(
    tmp_path: Path,
) -> None:
    client = RecordingClient()
    compiler = _compiler(tmp_path, client)
    artifact = compiler.compile(
        first_user_utterance="Question",
        opened_pages=_selection(_page("page-a", "body"), _page("page-a", "later")),
        public_trace={"secret": "not included by default"},
        seed=20260904,
    )

    assert artifact.valid is True
    assert artifact.source_page_ids == (
        "page-a",
        *(f"filler-{index}" for index in range(SELECTION_K - 1)),
    )
    assert validate_skill_text(artifact.text) is None
    call = client.calls[0]
    assert call["tools"] is None
    assert call["seed"] == 20260904
    sent_payload = json.loads(call["messages"][1]["content"])
    assert set(sent_payload) == {"task", "documents_actually_read"}


@pytest.mark.parametrize(
    ("response", "failure"),
    [
        ({"content": "not a skill"}, "invalid_skill_frontmatter_missing"),
        ({"content": ""}, "empty_skill"),
        (
            {"content": VALID_SKILL, "tool_calls": [{"id": "unexpected"}]},
            "compiler_returned_tool_calls",
        ),
    ],
)
def test_invalid_compiler_output_never_becomes_a_skill(
    tmp_path: Path,
    response: dict[str, Any],
    failure: str,
) -> None:
    compiler = _compiler(tmp_path, RecordingClient(response))
    artifact = compiler.compile(
        first_user_utterance="Question",
        opened_pages=_selection(_page("page-a", "body")),
    )
    assert artifact.valid is False
    assert artifact.text == ""
    assert artifact.failure == failure
