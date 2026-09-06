"""HTTP client and content-addressed cache for the pinned dense service."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .batch_constants import (
    DENSE_DIMENSIONS,
    DENSE_MAX_INPUT_TOKENS,
    DENSE_MODEL_ID,
    DENSE_MODEL_REVISION,
)
from .hybrid_retrieval import QWEN3_EMBEDDING_ARTIFACT_SHA256
from .records import canonical_json_bytes, sha256_json


class DenseClientError(RuntimeError):
    pass


class HttpCachedDenseEmbedder:
    """Encode on localhost and cache exact float32 document matrices by content."""

    model_id = DENSE_MODEL_ID
    revision = DENSE_MODEL_REVISION
    artifact_sha256: Mapping[str, str] = QWEN3_EMBEDDING_ARTIFACT_SHA256

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:18139",
        *,
        cache_root: Path,
        timeout_seconds: float = 900.0,
        batch_size: int = 8,
    ) -> None:
        if not endpoint or timeout_seconds <= 0:
            raise ValueError("dense endpoint and timeout must be valid")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        self.endpoint = endpoint.rstrip("/")
        self.cache_root = Path(cache_root)
        self.timeout_seconds = float(timeout_seconds)
        self.batch_size = batch_size

    def _request(self, kind: str, texts: Sequence[str]) -> np.ndarray:
        request = urllib.request.Request(
            self.endpoint + "/encode",
            data=json.dumps(
                {"kind": kind, "texts": list(texts)},
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                value = json.loads(response.read())
        except Exception as exc:
            raise DenseClientError("dense encoder request failed") from exc
        vectors = value.get("vectors") if isinstance(value, dict) else None
        try:
            matrix = np.asarray(vectors, dtype=np.float32)
        except (TypeError, ValueError) as exc:
            raise DenseClientError("dense service returned invalid vectors") from exc
        if matrix.shape != (len(texts), DENSE_DIMENSIONS) or not np.isfinite(matrix).all():
            raise DenseClientError("dense service returned the wrong vector shape")
        norms = np.linalg.norm(matrix, axis=1)
        if not np.allclose(norms, 1.0, rtol=1e-5, atol=1e-6):
            raise DenseClientError("dense service returned non-normalized vectors")
        return matrix

    @staticmethod
    def _text_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _cache_identity(self, texts: Sequence[str]) -> dict[str, Any]:
        return {
            "schema_version": "r2sp.tau-dense-cache.v1",
            "model_id": self.model_id,
            "revision": self.revision,
            "artifact_sha256": dict(self.artifact_sha256),
            "pooling": "last-token",
            "normalization": "l2-float32",
            "max_input_tokens": DENSE_MAX_INPUT_TOKENS,
            "dimensions": DENSE_DIMENSIONS,
            "document_body_sha256": [self._text_hash(text) for text in texts],
        }

    def _paths(self, identity: dict[str, Any]) -> tuple[Path, Path]:
        key = sha256_json(identity)
        directory = self.cache_root / key[:2] / key
        return directory / "vectors.npy", directory / "manifest.json"

    def cache_artifacts(self, texts: Sequence[str]) -> dict[str, Any]:
        """Return and verify the sealed cache entry for an ordered corpus.

        This never calls the encoder service.  Formal GPU jobs use it to prove
        that all document matrices were built before submission.
        """

        values = tuple(texts)
        if not values or any(not isinstance(text, str) or not text for text in values):
            raise ValueError("document texts must be non-empty strings")
        identity = self._cache_identity(values)
        vectors_path, manifest_path = self._paths(identity)
        if not vectors_path.is_file() or not manifest_path.is_file():
            raise DenseClientError("sealed dense cache entry is missing")
        try:
            manifest_bytes = manifest_path.read_bytes()
            manifest = json.loads(manifest_bytes)
            matrix = np.load(vectors_path, allow_pickle=False)
        except Exception as exc:
            raise DenseClientError("dense cache is unreadable") from exc
        if manifest.get("identity") != identity:
            raise DenseClientError("dense cache identity mismatch")
        if matrix.dtype != np.float32 or matrix.shape != (len(values), DENSE_DIMENSIONS):
            raise DenseClientError("dense cache matrix contract mismatch")
        vectors_bytes = vectors_path.read_bytes()
        vectors_sha256 = hashlib.sha256(vectors_bytes).hexdigest()
        if vectors_sha256 != manifest.get("vectors_sha256"):
            raise DenseClientError("dense cache matrix hash mismatch")
        return {
            "identity": identity,
            "cache_key": sha256_json(identity),
            "vectors_path": vectors_path,
            "vectors_bytes": vectors_bytes,
            "vectors_sha256": vectors_sha256,
            "manifest_path": manifest_path,
            "manifest_bytes": manifest_bytes,
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "shape": list(matrix.shape),
            "dtype": str(matrix.dtype),
        }

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        values = tuple(texts)
        if not values or any(not isinstance(text, str) or not text for text in values):
            raise ValueError("document texts must be non-empty strings")
        identity = self._cache_identity(values)
        vectors_path, manifest_path = self._paths(identity)
        if vectors_path.is_file() and manifest_path.is_file():
            cache = self.cache_artifacts(values)
            matrix = np.load(cache["vectors_path"], allow_pickle=False)
            return matrix.tolist()

        chunks: list[np.ndarray] = []
        for start in range(0, len(values), self.batch_size):
            chunks.append(self._request("document", values[start : start + self.batch_size]))
        matrix = np.concatenate(chunks, axis=0).astype(np.float32, copy=False)
        vectors_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".dense-cache-", dir=vectors_path.parent) as tmp:
            staging = Path(tmp)
            staged_vectors = staging / "vectors.npy"
            with staged_vectors.open("wb") as handle:
                np.save(handle, matrix, allow_pickle=False)
                handle.flush()
                os.fsync(handle.fileno())
            manifest = {
                "identity": identity,
                "vectors_sha256": hashlib.sha256(staged_vectors.read_bytes()).hexdigest(),
                "shape": list(matrix.shape),
                "dtype": "float32",
            }
            staged_manifest = staging / "manifest.json"
            staged_manifest.write_bytes(canonical_json_bytes(manifest))
            try:
                os.link(staged_vectors, vectors_path)
                os.link(staged_manifest, manifest_path)
            except FileExistsError:
                pass
        return matrix.tolist()

    def embed_query(self, text: str) -> Sequence[float]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("query must be a non-empty string")
        return self._request("query", [text])[0].tolist()

    def health(self) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(self.endpoint + "/health", timeout=30) as response:
                value = json.loads(response.read())
        except Exception as exc:
            raise DenseClientError("dense service health check failed") from exc
        expected = {
            "status": "ok",
            "model_id": self.model_id,
            "revision": self.revision,
            "dimensions": DENSE_DIMENSIONS,
            "device": "cpu",
        }
        if value != expected:
            raise DenseClientError("dense service health contract mismatch")
        return value


__all__ = ["DenseClientError", "HttpCachedDenseEmbedder"]
