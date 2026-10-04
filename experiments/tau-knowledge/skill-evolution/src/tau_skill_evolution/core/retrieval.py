"""Deterministic body-only BM25 and the bounded web-search session adapter."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Protocol

from ._canonical import canonical_json_sha256
from .protocol import (
    HybridCandidate,
    HybridSearchEvent,
    Page,
    PageSnippet,
    SearchEvent,
    SearchHit,
)

_TOKEN_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)


class RetrievalError(RuntimeError):
    """Base class for protocol-level retrieval failures."""


class InvalidQueryError(RetrievalError, ValueError):
    """Raised when a query has no searchable tokens."""


class SearchBudgetExceeded(RetrievalError):
    """Raised after the session's final permitted search invocation."""


class OpenBudgetExceeded(RetrievalError):
    """Raised before opening more than the permitted number of unique pages."""


class PageNotExposedError(RetrievalError):
    """Raised when an agent tries to open an ID it was not shown."""


class RetrieverClosedError(RetrievalError):
    """Raised when a destroyed session is reused."""


class HybridRetrievalInvalid(RetrievalError):
    """Raised when either mandatory hybrid route fails or returns invalid evidence."""


class OpenPagesValidationError(RetrievalError, ValueError):
    """Raised when a hybrid full-text selection violates its contract."""


class OpenSelectionRequiredError(RetrievalError):
    """Raised when a new hybrid search is attempted before reading a candidate batch."""


class OpenPagesAlreadyCalledError(RetrievalError):
    """Legacy error retained for replay compatibility with one-shot sessions."""


class SearchAfterOpenError(RetrievalError):
    """Legacy error retained for replay compatibility with one-shot sessions."""


def tokenize(text: str) -> tuple[str, ...]:
    """Apply the fixed NFKC + casefold + Unicode-word tokenizer."""

    if not isinstance(text, str):
        raise TypeError("tokenize expects str")
    return tuple(_TOKEN_RE.findall(unicodedata.normalize("NFKC", text).casefold()))


def _unique_terms(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tokenize(text)))


