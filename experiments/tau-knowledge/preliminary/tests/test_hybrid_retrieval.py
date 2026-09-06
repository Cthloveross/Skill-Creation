from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from r2sp_common import (
    DeterministicBM25,
    InvalidQueryError,
    InvalidSelectionError,
    Page,
    RetrieverClosedError,
    SearchBudgetExceeded,
)
from r2sp_tau_knowledge.hybrid_retrieval import (
    BM25_MODEL_ID,
    QWEN3_EMBEDDING_ARTIFACT_SHA256,
    QWEN3_EMBEDDING_MODEL_ID,
    QWEN3_EMBEDDING_REVISION,
    DenseCosineIndex,
    HybridSessionRetriever,
)


class FakePinnedEmbedder:
    """Offline stand-in that makes lexical and semantic ranks easy to audit."""

    model_id = QWEN3_EMBEDDING_MODEL_ID
    revision = QWEN3_EMBEDDING_REVISION
    artifact_sha256: Mapping[str, str] = QWEN3_EMBEDDING_ARTIFACT_SHA256

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if "semantic-group-a" in text:
                vectors.append([20.0, 0.0])
            elif "semantic-group-b" in text:
                vectors.append([0.0, 30.0])
            else:
                vectors.append([-40.0, 0.0])
        return vectors

    def embed_query(self, text: str) -> Sequence[float]:
        if "backend-failure" in text.casefold():
            raise RuntimeError("synthetic embedding outage")
        if "overlap" in text.casefold():
            return [0.0, 70.0]
        if "alpha" in text.casefold():
            return [100.0, 0.0]
        if "beta" in text.casefold():
            return [0.0, 70.0]
        return [-10.0, 0.0]


def _pages() -> tuple[Page, ...]:
    pages: list[Page] = []
    for index in range(30):
        if index < 10:
            # "alpha" occurs only in the title.  Both indexes must ignore it.
            title = f"Alpha title decoy {index:02d}"
            body = f"semantic-group-a generic banking material ordinal-{index:02d}"
        elif index < 20:
            title = f"Neutral document {index:02d}"
            body = f"semantic-group-b alpha lexical banking material ordinal-{index:02d}"
        else:
            title = f"Neutral document {index:02d}"
            body = f"semantic-group-c beta lexical banking material ordinal-{index:02d}"
        pages.append(Page(page_id=f"doc_{index:02d}", title=title, body=body))
    return tuple(pages)


def _session() -> HybridSessionRetriever:
    return HybridSessionRetriever.from_pages(_pages(), FakePinnedEmbedder())


def test_agent_gets_one_rrf_ordered_list_while_evidence_keeps_both_top_tens() -> None:
    session = _session()

    result = session.search_web("alpha")

    assert set(result) == {"results"}
    expected_ids = [
        page_id for rank in range(10) for page_id in (f"doc_{rank:02d}", f"doc_{rank + 10:02d}")
    ]
    assert [item["page_id"] for item in result["results"]] == expected_ids
    assert len(result["results"]) == 20
    assert all(set(item) == {"page_id", "title", "body"} for item in result["results"])
    assert all(item["body"] for item in result["results"])
    serialized_agent_view = repr(result)
    for evaluator_only_name in (
        "channel",
        "rank",
        "score",
        "sha256",
        "correct_answer",
        "required_documents",
    ):
        assert evaluator_only_name not in serialized_agent_view

    event = session.search_events[0]
    assert event.displayed_slot_count == 20
    assert len(event.bm25.top10) == 10
    assert len(event.dense.top10) == 10
    assert [hit.page_id for hit in event.bm25.top10] == [
        f"doc_{index:02d}" for index in range(10, 20)
    ]
    assert [hit.page_id for hit in event.dense.top10] == [f"doc_{index:02d}" for index in range(10)]
    assert event.fused_page_ids == tuple(expected_ids)
    assert event.shown_page_ids == tuple(expected_ids)
    assert event.bm25.model_id == BM25_MODEL_ID
    assert event.dense.model_id == QWEN3_EMBEDDING_MODEL_ID
    assert event.dense.revision == QWEN3_EMBEDDING_REVISION
    assert dict(event.dense.artifact_sha256) == dict(QWEN3_EMBEDDING_ARTIFACT_SHA256)
    assert event.bm25.corpus_sha256 == event.dense.corpus_sha256
    assert len(event.bm25.index_sha256) == 64
    assert len(event.dense.index_sha256) == 64
    # Scores exist only in evaluator evidence and prove raw magnitudes were normalized.
    assert event.dense.top10[0].score == pytest.approx(1.0)
    assert event.to_dict()["rrf_k"] == 60


def test_channel_overlap_is_deduplicated_without_fetching_replacement_hits() -> None:
    session = _session()

    result = session.search_web("alpha overlap")

    expected = [f"doc_{index:02d}" for index in range(10, 20)]
    assert [item["page_id"] for item in result["results"]] == expected
    assert len(result["results"]) == 10
    event = session.search_events[0]
    assert event.bm25.page_ids == tuple(expected)
    assert event.dense.page_ids == tuple(expected)
    assert event.fused_page_ids == tuple(expected)
    assert event.shown_page_ids == tuple(expected)
    assert event.displayed_slot_count == 20
    assert session.exposed_page_ids == frozenset(expected)


