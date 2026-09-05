from __future__ import annotations

import json

import pytest

from r2sp_common import Page, PublicTrace, SearchEvent, SearchHit, TraceEvent


def test_page_binds_hash_to_exact_utf8_body_and_separates_public_views() -> None:
    page = Page(page_id="doc-1", title="Gold Rewards", body="café\n")

    assert page.content_sha256 == "7b49b9e063bd91a4f9252b413261f5557b9c570aa61516989499f64a62dbcdd6"
    assert page.to_agent_header() == {"page_id": "doc-1", "title": "Gold Rewards"}
    assert page.to_open_dict() == {
        "page_id": "doc-1",
        "title": "Gold Rewards",
        "body": "café\n",
        "content_sha256": page.content_sha256,
    }

    with pytest.raises(ValueError, match="content_sha256"):
        Page("doc-1", "Gold Rewards", "café\n", "0" * 64)


def test_search_event_serializes_hidden_top10_and_body_free_visible_prefix() -> None:
    hits = tuple(
        SearchHit(
            rank=index,
            page_id=f"doc-{index}",
            title=f"Title {index}",
            score=1.0 / index,
            content_sha256=f"{index:064x}",
        )
        for index in range(1, 11)
    )
    event = SearchEvent(
        search_index=1,
        query="gold card",
        query_terms=("gold", "card"),
        top10=hits,
        visible_count=5,
    )

    assert event.agent_results == tuple(
        {"page_id": f"doc-{index}", "title": f"Title {index}"} for index in range(1, 6)
    )
    encoded = event.to_dict()
    assert len(encoded["top10"]) == 10
    assert encoded["top10"][0]["score"] == 1.0
    assert encoded["top10"][0]["content_sha256"] == f"{1:064x}"
    assert all("body" not in hit for hit in encoded["top10"])
    assert encoded["visible_page_ids"] == [f"doc-{index}" for index in range(1, 6)]


def test_search_event_rejects_duplicate_terms_or_non_prefix_ranks() -> None:
    hit = SearchHit(1, "a", "A", 1.0, "a" * 64)
    with pytest.raises(ValueError, match="query_terms"):
        SearchEvent(1, "a", ("a", "a"), (hit,), 1)
    with pytest.raises(ValueError, match="rank"):
        SearchEvent(
            1,
            "a",
            ("a",),
            (SearchHit(2, "a", "A", 1.0, "a" * 64),),
            1,
        )


def test_public_trace_is_ordered_json_and_extracts_first_visible_user_utterance() -> None:
    trace = PublicTrace(
        (
            TraceEvent(0, "system", "message", {"content": "trusted policy"}),
            TraceEvent(1, "user", "message", {"content": "Please compare cards."}),
            TraceEvent(2, "assistant", "tool_call", {"name": "search_web"}),
            TraceEvent(3, "tool", "tool_result", {"results": [{"page_id": "a"}]}),
        )
    )

    assert trace.first_user_utterance == "Please compare cards."
    assert PublicTrace.from_dict(trace.to_dict()) == trace
    assert json.loads(trace.to_json())["schema_version"] == "r2sp.public-trace.v1"

    with pytest.raises(ValueError, match="contiguous"):
        PublicTrace((TraceEvent(1, "user", "message", {"content": "late"}),))


def test_trace_event_defensively_freezes_nested_json_payload() -> None:
    payload = {"items": [{"page_id": "a"}]}
    event = TraceEvent(0, "tool", "tool_result", payload)
    payload["items"][0]["page_id"] = "changed"

    assert event.to_dict()["payload"] == {"items": [{"page_id": "a"}]}
    with pytest.raises(TypeError):
        TraceEvent(0, "tool", "tool_result", {"bad": object()})
