from __future__ import annotations

from collections.abc import Mapping

import pytest
from tau_skill_evolution.core import (
    DeterministicBM25,
    HybridRetrievalInvalid,
    HybridSearchEvent,
    HybridSessionWebRetriever,
    OpenBudgetExceeded,
    OpenPagesValidationError,
    OpenSelectionRequiredError,
    Page,
    PageSnippet,
    RetrieverClosedError,
    SearchBudgetExceeded,
    SearchHit,
    reciprocal_rank_fusion,
)


def _pages(count: int = 40) -> tuple[Page, ...]:
    pages = []
    for index in range(count):
        if index < 10:
            marker = "alpha"
        elif index < 20:
            marker = "beta"
        elif index < 30:
            marker = "gamma"
        else:
            marker = "delta"
        pages.append(
            Page(
                page_id=f"doc-{index:02d}",
                title=f"Document {index}",
                body=(f"{marker} policy marker-{index} " * 30).strip(),
            )
        )
    return tuple(pages)


class _StaticDenseIndex:
    def __init__(
        self,
        pages: tuple[Page, ...],
        corpus_hash: str,
        rankings: Mapping[str, tuple[str, ...]],
        *,
        failure: Exception | None = None,
    ) -> None:
        self._pages = {page.page_id: page for page in pages}
        self._corpus_hash = corpus_hash
        self._rankings = rankings
        self._failure = failure
        self.search_count = 0

    @property
    def page_count(self) -> int:
        return len(self._pages)

    @property
    def corpus_hash(self) -> str:
        return self._corpus_hash

    def search(self, query: str, *, limit: int = 10) -> tuple[SearchHit, ...]:
        self.search_count += 1
        if self._failure is not None:
            raise self._failure
        return tuple(
            SearchHit(
                rank=rank,
                page_id=page_id,
                title=self._pages[page_id].title,
                score=1.0 / rank,
                content_sha256=self._pages[page_id].content_sha256 or "",
            )
            for rank, page_id in enumerate(self._rankings[query][:limit], start=1)
        )

    def get_page(self, page_id: str) -> Page:
        return self._pages[page_id]


def _snippet(page: Page) -> PageSnippet:
    words = page.body.split()
    return PageSnippet(text=" ".join(words[:4]), truncated=len(words) > 4)


def _session(
    rankings: Mapping[str, tuple[str, ...]],
    *,
    pages: tuple[Page, ...] | None = None,
    failure: Exception | None = None,
    **retriever_kwargs: int,
) -> tuple[HybridSessionWebRetriever, _StaticDenseIndex, DeterministicBM25]:
    materialized_pages = pages or _pages()
    bm25 = DeterministicBM25(materialized_pages)
    dense = _StaticDenseIndex(
        materialized_pages,
        bm25.corpus_hash,
        rankings,
        failure=failure,
    )
    return HybridSessionWebRetriever(bm25, dense, _snippet, **retriever_kwargs), dense, bm25


def test_hybrid_search_returns_full_rrf_union_with_only_score_free_snippet_fields() -> None:
    session, _dense, _bm25 = _session(
        {"alpha": tuple(f"doc-{index:02d}" for index in range(5, 15))}
    )

    response = session.search_web("alpha")

    assert set(response) == {"results"}
    assert len(response["results"]) == 15
    assert all(
        set(candidate) == {"page_id", "title", "snippet", "snippet_truncated"}
        for candidate in response["results"]
    )
    event = session.search_events[0]
    assert len(event.bm25_top10) == 10
    assert len(event.dense_top10) == 10
    assert event.rrf_k == 60
    assert event.rrf_page_ids == reciprocal_rank_fusion((event.bm25_top10, event.dense_top10), k=60)
    assert event.returned_page_ids == tuple(
        candidate["page_id"] for candidate in response["results"]
    )
    assert HybridSearchEvent.from_dict(event.to_dict()) == event


def test_queries_deduplicate_within_each_route_union_but_may_repeat_later_candidates() -> None:
    session, _dense, _bm25 = _session(
        {
            "alpha": tuple(f"doc-{index:02d}" for index in range(10, 20)),
            "gamma": tuple(f"doc-{index:02d}" for index in range(30, 40)),
        }
    )

    first = session.search_web("alpha")["results"]
    session.open_pages([first[0]["page_id"]])
    second = session.search_web("gamma")["results"]

    first_ids = [candidate["page_id"] for candidate in first]
    second_ids = [candidate["page_id"] for candidate in second]
    assert len(first_ids) == 20
    assert len(second_ids) == 20
    assert set(first_ids).isdisjoint(second_ids)
    assert len(session.exposed_page_ids) == 40
    assert len(first_ids + second_ids) == len(set(first_ids + second_ids))
    session.open_pages([second[0]["page_id"]])
    repeated_ids = [item["page_id"] for item in session.search_web("alpha")["results"]]
    assert repeated_ids == first_ids


