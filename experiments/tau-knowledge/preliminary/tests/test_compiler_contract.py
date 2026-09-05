from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from r2sp_tau_knowledge.compiler import TauSkillCompiler, validate_skill_text

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


def _compiler(
    tmp_path: Path,
    client: RecordingClient,
    *,
    include_public_trace: bool = False,
) -> TauSkillCompiler:
    prompt = tmp_path / "compiler.md"
    prompt.write_text("Compile only the allowed evidence.", encoding="utf-8")
    return TauSkillCompiler(
        client,
        include_public_trace=include_public_trace,
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
    trace = {"events": [{"hidden_scenario": "must not leak"}]}

    payload = compiler.build_payload(
        first_user_utterance="Which card fits me?",
        opened_pages=[first, second, duplicate],
        task_id="task_001",
        task_success=True,
        public_trace=trace,
    )

    assert payload == {
        "task": "Which card fits me?",
        "documents_actually_read": [first, second],
        "official_result": {"task_id": "task_001", "task_success": True},
    }
    assert "public_trace" not in payload
    assert "hidden_scenario" not in json.dumps(payload)


@pytest.mark.parametrize(
    "hidden_name",
    ["scenario", "required_documents", "gold_actions", "reward_breakdown", "db_snapshot"],
)
def test_hidden_fields_are_not_accepted_by_compiler_api(
    tmp_path: Path,
    hidden_name: str,
) -> None:
    compiler = _compiler(tmp_path, RecordingClient())
    arguments: dict[str, Any] = {
        "first_user_utterance": "Question",
        "opened_pages": [_page("page-a", "body")],
        "task_id": "task_001",
        "task_success": True,
        hidden_name: {"secret": True},
    }
    with pytest.raises(TypeError):
        compiler.build_payload(**arguments)


def test_public_trace_is_explicitly_opt_in(tmp_path: Path) -> None:
    compiler = _compiler(tmp_path, RecordingClient(), include_public_trace=True)
    trace = {"events": [{"role": "assistant", "tool": "search_web"}]}
    payload = compiler.build_payload(
        first_user_utterance="Question",
        opened_pages=[_page("page-a", "body")],
        task_id="task_001",
        task_success=False,
        public_trace=trace,
    )
    assert payload["public_trace"] == trace

    with pytest.raises(ValueError, match="public_trace is required"):
        compiler.build_payload(
            first_user_utterance="Question",
            opened_pages=[],
            task_id="task_001",
            task_success=False,
        )


def test_compile_sends_only_allowlisted_payload_and_records_first_source_ids(
    tmp_path: Path,
) -> None:
    client = RecordingClient()
    compiler = _compiler(tmp_path, client)
    artifact = compiler.compile(
        first_user_utterance="Question",
        opened_pages=[_page("page-a", "body"), _page("page-a", "later")],
        task_id="task_001",
        task_success=True,
        public_trace={"secret": "not included by default"},
        seed=20260904,
    )

    assert artifact.valid is True
    assert artifact.source_page_ids == ("page-a",)
    assert validate_skill_text(artifact.text) is None
    call = client.calls[0]
    assert call["tools"] is None
    assert call["seed"] == 20260904
    sent_payload = json.loads(call["messages"][1]["content"])
    assert set(sent_payload) == {"task", "documents_actually_read", "official_result"}


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
        opened_pages=[_page("page-a", "body")],
        task_id="task_001",
        task_success=True,
    )
    assert artifact.valid is False
    assert artifact.text == ""
    assert artifact.failure == failure
