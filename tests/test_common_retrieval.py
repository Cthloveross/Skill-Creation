from __future__ import annotations

import math

import pytest

from r2sp_common import (
    DeterministicBM25,
    InvalidQueryError,
    OpenBudgetExceeded,
    Page,
    PageNotExposedError,
    RetrieverClosedError,
    SearchBudgetExceeded,
    SessionWebRetriever,
    tokenize,
)


def _pages(count: int = 12) -> tuple[Page, ...]:
    return tuple(
        Page(
            page_id=f"doc-{index:02d}",
            title=f"Document {index}",
            body=("gold rewards benefits " * (count - index + 1)) + f"marker{index}",
        )
        for index in range(1, count + 1)
    )


def test_tokenizer_is_nfkc_casefold_unicode_word_and_splits_underscore() -> None:
    assert tokenize("ＧＯＬＤ_rewards Straße 東京") == (
        "gold",
        "rewards",
        "strasse",
        "東京",
    )


def test_bm25_indexes_only_body_suppresses_duplicate_query_terms_and_ties_by_id() -> None:
    pages = (
        Page("z", "needle only in title", "same body"),
        Page("a", "irrelevant", "same body"),
        Page("m", "irrelevant", "body contains needle"),
    )
    index = DeterministicBM25(pages)

    title_only = index.search("needle", limit=3)
    duplicated = index.search("needle needle needle", limit=3)

    assert [hit.page_id for hit in title_only] == ["m", "a", "z"]
    assert [(hit.page_id, hit.score) for hit in duplicated] == [
        (hit.page_id, hit.score) for hit in title_only
    ]
    assert [hit.page_id for hit in index.search("absent", limit=3)] == ["a", "m", "z"]


def test_bm25_uses_locked_k1_b_and_robertson_idf_formula() -> None:
    index = DeterministicBM25(
        (
            Page("short", "Short", "term"),
            Page("long", "Long", "term term filler"),
        )
    )

    hits = {hit.page_id: hit.score for hit in index.search("term", limit=2)}
    inverse_document_frequency = math.log(1.0 + 0.5 / 2.5)

    assert index.k1 == 1.2
    assert index.b == 0.75
    assert hits["short"] == pytest.approx(inverse_document_frequency * 2.2 / 1.75)
    assert hits["long"] == pytest.approx(inverse_document_frequency * 4.4 / 3.65)


@pytest.mark.parametrize("query", ["", "   ", "___", "!!!"])
def test_empty_or_tokenless_query_is_invalid(query: str) -> None:
    index = DeterministicBM25(_pages(1))
    with pytest.raises(InvalidQueryError):
        index.search(query)


def test_session_keeps_top10_but_returns_exactly_five_score_free_body_free_headers() -> None:
    session = SessionWebRetriever(DeterministicBM25(_pages()))

    response = session.search_web("gold rewards")

    assert set(response) == {"results"}
    assert len(response["results"]) == 5
    assert all(set(item) == {"page_id", "title"} for item in response["results"])
    assert len(session.search_events) == 1
    event = session.search_events[0]
    assert len(event.top10) == 10
    assert event.visible_page_ids == tuple(item["page_id"] for item in response["results"])
    assert all(hit.content_sha256 for hit in event.top10)


def test_open_page_requires_prior_visible_exposure_and_tracks_unique_first_open_order() -> None:
    session = SessionWebRetriever(DeterministicBM25(_pages()))
    visible = session.search_web("gold rewards")["results"]

    with pytest.raises(PageNotExposedError):
        session.open_page("doc-12")

    first = session.open_page(visible[1]["page_id"])
    repeated = session.open_page(visible[1]["page_id"])
    second = session.open_page(visible[0]["page_id"])

    assert first == repeated
    assert set(first) == {"page_id", "title", "body", "content_sha256"}
    assert [page.page_id for page in session.opened_pages] == [
        visible[1]["page_id"],
        visible[0]["page_id"],
    ]
    assert second["body"]


def test_search_and_unique_open_budgets_are_fail_closed_and_configurable() -> None:
    session = SessionWebRetriever(
        DeterministicBM25(_pages()),
        internal_k=6,
        visible_k=6,
        max_searches=2,
        max_unique_opens=2,
    )
    results = session.search_web("gold")["results"]
    session.search_web("rewards")
    with pytest.raises(SearchBudgetExceeded):
        session.search_web("benefits")

    session.open_page(results[0]["page_id"])
    session.open_page(results[1]["page_id"])
    session.open_page(results[0]["page_id"])
    with pytest.raises(OpenBudgetExceeded):
        session.open_page(results[2]["page_id"])


def test_invalid_search_attempt_consumes_budget_and_close_destroys_session_state() -> None:
    session = SessionWebRetriever(DeterministicBM25(_pages()), max_searches=1, max_unique_opens=1)

    with pytest.raises(InvalidQueryError):
        session.search_web("!!!")
    assert session.search_calls == 1
    with pytest.raises(SearchBudgetExceeded):
        session.search_web("gold")

    session.close()
    assert session.closed
    assert session.search_events == ()
    assert session.opened_pages == ()
    assert session.exposed_page_ids == frozenset()
    with pytest.raises(RetrieverClosedError):
        session.search_web("gold")
    with pytest.raises(RetrieverClosedError):
        session.open_page("doc-01")