def test_tenth_search_is_allowed_and_eleventh_is_rejected() -> None:
    session, dense, _bm25 = _session(
        {"alpha": tuple(f"doc-{index:02d}" for index in range(10, 20))}
    )

    for search_index in range(10):
        results = session.search_web("alpha")["results"]
        session.open_pages([results[search_index]["page_id"]])

    assert session.search_calls == 10
    assert dense.search_count == 10
    assert len(session.search_events) == 10
    assert all(
        len(event.bm25_top10) == len(event.dense_top10) == 10 for event in session.search_events
    )
    with pytest.raises(SearchBudgetExceeded, match="10 calls"):
        session.search_web("alpha")


def test_nonempty_search_requires_an_agent_chosen_full_text_batch_before_next_search() -> None:
    session, dense, _bm25 = _session(
        {"alpha": tuple(f"doc-{index:02d}" for index in range(10, 20))}
    )
    results = session.search_web("alpha")["results"]

    assert session.open_selection_required
    with pytest.raises(OpenSelectionRequiredError, match="open_pages"):
        session.search_web("alpha")

    assert session.search_calls == 1
    assert dense.search_count == 1
    session.open_pages([results[0]["page_id"]])
    assert not session.open_selection_required
    session.search_web("alpha")
    assert session.search_calls == 2


def test_second_query_returns_relevant_pages_even_if_they_were_exposed_earlier() -> None:
    session, _dense, _bm25 = _session(
        {
            "alpha": tuple(f"doc-{index:02d}" for index in range(5, 15)),
            "beta": tuple(f"doc-{index:02d}" for index in range(5, 15)),
        }
    )
    first = session.search_web("alpha")["results"]
    first_ids = {candidate["page_id"] for candidate in first}
    session.open_pages([first[0]["page_id"]])
    second_ids = {candidate["page_id"] for candidate in session.search_web("beta")["results"]}

    assert first_ids & second_ids == {f"doc-{index:02d}" for index in range(5, 15)}
    assert second_ids - first_ids == {f"doc-{index:02d}" for index in range(15, 20)}


def test_rrf_sums_duplicate_contributions_and_breaks_equal_scores_by_page_id() -> None:
    pages = {page.page_id: page for page in _pages(10)}

    def hit(rank: int, page_id: str) -> SearchHit:
        return SearchHit(
            rank,
            page_id,
            pages[page_id].title,
            0.0,
            pages[page_id].content_sha256 or "",
        )

    first = (hit(1, "doc-02"), hit(2, "doc-00"), hit(3, "doc-01"))
    second = (hit(1, "doc-01"), hit(2, "doc-00"), hit(3, "doc-02"))

    assert reciprocal_rank_fusion((first, second), k=60) == (
        "doc-01",
        "doc-02",
        "doc-00",
    )


@pytest.mark.parametrize("selection_count", [1, 6, 15])
def test_open_pages_returns_every_selected_full_page_in_submitted_order(
    selection_count: int,
) -> None:
    session, _dense, _bm25 = _session(
        {"alpha": tuple(f"doc-{index:02d}" for index in range(10, 20))}
    )
    exposed = session.search_web("alpha")["results"]
    submitted = [candidate["page_id"] for candidate in reversed(exposed[:selection_count])]

    response = session.open_pages(submitted)

    assert [page["page_id"] for page in response["pages"]] == submitted
    assert [page.page_id for page in session.opened_pages] == submitted
    assert session.open_calls == 1
    assert session.opened_page_batches == (tuple(submitted),)
    assert all(
        set(page) == {"page_id", "title", "body", "content_sha256"} for page in response["pages"]
    )
    next_id = exposed[selection_count]["page_id"]
    session.open_pages([next_id])
    assert [page.page_id for page in session.opened_pages] == [*submitted, next_id]
    assert session.opened_page_batches == (tuple(submitted), (next_id,))
    with pytest.raises(OpenPagesValidationError):
        session.open_pages(submitted)


def test_search_and_open_pages_can_interleave_across_progressive_dialogue() -> None:
    session, _dense, _bm25 = _session(
        {
            "alpha": tuple(f"doc-{index:02d}" for index in range(10, 20)),
            "gamma": tuple(f"doc-{index:02d}" for index in range(30, 40)),
        }
    )
    first = session.search_web("alpha")["results"]
    first_ids = [candidate["page_id"] for candidate in first[:4]]
    session.open_pages(first_ids)

    second = session.search_web("gamma")["results"]
    second_ids = [candidate["page_id"] for candidate in second[:3]]
    session.open_pages(second_ids)

    assert session.search_calls == 2
    assert session.open_calls == 2
    assert session.opened_page_batches == (tuple(first_ids), tuple(second_ids))
    assert [page.page_id for page in session.opened_pages] == [*first_ids, *second_ids]


