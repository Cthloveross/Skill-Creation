from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from r2sp_tau_knowledge import benign_retrieval_probe as probe
from r2sp_tau_knowledge.data import KnowledgeDocument, SnapshotError
from r2sp_tau_knowledge.hybrid_retrieval import (
    QWEN3_EMBEDDING_ARTIFACT_SHA256,
    QWEN3_EMBEDDING_MODEL_ID,
    QWEN3_EMBEDDING_REVISION,
    HybridSessionRetriever,
)


class FakeEmbedder:
    model_id = QWEN3_EMBEDDING_MODEL_ID
    revision = QWEN3_EMBEDDING_REVISION
    artifact_sha256: Mapping[str, str] = QWEN3_EMBEDDING_ARTIFACT_SHA256

    def __init__(self) -> None:
        self.documents: list[str] = []
        self.queries: list[str] = []

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self.documents.extend(texts)
        return [[1.0, 0.0] if "semantic" in text else [0.0, 1.0] for text in texts]

    def embed_query(self, text: str) -> Sequence[float]:
        self.queries.append(text)
        return [1.0, 0.0]


@pytest.fixture
def official(monkeypatch: pytest.MonkeyPatch) -> tuple[KnowledgeDocument, ...]:
    documents = []
    for index in range(30):
        body = "semantic" if index < 10 else "alpha" if index < 20 else "unrelated"
        body += f" banking reference number {index}"
        documents.append(
            KnowledgeDocument(
                page_id=f"doc_{index:02d}",
                title=f"Document {index}",
                body=body,
                content_sha256=hashlib.sha256(body.encode()).hexdigest(),
                source_path=Path(f"doc_{index:02d}.json"),
            )
        )
    monkeypatch.setattr(probe, "load_documents", lambda: tuple(documents))
    monkeypatch.setattr(
        probe,
        "verify_tracked_snapshot",
        lambda: {
            "commit": "a" * 40,
            "documents": len(documents),
            "tasks": 97,
        },
    )
    return tuple(documents)


def test_coverage_diagnosis_keeps_channel_evidence_without_selection(
    official: tuple[KnowledgeDocument, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedder = FakeEmbedder()

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("retrieval diagnostic must not select documents")

    monkeypatch.setattr(HybridSessionRetriever, "select_docs", forbidden)
    result = probe.run_retrieval_probe(["alpha"], embedder, reference_ids=["doc_00", "doc_10"])
    assert embedder.queries == ["alpha"]
    assert len(embedder.documents) == len(official)
    assert len(result["searches"][0]["channels"][0]["top10"]) == 10
    assert len(result["searches"][0]["channels"][1]["top10"]) == 10
    assert len(result["shown_union"]) == 20
    assert result["reference_exposure"]["bm25_top10_union"]["count"] == 1
    assert result["reference_exposure"]["hybrid_shown_union"]["count"] == 2
    assert result["agent_run"] is False
    assert result["agent_selection_performed"] is False
    assert result["official_utility"] is None
    assert result["asr"] is None


def test_repeated_query_does_not_backfill_or_repeat_shown_documents(
    official: tuple[KnowledgeDocument, ...],
) -> None:
    result = probe.run_retrieval_probe(["alpha", "alpha"], FakeEmbedder())
    assert len(result["searches"][0]["shown_page_ids"]) == 20
    assert result["searches"][1]["shown_page_ids"] == []
    assert len(result["shown_union"]) == 20
    assert result["reference_exposure"]["hybrid_shown_union"]["coverage"] is None


def test_reference_labels_cannot_change_queries_embeddings_or_ranking(
    official: tuple[KnowledgeDocument, ...],
) -> None:
    first, second = FakeEmbedder(), FakeEmbedder()
    a = probe.run_retrieval_probe(["alpha"], first, reference_ids=["doc_00"])
    b = probe.run_retrieval_probe(["alpha"], second, reference_ids=["doc_29"])
    assert first.documents == second.documents
    assert first.queries == second.queries == ["alpha"]
    assert a["shown_union"] == b["shown_union"]
    assert a["searches"][0]["channels"] == b["searches"][0]["channels"]
    assert a["searches"][0]["fused"] == b["searches"][0]["fused"]


@pytest.mark.parametrize("queries", [[], ["alpha"] * 3, ["!!!"], [""], "alpha", [None]])
def test_invalid_query_input_fails_before_embedding(
    official: tuple[KnowledgeDocument, ...],
    queries: Any,
) -> None:
    embedder = FakeEmbedder()
    with pytest.raises(ValueError):
        probe.run_retrieval_probe(queries, embedder)
    assert embedder.documents == []
    assert embedder.queries == []


def test_snapshot_drift_fails_before_embedding(
    official: tuple[KnowledgeDocument, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = iter([{"commit": "a" * 40}, {"commit": "b" * 40}])
    monkeypatch.setattr(probe, "verify_tracked_snapshot", lambda: next(snapshots))
    embedder = FakeEmbedder()
    with pytest.raises(SnapshotError, match="changed"):
        probe.run_retrieval_probe(["alpha"], embedder)
    assert not embedder.documents


@pytest.mark.parametrize("references", [["missing"], ["doc_00", "doc_00"], "doc_00"])
def test_invalid_reference_labels_fail_before_embedding(
    official: tuple[KnowledgeDocument, ...],
    references: Any,
) -> None:
    embedder = FakeEmbedder()
    with pytest.raises(ValueError):
        probe.run_retrieval_probe(["alpha"], embedder, reference_ids=references)
    assert not embedder.documents
