"""Pinned exact dense retrieval for tau-Knowledge Skill evolution.

The serving process owns the transformer and last-token pooling.  This module
keeps the experiment-side contract small and auditable: it verifies every
input with the same pinned tokenizer, calls a loopback OpenAI-compatible
embedding endpoint, converts embeddings to normalized float32 vectors, and
performs an exhaustive cosine scan.  It deliberately contains no chunking,
ANN index, FAISS integration, or reranking path.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from tau_skill_evolution.core._canonical import canonical_json_bytes, canonical_json_sha256
from tau_skill_evolution.core.protocol import Page, PageSnippet, SearchHit

DENSE_MODEL_ID = "Qwen/Qwen3-Embedding-4B"
DENSE_MODEL_REVISION = "5cf2132abc99cad020ac570b19d031efec650f2b"
DENSE_EMBEDDING_DIMENSIONS = 2560
DENSE_MAX_INPUT_TOKENS = 4096
DENSE_SNIPPET_TOKENS = 256
DENSE_POOLING = "last_token"
DENSE_NORMALIZATION = "float32_l2"
DENSE_SIMILARITY = "exact_cosine"
DENSE_CACHE_SCHEMA_VERSION = 2
DENSE_CACHE_MANIFEST = "manifest.json"
DENSE_CACHE_VECTORS = "vectors.f32"
DENSE_DOCUMENT_FORMAT = "title\n\nbody"
QUERY_INSTRUCTION = (
    "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"
)


# Gateway/overload statuses from the loopback embedding front are transient.
_RETRYABLE_HTTP_STATUSES = frozenset({502, 503, 504})


class DenseBackendError(RuntimeError):
    """Base class for fail-closed dense-backend failures."""


class DenseContractError(DenseBackendError):
    """A tokenizer, embedding, or pinned-identity contract was violated."""


class DenseInputTooLongError(DenseContractError):
    """An input cannot be encoded without exceeding the locked token limit."""


class DenseServiceError(DenseBackendError):
    """The loopback embedding service failed or returned malformed data."""

    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def _no_redirect_urlopen(request: urllib.request.Request, *, timeout: float) -> Any:
    return urllib.request.build_opener(_RejectRedirects()).open(request, timeout=timeout)


def _validate_model_identity(
    *, model_id: str, revision: str, dimensions: int
) -> tuple[str, str, int]:
    if not isinstance(model_id, str) or not model_id.strip() or model_id != model_id.strip():
        raise ValueError("model_id must be a non-empty canonical string")
    if not isinstance(revision, str) or not revision.strip() or revision != revision.strip():
        raise ValueError("revision must be a non-empty immutable identifier")
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions <= 0:
        raise ValueError("dimensions must be a positive integer")
    return model_id, revision, dimensions


def format_query(query: str) -> str:
    """Apply the Qwen model card's retrieval-query instruction exactly once."""

    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if not query.strip():
        raise ValueError("query must be non-empty")
    return QUERY_INSTRUCTION + query


class DenseTokenizer(Protocol):
    """Minimal pinned-tokenizer surface consumed by :class:`DenseIndex`."""

    model_id: str
    revision: str
    dimensions: int

    def input_token_ids(self, text: str) -> tuple[int, ...]: ...

    def content_token_offsets(self, text: str) -> tuple[tuple[int, int], ...]: ...


class EmbeddingClient(Protocol):
    """Embedding boundary; query instruction application belongs to the client."""

    model_id: str
    revision: str
    pooling: str
    dimensions: int

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...

    def embed_query(self, query: str) -> tuple[float, ...]: ...


