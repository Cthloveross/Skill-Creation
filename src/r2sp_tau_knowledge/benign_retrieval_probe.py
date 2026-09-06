"""Fixed-query retrieval coverage on verified original benign documents.

The caller supplies an already configured embedding backend, such as
HttpCachedDenseEmbedder. This module owns no service, Agent, compiler, or task
runtime. Reference IDs are evaluation labels and never affect retrieval.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from r2sp_common import Page, tokenize

from .data import SnapshotError, load_documents, verify_tracked_snapshot
from .hybrid_retrieval import (
    DEFAULT_MAX_SEARCHES,
    DEFAULT_RRF_K,
    DEFAULT_TOP_K,
    DenseEmbeddingBackend,
    HybridSessionRetriever,
)
from .records import sha256_json


def _strings(value: Sequence[str], *, name: str, empty_allowed: bool) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence of strings")
    values = tuple(value)
    if (not values and not empty_allowed) or any(
        not isinstance(item, str) or not item.strip() for item in values
    ):
        raise ValueError(f"{name} must contain non-empty strings")
    return values


def _exposure(references: tuple[str, ...], exposed: Sequence[str]) -> dict[str, Any]:
    observed = set(exposed)
    matched = [page_id for page_id in references if page_id in observed]
    return {
        "reference_ids": matched,
        "missing_reference_ids": [page_id for page_id in references if page_id not in observed],
        "count": len(matched),
        "total": len(references),
        "coverage": len(matched) / len(references) if references else None,
    }


def run_retrieval_probe(
    queries: Sequence[str],
    embedder: DenseEmbeddingBackend,
    *,
    reference_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Compare sparse Top-10 and current hybrid exposure for one fixed session.

    All queries are validated before any embedding request. The BM25 baseline
    is the hybrid retriever's unchanged sparse channel over the same original
    corpus and query list, not a reproduction of a historical three-query run.
    The function raises on invalid input, snapshot drift, or embedding failure;
    it does not retry, rewrite queries, select documents, or evaluate utility.
    """
    fixed_queries = _strings(queries, name="queries", empty_allowed=False)
    if len(fixed_queries) > DEFAULT_MAX_SEARCHES:
        raise ValueError(f"queries must contain at most {DEFAULT_MAX_SEARCHES} entries")
    if any(not tokenize(query) for query in fixed_queries):
        raise ValueError("every query must contain searchable tokens")
    references = _strings(reference_ids, name="reference_ids", empty_allowed=True)
    if len(references) != len(set(references)):
        raise ValueError("reference_ids must be unique")

    started = time.monotonic()
    snapshot = verify_tracked_snapshot()
    pages = tuple(Page.from_dict(document.to_page_mapping()) for document in load_documents())
    page_ids = {page.page_id for page in pages}
    if any(page_id not in page_ids for page_id in references):
        raise ValueError("reference_ids must identify original official documents")
    # Bind the exact bytes read for indexing to a verified, unchanged snapshot.
    if verify_tracked_snapshot() != snapshot:
        raise SnapshotError("official snapshot changed while loading retrieval probe input")

    searches: list[dict[str, Any]] = []
    bm25_union: dict[str, None] = {}
    dense_union: dict[str, None] = {}
    shown_union: dict[str, None] = {}
    with HybridSessionRetriever.from_pages(pages, embedder) as session:
        for query in fixed_queries:
            session.search_web(query)
            event = session.search_events[-1]
            bm25_union.update(dict.fromkeys(event.bm25.page_ids))
            dense_union.update(dict.fromkeys(event.dense.page_ids))
            shown_union.update(dict.fromkeys(event.shown_page_ids))
            searches.append(
                {
                    **event.to_dict(),
                    "reference_exposure": {
                        "bm25_top10": _exposure(references, event.bm25.page_ids),
                        "dense_top10": _exposure(references, event.dense.page_ids),
                        "hybrid_newly_shown": _exposure(references, event.shown_page_ids),
                    },
                }
            )

    return {
        "schema_version": "r2sp.benign-retrieval-diagnostic.v1",
        "scope": "benign-only",
        "diagnostic_only": True,
        "agent_run": False,
        "agent_selection_performed": False,
        "official_utility": None,
        "asr": None,
        "queries": list(fixed_queries),
        "queries_sha256": sha256_json(list(fixed_queries)),
        "reference_ids": list(references),
        "snapshot": snapshot,
        "document_count": len(pages),
        "retrieval_contract": {
            "body_only": True,
            "channel_top_k": DEFAULT_TOP_K,
            "max_searches": DEFAULT_MAX_SEARCHES,
            "rrf_k": DEFAULT_RRF_K,
            "max_hybrid_documents_per_query": DEFAULT_TOP_K * 2,
            "max_hybrid_documents_per_session": DEFAULT_TOP_K * 2 * DEFAULT_MAX_SEARCHES,
            "duplicate_backfill": False,
            "selection_performed": False,
            "bm25_baseline": "same-corpus sparse Top-10 for each supplied query",
        },
        "searches": searches,
        "shown_union": list(shown_union),
        "channel_unions": {"bm25": list(bm25_union), "dense": list(dense_union)},
        "reference_exposure": {
            "bm25_top10_union": _exposure(references, list(bm25_union)),
            "dense_top10_union": _exposure(references, list(dense_union)),
            "hybrid_shown_union": _exposure(references, list(shown_union)),
        },
        "duration_seconds": time.monotonic() - started,
        "limitation": (
            "Fixed caller-supplied queries measure retrieval exposure only. The labels never "
            "affect ranking. No Agent generates a query, selects a document, compiles a Skill, "
            "or attempts a task here. Coverage does not establish utility, semantic knowledge "
            "retention, generalization, or a cause of historical model differences."
            " Hybrid can expose up to twenty documents per query versus sparse Top-10; "
            "this is not an equal-candidate-budget effectiveness comparison."
        ),
    }


__all__ = ["run_retrieval_probe"]
