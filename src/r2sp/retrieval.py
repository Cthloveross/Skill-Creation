"""Deterministic global BM25 retrieval for the frozen v0.3 design."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable

from .models import PoolManifest, Resource, SearchHit

_TOKEN_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)


def tokenize(text: str) -> tuple[str, ...]:
    """Apply the fixed NFKC + casefold + Unicode word tokenizer.

    Underscores and punctuation are separators so an API identifier such as
    ``create_event`` is retrievable with the natural-language query
    ``create event``. No language-specific stopword list or stemming is used.
    """

    if not isinstance(text, str):
        raise TypeError("tokenize expects str")
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(_TOKEN_RE.findall(normalized))


def _index_text(resource: Resource) -> str:
    # All task-facing metadata and the full document body are searchable. The
    # result object still exposes only the public header, never a body/snippet.
    return "\n".join((resource.app_name, resource.api_name, resource.title, resource.body))


class DeterministicBM25:
    """A dependency-free BM25Okapi index with an explicit stable tie-break."""

    def __init__(
        self,
        resources: Iterable[Resource],
        *,
        k1: float = 1.2,
        b: float = 0.75,
        top_k: int = 10,
    ) -> None:
        if isinstance(k1, bool) or not isinstance(k1, (int, float)) or k1 <= 0:
            raise ValueError("k1 must be a positive number")
        if isinstance(b, bool) or not isinstance(b, (int, float)) or not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")

        ordered = tuple(sorted(resources, key=lambda resource: resource.resource_id))
        if not ordered:
            raise ValueError("BM25 requires at least one resource")
        if any(not isinstance(resource, Resource) for resource in ordered):
            raise TypeError("resources must contain only Resource objects")
        ids = [resource.resource_id for resource in ordered]
        if len(ids) != len(set(ids)):
            raise ValueError("BM25 resources contain duplicate resource_id values")

        self._resources = ordered
        self.k1 = float(k1)
        self.b = float(b)
        self.top_k = top_k
        self._term_frequencies = tuple(
            Counter(tokenize(_index_text(resource))) for resource in ordered
        )
        self._document_lengths = tuple(
            sum(frequencies.values()) for frequencies in self._term_frequencies
        )
        self._average_length = sum(self._document_lengths) / len(self._document_lengths)

        document_frequency: Counter[str] = Counter()
        for frequencies in self._term_frequencies:
            document_frequency.update(frequencies.keys())
        document_count = len(ordered)
        self._idf = {
            term: math.log(1.0 + (document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }
        self._manifest = PoolManifest.from_resources(ordered)

    @property
    def manifest_hash(self) -> str:
        assert self._manifest.manifest_hash is not None
        return self._manifest.manifest_hash

    @property
    def resource_count(self) -> int:
        return len(self._resources)

    def _score(self, query_terms: tuple[str, ...], document_index: int) -> float:
        frequencies = self._term_frequencies[document_index]
        document_length = self._document_lengths[document_index]
        length_ratio = document_length / self._average_length if self._average_length else 0.0
        score = 0.0
        # Repeating a query token should not accidentally weight it; BM25 here
        # treats the agent query as a set of search terms.
        for term in dict.fromkeys(query_terms):
            frequency = frequencies.get(term, 0)
            if frequency == 0:
                continue
            denominator = frequency + self.k1 * (1.0 - self.b + self.b * length_ratio)
            score += self._idf.get(term, 0.0) * (frequency * (self.k1 + 1.0)) / denominator
        return score

    def search(self, query: str, *, top_k: int | None = None) -> tuple[SearchHit, ...]:
        """Return score-descending hits with ``resource_id`` ascending on ties."""

        query_terms = tokenize(query)
        if not query_terms:
            return ()
        limit = self.top_k if top_k is None else top_k
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("top_k must be a positive integer")

        ranked: list[tuple[float, Resource]] = []
        for index, resource in enumerate(self._resources):
            ranked.append((self._score(query_terms, index), resource))
        ranked.sort(key=lambda item: (-item[0], item[1].resource_id))

        return tuple(
            SearchHit(
                resource_id=resource.resource_id,
                app_name=resource.app_name,
                api_name=resource.api_name,
                title=resource.title,
                score=score,
            )
            for score, resource in ranked[:limit]
        )

    def search_docs(self, query: str, *, top_k: int | None = None) -> tuple[SearchHit, ...]:
        """Protocol-facing alias used by the four-tool agent adapter."""

        return self.search(query, top_k=top_k)

    def read_doc(self, resource_id: str) -> Resource:
        """Return a full document only after an explicit opaque-ID read."""

        for resource in self._resources:
            if resource.resource_id == resource_id:
                return resource
        raise KeyError(f"unknown resource_id: {resource_id}")

    def read(self, resource_id: str) -> Resource:
        """Compatibility alias for adapters implementing ``Retriever.read``."""

        return self.read_doc(resource_id)


# A descriptive alias for callers that prefer the protocol term.
BM25Retriever = DeterministicBM25