class HuggingFaceQwenTokenizer:
    """Adapter around the pinned fast Hugging Face tokenizer.

    ``transformers`` is imported lazily so offline artifact inspection and unit
    tests do not need the model-service environment installed.
    """

    def __init__(
        self,
        tokenizer: Any,
        *,
        model_id: str = DENSE_MODEL_ID,
        revision: str = DENSE_MODEL_REVISION,
        dimensions: int = DENSE_EMBEDDING_DIMENSIONS,
    ) -> None:
        if (
            tokenizer is None
            or not callable(tokenizer)
            or not callable(getattr(tokenizer, "encode", None))
        ):
            raise TypeError("tokenizer must be a Hugging Face-compatible tokenizer")
        if getattr(tokenizer, "is_fast", False) is not True:
            raise DenseContractError("the pinned tokenizer must be fast and expose offsets")
        self.model_id, self.revision, self.dimensions = _validate_model_identity(
            model_id=model_id,
            revision=revision,
            dimensions=dimensions,
        )
        self._tokenizer = tokenizer

    @classmethod
    def from_pretrained(
        cls,
        *,
        cache_dir: str | None = None,
        local_files_only: bool = True,
        model_id: str = DENSE_MODEL_ID,
        revision: str = DENSE_MODEL_REVISION,
        dimensions: int = DENSE_EMBEDDING_DIMENSIONS,
    ) -> HuggingFaceQwenTokenizer:
        """Load only the requested immutable tokenizer identity."""

        model_id, revision, dimensions = _validate_model_identity(
            model_id=model_id,
            revision=revision,
            dimensions=dimensions,
        )

        try:
            from transformers import AutoTokenizer
        except ImportError as exc:  # pragma: no cover - exercised only in the live env
            raise DenseContractError("transformers is required to load the Qwen tokenizer") from exc
        tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            revision=revision,
            cache_dir=cache_dir,
            local_files_only=local_files_only,
            use_fast=True,
        )
        return cls(
            tokenizer,
            model_id=model_id,
            revision=revision,
            dimensions=dimensions,
        )

    def input_token_ids(self, text: str) -> tuple[int, ...]:
        if not isinstance(text, str):
            raise TypeError("tokenizer input must be text")
        # Explicitly disable truncation.  add_special_tokens=True matches the
        # official tokenizer default used for model inputs.
        values = self._tokenizer.encode(
            text,
            add_special_tokens=True,
            truncation=False,
        )
        return _validate_token_ids(values)

    def content_token_offsets(self, text: str) -> tuple[tuple[int, int], ...]:
        if not isinstance(text, str):
            raise TypeError("tokenizer input must be text")
        encoded = self._tokenizer(
            text,
            add_special_tokens=False,
            return_attention_mask=False,
            return_offsets_mapping=True,
            truncation=False,
        )
        if not isinstance(encoded, Mapping):
            raise DenseContractError("tokenizer did not return a mapping")
        token_ids = _validate_token_ids(encoded.get("input_ids"))
        offsets = _validate_offsets(encoded.get("offset_mapping"), text)
        if len(offsets) != len(token_ids):
            raise DenseContractError("tokenizer offsets do not match its token IDs")
        return offsets


def _validate_token_ids(value: object) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DenseContractError("tokenizer returned invalid token IDs")
    result = tuple(value)
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in result):
        raise DenseContractError("tokenizer returned invalid token IDs")
    return result


def _validate_offsets(value: object, text: str) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DenseContractError("tokenizer returned invalid offsets")
    result: list[tuple[int, int]] = []
    previous_start = 0
    previous_end = 0
    for raw in value:
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 2:
            raise DenseContractError("tokenizer returned invalid offsets")
        start, end = raw
        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or start < previous_start
            or end < previous_end
            or not 0 <= start < end <= len(text)
        ):
            raise DenseContractError("tokenizer returned non-monotonic offsets")
        previous_start, previous_end = start, end
        result.append((start, end))
    return tuple(result)


def _require_loopback_base_url(base_url: str) -> str:
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("base_url must be a non-empty loopback URL")
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "http" or parsed.username is not None or parsed.password is not None:
        raise ValueError("embedding endpoint must be an unauthenticated HTTP loopback URL")
    if parsed.query or parsed.fragment or not parsed.hostname or parsed.port is None:
        raise ValueError("embedding endpoint must include only a loopback host, port, and path")
    try:
        if not ipaddress.ip_address(parsed.hostname).is_loopback:
            raise ValueError("embedding endpoint host must be a loopback IP address")
    except ValueError as exc:
        raise ValueError("embedding endpoint host must be a loopback IP address") from exc
    return base_url.rstrip("/")