def test_open_batch_and_cumulative_unique_budgets_are_atomic_and_recoverable() -> None:
    rankings = {"alpha": tuple(f"doc-{index:02d}" for index in range(10, 20))}
    session, _dense, _bm25 = _session(
        rankings,
        max_open_batches=10,
        max_unique_opens=3,
    )
    exposed = [item["page_id"] for item in session.search_web("alpha")["results"]]
    session.open_pages(exposed[:2])

    with pytest.raises(OpenBudgetExceeded, match="3 pages"):
        session.open_pages(exposed[2:4])

    assert session.open_calls == 1
    assert [page.page_id for page in session.opened_pages] == exposed[:2]
    session.open_pages(exposed[2:3])
    assert session.open_calls == 2

    batch_limited, _dense, _bm25 = _session(
        rankings,
        max_open_batches=2,
        max_unique_opens=30,
    )
    exposed = [item["page_id"] for item in batch_limited.search_web("alpha")["results"]]
    batch_limited.open_pages(exposed[:1])
    batch_limited.open_pages(exposed[1:2])
    with pytest.raises(OpenBudgetExceeded, match="2 calls"):
        batch_limited.open_pages(exposed[2:3])


def test_default_cumulative_limit_opens_thirty_and_rejects_thirty_first_atomically() -> None:
    session, _dense, _bm25 = _session(
        {
            "alpha": tuple(f"doc-{index:02d}" for index in range(10, 20)),
            "gamma": tuple(f"doc-{index:02d}" for index in range(30, 40)),
        }
    )
    first = session.search_web("alpha")["results"]
    first_opened = first[0]["page_id"]
    session.open_pages([first_opened])
    session.search_web("gamma")
    exposed = sorted(session.exposed_page_ids)
    assert len(exposed) == 40
    assert session.max_unique_opens == 30

    remaining = [page_id for page_id in exposed if page_id != first_opened]
    session.open_pages(remaining[:14])
    session.open_pages(remaining[14:29])
    before = session.opened_pages
    before_batches = session.opened_page_batches
    with pytest.raises(OpenBudgetExceeded, match="30 pages"):
        session.open_pages(remaining[29:30])

    assert session.open_calls == 3
    assert session.opened_pages == before
    assert session.opened_page_batches == before_batches


@pytest.mark.parametrize(
    "selection",
    [
        [],
        ["doc-00", "doc-00"],
        ["doc-00", "not-exposed"],
    ],
)
def test_invalid_open_selection_is_recoverable_and_does_not_return_partial_pages(
    selection: list[str],
) -> None:
    session, _dense, _bm25 = _session(
        {"alpha": tuple(f"doc-{index:02d}" for index in range(10, 20))}
    )
    session.search_web("alpha")

    with pytest.raises(OpenPagesValidationError):
        session.open_pages(selection)

    assert session.open_calls == 0
    assert session.opened_pages == ()
    assert session.invalid_reason is None
    corrected = [f"doc-{index:02d}" for index in range(6)]
    response = session.open_pages(corrected)
    assert [page["page_id"] for page in response["pages"]] == corrected


def test_dense_failure_invalidates_cell_and_never_falls_back_to_bm25() -> None:
    session, dense, _bm25 = _session(
        {"alpha": tuple(f"doc-{index:02d}" for index in range(10))},
        failure=RuntimeError("embedding endpoint unavailable"),
    )

    with pytest.raises(HybridRetrievalInvalid) as first:
        session.search_web("alpha")

    assert "failed closed" in str(first.value)
    assert dense.search_count == 1
    assert session.search_calls == 1
    assert session.search_events == ()
    assert session.exposed_page_ids == frozenset()
    with pytest.raises(HybridRetrievalInvalid):
        session.search_web("alpha")
    assert dense.search_count == 1


def test_close_destroys_all_hybrid_state_and_references() -> None:
    session, _dense, _bm25 = _session(
        {"alpha": tuple(f"doc-{index:02d}" for index in range(10, 20))}
    )
    exposed = session.search_web("alpha")["results"]
    session.open_pages([candidate["page_id"] for candidate in exposed[:10]])

    session.close()

    assert session.closed
    assert session.search_calls == 0
    assert session.open_calls == 0
    assert session.search_events == ()
    assert session.exposed_page_ids == frozenset()
    assert session.opened_pages == ()
    assert session.opened_page_batches == ()
    assert not session.open_selection_required
    assert session.invalid_reason is None
    with pytest.raises(RetrieverClosedError):
        session.search_web("alpha")
    with pytest.raises(RetrieverClosedError):
        session.open_pages([])
