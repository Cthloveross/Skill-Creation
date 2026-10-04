"""Dataset-neutral, serializable acquisition protocol contracts."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from ._canonical import freeze_json, require_sha256, sha256_text, thaw_json


def _required_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class Page:
    """One immutable page; only ``body`` contributes to retrieval scores."""

    page_id: str
    title: str
    body: str
    content_sha256: str | None = None

    def __post_init__(self) -> None:
        _required_text("page_id", self.page_id)
        _required_text("title", self.title)
        if not isinstance(self.body, str) or not self.body.strip():
            raise ValueError("body must be a non-empty string")
        observed = sha256_text(self.body)
        if self.content_sha256 is None:
            object.__setattr__(self, "content_sha256", observed)
        elif require_sha256("content_sha256", self.content_sha256) != observed:
            raise ValueError("content_sha256 does not match the exact UTF-8 body")

    def to_agent_header(self) -> dict[str, str]:
        return {"page_id": self.page_id, "title": self.title}

    def to_open_dict(self) -> dict[str, str]:
        assert self.content_sha256 is not None
        return {
            "page_id": self.page_id,
            "title": self.title,
            "body": self.body,
            "content_sha256": self.content_sha256,
        }

    def to_dict(self) -> dict[str, str]:
        return self.to_open_dict()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Page:
        if not isinstance(value, Mapping):
            raise TypeError("page must be a mapping")
        return cls(
            page_id=value["page_id"],
            title=value["title"],
            body=value["body"],
            content_sha256=value.get("content_sha256"),
        )


@dataclass(frozen=True, slots=True)
class SearchHit:
    """Evaluator-only ranked hit. It intentionally contains no page body."""

    rank: int
    page_id: str
    title: str
    score: float
    content_sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank <= 0:
            raise ValueError("rank must be a positive integer")
        _required_text("page_id", self.page_id)
        _required_text("title", self.title)
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise TypeError("score must be numeric")
        normalized_score = float(self.score)
        if not math.isfinite(normalized_score):
            raise ValueError("score must be finite")
        object.__setattr__(self, "score", 0.0 if normalized_score == 0.0 else normalized_score)
        require_sha256("content_sha256", self.content_sha256)

    def to_agent_dict(self) -> dict[str, str]:
        return {"page_id": self.page_id, "title": self.title}

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "page_id": self.page_id,
            "title": self.title,
            "score": self.score,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SearchHit:
        if not isinstance(value, Mapping):
            raise TypeError("search hit must be a mapping")
        return cls(
            rank=value["rank"],
            page_id=value["page_id"],
            title=value["title"],
            score=value["score"],
            content_sha256=value["content_sha256"],
        )


@dataclass(frozen=True, slots=True)
class SearchEvent:
    """Full evaluator-side evidence for one successful search call."""

    search_index: int
    query: str
    query_terms: tuple[str, ...]
    top10: tuple[SearchHit, ...]
    visible_count: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.search_index, bool)
            or not isinstance(self.search_index, int)
            or self.search_index <= 0
        ):
            raise ValueError("search_index must be a positive integer")
        _required_text("query", self.query)
        terms = tuple(self.query_terms)
        if not terms or any(not isinstance(term, str) or not term for term in terms):
            raise ValueError("query_terms must contain non-empty strings")
        if len(terms) != len(set(terms)):
            raise ValueError("query_terms must not contain duplicates")
        object.__setattr__(self, "query_terms", terms)

        hits = tuple(self.top10)
        if any(not isinstance(hit, SearchHit) for hit in hits):
            raise TypeError("top10 must contain only SearchHit values")
        if [hit.rank for hit in hits] != list(range(1, len(hits) + 1)):
            raise ValueError("top10 ranks must be contiguous and start at one")
        page_ids = [hit.page_id for hit in hits]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("top10 page IDs must be unique")
        object.__setattr__(self, "top10", hits)

        if (
            isinstance(self.visible_count, bool)
            or not isinstance(self.visible_count, int)
            or not 0 <= self.visible_count <= len(hits)
        ):
            raise ValueError("visible_count must be between zero and the hit count")

    @property
    def visible_page_ids(self) -> tuple[str, ...]:
        return tuple(hit.page_id for hit in self.top10[: self.visible_count])

    @property
    def agent_results(self) -> tuple[dict[str, str], ...]:
        return tuple(hit.to_agent_dict() for hit in self.top10[: self.visible_count])

    def to_dict(self) -> dict[str, Any]:
        return {
            "search_index": self.search_index,
            "query": self.query,
            "query_terms": list(self.query_terms),
            "top10": [hit.to_dict() for hit in self.top10],
            "visible_page_ids": list(self.visible_page_ids),
            "visible_count": self.visible_count,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SearchEvent:
        if not isinstance(value, Mapping):
            raise TypeError("search event must be a mapping")
        event = cls(
            search_index=value["search_index"],
            query=value["query"],
            query_terms=tuple(value["query_terms"]),
            top10=tuple(SearchHit.from_dict(hit) for hit in value["top10"]),
            visible_count=value["visible_count"],
        )
        if (
            "visible_page_ids" in value
            and tuple(value["visible_page_ids"]) != event.visible_page_ids
        ):
            raise ValueError("visible_page_ids must be the ranked visible prefix")
        return event


@dataclass(frozen=True, slots=True)
class PageSnippet:
    """A tokenizer-derived page prefix kept separate from the full page body."""

    text: str
    truncated: bool

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text:
            raise ValueError("snippet text must be a non-empty string")
        if not isinstance(self.truncated, bool):
            raise TypeError("snippet truncated must be a boolean")


@dataclass(frozen=True, slots=True)
class HybridCandidate:
    """The complete score-free candidate view exposed to an acquisition agent."""

    page_id: str
    title: str
    snippet: str
    snippet_truncated: bool

    def __post_init__(self) -> None:
        _required_text("page_id", self.page_id)
        _required_text("title", self.title)
        if not isinstance(self.snippet, str) or not self.snippet:
            raise ValueError("snippet must be a non-empty string")
        if not isinstance(self.snippet_truncated, bool):
            raise TypeError("snippet_truncated must be a boolean")

    def to_agent_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "title": self.title,
            "snippet": self.snippet,
            "snippet_truncated": self.snippet_truncated,
        }

    def to_dict(self) -> dict[str, Any]:
        return self.to_agent_dict()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> HybridCandidate:
        if not isinstance(value, Mapping):
            raise TypeError("hybrid candidate must be a mapping")
        return cls(
            page_id=value["page_id"],
            title=value["title"],
            snippet=value["snippet"],
            snippet_truncated=value["snippet_truncated"],
        )


def _validate_ranked_hits(name: str, values: tuple[SearchHit, ...]) -> None:
    if len(values) != 10:
        raise ValueError(f"{name} must contain exactly ten hits")
    if any(not isinstance(hit, SearchHit) for hit in values):
        raise TypeError(f"{name} must contain only SearchHit values")
    if [hit.rank for hit in values] != list(range(1, 11)):
        raise ValueError(f"{name} ranks must be contiguous from one through ten")
    page_ids = [hit.page_id for hit in values]
    if len(page_ids) != len(set(page_ids)):
        raise ValueError(f"{name} page IDs must be unique")


def _rrf_page_ids(
    bm25_top10: tuple[SearchHit, ...],
    dense_top10: tuple[SearchHit, ...],
    *,
    k: int,
) -> tuple[str, ...]:
    scores: dict[str, float] = {}
    for ranking in (bm25_top10, dense_top10):
        for hit in ranking:
            scores[hit.page_id] = scores.get(hit.page_id, 0.0) + 1.0 / (k + hit.rank)
    return tuple(sorted(scores, key=lambda page_id: (-scores[page_id], page_id)))


@dataclass(frozen=True, slots=True)
class HybridSearchEvent:
    """Evaluator-only evidence for one fail-closed BM25+dense search call."""

    search_index: int
    query: str
    query_terms: tuple[str, ...]
    bm25_top10: tuple[SearchHit, ...]
    dense_top10: tuple[SearchHit, ...]
    rrf_k: int
    rrf_page_ids: tuple[str, ...]
    returned_candidates: tuple[HybridCandidate, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.search_index, bool)
            or not isinstance(self.search_index, int)
            or self.search_index <= 0
        ):
            raise ValueError("search_index must be a positive integer")
        _required_text("query", self.query)
        terms = tuple(self.query_terms)
        if not terms or any(not isinstance(term, str) or not term for term in terms):
            raise ValueError("query_terms must contain non-empty strings")
        if len(terms) != len(set(terms)):
            raise ValueError("query_terms must not contain duplicates")
        object.__setattr__(self, "query_terms", terms)

        bm25_hits = tuple(self.bm25_top10)
        dense_hits = tuple(self.dense_top10)
        _validate_ranked_hits("bm25_top10", bm25_hits)
        _validate_ranked_hits("dense_top10", dense_hits)
        object.__setattr__(self, "bm25_top10", bm25_hits)
        object.__setattr__(self, "dense_top10", dense_hits)

        if isinstance(self.rrf_k, bool) or not isinstance(self.rrf_k, int) or self.rrf_k <= 0:
            raise ValueError("rrf_k must be a positive integer")
        rrf_page_ids = tuple(self.rrf_page_ids)
        expected_rrf_page_ids = _rrf_page_ids(bm25_hits, dense_hits, k=self.rrf_k)
        if rrf_page_ids != expected_rrf_page_ids:
            raise ValueError("rrf_page_ids do not match the two complete source rankings")
        object.__setattr__(self, "rrf_page_ids", rrf_page_ids)

        candidates = tuple(self.returned_candidates)
        if any(not isinstance(candidate, HybridCandidate) for candidate in candidates):
            raise TypeError("returned_candidates must contain only HybridCandidate values")
        candidate_ids = tuple(candidate.page_id for candidate in candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("returned candidate page IDs must be unique")
        positions = [rrf_page_ids.index(page_id) for page_id in candidate_ids]
        if positions != sorted(positions):
            raise ValueError("returned candidates must preserve RRF display order")
        object.__setattr__(self, "returned_candidates", candidates)

    @property
    def returned_page_ids(self) -> tuple[str, ...]:
        return tuple(candidate.page_id for candidate in self.returned_candidates)

    @property
    def agent_results(self) -> tuple[dict[str, Any], ...]:
        return tuple(candidate.to_agent_dict() for candidate in self.returned_candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "search_index": self.search_index,
            "query": self.query,
            "query_terms": list(self.query_terms),
            "bm25_top10": [hit.to_dict() for hit in self.bm25_top10],
            "dense_top10": [hit.to_dict() for hit in self.dense_top10],
            "rrf_k": self.rrf_k,
            "rrf_page_ids": list(self.rrf_page_ids),
            "returned_page_ids": list(self.returned_page_ids),
            "returned_candidates": [candidate.to_dict() for candidate in self.returned_candidates],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> HybridSearchEvent:
        if not isinstance(value, Mapping):
            raise TypeError("hybrid search event must be a mapping")
        event = cls(
            search_index=value["search_index"],
            query=value["query"],
            query_terms=tuple(value["query_terms"]),
            bm25_top10=tuple(SearchHit.from_dict(hit) for hit in value["bm25_top10"]),
            dense_top10=tuple(SearchHit.from_dict(hit) for hit in value["dense_top10"]),
            rrf_k=value["rrf_k"],
            rrf_page_ids=tuple(value["rrf_page_ids"]),
            returned_candidates=tuple(
                HybridCandidate.from_dict(candidate) for candidate in value["returned_candidates"]
            ),
        )
        if (
            "returned_page_ids" in value
            and tuple(value["returned_page_ids"]) != event.returned_page_ids
        ):
            raise ValueError("returned_page_ids do not match returned_candidates")
        return event


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """One event that was visible to the deployed or acquisition agent."""

    sequence: int
    actor: str
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    VALID_ACTORS: ClassVar[frozenset[str]] = frozenset(
        {"system", "user", "assistant", "tool", "runtime"}
    )

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError("sequence must be a non-negative integer")
        if self.actor not in self.VALID_ACTORS:
            raise ValueError(f"actor must be one of {sorted(self.VALID_ACTORS)}")
        _required_text("kind", self.kind)
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        object.__setattr__(self, "payload", freeze_json(self.payload))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "actor": self.actor,
            "kind": self.kind,
            "payload": thaw_json(self.payload),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TraceEvent:
        if not isinstance(value, Mapping):
            raise TypeError("trace event must be a mapping")
        return cls(
            sequence=value["sequence"],
            actor=value["actor"],
            kind=value["kind"],
            payload=value.get("payload", {}),
        )


@dataclass(frozen=True, slots=True)
class PublicTrace:
    """Ordered public trajectory, excluding hidden simulator/evaluator state."""

    SCHEMA_VERSION: ClassVar[str] = "r2sp.public-trace.v1"

    events: tuple[TraceEvent, ...] = ()

    def __post_init__(self) -> None:
        events = tuple(self.events)
        if any(not isinstance(event, TraceEvent) for event in events):
            raise TypeError("events must contain only TraceEvent values")
        if [event.sequence for event in events] != list(range(len(events))):
            raise ValueError("trace event sequences must be contiguous and start at zero")
        object.__setattr__(self, "events", events)

    @property
    def first_user_utterance(self) -> str | None:
        for event in self.events:
            content = event.payload.get("content")
            if event.actor == "user" and isinstance(content, str) and content.strip():
                return content
        return None

    def append(self, actor: str, kind: str, payload: Mapping[str, Any]) -> PublicTrace:
        return PublicTrace(self.events + (TraceEvent(len(self.events), actor, kind, payload),))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "events": [event.to_dict() for event in self.events],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PublicTrace:
        if not isinstance(value, Mapping):
            raise TypeError("public trace must be a mapping")
        if value.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported public trace schema_version")
        return cls(tuple(TraceEvent.from_dict(event) for event in value["events"]))
