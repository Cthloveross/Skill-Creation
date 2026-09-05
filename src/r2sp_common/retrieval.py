"""Deterministic body-only BM25 and the bounded web-search session adapter."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from typing import Any

from ._canonical import canonical_json_sha256
from .protocol import Page, SearchEvent, SearchHit

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


def tokenize(text: str) -> tuple[str, ...]:
    """Apply the fixed NFKC + casefold + Unicode-word tokenizer."""

    if not isinstance(text, str):
        raise TypeError("tokenize expects str")
    return tuple(_TOKEN_RE.findall(unicodedata.normalize("NFKC", text).casefold()))


def _unique_terms(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tokenize(text)))


class DeterministicBM25:
    """Dependency-free BM25 whose index consists exclusively of page bodies."""

    def __init__(
        self,
        pages: Iterable[Page],
        *,
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        if isinstance(k1, bool) or not isinstance(k1, (int, float)) or k1 <= 0:
            raise ValueError("k1 must be a positive number")
        if isinstance(b, bool) or not isinstance(b, (int, float)) or not 0 <= b <= 1:
            raise ValueError("b must be between zero and one")

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
        self._frequencies = tuple(Counter(tokenize(page.body)) for page in self._pages)
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
