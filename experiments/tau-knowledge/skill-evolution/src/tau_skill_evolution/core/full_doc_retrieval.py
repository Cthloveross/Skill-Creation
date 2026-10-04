"""Fail-closed full-document BM25+dense retrieval for acquisition cells.

A successful search returns the complete RRF union immediately.
Like the upstream tau-Knowledge search tool, every call returns the complete
documents even when a page appeared in an earlier result.  The session keeps a
separate page-ID-deduplicated exposed-document inventory.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .protocol import Page, SearchHit
from .retrieval import (
    HybridRetrievalInvalid,
    InvalidQueryError,
    RetrieverClosedError,
    reciprocal_rank_fusion,
    tokenize,
)


class FullDocumentRankedIndex(Protocol):
    """Minimal interface required from each mandatory retrieval route."""

    @property
    def page_count(self) -> int: ...

    @property
    def corpus_hash(self) -> str: ...

    def search(self, query: str, *, limit: int = 10) -> tuple[SearchHit, ...]: ...

    def get_page(self, page_id: str) -> Page: ...


def serialize_full_document_response(response: Mapping[str, Any]) -> str:
    """Serialize exactly the value supplied to the Qwen wire-token counter.

    The compact UTF-8 JSON representation is stable and contains precisely the
    tool payload returned by :meth:`FullDocumentHybridSession.search_web`.
    Callers can therefore attest the token count independently with the pinned
    Qwen tokenizer.
    """

    if not isinstance(response, Mapping):
        raise TypeError("full-document response must be a mapping")
    try:
        return json.dumps(
            dict(response),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise TypeError("full-document response must be JSON-compatible") from exc


@dataclass(frozen=True, slots=True)
class FullDocumentSearchEvent:
    """Evaluator-only evidence for one completed hybrid search attempt."""

    search_index: int
    query: str
    query_terms: tuple[str, ...]
    bm25_top10: tuple[SearchHit, ...]
    dense_top10: tuple[SearchHit, ...]
    rrf_k: int
    rrf_page_ids: tuple[str, ...]
    new_page_ids: tuple[str, ...]
    repeated_page_ids: tuple[str, ...]
    returned_page_ids: tuple[str, ...]
    first_seen_searches: tuple[tuple[str, int], ...]
    status: str
    proposed_wire_tokens: int
    committed_wire_tokens: int
    cumulative_wire_tokens: int

    VALID_STATUSES = frozenset({"ok", "context_budget_exhausted"})

    def __post_init__(self) -> None:
        if (
            isinstance(self.search_index, bool)
            or not isinstance(self.search_index, int)
            or self.search_index <= 0
        ):
            raise ValueError("search_index must be a positive integer")
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("query must be non-empty")
        if self.status not in self.VALID_STATUSES:
            raise ValueError("invalid full-document search status")
        if self.rrf_k != 60:
            raise ValueError("full-document RRF k must be 60")
        for name in (
            "proposed_wire_tokens",
            "committed_wire_tokens",
            "cumulative_wire_tokens",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.status == "ok":
            if self.returned_page_ids != self.rrf_page_ids:
                raise ValueError("successful search must return its complete RRF union")
            if self.committed_wire_tokens != self.proposed_wire_tokens:
                raise ValueError("successful search must commit its complete wire payload")
        elif self.returned_page_ids or self.first_seen_searches:
            raise ValueError("budget-rejected search cannot return partial results")
        if self.status == "context_budget_exhausted" and self.committed_wire_tokens:
            raise ValueError("budget-rejected search cannot commit wire tokens")

    @property
    def first_seen_search(self) -> dict[str, int]:
        return dict(self.first_seen_searches)

    def to_dict(self) -> dict[str, Any]:
        return {
            "search_index": self.search_index,
            "query": self.query,
            "query_terms": list(self.query_terms),
            "bm25_top10": [hit.to_dict() for hit in self.bm25_top10],
            "dense_top10": [hit.to_dict() for hit in self.dense_top10],
            "rrf_k": self.rrf_k,
            "rrf_page_ids": list(self.rrf_page_ids),
            "new_page_ids": list(self.new_page_ids),
            "repeated_page_ids": list(self.repeated_page_ids),
            "returned_page_ids": list(self.returned_page_ids),
            "first_seen_search": self.first_seen_search,
            "status": self.status,
            "proposed_wire_tokens": self.proposed_wire_tokens,
            "committed_wire_tokens": self.committed_wire_tokens,
            "cumulative_wire_tokens": self.cumulative_wire_tokens,
        }


class FullDocumentHybridSession:
    """An uncapped full-text search session with no open-page phase.

    ``token_counter`` must count the pinned Qwen tokens in the exact string
    produced by :func:`serialize_full_document_response`.  It is injected so
    this dataset-neutral module does not load model weights or tokenizer files.
    ``wire_token_budget`` is an atomic ceiling for one complete response, not a
    cumulative search-call budget.  The caller controls model-context admission
    separately and can freeze collection when the next full context cannot fit.
    """

    INTERNAL_K = 10
    RRF_K = 60
    MAX_WIRE_TOKENS = 65_536

    def __init__(
        self,
        bm25_index: FullDocumentRankedIndex,
        dense_index: FullDocumentRankedIndex,
        token_counter: Callable[[str], int],
        *,
        wire_token_budget: int = MAX_WIRE_TOKENS,
    ) -> None:
        bm25_count, bm25_hash = self._inspect_index("bm25", bm25_index)
        dense_count, dense_hash = self._inspect_index("dense", dense_index)
        if bm25_count < self.INTERNAL_K or dense_count < self.INTERNAL_K:
            raise ValueError("both hybrid indexes require at least ten pages")
        if bm25_count != dense_count:
            raise ValueError("BM25 and dense indexes have different page counts")
        if bm25_hash != dense_hash:
            raise ValueError("BM25 and dense indexes have different corpus hashes")
        if not callable(token_counter):
            raise TypeError("token_counter must be callable")
        if (
            isinstance(wire_token_budget, bool)
            or not isinstance(wire_token_budget, int)
            or not 1 <= wire_token_budget <= self.MAX_WIRE_TOKENS
        ):
            raise ValueError("wire_token_budget must be between one and 65536")

        self._bm25_index: FullDocumentRankedIndex | None = bm25_index
        self._dense_index: FullDocumentRankedIndex | None = dense_index
        self._token_counter: Callable[[str], int] | None = token_counter
        self.wire_token_budget = wire_token_budget
        self._search_calls = 0
        self._wire_tokens_used = 0
        self._events: list[FullDocumentSearchEvent] = []
        self._first_seen_search: dict[str, int] = {}
        self._retrieved_pages: list[Page] = []
        self._invalid_reason: str | None = None

    @staticmethod
    def _inspect_index(name: str, index: object) -> tuple[int, str]:
        try:
            page_count = index.page_count  # type: ignore[attr-defined]
            corpus_hash = index.corpus_hash  # type: ignore[attr-defined]
            search = index.search  # type: ignore[attr-defined]
            get_page = index.get_page  # type: ignore[attr-defined]
        except (AttributeError, TypeError) as exc:
            raise TypeError(f"{name}_index does not implement FullDocumentRankedIndex") from exc
        if (
            isinstance(page_count, bool)
            or not isinstance(page_count, int)
            or page_count <= 0
            or not isinstance(corpus_hash, str)
            or not corpus_hash
            or not callable(search)
            or not callable(get_page)
        ):
            raise TypeError(f"{name}_index does not implement FullDocumentRankedIndex")
        return page_count, corpus_hash

    @property
    def closed(self) -> bool:
        return self._bm25_index is None

    @property
    def invalid_reason(self) -> str | None:
        return self._invalid_reason

    @property
    def search_calls(self) -> int:
        return self._search_calls

    @property
    def wire_tokens_used(self) -> int:
        return self._wire_tokens_used

    @property
    def search_events(self) -> tuple[FullDocumentSearchEvent, ...]:
        return tuple(self._events)

    @property
    def retrieved_pages(self) -> tuple[Page, ...]:
        return tuple(self._retrieved_pages)

    @property
    def retrieved_page_ids(self) -> tuple[str, ...]:
        return tuple(page.page_id for page in self._retrieved_pages)

    @property
    def first_seen_search(self) -> dict[str, int]:
        return dict(self._first_seen_search)

    def _require_open(
        self,
    ) -> tuple[
        FullDocumentRankedIndex,
        FullDocumentRankedIndex,
        Callable[[str], int],
    ]:
        if self._bm25_index is None or self._dense_index is None or self._token_counter is None:
            raise RetrieverClosedError("retrieval session has been closed")
        return self._bm25_index, self._dense_index, self._token_counter

    def _require_valid(self) -> None:
        if self._invalid_reason is not None:
            raise HybridRetrievalInvalid(self._invalid_reason)

    def _invalidate(self) -> HybridRetrievalInvalid:
        self._invalid_reason = f"full-document hybrid search {self._search_calls} failed closed"
        return HybridRetrievalInvalid(self._invalid_reason)

    @classmethod
    def _validate_route(
        cls,
        route: str,
        raw_hits: object,
        route_index: FullDocumentRankedIndex,
        canonical_index: FullDocumentRankedIndex,
    ) -> tuple[SearchHit, ...]:
        try:
            hits = tuple(raw_hits)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TypeError(f"{route} route did not return an iterable ranking") from exc
        if len(hits) != cls.INTERNAL_K:
            raise ValueError(f"{route} route must return exactly ten hits")
        if any(not isinstance(hit, SearchHit) for hit in hits):
            raise TypeError(f"{route} route must return SearchHit values")
        typed_hits = tuple(hits)
        if tuple(hit.rank for hit in typed_hits) != tuple(range(1, cls.INTERNAL_K + 1)):
            raise ValueError(f"{route} route ranks must be contiguous from one through ten")
        page_ids = tuple(hit.page_id for hit in typed_hits)
        if len(page_ids) != len(set(page_ids)):
            raise ValueError(f"{route} route returned duplicate page IDs")
        for hit in typed_hits:
            canonical_page = canonical_index.get_page(hit.page_id)
            route_page = route_index.get_page(hit.page_id)
            if not isinstance(canonical_page, Page) or route_page != canonical_page:
                raise ValueError(f"{route} route page does not match the bound corpus")
            if (
                hit.title != canonical_page.title
                or hit.content_sha256 != canonical_page.content_sha256
            ):
                raise ValueError(f"{route} hit metadata does not match the bound corpus")
        return typed_hits

    @staticmethod
    def _query_terms(query: object) -> tuple[str, ...]:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        terms = tuple(dict.fromkeys(tokenize(query)))
        if not terms:
            raise InvalidQueryError("query must contain at least one Unicode word token")
        return terms

    @staticmethod
    def _count_wire_tokens(token_counter: Callable[[str], int], wire_text: str) -> int:
        observed = token_counter(wire_text)
        if isinstance(observed, bool) or not isinstance(observed, int) or observed <= 0:
            raise TypeError("token_counter must return a positive integer")
        return observed

    def search_web(self, query: str) -> dict[str, Any]:
        """Return one complete hybrid union, or atomically reject it for context budget."""

        bm25_index, dense_index, token_counter = self._require_open()
        self._require_valid()
        # A malformed query, failed route, or failed tokenizer still consumes
        # one search attempt and permanently invalidates the cell.
        self._search_calls += 1
        try:
            query_terms = self._query_terms(query)
            bm25_hits = self._validate_route(
                "bm25",
                bm25_index.search(query, limit=self.INTERNAL_K),
                bm25_index,
                bm25_index,
            )
            dense_hits = self._validate_route(
                "dense",
                dense_index.search(query, limit=self.INTERNAL_K),
                dense_index,
                bm25_index,
            )
            rrf_page_ids = reciprocal_rank_fusion(
                (bm25_hits, dense_hits),
                k=self.RRF_K,
            )

            results: list[dict[str, Any]] = []
            proposed_new_ids: list[str] = []
            repeated_ids: list[str] = []
            first_seen_pairs: list[tuple[str, int]] = []
            proposed_new_pages: list[Page] = []
            for page_id in rrf_page_ids:
                first_seen = self._first_seen_search.get(page_id)
                if first_seen is None:
                    proposed_new_ids.append(page_id)
                else:
                    repeated_ids.append(page_id)
                    first_seen_pairs.append((page_id, first_seen))
                page = bm25_index.get_page(page_id)
                if not isinstance(page, Page):
                    raise TypeError("canonical index get_page must return Page")
                results.append({"page_id": page.page_id, "title": page.title, "content": page.body})
                if first_seen is None:
                    proposed_new_pages.append(page)

            success_response: dict[str, Any] = {"status": "ok", "results": results}
            proposed_wire_tokens = self._count_wire_tokens(
                token_counter,
                serialize_full_document_response(success_response),
            )
        except Exception as exc:
            raise self._invalidate() from exc

        if proposed_wire_tokens > self.wire_token_budget:
            event = FullDocumentSearchEvent(
                search_index=self._search_calls,
                query=query,
                query_terms=query_terms,
                bm25_top10=bm25_hits,
                dense_top10=dense_hits,
                rrf_k=self.RRF_K,
                rrf_page_ids=rrf_page_ids,
                new_page_ids=tuple(proposed_new_ids),
                repeated_page_ids=tuple(repeated_ids),
                returned_page_ids=(),
                first_seen_searches=(),
                status="context_budget_exhausted",
                proposed_wire_tokens=proposed_wire_tokens,
                committed_wire_tokens=0,
                cumulative_wire_tokens=self._wire_tokens_used,
            )
            self._events.append(event)
            return {"status": "context_budget_exhausted", "results": []}

        self._wire_tokens_used += proposed_wire_tokens
        self._first_seen_search.update(
            {page_id: self._search_calls for page_id in proposed_new_ids}
        )
        self._retrieved_pages.extend(proposed_new_pages)
        event = FullDocumentSearchEvent(
            search_index=self._search_calls,
            query=query,
            query_terms=query_terms,
            bm25_top10=bm25_hits,
            dense_top10=dense_hits,
            rrf_k=self.RRF_K,
            rrf_page_ids=rrf_page_ids,
            new_page_ids=tuple(proposed_new_ids),
            repeated_page_ids=tuple(repeated_ids),
            returned_page_ids=rrf_page_ids,
            first_seen_searches=tuple(first_seen_pairs),
            status="ok",
            proposed_wire_tokens=proposed_wire_tokens,
            committed_wire_tokens=proposed_wire_tokens,
            cumulative_wire_tokens=self._wire_tokens_used,
        )
        self._events.append(event)
        return success_response

    def _clear_state(self) -> None:
        self._search_calls = 0
        self._wire_tokens_used = 0
        self._events.clear()
        self._first_seen_search.clear()
        self._retrieved_pages.clear()
        self._invalid_reason = None

    def reset(self) -> None:
        """Clear all cell state while retaining the immutable bound indexes."""

        self._require_open()
        self._clear_state()

    def close(self) -> None:
        """Drop indexes, tokenizer callback, full texts, evidence, and counters."""

        self._bm25_index = None
        self._dense_index = None
        self._token_counter = None
        self._clear_state()

    def __enter__(self) -> FullDocumentHybridSession:
        self._require_open()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


__all__ = [
    "FullDocumentHybridSession",
    "FullDocumentRankedIndex",
    "FullDocumentSearchEvent",
    "serialize_full_document_response",
]
