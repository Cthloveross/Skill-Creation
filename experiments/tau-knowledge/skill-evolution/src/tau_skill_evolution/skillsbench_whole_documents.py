"""Whole-source-document retrieval control; the frozen v8 chunk pools stay unchanged."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from tau_skill_evolution.artifacts import atomic_json
from tau_skill_evolution.core import DeterministicBM25, FullDocumentHybridSession, Page
from tau_skill_evolution.core._canonical import canonical_json_sha256
from tau_skill_evolution.dense import (
    DenseIndex,
    HuggingFaceQwenTokenizer,
    OpenAICompatibleEmbeddingClient,
)
from tau_skill_evolution.retrieval import ensure_cache, text_counter
from tau_skill_evolution.skillsbench import SkillsBenchSource, selected_pool, validate_pool

MAX_INPUT_TOKENS = 8192
SCHEMA = "skillsbench.pool.whole-documents.research.v1"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hash(value: Any) -> str:
    return _sha(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


def _path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("whole_document_path_outside_source")
    return path


def _load_pages(directory: Path, manifest: dict[str, Any]) -> tuple[Page, ...]:
    if manifest.get("corpus_hash") != _hash(
        {key: value for key, value in manifest.items() if key != "corpus_hash"}
    ):
        raise ValueError("whole_document_manifest_changed")
    pages = []
    identifiers = set()
    for record in manifest["pages"]:
        value = json.loads(_path(directory, record["file"]).read_text())
        if (
            value.get("page_id") != value.get("source_document_id")
            or value.get("page_id") in identifiers
            or _sha(value["body"].encode()) != value.get("content_sha256")
            or any(value.get(key) != item for key, item in record.items() if key != "file")
        ):
            raise ValueError("whole_document_page_changed")
        identifiers.add(value["page_id"])
        pages.append(Page(value["page_id"], value["title"], value["body"], value["content_sha256"]))
    return tuple(pages)


def prepare_pool(spec: Any, source: Any, arm: str) -> tuple[Path, dict[str, Any]]:
    """Seal exactly one full, untruncated Page per original background source."""
    original_directory = selected_pool(spec, arm)
    original = validate_pool(spec.root, source, directory=original_directory)
    originals = {
        entry["document_id"]: entry
        for entry in source.manifest["files"]
        if entry["relative_path"].startswith("background/")
    }
    modified = {item["source_document_id"]: item for item in original.get("documents", [])}
    if arm != "benign" and set(modified) != set(originals):
        raise ValueError("whole_document_injected_sources_incomplete")
    pages = []
    for identifier, entry in sorted(originals.items()):
        raw = _path(source.checkout, entry["path"]).read_bytes()
        if _sha(raw) != entry["sha256"]:
            raise ValueError("whole_document_source_changed")
        document = modified.get(identifier)
        span = None
        if document is not None:
            raw = _path(original_directory, document["file"]).read_bytes()
            if _sha(raw) != document["materialized_sha256"]:
                raise ValueError("whole_document_injected_source_changed")
            span = document.get("insertion")
            if (
                span is not None
                and _sha(raw[span["payload_byte_start"] : span["payload_byte_end"]])
                != span["payload_sha256"]
            ):
                raise ValueError("whole_document_payload_span_changed")
        page = {
            "page_id": identifier,
            "source_document_id": identifier,
            "title": identifier,
            "body": raw.decode("utf-8"),
            "content_sha256": _sha(raw),
            "source_sha256": entry["sha256"],
            "source_poisoned": span is not None,
            "payload_present": span is not None,
            "full_payload_present": span is not None,
        }
        if span is not None:
            page.update(payload_sha256=span["payload_sha256"], insertion=span)
        pages.append(page)
    request = {
        "schema": SCHEMA,
        "document_unit": "source_document",
        "chunking": False,
        "max_input_tokens": MAX_INPUT_TOKENS,
        "source_manifest_hash": source.manifest["manifest_hash"],
        "original_corpus_hash": original["corpus_hash"],
        "original_pool_manifest_sha256": _sha((original_directory / "manifest.json").read_bytes()),
        "condition_id": arm,
        "page_descriptors": [
            {key: value for key, value in page.items() if key != "body"} for page in pages
        ],
    }
    destination = Path(spec.root) / "data/skillsbench/whole-documents" / _hash(request)
    destination.parent.mkdir(parents=True, exist_ok=True)

    def build(output: Path) -> None:
        (output / "pages").mkdir(parents=True)
        records = []
        for page in pages:
            filename = "pages/" + _sha(page["page_id"].encode()) + ".json"
            atomic_json(output / filename, page)
            records.append({"file": filename, **{k: v for k, v in page.items() if k != "body"}})
        manifest = {
            **{key: value for key, value in request.items() if key != "page_descriptors"},
            "scope": "background_docs_only",
            "source_documents": len(pages),
            "pages": records,
        }
        if "injection" in original:
            manifest["injection"] = original["injection"]
        manifest["corpus_hash"] = _hash(manifest)
        atomic_json(output / "manifest.json", manifest)

    ensure_cache(destination, build)
    manifest = json.loads((destination / "manifest.json").read_text())
    if (
        any(
            manifest.get(key) != value
            for key, value in request.items()
            if key != "page_descriptors"
        )
        or [
            {key: value for key, value in record.items() if key != "file"}
            for record in manifest["pages"]
        ]
        != request["page_descriptors"]
    ):
        raise ValueError("whole_document_sealed_pool_changed")
    actual = _load_pages(destination, manifest)
    expected = tuple(
        Page(page["page_id"], page["title"], page["body"], page["content_sha256"]) for page in pages
    )
    if actual != expected:
        raise ValueError("whole_document_sealed_pool_changed")
    return destination, manifest


def _client(embedding: dict[str, Any]) -> OpenAICompatibleEmbeddingClient:
    if embedding["max_length"] != MAX_INPUT_TOKENS:
        raise ValueError("whole_document_embedding_limit_must_be_8192")
    return OpenAICompatibleEmbeddingClient(
        embedding["endpoint"],
        model_id=embedding["model"],
        revision=embedding["revision"],
        dimensions=embedding["dimension"],
    )


def _cache(root: Path, manifest: dict[str, Any]) -> Path:
    return root / "data/skillsbench/whole-documents-dense" / manifest["corpus_hash"]


def _build_cache(root: Path, directory: Path, embedding: dict[str, Any]) -> None:
    manifest = json.loads((directory / "manifest.json").read_text())
    pages = _load_pages(directory, manifest)
    client = _client(embedding)
    hf_cache = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache/huggingface")))
    tokenizer = HuggingFaceQwenTokenizer.from_pretrained(
        cache_dir=str(hf_cache / "hub"),
        local_files_only=True,
        model_id=embedding["model"],
        revision=embedding["revision"],
        dimensions=embedding["dimension"],
    )
    cache = _cache(root, manifest)
    cache.parent.mkdir(parents=True, exist_ok=True)
    ensure_cache(
        cache,
        lambda output: DenseIndex.build(
            pages, client=client, tokenizer=tokenizer, max_input_tokens=MAX_INPUT_TOKENS
        ).save_cache(output),
    )
    DenseIndex.load_cache(
        cache,
        pages,
        client=client,
        tokenizer=tokenizer,
        max_input_tokens=MAX_INPUT_TOKENS,
    )


def prepare_corpus(spec: Any, task: str, arm: str) -> FullDocumentHybridSession:
    """Use full source documents in both routes; never expand chunk search hits."""
    del task
    directory, manifest = prepare_pool(spec, SkillsBenchSource(spec.root), arm)
    pages = _load_pages(directory, manifest)
    embedding = spec.values["embedding"]
    client = _client(embedding)
    cache = _cache(Path(spec.root), manifest)
    if not cache.exists():
        environment = dict(os.environ)
        source_path = str(Path(__file__).resolve().parents[1])
        environment["PYTHONPATH"] = source_path + os.pathsep + environment.get("PYTHONPATH", "")
        subprocess.run(
            [
                str((Path(spec.root) / embedding["vllm"]).parent / "python"),
                "-m",
                "tau_skill_evolution.skillsbench_whole_documents",
                "--root",
                str(spec.root),
                "--pool-directory",
                str(directory),
                "--embedding",
                json.dumps(embedding),
            ],
            env=environment,
            check=True,
            capture_output=True,
            timeout=900,
        )
    dense = DenseIndex.load_cache(cache, pages, client=client, max_input_tokens=MAX_INPUT_TOKENS)
    return FullDocumentHybridSession(
        DeterministicBM25(pages),
        dense,
        text_counter(spec),
        wire_token_budget=spec.values["retrieval"]["wire_token_limit"],
    )


def retrieval_contract(spec: Any, arm: str) -> dict[str, Any]:
    """Bind full-source bytes and both indexes to the acquisition-only trial."""
    directory, manifest = prepare_pool(spec, SkillsBenchSource(spec.root), arm)
    pages = _load_pages(directory, manifest)
    cache = _cache(Path(spec.root), manifest)
    dense = DenseIndex.load_cache(
        cache, pages, client=_client(spec.values["embedding"]), max_input_tokens=MAX_INPUT_TOKENS
    )
    cache_manifest = json.loads((cache / "manifest.json").read_text())
    from tau_skill_evolution.skillsbench_attack import condition

    descriptors = [
        {"page_id": page.page_id, "title": page.title, "content_sha256": page.content_sha256}
        for page in pages
    ]
    return {
        "condition": condition(spec, arm),
        "document_unit": "source_document",
        "chunking": False,
        "pool_path": str(directory.relative_to(spec.root)),
        "pool_manifest_sha256": _sha((directory / "manifest.json").read_bytes()),
        "corpus_hash": manifest["corpus_hash"],
        "source_manifest_hash": manifest["source_manifest_hash"],
        "original_corpus_hash": manifest["original_corpus_hash"],
        "original_pool_manifest_sha256": manifest["original_pool_manifest_sha256"],
        "page_count": len(pages),
        "source_documents": len(pages),
        "page_set_hash": canonical_json_sha256(descriptors),
        "bm25_identity": _hash({"implementation": "DeterministicBM25", "pages": descriptors}),
        "dense_manifest_sha256": _sha((cache / "manifest.json").read_bytes()),
        "dense_manifest_payload_sha256": cache_manifest["manifest_payload_sha256"],
        "dense_contract": dense.manifest,
        "dense_vectors": cache_manifest["vectors"],
        "embedding": {
            "model": spec.values["embedding"]["model"],
            "revision": spec.values["embedding"]["revision"],
            "dimensions": spec.values["embedding"]["dimension"],
            "max_input_tokens": MAX_INPUT_TOKENS,
            "endpoint": spec.values["embedding"]["endpoint"],
        },
        "payload_document_count": sum(
            item.get("payload_present", False) for item in manifest["pages"]
        ),
        "full_payload_document_count": sum(
            item.get("full_payload_present", False) for item in manifest["pages"]
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--pool-directory", type=Path, required=True)
    parser.add_argument("--embedding", required=True)
    arguments = parser.parse_args()
    _build_cache(arguments.root, arguments.pool_directory, json.loads(arguments.embedding))
