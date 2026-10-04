from __future__ import annotations

from collections.abc import Mapping

import pytest
from tau_skill_evolution.core import (
    FullDocumentHybridSession,
    HybridRetrievalInvalid,
    Page,
    RetrieverClosedError,
    SearchHit,
    reciprocal_rank_fusion,
    serialize_full_document_response,
)


def _pages(count: int = 30) -> tuple[Page, ...]:
    return tuple(
        Page(
            page_id=f"doc-{index:02d}",
            title=f"Document {index}",
            body=f"Complete policy body for document {index}. " * 4,
        )
        for index in range(count)
    )


class _StaticIndex:
    def __init__(
        self,
        pages: tuple[Page, ...],
        rankings: Mapping[str, tuple[str, ...]],
        *,
        corpus_hash: str = "shared-corpus",
        failure: Exception | None = None,
    ) -> None:
        self._pages = {page.page_id: page for page in pages}
        self._rankings = dict(rankings)
        self._corpus_hash = corpus_hash
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
        page_ids = self._rankings[query][:limit]
        return tuple(
            SearchHit(
                rank=rank,
                page_id=page_id,
                title=self._pages[page_id].title,
                score=1.0 / rank,
                content_sha256=self._pages[page_id].content_sha256 or "",
            )
            for rank, page_id in enumerate(page_ids, start=1)
        )

    def get_page(self, page_id: str) -> Page:
        return self._pages[page_id]


RANKINGS = {
    "alpha": tuple(f"doc-{index:02d}" for index in range(0, 10)),
    "alpha-dense": tuple(f"doc-{index:02d}" for index in range(5, 15)),
    "beta": tuple(f"doc-{index:02d}" for index in range(10, 20)),
    "beta-dense": tuple(f"doc-{index:02d}" for index in range(15, 25)),
}


def _session(
    *,
    wire_token_budget: int = 65_536,
    dense_failure: Exception | None = None,
    dense_alpha: tuple[str, ...] | None = None,
) -> tuple[FullDocumentHybridSession, _StaticIndex, _StaticIndex]:
    pages = _pages()
    bm25 = _StaticIndex(
        pages,
        {"alpha": RANKINGS["alpha"], "beta": RANKINGS["beta"]},
    )
    dense = _StaticIndex(
        pages,
        {
            "alpha": dense_alpha or RANKINGS["alpha-dense"],
            "beta": RANKINGS["beta-dense"],
        },
        failure=dense_failure,
    )
    return (
        FullDocumentHybridSession(
            bm25,
            dense,
            len,
            wire_token_budget=wire_token_budget,
        ),
        bm25,
        dense,
    )


def test_search_returns_complete_score_free_rrf_union_as_full_documents() -> None:
    session, _bm25, _dense = _session()

    response = session.search_web("alpha")

    assert response["status"] == "ok"
    assert len(response["results"]) == 15
    assert all(set(item) == {"page_id", "title", "content"} for item in response["results"])
    event = session.search_events[0]
    assert len(event.bm25_top10) == len(event.dense_top10) == 10
    assert event.rrf_k == 60
    assert event.rrf_page_ids == reciprocal_rank_fusion((event.bm25_top10, event.dense_top10), k=60)
    assert event.returned_page_ids == tuple(item["page_id"] for item in response["results"])
    assert session.retrieved_page_ids == event.rrf_page_ids
    assert session.wire_tokens_used == len(serialize_full_document_response(response))
    assert all("score" not in item and "rank" not in item for item in response["results"])


def test_each_query_returns_full_documents_but_compiler_evidence_stays_deduplicated() -> None:
    session, _bm25, _dense = _session()

    first = session.search_web("alpha")
    second = session.search_web("beta")
    third = session.search_web("alpha")

    first_ids = {item["page_id"] for item in first["results"]}
    second_by_id = {item["page_id"]: item for item in second["results"]}
    assert first_ids == {f"doc-{index:02d}" for index in range(15)}
    assert set(second_by_id) == {f"doc-{index:02d}" for index in range(10, 25)}
    assert all(set(item) == {"page_id", "title", "content"} for item in second["results"])
    assert all(set(item) == {"page_id", "title", "content"} for item in third["results"])
    assert len(session.retrieved_pages) == 25
    assert len(session.retrieved_page_ids) == len(set(session.retrieved_page_ids))
    assert session.search_events[1].first_seen_search == {
        f"doc-{index:02d}": 1 for index in range(10, 15)
    }