class OpenAICompatibleEmbeddingClient:
    """Strict, no-retry client for a pinned loopback embeddings service."""

    pooling = DENSE_POOLING

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:18140/v1",
        *,
        timeout_seconds: float = 120.0,
        batch_size: int = 32,
        api_key: str | None = None,
        opener: Any | None = None,
        max_response_bytes: int = 32 * 1024 * 1024,
        model_id: str = DENSE_MODEL_ID,
        revision: str = DENSE_MODEL_REVISION,
        dimensions: int = DENSE_EMBEDDING_DIMENSIONS,
        retry_attempts: int = 5,
        retry_backoff_seconds: float = 0.2,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive finite number")
        if isinstance(retry_attempts, bool) or not isinstance(retry_attempts, int):
            raise ValueError("retry_attempts must be an integer")
        if retry_attempts < 1 or retry_backoff_seconds < 0:
            raise ValueError("retry_attempts must be >= 1 and retry_backoff_seconds >= 0")
        self.retry_attempts = retry_attempts
        self.retry_backoff_seconds = float(retry_backoff_seconds)
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or max_response_bytes <= 0
        ):
            raise ValueError("max_response_bytes must be a positive integer")
        if api_key is not None and (not isinstance(api_key, str) or not api_key):
            raise ValueError("api_key must be None or a non-empty string")
        self.model_id, self.revision, self.dimensions = _validate_model_identity(
            model_id=model_id,
            revision=revision,
            dimensions=dimensions,
        )
        self.base_url = _require_loopback_base_url(base_url)
        self.timeout_seconds = float(timeout_seconds)
        self.batch_size = batch_size
        self.api_key = api_key
        self.max_response_bytes = max_response_bytes
        self._opener = opener or _no_redirect_urlopen

    @property
    def endpoint(self) -> str:
        if self.base_url.endswith("/embeddings"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return self.base_url + "/embeddings"
        return self.base_url + "/v1/embeddings"

    @property
    def identity(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_revision": self.revision,
            "pooling": self.pooling,
            "dimensions": self.dimensions,
            "endpoint": self.endpoint,
        }

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        normalized = _validate_text_batch(texts)
        result: list[tuple[float, ...]] = []
        for offset in range(0, len(normalized), self.batch_size):
            result.extend(self._embed_batch(normalized[offset : offset + self.batch_size]))
        return tuple(result)

    def embed_query(self, query: str) -> tuple[float, ...]:
        return self._embed_batch((format_query(query),))[0]

    def _embed_batch(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        payload = {
            "model": self.model_id,
            "input": list(texts),
            "encoding_format": "float",
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if self.api_key is not None:
            request.add_header("Authorization", f"Bearer {self.api_key}")
        # Embedding a fixed text is deterministic and side-effect free, so transient
        # loopback/tunnel outages are retried briefly; the result is still fail-closed.
        attempt = 0
        while True:
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    raw = response.read(self.max_response_bytes + 1)
                break
            except urllib.error.HTTPError as exc:
                attempt += 1
                if attempt < self.retry_attempts and exc.code in _RETRYABLE_HTTP_STATUSES:
                    time.sleep(self.retry_backoff_seconds * 2 ** (attempt - 1))
                    continue
                raise DenseServiceError(
                    "http_error", f"embedding service returned HTTP {exc.code}", status=exc.code
                ) from exc
            except (OSError, TimeoutError, urllib.error.URLError) as exc:
                attempt += 1
                if attempt < self.retry_attempts:
                    time.sleep(self.retry_backoff_seconds * 2 ** (attempt - 1))
                    continue
                raise DenseServiceError("transport_error", str(exc)) from exc
        if len(raw) > self.max_response_bytes:
            raise DenseServiceError("response_too_large", "embedding response exceeded size limit")
        try:
            decoded = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DenseServiceError(
                "invalid_json", "embedding service returned invalid JSON"
            ) from exc
        return _decode_embedding_response(
            decoded,
            expected_count=len(texts),
            dimensions=self.dimensions,
        )


def _validate_text_batch(texts: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(texts, Sequence) or isinstance(texts, (str, bytes)):
        raise TypeError("embedding inputs must be a sequence of strings")
    normalized = tuple(texts)
    if not normalized:
        raise ValueError("embedding inputs must not be empty")
    if any(not isinstance(text, str) or not text for text in normalized):
        raise ValueError("embedding inputs must contain non-empty strings")
    return normalized


def _decode_embedding_response(
    decoded: object, *, expected_count: int, dimensions: int
) -> tuple[tuple[float, ...], ...]:
    data = decoded.get("data") if isinstance(decoded, Mapping) else None
    if not isinstance(data, list) or len(data) != expected_count:
        raise DenseServiceError(
            "invalid_response", "embedding response has the wrong number of vectors"
        )
    by_index: dict[int, tuple[float, ...]] = {}
    for item in data:
        if not isinstance(item, Mapping):
            raise DenseServiceError("invalid_response", "embedding item must be an object")
        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index in by_index:
            raise DenseServiceError("invalid_response", "embedding indices are invalid")
        try:
            vector = _coerce_raw_vector(item.get("embedding"), dimensions=dimensions)
        except DenseContractError as exc:
            raise DenseServiceError("invalid_response", str(exc)) from exc
        by_index[index] = vector
    if set(by_index) != set(range(expected_count)):
        raise DenseServiceError("invalid_response", "embedding indices are not contiguous")
    return tuple(by_index[index] for index in range(expected_count))


def _float32(value: float) -> float:
    try:
        return struct.unpack("!f", struct.pack("!f", value))[0]
    except (OverflowError, struct.error) as exc:
        raise DenseContractError("embedding component is outside float32 range") from exc


def _coerce_raw_vector(value: object, *, dimensions: int) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DenseContractError("embedding must be a numeric sequence")
    if len(value) != dimensions:
        raise DenseContractError(f"embedding dimension must be {dimensions}, got {len(value)}")
    result: list[float] = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise DenseContractError("embedding components must be numeric")
        converted = float(component)
        if not math.isfinite(converted):
            raise DenseContractError("embedding components must be finite")
        converted = _float32(converted)
        if not math.isfinite(converted):
            raise DenseContractError("embedding components must remain finite in float32")
        result.append(converted)
    return tuple(result)


def _normalize_float32(value: object, *, dimensions: int) -> tuple[float, ...]:
    vector = _coerce_raw_vector(value, dimensions=dimensions)
    norm = math.sqrt(math.fsum(component * component for component in vector))
    if not math.isfinite(norm) or norm == 0.0:
        raise DenseContractError("embedding vector must have a finite non-zero L2 norm")
    normalized = tuple(_float32(component / norm) for component in vector)
    if not any(normalized):
        raise DenseContractError("embedding underflowed to an all-zero float32 vector")
    return normalized


@dataclass(frozen=True, slots=True)
class _PreparedPage:
    page: Page
    embedding_text: str
    token_count: int
    snippet: PageSnippet


def _document_embedding_text(page: Page) -> str:
    """Return the exact whole-page text sent to the embedding service."""

    return f"{page.title}\n\n{page.body}"


def _prepare_pages(
    pages: Iterable[Page], *, tokenizer: DenseTokenizer
) -> tuple[_PreparedPage, ...]:
    ordered = _materialize_pages(pages)

    # This loop intentionally finishes for every page before embed_documents
    # is reachable.  A too-long document can therefore never yield a
    # partially materialized or silently truncated index.
    prepared: list[_PreparedPage] = []
    for page in ordered:
        embedding_text = _document_embedding_text(page)
        input_ids = tokenizer.input_token_ids(embedding_text)
        token_count = len(input_ids)
        if token_count > DENSE_MAX_INPUT_TOKENS:
            raise DenseInputTooLongError(
                f"document {page.page_id} has {token_count} tokens; "
                f"maximum is {DENSE_MAX_INPUT_TOKENS}"
            )
        offsets = tokenizer.content_token_offsets(page.body)
        snippet = _snippet_from_offsets(page.body, offsets)
        prepared.append(_PreparedPage(page, embedding_text, token_count, snippet))
    return tuple(prepared)


class DenseIndex:
    """Immutable whole-document index with exhaustive normalized-cosine search."""

    def __init__(
        self,
        *,
        prepared_pages: Sequence[_PreparedPage],
        vectors: Sequence[tuple[float, ...]],
        client: EmbeddingClient,
        tokenizer: DenseTokenizer | None,
    ) -> None:
        if len(prepared_pages) != len(vectors) or not prepared_pages:
            raise DenseContractError("prepared pages and embeddings must be non-empty and aligned")
        self._prepared_pages = tuple(prepared_pages)
        self._vectors = tuple(vectors)
        self._client = client
        self._tokenizer = tokenizer
        self._model_id = client.model_id
        self._model_revision = client.revision
        self._dimensions = client.dimensions
        self._page_by_id = {item.page.page_id: item.page for item in self._prepared_pages}
        self._snippet_by_id = {item.page.page_id: item.snippet for item in self._prepared_pages}
        self._token_count_by_id = {
            item.page.page_id: item.token_count for item in self._prepared_pages
        }
        self._corpus_hash = canonical_json_sha256(
            [
                {
                    "page_id": item.page.page_id,
                    "title": item.page.title,
                    "content_sha256": item.page.content_sha256,
                }
                for item in self._prepared_pages
            ]
        )

    @classmethod
    def build(
        cls,
        pages: Iterable[Page],
        *,
        client: EmbeddingClient,
        tokenizer: DenseTokenizer,
    ) -> DenseIndex:
        """Validate the complete corpus before issuing any embedding request."""

        _verify_identity(client=client, tokenizer=tokenizer)
        prepared = _prepare_pages(pages, tokenizer=tokenizer)
        raw_vectors = client.embed_documents(tuple(item.embedding_text for item in prepared))
        if len(raw_vectors) != len(prepared):
            raise DenseContractError("embedding client returned the wrong document count")
        vectors = tuple(
            _normalize_float32(vector, dimensions=client.dimensions) for vector in raw_vectors
        )
        return cls(
            prepared_pages=prepared,
            vectors=vectors,
            client=client,
            tokenizer=tokenizer,
        )

    @classmethod
    def load_cache(
        cls,
        directory: Path,
        pages: Iterable[Page],
        *,
        client: EmbeddingClient,
        tokenizer: DenseTokenizer | None = None,
        expected_manifest_sha256: str | None = None,
    ) -> DenseIndex:
        """Load a cache only after revalidating it against the current corpus.

        Document vectors are never requested here.  Query embeddings continue
        to use ``client`` so every search retains the same pinned live-service
        boundary as a newly built index.
        """

        _verify_identity(client=client, tokenizer=tokenizer)
        root = Path(directory)
        manifest_path = root / DENSE_CACHE_MANIFEST
        vectors_path = root / DENSE_CACHE_VECTORS
        manifest = _read_cache_manifest(
            manifest_path, expected_manifest_sha256=expected_manifest_sha256
        )
        prepared = _prepared_from_cache_contract(
            pages,
            manifest["contract"],
            model_id=client.model_id,
            revision=client.revision,
            dimensions=client.dimensions,
        )
        if tokenizer is not None:
            retokenized = _prepare_pages((item.page for item in prepared), tokenizer=tokenizer)
            if (
                _cache_contract(
                    retokenized,
                    model_id=client.model_id,
                    revision=client.revision,
                    dimensions=client.dimensions,
                )
                != manifest["contract"]
            ):
                raise DenseContractError(
                    "dense cache tokenization does not match the pinned tokenizer"
                )
            prepared = retokenized

        vectors_metadata = manifest["vectors"]
        if not isinstance(vectors_metadata, Mapping):
            raise DenseContractError("dense cache vectors metadata is invalid")
        expected_vector_metadata = {
            "filename",
            "dtype",
            "endianness",
            "shape",
            "size_bytes",
            "sha256",
        }
        if set(vectors_metadata) != expected_vector_metadata:
            raise DenseContractError("dense cache vectors metadata schema is invalid")
        if (
            vectors_metadata["filename"] != DENSE_CACHE_VECTORS
            or vectors_metadata["dtype"] != "float32"
            or vectors_metadata["endianness"] != "little"
            or vectors_metadata["shape"] != [len(prepared), client.dimensions]
        ):
            raise DenseContractError("dense cache vector layout is invalid")
        expected_size = len(prepared) * client.dimensions * 4
        if vectors_metadata["size_bytes"] != expected_size:
            raise DenseContractError("dense cache vector size metadata is invalid")
        try:
            raw_vectors = vectors_path.read_bytes()
        except OSError as exc:
            raise DenseContractError("unable to read dense cache vectors") from exc
        if len(raw_vectors) != expected_size:
            raise DenseContractError("dense cache vector file has the wrong size")
        if hashlib.sha256(raw_vectors).hexdigest() != vectors_metadata["sha256"]:
            raise DenseContractError("dense cache vector hash mismatch")
        vectors = _decode_cached_vectors(
            raw_vectors,
            page_count=len(prepared),
            dimensions=client.dimensions,
        )
        return cls(
            prepared_pages=prepared,
            vectors=vectors,
            client=client,
            tokenizer=tokenizer,
        )

    @property
    def page_count(self) -> int:
        return len(self._prepared_pages)

    @property
    def corpus_hash(self) -> str:
        return self._corpus_hash

    @property
    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": DENSE_CACHE_SCHEMA_VERSION,
            "model_id": self._model_id,
            "model_revision": self._model_revision,
            "tokenizer_id": self._model_id,
            "tokenizer_revision": self._model_revision,
            "pooling": DENSE_POOLING,
            "normalization": DENSE_NORMALIZATION,
            "similarity": DENSE_SIMILARITY,
            "dimensions": self._dimensions,
            "max_input_tokens": DENSE_MAX_INPUT_TOKENS,
            "snippet_tokens": DENSE_SNIPPET_TOKENS,
            "query_instruction": QUERY_INSTRUCTION,
            "document_format": DENSE_DOCUMENT_FORMAT,
            "whole_document": True,
            "chunking": False,
            "reranker": False,
            "approximate_index": False,
            "page_count": self.page_count,
            "corpus_hash": self.corpus_hash,
            "document_token_counts": dict(self._token_count_by_id),
        }

    def save_cache(self, directory: Path) -> dict[str, Any]:
        """Write a new canonical cache directory without overwriting files."""

        root = Path(directory)
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DenseContractError("unable to create dense cache directory") from exc
        manifest_path = root / DENSE_CACHE_MANIFEST
        vectors_path = root / DENSE_CACHE_VECTORS
        if manifest_path.exists() or vectors_path.exists():
            raise DenseContractError("dense cache files already exist; refusing to overwrite")

        raw_vectors = b"".join(
            struct.pack(f"<{self._dimensions}f", *vector) for vector in self._vectors
        )
        vectors_sha256 = hashlib.sha256(raw_vectors).hexdigest()
        unsigned_manifest = {
            "schema_version": DENSE_CACHE_SCHEMA_VERSION,
            "format": "r2sp_tau_dense_cache",
            "contract": _cache_contract(
                self._prepared_pages,
                model_id=self._model_id,
                revision=self._model_revision,
                dimensions=self._dimensions,
            ),
            "vectors": {
                "filename": DENSE_CACHE_VECTORS,
                "dtype": "float32",
                "endianness": "little",
                "shape": [self.page_count, self._dimensions],
                "size_bytes": len(raw_vectors),
                "sha256": vectors_sha256,
            },
        }
        manifest = {
            **unsigned_manifest,
            "manifest_payload_sha256": canonical_json_sha256(unsigned_manifest),
        }
        manifest_bytes = canonical_json_bytes(manifest) + b"\n"
        try:
            with vectors_path.open("xb") as handle:
                handle.write(raw_vectors)
            with manifest_path.open("xb") as handle:
                handle.write(manifest_bytes)
        except OSError as exc:
            raise DenseContractError("unable to write dense cache") from exc
        return manifest

    def get_page(self, page_id: str) -> Page:
        if not isinstance(page_id, str) or not page_id.strip():
            raise ValueError("page_id must be a non-empty string")
        try:
            return self._page_by_id[page_id]
        except KeyError as exc:
            raise KeyError(f"unknown page_id: {page_id}") from exc

    def snippet_for(self, page: Page | str) -> PageSnippet:
        page_id = page.page_id if isinstance(page, Page) else page
        if not isinstance(page_id, str) or not page_id.strip():
            raise ValueError("page must be a Page or a non-empty page_id")
        try:
            return self._snippet_by_id[page_id]
        except KeyError as exc:
            raise KeyError(f"unknown page_id: {page_id}") from exc

    def search(self, query: str, *, limit: int = 10) -> tuple[SearchHit, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        instructed_query = format_query(query)
        if self._tokenizer is not None:
            token_count = len(self._tokenizer.input_token_ids(instructed_query))
            if token_count > DENSE_MAX_INPUT_TOKENS:
                raise DenseInputTooLongError(
                    f"instructed query has {token_count} tokens; "
                    f"maximum is {DENSE_MAX_INPUT_TOKENS}"
                )
        query_vector = _normalize_float32(
            self._client.embed_query(query),
            dimensions=self._dimensions,
        )
        ranked = [
            (
                math.fsum(left * right for left, right in zip(query_vector, vector, strict=True)),
                prepared.page,
            )
            for prepared, vector in zip(self._prepared_pages, self._vectors, strict=True)
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


def _verify_identity(*, client: EmbeddingClient, tokenizer: DenseTokenizer | None) -> None:
    try:
        model_id, revision, dimensions = _validate_model_identity(
            model_id=getattr(client, "model_id", None),
            revision=getattr(client, "revision", None),
            dimensions=getattr(client, "dimensions", None),
        )
    except (TypeError, ValueError) as exc:
        raise DenseContractError("embedding client model identity is invalid") from exc
    if getattr(client, "pooling", None) != DENSE_POOLING:
        raise DenseContractError(f"embedding client pooling must be {DENSE_POOLING!r}")
    if tokenizer is not None:
        expected = {
            "model_id": model_id,
            "revision": revision,
            "dimensions": dimensions,
        }
        for name, value in expected.items():
            if getattr(tokenizer, name, None) != value:
                raise DenseContractError(f"tokenizer {name} must match embedding client {value!r}")
        for name in ("input_token_ids", "content_token_offsets"):
            if not callable(getattr(tokenizer, name, None)):
                raise DenseContractError(f"tokenizer is missing {name}")
    for name in ("embed_documents", "embed_query"):
        if not callable(getattr(client, name, None)):
            raise DenseContractError(f"embedding client is missing {name}")


def _snippet_from_offsets(body: str, offsets: Sequence[tuple[int, int]]) -> PageSnippet:
    if len(offsets) <= DENSE_SNIPPET_TOKENS:
        return PageSnippet(text=body, truncated=False)
    end = offsets[DENSE_SNIPPET_TOKENS - 1][1]
    return PageSnippet(text=body[:end], truncated=True)


def _cache_contract(
    prepared_pages: Sequence[_PreparedPage],
    *,
    model_id: str,
    revision: str,
    dimensions: int,
) -> dict[str, Any]:
    corpus_descriptor = [
        {
            "page_id": item.page.page_id,
            "title": item.page.title,
            "content_sha256": item.page.content_sha256,
        }
        for item in prepared_pages
    ]
    return {
        "model_id": model_id,
        "model_revision": revision,
        "tokenizer_id": model_id,
        "tokenizer_revision": revision,
        "pooling": DENSE_POOLING,
        "normalization": DENSE_NORMALIZATION,
        "similarity": DENSE_SIMILARITY,
        "dimensions": dimensions,
        "max_input_tokens": DENSE_MAX_INPUT_TOKENS,
        "snippet_tokens": DENSE_SNIPPET_TOKENS,
        "query_instruction": QUERY_INSTRUCTION,
        "document_format": DENSE_DOCUMENT_FORMAT,
        "whole_document": True,
        "chunking": False,
        "reranker": False,
        "approximate_index": False,
        "page_count": len(prepared_pages),
        "corpus_hash": canonical_json_sha256(corpus_descriptor),
        "pages": [
            {
                **descriptor,
                "token_count": prepared.token_count,
                "snippet": prepared.snippet.text,
                "snippet_truncated": prepared.snippet.truncated,
            }
            for descriptor, prepared in zip(corpus_descriptor, prepared_pages, strict=True)
        ],
    }


def _materialize_pages(pages: Iterable[Page]) -> tuple[Page, ...]:
    materialized = tuple(pages)
    if not materialized:
        raise ValueError("dense index requires at least one page")
    if any(not isinstance(page, Page) for page in materialized):
        raise TypeError("pages must contain only Page values")
    page_ids = [page.page_id for page in materialized]
    if len(page_ids) != len(set(page_ids)):
        raise ValueError("dense index pages contain duplicate page_id values")
    return tuple(sorted(materialized, key=lambda page: page.page_id))


def _prepared_from_cache_contract(
    pages: Iterable[Page],
    contract: object,
    *,
    model_id: str,
    revision: str,
    dimensions: int,
) -> tuple[_PreparedPage, ...]:
    if not isinstance(contract, Mapping):
        raise DenseContractError("dense cache contract must be an object")
    expected_keys = {
        "model_id",
        "model_revision",
        "tokenizer_id",
        "tokenizer_revision",
        "pooling",
        "normalization",
        "similarity",
        "dimensions",
        "max_input_tokens",
        "snippet_tokens",
        "query_instruction",
        "document_format",
        "whole_document",
        "chunking",
        "reranker",
        "approximate_index",
        "page_count",
        "corpus_hash",
        "pages",
    }
    if set(contract) != expected_keys:
        raise DenseContractError("dense cache contract schema is invalid")
    fixed_values = {
        "model_id": model_id,
        "model_revision": revision,
        "tokenizer_id": model_id,
        "tokenizer_revision": revision,
        "pooling": DENSE_POOLING,
        "normalization": DENSE_NORMALIZATION,
        "similarity": DENSE_SIMILARITY,
        "dimensions": dimensions,
        "max_input_tokens": DENSE_MAX_INPUT_TOKENS,
        "snippet_tokens": DENSE_SNIPPET_TOKENS,
        "query_instruction": QUERY_INSTRUCTION,
        "document_format": DENSE_DOCUMENT_FORMAT,
        "whole_document": True,
        "chunking": False,
        "reranker": False,
        "approximate_index": False,
    }
    if any(contract[name] != value for name, value in fixed_values.items()):
        raise DenseContractError("dense cache uses a different retrieval contract")

    ordered = _materialize_pages(pages)
    raw_page_records = contract["pages"]
    if (
        isinstance(contract["page_count"], bool)
        or contract["page_count"] != len(ordered)
        or not isinstance(raw_page_records, list)
        or len(raw_page_records) != len(ordered)
    ):
        raise DenseContractError("dense cache page count is invalid")
    descriptor = [
        {
            "page_id": page.page_id,
            "title": page.title,
            "content_sha256": page.content_sha256,
        }
        for page in ordered
    ]
    if contract["corpus_hash"] != canonical_json_sha256(descriptor):
        raise DenseContractError("dense cache corpus hash does not match current pages")

    prepared: list[_PreparedPage] = []
    page_keys = {
        "page_id",
        "title",
        "content_sha256",
        "token_count",
        "snippet",
        "snippet_truncated",
    }
    for page, expected_descriptor, raw in zip(ordered, descriptor, raw_page_records, strict=True):
        if not isinstance(raw, Mapping) or set(raw) != page_keys:
            raise DenseContractError("dense cache page record schema is invalid")
        if any(raw[name] != value for name, value in expected_descriptor.items()):
            raise DenseContractError("dense cache page does not match the current corpus")
        token_count = raw["token_count"]
        snippet = raw["snippet"]
        truncated = raw["snippet_truncated"]
        if (
            isinstance(token_count, bool)
            or not isinstance(token_count, int)
            or not 1 <= token_count <= DENSE_MAX_INPUT_TOKENS
        ):
            raise DenseContractError("dense cache page token count is invalid")
        if not isinstance(snippet, str) or not snippet or not page.body.startswith(snippet):
            raise DenseContractError("dense cache page snippet is not a body prefix")
        if not isinstance(truncated, bool):
            raise DenseContractError("dense cache snippet flag is invalid")
        if (not truncated and snippet != page.body) or (truncated and snippet == page.body):
            raise DenseContractError("dense cache snippet flag disagrees with its body prefix")
        prepared.append(
            _PreparedPage(
                page=page,
                embedding_text=_document_embedding_text(page),
                token_count=token_count,
                snippet=PageSnippet(text=snippet, truncated=truncated),
            )
        )
    return tuple(prepared)


def _read_cache_manifest(path: Path, *, expected_manifest_sha256: str | None) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DenseContractError("unable to read dense cache manifest") from exc
    if len(raw) > 128 * 1024 * 1024:
        raise DenseContractError("dense cache manifest exceeds size limit")
    observed_file_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_manifest_sha256 is not None:
        if (
            not isinstance(expected_manifest_sha256, str)
            or len(expected_manifest_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_manifest_sha256)
        ):
            raise ValueError("expected_manifest_sha256 must be a lowercase SHA-256 digest")
        if observed_file_sha256 != expected_manifest_sha256:
            raise DenseContractError("dense cache manifest file hash mismatch")
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DenseContractError("dense cache manifest is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise DenseContractError("dense cache manifest must be an object")
    if raw != canonical_json_bytes(decoded) + b"\n":
        raise DenseContractError("dense cache manifest is not canonical JSON")
    expected_keys = {
        "schema_version",
        "format",
        "contract",
        "vectors",
        "manifest_payload_sha256",
    }
    if set(decoded) != expected_keys:
        raise DenseContractError("dense cache manifest schema is invalid")
    if (
        decoded["schema_version"] != DENSE_CACHE_SCHEMA_VERSION
        or decoded["format"] != "r2sp_tau_dense_cache"
    ):
        raise DenseContractError("dense cache manifest version is unsupported")
    unsigned = {key: value for key, value in decoded.items() if key != "manifest_payload_sha256"}
    if decoded["manifest_payload_sha256"] != canonical_json_sha256(unsigned):
        raise DenseContractError("dense cache manifest payload hash mismatch")
    return decoded


def _decode_cached_vectors(
    raw: bytes, *, page_count: int, dimensions: int
) -> tuple[tuple[float, ...], ...]:
    total_components = page_count * dimensions
    try:
        flat = struct.unpack(f"<{total_components}f", raw)
    except struct.error as exc:
        raise DenseContractError("dense cache vector file cannot be decoded") from exc
    result: list[tuple[float, ...]] = []
    for page_index in range(page_count):
        start = page_index * dimensions
        vector = tuple(flat[start : start + dimensions])
        if any(not math.isfinite(component) for component in vector):
            raise DenseContractError("dense cache vector contains a non-finite component")
        norm = math.sqrt(math.fsum(component * component for component in vector))
        if not math.isclose(norm, 1.0, rel_tol=5e-6, abs_tol=5e-6):
            raise DenseContractError("dense cache vector is not float32 L2-normalized")
        result.append(vector)
    return tuple(result)


__all__ = [
    "DENSE_CACHE_MANIFEST",
    "DENSE_CACHE_SCHEMA_VERSION",
    "DENSE_CACHE_VECTORS",
    "DENSE_DOCUMENT_FORMAT",
    "DENSE_EMBEDDING_DIMENSIONS",
    "DENSE_MAX_INPUT_TOKENS",
    "DENSE_MODEL_ID",
    "DENSE_MODEL_REVISION",
    "DENSE_NORMALIZATION",
    "DENSE_POOLING",
    "DENSE_SIMILARITY",
    "DENSE_SNIPPET_TOKENS",
    "QUERY_INSTRUCTION",
    "DenseBackendError",
    "DenseContractError",
    "DenseIndex",
    "DenseInputTooLongError",
    "DenseServiceError",
    "DenseTokenizer",
    "EmbeddingClient",
    "HuggingFaceQwenTokenizer",
    "OpenAICompatibleEmbeddingClient",
    "format_query",
]
