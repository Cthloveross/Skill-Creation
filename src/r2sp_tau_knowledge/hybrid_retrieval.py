"""Deterministic hybrid retrieval for the tau-Knowledge experiment.

Each search internally takes the body-only BM25 Top10 and normalized dense
cosine Top10, merges duplicate IDs with reciprocal-rank fusion (``k=60``),
and shows the agent one score-free list of complete pages.  IDs already shown
by an earlier query are omitted and neither channel is searched past rank 10
to replace them.  Ranked channel evidence, RRF scores, and reproducibility
metadata remain evaluator-only.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Protocol

from r2sp_common import (
    DeterministicBM25,
    InvalidQueryError,
    InvalidSelectionError,
    Page,
    RetrieverClosedError,
    SearchBudgetExceeded,
    SearchHit,
    tokenize,
)
from r2sp_common._canonical import canonical_json_sha256, require_sha256

QWEN3_EMBEDDING_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
QWEN3_EMBEDDING_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
QWEN3_EMBEDDING_MODEL_SIZE_BYTES = 1_191_586_416
QWEN3_EMBEDDING_ARTIFACT_SHA256: Mapping[str, str] = MappingProxyType(
    {
        "config.json": "b5bf1f51fc45be473a54718cef92448d90a1be001bf9b9a44b8c7f10a19feaa9",
        "model.safetensors": ("0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd"),
        "tokenizer.json": ("def76fb086971c7867b829c23a26261e38d9d74e02139253b38aeb9df8b4b50a"),
        "tokenizer_config.json": (
            "253153d0738ceb4c668d2eff957714dd2bea0b56de772a9fdccd96cbf517e6a0"
        ),
    }
)

BM25_CHANNEL = "bm25"
DENSE_CHANNEL = "dense"
BM25_MODEL_ID = "r2sp_common.DeterministicBM25"
BM25_REVISION = "body-only-nfkc-casefold-unicode-v1"
DEFAULT_TOP_K = 10
DEFAULT_MAX_SEARCHES = 2
DEFAULT_SELECTION_K = 10
DEFAULT_RRF_K = 60


class DenseEmbeddingBackend(Protocol):
    """Pinned backend interface; implementations may be local or remote."""

    model_id: str
    revision: str
    artifact_sha256: Mapping[str, str]

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one vector for each document body, in input order."""

    def embed_query(self, text: str) -> Sequence[float]:
        """Return the query vector produced by the pinned model."""


def _require_positive_integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _normalize_vector(
    value: Sequence[float],
    *,
    name: str,
    expected_dimension: int | None = None,
) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be a sequence of finite numbers")
    vector: list[float] = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise TypeError(f"{name} must contain only finite numbers")
        number = float(component)
        if not math.isfinite(number):
            raise ValueError(f"{name} must contain only finite numbers")
        vector.append(number)
    if not vector:
        raise ValueError(f"{name} must not be empty")
    if expected_dimension is not None and len(vector) != expected_dimension:
        raise ValueError(f"{name} has dimension {len(vector)}; expected {expected_dimension}")
    norm = math.sqrt(math.fsum(component * component for component in vector))
    if not math.isfinite(norm) or norm == 0.0:
        raise ValueError(f"{name} must have a finite, non-zero norm")
    return tuple(
        0.0 if (normalized := component / norm) == 0.0 else normalized for component in vector
    )


def _corpus_sha256(pages: Sequence[Page]) -> str:
    return canonical_json_sha256(
        [
            {
                "page_id": page.page_id,
                "title": page.title,
                "content_sha256": page.content_sha256,
            }
            for page in pages
        ]
    )