def test_search_calls_have_no_retrieval_specific_limit() -> None:
    session, bm25, dense = _session()

    for _ in range(25):
        assert session.search_web("alpha")["status"] == "ok"

    assert session.search_calls == bm25.search_count == dense.search_count == 25


def test_dense_failure_or_non_top10_result_invalidates_without_bm25_fallback() -> None:
    failed, bm25, dense = _session(dense_failure=RuntimeError("endpoint unavailable"))

    with pytest.raises(HybridRetrievalInvalid, match="failed closed"):
        failed.search_web("alpha")

    assert bm25.search_count == dense.search_count == 1
    assert failed.search_events == ()
    assert failed.retrieved_pages == ()
    assert failed.invalid_reason is not None
    with pytest.raises(HybridRetrievalInvalid):
        failed.search_web("alpha")
    assert bm25.search_count == dense.search_count == 1

    short, _bm25, _dense = _session(dense_alpha=RANKINGS["alpha-dense"][:9])
    with pytest.raises(HybridRetrievalInvalid):
        short.search_web("alpha")
    assert short.retrieved_pages == ()


def test_wire_budget_rejects_the_whole_query_without_committing_pages_or_tokens() -> None:
    probe, _bm25, _dense = _session()
    first_response = probe.search_web("alpha")
    exact_first_tokens = len(serialize_full_document_response(first_response))

    rejected, _bm25, _dense = _session(wire_token_budget=exact_first_tokens - 1)
    response = rejected.search_web("alpha")

    assert response == {"status": "context_budget_exhausted", "results": []}
    assert rejected.retrieved_pages == ()
    assert rejected.first_seen_search == {}
    assert rejected.wire_tokens_used == 0
    event = rejected.search_events[0]
    assert event.status == "context_budget_exhausted"
    assert event.returned_page_ids == ()
    assert event.committed_wire_tokens == 0
    assert event.proposed_wire_tokens == exact_first_tokens

    exact, _bm25, _dense = _session(wire_token_budget=exact_first_tokens)
    assert exact.search_web("alpha") == first_response
    assert exact.wire_tokens_used == exact_first_tokens


def test_wire_limit_is_per_response_not_a_cumulative_search_wall() -> None:
    alpha_probe, _bm25, _dense = _session()
    alpha_tokens = len(serialize_full_document_response(alpha_probe.search_web("alpha")))
    beta_probe, _bm25, _dense = _session()
    beta_tokens = len(serialize_full_document_response(beta_probe.search_web("beta")))

    session, _bm25, _dense = _session(wire_token_budget=max(alpha_tokens, beta_tokens))
    assert session.search_web("alpha")["status"] == "ok"
    assert session.search_web("beta")["status"] == "ok"
    assert session.wire_tokens_used == alpha_tokens + beta_tokens
    assert session.wire_tokens_used > session.wire_token_budget
    assert len(session.retrieved_pages) == 25


def test_reset_and_close_clear_every_cell_reference_and_no_open_api_exists() -> None:
    session, _bm25, _dense = _session()
    session.search_web("alpha")

    assert not hasattr(session, "open_page")
    assert not hasattr(session, "open_pages")
    session.reset()
    assert session.search_calls == 0
    assert session.wire_tokens_used == 0
    assert session.search_events == ()
    assert session.retrieved_pages == ()
    assert session.first_seen_search == {}
    assert session.invalid_reason is None
    assert all("content" in item for item in session.search_web("alpha")["results"])

    session.close()
    assert session.closed
    assert session.search_calls == 0
    assert session.wire_tokens_used == 0
    assert session.search_events == ()
    assert session.retrieved_pages == ()
    assert session.first_seen_search == {}
    with pytest.raises(RetrieverClosedError):
        session.search_web("alpha")
    with pytest.raises(RetrieverClosedError):
        session.reset()


def test_bad_token_counter_fails_closed_and_single_response_cap_cannot_be_raised() -> None:
    pages = _pages()
    rankings = {"alpha": RANKINGS["alpha"]}
    bm25 = _StaticIndex(pages, rankings)
    dense = _StaticIndex(pages, rankings)
    session = FullDocumentHybridSession(bm25, dense, lambda _text: True)

    with pytest.raises(HybridRetrievalInvalid):
        session.search_web("alpha")
    assert session.invalid_reason is not None
    assert session.search_events == ()

    with pytest.raises(ValueError, match="65536"):
        FullDocumentHybridSession(bm25, dense, len, wire_token_budget=65_537)
