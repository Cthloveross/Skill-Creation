"""Build one full-document dense cache in the pinned model-service environment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from r2sp_common import Page

from .data import load_documents
from .dense import (
    DenseIndex,
    HuggingFaceQwenTokenizer,
    OpenAICompatibleEmbeddingClient,
)


def _pages(directory: Path, *, materialized_root: Path) -> tuple[Page, ...]:
    resolved = directory.resolve(strict=True)
    root = materialized_root.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved.name != "documents":
        raise ValueError("dense corpus is outside the full-document materialized root")
    return tuple(
        Page(item.page_id, item.title, item.body, item.content_sha256)
        for item in load_documents(resolved)
    )


def _cache_path(directory: Path, *, dense_root: Path) -> Path:
    resolved = directory.resolve(strict=False)
    root = dense_root.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError("dense cache is outside the full-document dense root")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--hf-home", type=Path, required=True)
    parser.add_argument("--materialized-root", type=Path, required=True)
    parser.add_argument("--dense-root", type=Path, required=True)
    parser.add_argument("--embedding-endpoint", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--dimensions", type=int, required=True)
    args = parser.parse_args()

    tokenizer = HuggingFaceQwenTokenizer.from_pretrained(
        cache_dir=str(args.hf_home / "hub"),
        local_files_only=True,
        model_id=args.model_id,
        revision=args.revision,
        dimensions=args.dimensions,
    )
    client = OpenAICompatibleEmbeddingClient(
        args.embedding_endpoint,
        model_id=args.model_id,
        revision=args.revision,
        dimensions=args.dimensions,
    )
    index = DenseIndex.build(
        _pages(args.documents, materialized_root=args.materialized_root),
        client=client,
        tokenizer=tokenizer,
    )
    destination = _cache_path(args.cache, dense_root=args.dense_root)
    manifest = index.save_cache(destination)
    manifest_path = destination / "manifest.json"
    print(
        json.dumps(
            {
                "status": "SUCCESS",
                "corpus_hash": index.corpus_hash,
                "manifest": manifest,
                "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