@dataclass(frozen=True, slots=True)
class RetrievalChannelRecord:
    """Evaluator-only evidence for one ranked channel in one search."""

    channel: Literal["bm25", "dense"]
    model_id: str
    revision: str
    index_sha256: str
    corpus_sha256: str
    artifact_sha256: tuple[tuple[str, str], ...]
    top10: tuple[SearchHit, ...]

    def __post_init__(self) -> None:
        if self.channel not in {BM25_CHANNEL, DENSE_CHANNEL}:
            raise ValueError("channel must be 'bm25' or 'dense'")
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be a non-empty string")
        if not isinstance(self.revision, str) or not self.revision.strip():
            raise ValueError("revision must be a non-empty string")
        require_sha256("index_sha256", self.index_sha256)
        require_sha256("corpus_sha256", self.corpus_sha256)
        artifacts = tuple(self.artifact_sha256)
        if any(
            not isinstance(name, str) or not name or not isinstance(digest, str)
            for name, digest in artifacts
        ):
            raise ValueError("artifact_sha256 must contain non-empty file names and digests")
        if tuple(sorted(artifacts)) != artifacts or len(dict(artifacts)) != len(artifacts):
            raise ValueError("artifact_sha256 must be uniquely keyed and sorted")
        for name, digest in artifacts:
            require_sha256(f"artifact_sha256[{name}]", digest)
        object.__setattr__(self, "artifact_sha256", artifacts)

        hits = tuple(self.top10)
        if any(not isinstance(hit, SearchHit) for hit in hits):
            raise TypeError("top10 must contain only SearchHit values")
        if [hit.rank for hit in hits] != list(range(1, len(hits) + 1)):
            raise ValueError("top10 ranks must be contiguous and start at one")
        if len({hit.page_id for hit in hits}) != len(hits):
            raise ValueError("top10 page IDs must be unique within a channel")
        object.__setattr__(self, "top10", hits)

    @property
    def page_ids(self) -> tuple[str, ...]:
        return tuple(hit.page_id for hit in self.top10)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "model_id": self.model_id,
            "revision": self.revision,
            "index_sha256": self.index_sha256,
            "corpus_sha256": self.corpus_sha256,
            "artifact_sha256": dict(self.artifact_sha256),
            "top10": [hit.to_dict() for hit in self.top10],
        }


@dataclass(frozen=True, slots=True)
class HybridSearchEvent:
    """Evaluator-only record of one successful two-channel search."""

    search_index: int
    query: str
    query_terms: tuple[str, ...]
    bm25: RetrievalChannelRecord
    dense: RetrievalChannelRecord
    fused: tuple[tuple[str, float], ...]
    shown_page_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_positive_integer("search_index", self.search_index)
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("query must be a non-empty string")
        terms = tuple(self.query_terms)
        if not terms or any(not isinstance(term, str) or not term for term in terms):
            raise ValueError("query_terms must contain non-empty strings")
        if len(set(terms)) != len(terms):
            raise ValueError("query_terms must be unique")
        object.__setattr__(self, "query_terms", terms)
        if self.bm25.channel != BM25_CHANNEL or self.dense.channel != DENSE_CHANNEL:
            raise ValueError("hybrid event channels are out of order")
        if self.bm25.corpus_sha256 != self.dense.corpus_sha256:
            raise ValueError("hybrid event channels must use the same corpus")
        fused = tuple(self.fused)
        fused_ids = [page_id for page_id, _score in fused]
        expected_scores: dict[str, float] = {}
        for channel in (self.bm25, self.dense):
            for hit in channel.top10:
                expected_scores[hit.page_id] = expected_scores.get(hit.page_id, 0.0) + (
                    1.0 / (DEFAULT_RRF_K + hit.rank)
                )
        expected_fused = tuple(
            sorted(expected_scores.items(), key=lambda item: (-item[1], item[0]))
        )
        if len(fused_ids) != len(set(fused_ids)) or fused_ids != [
            page_id for page_id, _score in expected_fused
        ]:
            raise ValueError("fused ranking must contain the channel union exactly once")
        if any(
            not math.isclose(score, expected_score, rel_tol=0.0, abs_tol=1e-15)
            for (_page_id, score), (_expected_page_id, expected_score) in zip(
                fused, expected_fused, strict=True
            )
        ):
            raise ValueError("fused RRF scores do not match the recorded channel ranks")
        shown = tuple(self.shown_page_ids)
        if len(shown) != len(set(shown)) or any(page_id not in fused_ids for page_id in shown):
            raise ValueError("shown_page_ids must be a unique fused-ranking subset")
        shown_set = set(shown)
        if shown != tuple(page_id for page_id in fused_ids if page_id in shown_set):
            raise ValueError("shown_page_ids must preserve fused rank order")
        object.__setattr__(self, "fused", fused)
        object.__setattr__(self, "shown_page_ids", shown)

    @property
    def displayed_slot_count(self) -> int:
        """Raw channel slots consumed before cross-channel de-duplication."""

        return len(self.bm25.top10) + len(self.dense.top10)

    @property
    def exposed_page_ids(self) -> frozenset[str]:
        return frozenset(self.shown_page_ids)

    @property
    def fused_page_ids(self) -> tuple[str, ...]:
        return tuple(page_id for page_id, _score in self.fused)

    def to_dict(self) -> dict[str, Any]:
        return {
            "search_index": self.search_index,
            "query": self.query,
            "query_terms": list(self.query_terms),
            "displayed_slot_count": self.displayed_slot_count,
            "channels": [self.bm25.to_dict(), self.dense.to_dict()],
            "rrf_k": DEFAULT_RRF_K,
            "fused": [
                {"rank": rank, "page_id": page_id, "score": score}
                for rank, (page_id, score) in enumerate(self.fused, start=1)
            ],
            "shown_page_ids": list(self.shown_page_ids),
        }