class DeterministicBM25:
    """Dependency-free BM25 over bodies, optionally prefixed by page titles."""

    def __init__(
        self,
        pages: Iterable[Page],
        *,
        k1: float = 1.2,
        b: float = 0.75,
        include_title: bool = False,
    ) -> None:
        if isinstance(k1, bool) or not isinstance(k1, (int, float)) or k1 <= 0:
            raise ValueError("k1 must be a positive number")
        if isinstance(b, bool) or not isinstance(b, (int, float)) or not 0 <= b <= 1:
            raise ValueError("b must be between zero and one")
        if not isinstance(include_title, bool):
            raise TypeError("include_title must be bool")

        materialized = tuple(pages)
        if not materialized:
            raise ValueError("BM25 requires at least one page")
        if any(not isinstance(page, Page) for page in materialized):
            raise TypeError("pages must contain only Page values")
        page_ids = [page.page_id for page in materialized]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("BM25 pages contain duplicate page_id values")

        self._pages = tuple(sorted(materialized, key=lambda page: page.page_id))
        self._page_by_id = {page.page_id: page for page in self._pages}
        self.k1 = float(k1)
        self.b = float(b)
        self.include_title = include_title
        self._frequencies = tuple(
            Counter(tokenize(f"{page.title}\n\n{page.body}" if include_title else page.body))
            for page in self._pages
        )
        self._lengths = tuple(sum(frequencies.values()) for frequencies in self._frequencies)
        self._average_length = sum(self._lengths) / len(self._lengths)

        document_frequency: Counter[str] = Counter()
        for frequencies in self._frequencies:
            document_frequency.update(frequencies.keys())
        document_count = len(self._pages)
        self._idf = {
            term: math.log(1.0 + (document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }
        self._corpus_hash = canonical_json_sha256(
            [
                {
                    "page_id": page.page_id,
                    "title": page.title,
                    "content_sha256": page.content_sha256,
                }
                for page in self._pages
            ]
        )

    @property
    def page_count(self) -> int:
        return len(self._pages)

    @property
    def corpus_hash(self) -> str:
        return self._corpus_hash

    def _score(self, query_terms: tuple[str, ...], page_index: int) -> float:
        frequencies = self._frequencies[page_index]
        page_length = self._lengths[page_index]
        length_ratio = page_length / self._average_length if self._average_length else 0.0
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            denominator = frequency + self.k1 * (1.0 - self.b + self.b * length_ratio)
            score += self._idf[term] * (frequency * (self.k1 + 1.0)) / denominator
        return score

    def search(self, query: str, *, limit: int = 10) -> tuple[SearchHit, ...]:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        terms = _unique_terms(query)
        if not terms:
            raise InvalidQueryError("query must contain at least one Unicode word token")

        ranked = [(self._score(terms, index), page) for index, page in enumerate(self._pages)]
        ranked.sort(key=lambda item: (-item[0], item[1].page_id))
        return tuple(
            SearchHit(
                rank=rank,
                page_id=page.page_id,
                title=page.title,
                score=score,
                content_sha256=page.content_sha256 or "",
            )
            for rank, (score, page) in enumerate(ranked[:limit], start=1)
        )

    def get_page(self, page_id: str) -> Page:
        if not isinstance(page_id, str) or not page_id.strip():
            raise ValueError("page_id must be a non-empty string")
        try:
            return self._page_by_id[page_id]
        except KeyError as exc:
            raise KeyError(f"unknown page_id: {page_id}") from exc


class SessionWebRetriever:
    """Bounded agent view over a BM25 index with evaluator-only evidence."""

    def __init__(
        self,
        index: DeterministicBM25,
        *,
        internal_k: int = 10,
        visible_k: int = 5,
        max_searches: int = 12,
        max_unique_opens: int = 5,
    ) -> None:
        if not isinstance(index, DeterministicBM25):
            raise TypeError("index must be DeterministicBM25")
        for name, value in (
            ("internal_k", internal_k),
            ("visible_k", visible_k),
            ("max_searches", max_searches),
            ("max_unique_opens", max_unique_opens),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if visible_k > internal_k:
            raise ValueError("visible_k cannot exceed internal_k")

        self._index: DeterministicBM25 | None = index
        self.internal_k = internal_k
        self.visible_k = visible_k
        self.max_searches = max_searches
        self.max_unique_opens = max_unique_opens
        self._search_calls = 0
        self._events: list[SearchEvent] = []
        self._exposed_ids: set[str] = set()
        self._opened_ids: set[str] = set()
        self._opened_pages: list[Page] = []

    @property
    def closed(self) -> bool:
        return self._index is None

    @property
    def search_calls(self) -> int:
        return self._search_calls

    @property
    def search_events(self) -> tuple[SearchEvent, ...]:
        return tuple(self._events)

    @property
    def exposed_page_ids(self) -> frozenset[str]:
        return frozenset(self._exposed_ids)

    @property
    def opened_pages(self) -> tuple[Page, ...]:
        return tuple(self._opened_pages)

    def _require_open(self) -> DeterministicBM25:
        if self._index is None:
            raise RetrieverClosedError("retrieval session has been closed")
        return self._index

    def search_web(self, query: str) -> dict[str, list[dict[str, str]]]:
        index = self._require_open()
        if self._search_calls >= self.max_searches:
            raise SearchBudgetExceeded(f"search budget exhausted at {self.max_searches} calls")
        # Every invocation consumes budget, including a malformed/tokenless query.
        self._search_calls += 1
        hits = index.search(query, limit=self.internal_k)
        event = SearchEvent(
            search_index=self._search_calls,
            query=query,
            query_terms=_unique_terms(query),
            top10=hits,
            visible_count=min(self.visible_k, len(hits)),
        )
        self._events.append(event)
        self._exposed_ids.update(event.visible_page_ids)
        return {"results": [dict(result) for result in event.agent_results]}

    def open_page(self, page_id: str) -> dict[str, str]:
        index = self._require_open()
        if not isinstance(page_id, str) or not page_id.strip():
            raise PageNotExposedError("page_id was not exposed by search_web")
        if page_id not in self._exposed_ids:
            # Unknown and merely unexposed IDs deliberately have the same error.
            raise PageNotExposedError("page_id was not exposed by search_web")
        if page_id not in self._opened_ids:
            if len(self._opened_ids) >= self.max_unique_opens:
                raise OpenBudgetExceeded(
                    f"unique open budget exhausted at {self.max_unique_opens} pages"
                )
            page = index.get_page(page_id)
            self._opened_ids.add(page_id)
            self._opened_pages.append(page)
        else:
            page = index.get_page(page_id)
        return page.to_open_dict()

    def close(self) -> None:
        """Drop every session-held corpus, trace, authorization, and open-page reference."""

        self._index = None
        self._search_calls = 0
        self._events.clear()
        self._exposed_ids.clear()
        self._opened_ids.clear()
        self._opened_pages.clear()

    def __enter__(self) -> SessionWebRetriever:
        self._require_open()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


class RankedPageIndex(Protocol):
    """Structural contract shared by the mandatory BM25 and dense indexes."""

    @property
    def page_count(self) -> int: ...

    @property
    def corpus_hash(self) -> str: ...

    def search(self, query: str, *, limit: int = 10) -> tuple[SearchHit, ...]: ...

    def get_page(self, page_id: str) -> Page: ...


def reciprocal_rank_fusion(
    rankings: Iterable[Sequence[SearchHit]],
    *,
    k: int = 60,
) -> tuple[str, ...]:
    """Return every unique page ID ordered by deterministic reciprocal-rank fusion."""

    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")
    materialized = tuple(tuple(ranking) for ranking in rankings)
    if not materialized:
        raise ValueError("rankings must not be empty")
    scores: dict[str, float] = {}
    for ranking in materialized:
        page_ids: set[str] = set()
        for hit in ranking:
            if not isinstance(hit, SearchHit):
                raise TypeError("rankings must contain only SearchHit values")
            if hit.page_id in page_ids:
                raise ValueError("each source ranking must contain unique page IDs")
            page_ids.add(hit.page_id)
            scores[hit.page_id] = scores.get(hit.page_id, 0.0) + 1.0 / (k + hit.rank)
    return tuple(sorted(scores, key=lambda page_id: (-scores[page_id], page_id)))


class HybridSessionWebRetriever:
    """Bounded multi-round, fail-closed BM25+dense acquisition session.

    Each successful search exposes the full deduplicated union of both ten-result
    routes for that query. Scores, source labels, and ranks remain evaluator-only.
    Search and full-text selection may be interleaved throughout a progressive
    dialogue. Each successful ``open_pages`` call returns every newly selected
    page in full; the session retains the cumulative unique read set.
    """

    INTERNAL_K = 10
    MAX_SEARCHES = 10
    MAX_OPEN_BATCHES = 10
    MAX_UNIQUE_OPENS = 30
    RRF_K = 60

    def __init__(
        self,
        bm25_index: DeterministicBM25,
        dense_index: RankedPageIndex,
        snippet_provider: Callable[[Page], PageSnippet],
        *,
        max_searches: int = MAX_SEARCHES,
        max_open_batches: int = MAX_OPEN_BATCHES,
        max_unique_opens: int = MAX_UNIQUE_OPENS,
    ) -> None:
        if not isinstance(bm25_index, DeterministicBM25):
            raise TypeError("bm25_index must be DeterministicBM25")
        if not callable(snippet_provider):
            raise TypeError("snippet_provider must be callable")
        try:
            dense_page_count = dense_index.page_count
            dense_corpus_hash = dense_index.corpus_hash
            dense_search = dense_index.search
            dense_get_page = dense_index.get_page
        except (AttributeError, TypeError) as exc:
            raise TypeError("dense_index does not implement RankedPageIndex") from exc
        if not callable(dense_search) or not callable(dense_get_page):
            raise TypeError("dense_index does not implement RankedPageIndex")
        if bm25_index.page_count < self.INTERNAL_K or dense_page_count < self.INTERNAL_K:
            raise ValueError("both hybrid indexes require at least ten pages")
        if bm25_index.page_count != dense_page_count:
            raise ValueError("BM25 and dense indexes have different page counts")
        if bm25_index.corpus_hash != dense_corpus_hash:
            raise ValueError("BM25 and dense indexes have different corpus hashes")
        for name, value in (
            ("max_searches", max_searches),
            ("max_open_batches", max_open_batches),
            ("max_unique_opens", max_unique_opens),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

        self._bm25_index: DeterministicBM25 | None = bm25_index
        self._dense_index: RankedPageIndex | None = dense_index
        self._snippet_provider: Callable[[Page], PageSnippet] | None = snippet_provider
        self.max_searches = max_searches
        self.max_open_batches = max_open_batches
        self.max_unique_opens = max_unique_opens
        self._search_calls = 0
        self._open_calls = 0
        self._events: list[HybridSearchEvent] = []
        self._exposed_ids: set[str] = set()
        self._opened_ids: set[str] = set()
        self._opened_pages: list[Page] = []
        self._opened_page_batches: list[tuple[str, ...]] = []
        self._open_selection_required = False
        self._invalid_reason: str | None = None

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
    def open_calls(self) -> int:
        return self._open_calls

    @property
    def search_events(self) -> tuple[HybridSearchEvent, ...]:
        return tuple(self._events)

    @property
    def exposed_page_ids(self) -> frozenset[str]:
        return frozenset(self._exposed_ids)

    @property
    def opened_pages(self) -> tuple[Page, ...]:
        return tuple(self._opened_pages)

    @property
    def opened_page_batches(self) -> tuple[tuple[str, ...], ...]:
        return tuple(self._opened_page_batches)

    @property
    def open_selection_required(self) -> bool:
        return self._open_selection_required

    def _require_open(
        self,
    ) -> tuple[DeterministicBM25, RankedPageIndex, Callable[[Page], PageSnippet]]:
        if self._bm25_index is None or self._dense_index is None or self._snippet_provider is None:
            raise RetrieverClosedError("retrieval session has been closed")
        return self._bm25_index, self._dense_index, self._snippet_provider

    def _require_valid(self) -> None:
        if self._invalid_reason is not None:
            raise HybridRetrievalInvalid(self._invalid_reason)

    def _invalidate(self, reason: str) -> HybridRetrievalInvalid:
        self._invalid_reason = reason
        return HybridRetrievalInvalid(reason)

    @staticmethod
    def _validate_route(
        route: str,
        hits: object,
        route_index: RankedPageIndex,
        canonical_index: DeterministicBM25,
    ) -> tuple[SearchHit, ...]:
        try:
            materialized = tuple(hits)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TypeError(f"{route} route did not return an iterable ranking") from exc
        if len(materialized) != HybridSessionWebRetriever.INTERNAL_K:
            raise ValueError(f"{route} route must return exactly ten hits")
        if any(not isinstance(hit, SearchHit) for hit in materialized):
            raise TypeError(f"{route} route must return SearchHit values")
        typed_hits = tuple(materialized)
        if [hit.rank for hit in typed_hits] != list(range(1, 11)):
            raise ValueError(f"{route} route ranks must be contiguous from one through ten")
        page_ids = [hit.page_id for hit in typed_hits]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError(f"{route} route returned duplicate page IDs")
        for hit in typed_hits:
            canonical_page = canonical_index.get_page(hit.page_id)
            route_page = route_index.get_page(hit.page_id)
            if route_page != canonical_page:
                raise ValueError(f"{route} route page does not match the bound corpus")
            if (
                hit.title != canonical_page.title
                or hit.content_sha256 != canonical_page.content_sha256
            ):
                raise ValueError(f"{route} hit metadata does not match the bound corpus")
        return typed_hits

    def search_web(self, query: str) -> dict[str, list[dict[str, Any]]]:
        bm25_index, dense_index, snippet_provider = self._require_open()
        self._require_valid()
        if self._open_selection_required:
            raise OpenSelectionRequiredError(
                "open_pages must read at least one exposed candidate before another search"
            )
        if self._search_calls >= self.max_searches:
            raise SearchBudgetExceeded(f"search budget exhausted at {self.max_searches} calls")

        # Every invocation consumes budget, including a malformed query or route failure.
        self._search_calls += 1
        try:
            query_terms = _unique_terms(query)
            if not query_terms:
                raise InvalidQueryError("query must contain at least one Unicode word token")
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
            returned_candidates: list[HybridCandidate] = []
            for page_id in rrf_page_ids:
                page = bm25_index.get_page(page_id)
                snippet = snippet_provider(page)
                if not isinstance(snippet, PageSnippet):
                    raise TypeError("snippet_provider must return PageSnippet")
                returned_candidates.append(
                    HybridCandidate(
                        page_id=page.page_id,
                        title=page.title,
                        snippet=snippet.text,
                        snippet_truncated=snippet.truncated,
                    )
                )
            event = HybridSearchEvent(
                search_index=self._search_calls,
                query=query,
                query_terms=query_terms,
                bm25_top10=bm25_hits,
                dense_top10=dense_hits,
                rrf_k=self.RRF_K,
                rrf_page_ids=rrf_page_ids,
                returned_candidates=tuple(returned_candidates),
            )
        except Exception as exc:
            reason = f"hybrid search {self._search_calls} failed closed"
            raise self._invalidate(reason) from exc

        self._events.append(event)
        self._exposed_ids.update(event.returned_page_ids)
        self._open_selection_required = any(
            candidate.page_id not in self._opened_ids for candidate in event.returned_candidates
        )
        return {"results": [dict(candidate) for candidate in event.agent_results]}

    def open_pages(self, page_ids: Iterable[str]) -> dict[str, list[dict[str, str]]]:
        bm25_index, _dense_index, _snippet_provider = self._require_open()
        self._require_valid()
        if self._open_calls >= self.max_open_batches:
            raise OpenBudgetExceeded(
                f"open-pages batch budget exhausted at {self.max_open_batches} calls"
            )

        # Malformed model arguments and budget errors are recoverable and do not
        # consume a successful batch. Infrastructure/corpus failures still fail closed.
        try:
            if isinstance(page_ids, (str, bytes)):
                raise OpenPagesValidationError("page_ids must be a non-empty iterable of IDs")
            submitted_ids = tuple(page_ids)
            if not submitted_ids:
                raise OpenPagesValidationError("open_pages requires at least one page ID")
            if any(
                not isinstance(page_id, str) or not page_id.strip() for page_id in submitted_ids
            ):
                raise OpenPagesValidationError("every page_id must be a non-empty string")
            if len(submitted_ids) != len(set(submitted_ids)):
                raise OpenPagesValidationError("open_pages requires unique page IDs")
            if any(page_id not in self._exposed_ids for page_id in submitted_ids):
                raise OpenPagesValidationError("open_pages accepts only IDs exposed by search_web")
            if any(page_id in self._opened_ids for page_id in submitted_ids):
                raise OpenPagesValidationError("open_pages accepts only not-yet-opened page IDs")
            if len(self._opened_ids) + len(submitted_ids) > self.max_unique_opens:
                raise OpenBudgetExceeded(
                    f"unique open budget exhausted at {self.max_unique_opens} pages"
                )
            pages = tuple(bm25_index.get_page(page_id) for page_id in submitted_ids)
        except Exception as exc:
            if isinstance(exc, (OpenBudgetExceeded, OpenPagesValidationError)):
                raise
            error = OpenPagesValidationError("open_pages failed closed")
            self._invalid_reason = str(error)
            raise error from exc

        self._open_calls += 1
        self._opened_ids.update(submitted_ids)
        self._opened_pages.extend(pages)
        self._opened_page_batches.append(submitted_ids)
        self._open_selection_required = False
        return {"pages": [page.to_open_dict() for page in pages]}

    def close(self) -> None:
        """Drop indexes, snippets, evidence, authorization, and selected full text."""

        self._bm25_index = None
        self._dense_index = None
        self._snippet_provider = None
        self._search_calls = 0
        self._open_calls = 0
        self._events.clear()
        self._exposed_ids.clear()
        self._opened_ids.clear()
        self._opened_pages.clear()
        self._opened_page_batches.clear()
        self._open_selection_required = False
        self._invalid_reason = None

    def __enter__(self) -> HybridSessionWebRetriever:
        self._require_open()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()
