"""Reuse the existing materializer and whole-document hybrid retriever."""

from __future__ import annotations

import errno
import fcntl
import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from tau_skill_evolution.core import DeterministicBM25, FullDocumentHybridSession, Page

from .data import load_documents
from .dense import DenseIndex, OpenAICompatibleEmbeddingClient
from .materialize import CorpusMaterializer
from .model import VllmTextTokenCounter
from .spec import ExperimentSpec, digest


def publish_cache(output: Path, cache: Path) -> None:
    """Publish a built index; a concurrent identical publication wins untouched."""
    try:
        output.rename(cache)
    except OSError as exc:
        if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY} or not cache.exists():
            raise


def ensure_cache(cache: Path, build: Callable[[Path], None]) -> Path:
    """Build ``cache`` at most once across concurrent processes.

    Holding ``<cache>.lock`` serialises builders of the same key (many cells
    share one benign corpus); the staging directory lives beside the cache so
    the final rename is atomic.
    """
    if cache.exists():
        return cache
    with (cache.parent / f"{cache.name}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not cache.exists():
            with tempfile.TemporaryDirectory(prefix="build-", dir=cache.parent) as staging:
                output = Path(staging) / "index"
                build(output)
                publish_cache(output, cache)
    return cache


def embedding_argv(spec: ExperimentSpec) -> list[str]:
    embedding = spec.values["embedding"]
    cache = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface")))
    owner, model = embedding["model"].split("/", 1)
    snapshot = cache / "hub" / f"models--{owner}--{model}" / "snapshots" / embedding["revision"]
    return [
        str((spec.root / embedding["vllm"]).absolute()),
        "serve",
        str(snapshot),
        "--served-model-name",
        embedding["model"],
        "--runner",
        "pooling",
        "--pooler-config",
        '{"enable_chunked_processing":false,"pooling_type":"LAST","use_activation":true}',
        "--host",
        "127.0.0.1",
        "--port",
        embedding["endpoint"].rsplit(":", 1)[1].split("/")[0],
        "--dtype",
        embedding["dtype"],
        "--max-model-len",
        str(embedding["max_length"]),
        "--tensor-parallel-size",
        "1",
        "--pipeline-parallel-size",
        "1",
        "--gpu-memory-utilization",
        str(embedding["gpu_memory_utilization"]),
        "--max-num-seqs",
        "32",
    ]


def text_counter(spec: ExperimentSpec) -> VllmTextTokenCounter:
    embedding = spec.values["embedding"]
    return VllmTextTokenCounter(
        embedding["endpoint"],
        model=embedding["model"],
        timeout_seconds=spec.values["runtime"]["request_timeout_seconds"],
    )


def prepare_corpus(spec: ExperimentSpec, task: str, arm: str) -> FullDocumentHybridSession:
    if spec.experiment == "skillsbench":
        if arm != "benign":
            raise ValueError("SkillsBench supports only benign")
        from .skillsbench import prepare_corpus as prepare_skillsbench_corpus

        return prepare_skillsbench_corpus(spec)
    embedding = spec.values["embedding"]
    materializer = CorpusMaterializer(
        source_documents=spec.upstream
        / "data"
        / "tau2"
        / "domains"
        / "banking_knowledge"
        / "documents",
        output_root=spec.root / "data" / "materialized",
        injections_root=spec.root / "injections",
    )
    materialization = materializer.materialize(
        "mock-api-call" if arm == "benign" else spec.profile(task),
        "benign" if arm == "benign" else "poison",
        payload_snapshot=materializer.snapshot_payloads(),
        target_document_ids=spec.targets(arm) or spec.targets("poison-5")[:1],
    )
    documents = materialization.output_root / "documents"
    pages = tuple(
        Page(item.page_id, item.title, item.body, item.content_sha256)
        for item in load_documents(documents)
    )
    key = digest({"corpus": materialization.corpus_sha256, "embedding": embedding})
    dense_root = spec.root / "data" / "dense"
    dense_root.mkdir(parents=True, exist_ok=True)
    cache = dense_root / key

    def build(output: Path) -> None:
        vllm = (spec.root / embedding["vllm"]).absolute()
        command = [
            str(vllm.parent / "python"),
            "-m",
            "tau_skill_evolution.dense_worker",
            "--documents",
            str(documents),
            "--cache",
            str(output),
            "--hf-home",
            os.environ.get("HF_HOME", str(Path.home() / ".cache/huggingface")),
            "--materialized-root",
            str(spec.root / "data" / "materialized"),
            "--dense-root",
            str(dense_root),
            "--embedding-endpoint",
            embedding["endpoint"],
            "--model-id",
            embedding["model"],
            "--revision",
            embedding["revision"],
            "--dimensions",
            str(embedding["dimension"]),
        ]
        env = {**os.environ, "PYTHONPATH": str(spec.root / "src")}
        subprocess.run(
            command,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=spec.values["runtime"]["episode_timeout_seconds"],
        )

    ensure_cache(cache, build)
    client = OpenAICompatibleEmbeddingClient(
        embedding["endpoint"],
        model_id=embedding["model"],
        revision=embedding["revision"],
        dimensions=embedding["dimension"],
    )
    dense = DenseIndex.load_cache(cache, pages, client=client)
    return FullDocumentHybridSession(
        DeterministicBM25(pages),
        dense,
        text_counter(spec),
        wire_token_budget=spec.values["retrieval"]["wire_token_limit"],
    )