def test_two_queries_use_40_raw_slots_but_never_show_a_page_id_twice() -> None:
    session = _session()

    first = session.search_web("alpha")
    second = session.search_web("beta")

    assert session.search_calls == 2
    assert session.displayed_slot_count == 40
    assert len(session.exposed_page_ids) == 30
    first_ids = [item["page_id"] for item in first["results"]]
    second_ids = [item["page_id"] for item in second["results"]]
    assert len(first_ids) == 20
    assert second_ids == [f"doc_{index:02d}" for index in range(20, 30)]
    assert set(first_ids).isdisjoint(second_ids)
    assert session.search_events[1].shown_page_ids == tuple(second_ids)
    with pytest.raises(SearchBudgetExceeded, match="2 calls"):
        session.search_web("gamma")
    assert session.search_calls == 2
    assert session.displayed_slot_count == 40


def test_invalid_query_and_backend_failure_each_consume_one_attempt() -> None:
    invalid = _session()
    with pytest.raises(InvalidQueryError):
        invalid.search_web("   !!!   ")
    assert invalid.search_calls == 1
    assert invalid.search_events == ()
    valid = invalid.search_web("alpha")
    assert len(valid["results"]) == 20
    assert invalid.search_calls == 2
    assert invalid.search_events[0].search_index == 2
    with pytest.raises(SearchBudgetExceeded):
        invalid.search_web("beta")

    failed_backend = _session()
    with pytest.raises(RuntimeError, match="synthetic embedding outage"):
        failed_backend.search_web("backend-failure")
    assert failed_backend.search_calls == 1
    assert failed_backend.search_events == ()
    failed_backend.search_web("alpha")
    assert failed_backend.search_calls == 2
    with pytest.raises(SearchBudgetExceeded):
        failed_backend.search_web("beta")


def test_exact_ten_selection_is_atomic_returns_full_documents_and_closes() -> None:
    session = _session()
    session.search_web("alpha")
    session.search_web("beta")

    with pytest.raises(InvalidSelectionError, match="exactly 10"):
        session.select_docs([f"doc_{index:02d}" for index in range(9)])
    with pytest.raises(InvalidSelectionError, match="exactly 10"):
        session.select_docs(["doc_00"] * 10)
    with pytest.raises(InvalidSelectionError, match="exposed"):
        session.select_docs([*[f"doc_{index:02d}" for index in range(9)], "doc_unseen"])
    assert session.opened_pages == ()
    assert not session.closed
    assert not session.selection_complete
    assert not hasattr(session, "open_page")

    selected_ids = [
        "doc_29",
        "doc_00",
        "doc_19",
        "doc_01",
        "doc_18",
        "doc_02",
        "doc_17",
        "doc_03",
        "doc_16",
        "doc_04",
    ]
    result = session.select_docs(selected_ids)

    assert [document["page_id"] for document in result["documents"]] == selected_ids
    assert all(
        set(document) == {"page_id", "title", "body", "content_sha256"}
        for document in result["documents"]
    )
    assert [page.page_id for page in session.opened_pages] == selected_ids
    assert session.selection_complete
    assert session.closed
    with pytest.raises(RetrieverClosedError):
        session.search_web("alpha")
    with pytest.raises(RetrieverClosedError):
        session.select_docs(selected_ids)


def test_dense_index_is_order_independent_and_breaks_score_ties_by_page_id() -> None:
    pages = _pages()
    forward = DenseCosineIndex(pages, FakePinnedEmbedder())
    reversed_index = DenseCosineIndex(reversed(pages), FakePinnedEmbedder())

    assert forward.corpus_sha256 == reversed_index.corpus_sha256
    assert forward.index_sha256 == reversed_index.index_sha256
    hits = reversed_index.search("alpha", limit=10)
    assert [hit.page_id for hit in hits] == [f"doc_{index:02d}" for index in range(10)]
    assert all(hit.score == pytest.approx(1.0) for hit in hits)


def test_dense_index_rejects_unpinned_model_metadata() -> None:
    class WrongRevisionEmbedder(FakePinnedEmbedder):
        revision = "0" * 40

    with pytest.raises(ValueError, match="dense revision"):
        DenseCosineIndex(_pages(), WrongRevisionEmbedder())


def test_protocol_cardinalities_are_frozen() -> None:
    pages = _pages()
    dense = DenseCosineIndex(pages, FakePinnedEmbedder())
    bm25 = DeterministicBM25(pages)
    with pytest.raises(ValueError, match="top_k is frozen at 10"):
        HybridSessionRetriever(bm25, dense, top_k=9)
    with pytest.raises(ValueError, match="max_searches is frozen at 2"):
        HybridSessionRetriever(bm25, dense, max_searches=3)
    with pytest.raises(ValueError, match="selection_k is frozen at 10"):
        HybridSessionRetriever(bm25, dense, selection_k=9)