class DenseCosineIndex:
    """Exact body-only cosine index backed by the pinned Qwen3 embedder."""

    def __init__(
        self,
        pages: Iterable[Page],
        embedder: DenseEmbeddingBackend,
    ) -> None:
        materialized = tuple(pages)
        if not materialized:
            raise ValueError("dense index requires at least one page")
        if any(not isinstance(page, Page) for page in materialized):
            raise TypeError("pages must contain only Page values")
        page_ids = [page.page_id for page in materialized]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("dense index pages contain duplicate page_id values")
        self._require_pinned_embedder(embedder)

        self._pages = tuple(sorted(materialized, key=lambda page: page.page_id))
        self._page_by_id = {page.page_id: page for page in self._pages}
        self._embedder = embedder
        raw_vectors = tuple(embedder.embed_documents([page.body for page in self._pages]))
        if len(raw_vectors) != len(self._pages):
            raise ValueError("embed_documents must return one vector per page body")
        first = _normalize_vector(raw_vectors[0], name="document embedding 0")
        vectors = [first]
        for index, raw_vector in enumerate(raw_vectors[1:], start=1):
            vectors.append(
                _normalize_vector(
                    raw_vector,
                    name=f"document embedding {index}",
                    expected_dimension=len(first),
                )
            )
        self._vectors = tuple(vectors)
        self._dimension = len(first)
        self._corpus_sha256 = _corpus_sha256(self._pages)
        self._index_sha256 = canonical_json_sha256(
            {
                "algorithm": "exact-normalized-cosine-body-only-v1",
                "artifact_sha256": dict(QWEN3_EMBEDDING_ARTIFACT_SHA256),
                "corpus_sha256": self._corpus_sha256,
                "dimension": self._dimension,
                "model_id": QWEN3_EMBEDDING_MODEL_ID,
                "revision": QWEN3_EMBEDDING_REVISION,
                "vectors": [
                    {"page_id": page.page_id, "values": list(vector)}
                    for page, vector in zip(self._pages, self._vectors, strict=True)
                ],
            }
        )

    @staticmethod
    def _require_pinned_embedder(embedder: DenseEmbeddingBackend) -> None:
        if getattr(embedder, "model_id", None) != QWEN3_EMBEDDING_MODEL_ID:
            raise ValueError(f"dense model must be {QWEN3_EMBEDDING_MODEL_ID}")
        if getattr(embedder, "revision", None) != QWEN3_EMBEDDING_REVISION:
            raise ValueError(f"dense revision must be {QWEN3_EMBEDDING_REVISION}")
        observed = getattr(embedder, "artifact_sha256", None)
        if not isinstance(observed, Mapping) or dict(observed) != dict(
            QWEN3_EMBEDDING_ARTIFACT_SHA256
        ):
            raise ValueError("dense model artifact SHA-256 commitments do not match")
        if not callable(getattr(embedder, "embed_documents", None)) or not callable(
            getattr(embedder, "embed_query", None)
        ):
            raise TypeError("embedder must implement embed_documents and embed_query")

    @property
    def page_count(self) -> int:
        return len(self._pages)

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def corpus_sha256(self) -> str:
        return self._corpus_sha256

    @property
    def index_sha256(self) -> str:
        return self._index_sha256

    def search(self, query: str, *, limit: int = DEFAULT_TOP_K) -> tuple[SearchHit, ...]:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        _require_positive_integer("limit", limit)
        if not tokenize(query):
            raise InvalidQueryError("query must contain at least one Unicode word token")
        query_vector = _normalize_vector(
            self._embedder.embed_query(query),
            name="query embedding",
            expected_dimension=self._dimension,
        )
        ranked = [
            (
                math.fsum(left * right for left, right in zip(query_vector, vector, strict=True)),
                page,
            )
            for page, vector in zip(self._pages, self._vectors, strict=True)
        ]
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


class HybridSessionRetriever:
    """Two-attempt hybrid search view with one exact cumulative selection."""

    def __init__(
        self,
        bm25_index: DeterministicBM25,
        dense_index: DenseCosineIndex,
        *,
        top_k: int = DEFAULT_TOP_K,
        max_searches: int = DEFAULT_MAX_SEARCHES,
        selection_k: int = DEFAULT_SELECTION_K,
    ) -> None:
        if not isinstance(bm25_index, DeterministicBM25):
            raise TypeError("bm25_index must be DeterministicBM25")
        if not isinstance(dense_index, DenseCosineIndex):
            raise TypeError("dense_index must be DenseCosineIndex")
        _require_positive_integer("top_k", top_k)
        _require_positive_integer("max_searches", max_searches)
        _require_positive_integer("selection_k", selection_k)
        if top_k != DEFAULT_TOP_K:
            raise ValueError(f"top_k is frozen at {DEFAULT_TOP_K}")
        if max_searches != DEFAULT_MAX_SEARCHES:
            raise ValueError(f"max_searches is frozen at {DEFAULT_MAX_SEARCHES}")
        if selection_k != DEFAULT_SELECTION_K:
            raise ValueError(f"selection_k is frozen at {DEFAULT_SELECTION_K}")
        if bm25_index.page_count < DEFAULT_TOP_K or dense_index.page_count < DEFAULT_TOP_K:
            raise ValueError("hybrid retrieval requires at least 10 corpus pages")
        if bm25_index.corpus_hash != dense_index.corpus_sha256:
            raise ValueError("BM25 and dense indexes must use the exact same corpus")

        self._bm25: DeterministicBM25 | None = bm25_index
        self._dense: DenseCosineIndex | None = dense_index
        self.top_k = top_k
        self.max_searches = max_searches
        self.selection_k = selection_k
        self._events: list[HybridSearchEvent] = []
        self._search_attempts = 0
        self._exposed_ids: set[str] = set()
        self._opened_pages: list[Page] = []
        self._selection_complete = False
        self._bm25_index_sha256 = canonical_json_sha256(
            {
                "algorithm": "r2sp-common-deterministic-bm25-body-only-v1",
                "b": bm25_index.b,
                "corpus_sha256": bm25_index.corpus_hash,
                "k1": bm25_index.k1,
            }
        )

    @classmethod
    def from_pages(
        cls,
        pages: Iterable[Page],
        embedder: DenseEmbeddingBackend,
        **kwargs: int,
    ) -> HybridSessionRetriever:
        materialized = tuple(pages)
        return cls(
            DeterministicBM25(materialized),
            DenseCosineIndex(materialized, embedder),
            **kwargs,
        )

    @property
    def closed(self) -> bool:
        return self._bm25 is None or self._dense is None

    @property
    def search_calls(self) -> int:
        """Number of invocations, including malformed queries and backend failures."""

        return self._search_attempts

    @property
    def search_events(self) -> tuple[HybridSearchEvent, ...]:
        return tuple(self._events)

    @property
    def exposed_page_ids(self) -> frozenset[str]:
        return frozenset(self._exposed_ids)

    @property
    def displayed_slot_count(self) -> int:
        return sum(event.displayed_slot_count for event in self._events)

    @property
    def opened_pages(self) -> tuple[Page, ...]:
        return tuple(self._opened_pages)

    @property
    def selection_complete(self) -> bool:
        return self._selection_complete

    def _require_open(self) -> tuple[DeterministicBM25, DenseCosineIndex]:
        if self._bm25 is None or self._dense is None:
            raise RetrieverClosedError("retrieval session has been closed")
        return self._bm25, self._dense

    @staticmethod
    def _fuse(
        bm25_hits: Sequence[SearchHit], dense_hits: Sequence[SearchHit]
    ) -> tuple[tuple[str, float], ...]:
        scores: dict[str, float] = {}
        for hits in (bm25_hits, dense_hits):
            for hit in hits:
                scores[hit.page_id] = scores.get(hit.page_id, 0.0) + 1.0 / (
                    DEFAULT_RRF_K + hit.rank
                )
        return tuple(sorted(scores.items(), key=lambda item: (-item[1], item[0])))

    def search_web(self, query: str) -> dict[str, list[dict[str, str]]]:
        bm25, dense = self._require_open()
        if self.search_calls >= self.max_searches:
            raise SearchBudgetExceeded(f"search budget exhausted at {self.max_searches} calls")
        # Every invocation consumes budget, including a malformed query or a dense
        # backend failure.  This prevents unlimited query probing around the cap.
        self._search_attempts += 1
        bm25_hits = bm25.search(query, limit=self.top_k)
        dense_hits = dense.search(query, limit=self.top_k)
        if len(bm25_hits) != DEFAULT_TOP_K or len(dense_hits) != DEFAULT_TOP_K:
            raise RuntimeError("each hybrid channel must produce exactly 10 internal hits")
        query_terms = tuple(dict.fromkeys(tokenize(query)))
        artifact_items = tuple(sorted(QWEN3_EMBEDDING_ARTIFACT_SHA256.items()))
        fused = self._fuse(bm25_hits, dense_hits)
        shown_page_ids = tuple(
            page_id for page_id, _score in fused if page_id not in self._exposed_ids
        )
        event = HybridSearchEvent(
            search_index=self.search_calls,
            query=query,
            query_terms=query_terms,
            bm25=RetrievalChannelRecord(
                channel=BM25_CHANNEL,
                model_id=BM25_MODEL_ID,
                revision=BM25_REVISION,
                index_sha256=self._bm25_index_sha256,
                corpus_sha256=bm25.corpus_hash,
                artifact_sha256=(),
                top10=bm25_hits,
            ),
            dense=RetrievalChannelRecord(
                channel=DENSE_CHANNEL,
                model_id=QWEN3_EMBEDDING_MODEL_ID,
                revision=QWEN3_EMBEDDING_REVISION,
                index_sha256=dense.index_sha256,
                corpus_sha256=dense.corpus_sha256,
                artifact_sha256=artifact_items,
                top10=dense_hits,
            ),
            fused=fused,
            shown_page_ids=shown_page_ids,
        )
        response: dict[str, list[dict[str, str]]] = {"results": []}
        for page_id in shown_page_ids:
            page = dense.get_page(page_id)
            response["results"].append(
                {"page_id": page.page_id, "title": page.title, "body": page.body}
            )
        self._events.append(event)
        self._exposed_ids.update(event.exposed_page_ids)
        return response

    def select_docs(self, page_ids: list[str]) -> dict[str, list[dict[str, str]]]:
        """Return one exact ordered selection, then permanently close retrieval."""

        bm25, _dense = self._require_open()
        if (
            not isinstance(page_ids, list)
            or len(page_ids) != self.selection_k
            or any(not isinstance(page_id, str) or not page_id.strip() for page_id in page_ids)
            or len(set(page_ids)) != self.selection_k
        ):
            raise InvalidSelectionError(
                f"select_docs requires exactly {self.selection_k} unique non-empty page IDs"
            )
        if any(page_id not in self._exposed_ids for page_id in page_ids):
            raise InvalidSelectionError(
                "every selected page_id must have been exposed by search_web in this session"
            )

        # Resolve every page first so a failure cannot partially commit the selection.
        pages = [bm25.get_page(page_id) for page_id in page_ids]
        result = {"documents": [page.to_open_dict() for page in pages]}
        self._opened_pages.extend(pages)
        self._selection_complete = True
        self._bm25 = None
        self._dense = None
        return result

    def close(self) -> None:
        """Drop both indexes while retaining immutable evidence for the evaluator."""

        self._bm25 = None
        self._dense = None

    def __enter__(self) -> HybridSessionRetriever:
        self._require_open()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


__all__ = [
    "BM25_CHANNEL",
    "BM25_MODEL_ID",
    "BM25_REVISION",
    "DEFAULT_MAX_SEARCHES",
    "DEFAULT_SELECTION_K",
    "DEFAULT_TOP_K",
    "DEFAULT_RRF_K",
    "DENSE_CHANNEL",
    "DenseCosineIndex",
    "DenseEmbeddingBackend",
    "HybridSearchEvent",
    "HybridSessionRetriever",
    "QWEN3_EMBEDDING_ARTIFACT_SHA256",
    "QWEN3_EMBEDDING_MODEL_ID",
    "QWEN3_EMBEDDING_MODEL_SIZE_BYTES",
    "QWEN3_EMBEDDING_REVISION",
    "RetrievalChannelRecord",
]
