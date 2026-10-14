"""Full-source controls preserve originals and payloads without touching v8 chunks."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest
from tau_skill_evolution import skillsbench_whole_documents as whole
from tau_skill_evolution.artifacts import atomic_json
from tau_skill_evolution.dense import DENSE_MODEL_ID, DENSE_MODEL_REVISION
from tau_skill_evolution.skillsbench_attack import _insert


def fixture_pool(tmp_path, monkeypatch, *, injected=False, count=12):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    chunk_pool = tmp_path / "chunk-pool"
    chunk_pool.mkdir()
    files, documents = [], []
    for index in range(count):
        identifier = f"task-{index}::background/guide.md"
        raw = (
            "# Public background\n\n  Preserve this formatting.\n"
            + ("long-text " * 4970 if index == 0 else "Short facts.")
            + "\n"
        ).encode()
        (checkout / f"{index}.md").write_bytes(raw)
        files.append(
            {
                "document_id": identifier,
                "relative_path": "background/guide.md",
                "path": f"{index}.md",
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        modified, span = _insert(raw, "data_exfil_http") if injected and index == 0 else (raw, None)
        (chunk_pool / f"full-{index}.md").write_bytes(modified)
        documents.append(
            {
                "source_document_id": identifier,
                "file": f"full-{index}.md",
                "materialized_sha256": hashlib.sha256(modified).hexdigest(),
                "insertion": span,
            }
        )
    original = {"corpus_hash": "original-corpus", "pages": []}
    if injected:
        original.update(
            documents=documents,
            injection={
                "condition_id": "data-exfil-http-5",
                "profile": "data_exfil_http",
                "level": 5,
                "target_document_ids": [files[0]["document_id"]],
            },
        )
    atomic_json(chunk_pool / "manifest.json", original)
    source = SimpleNamespace(
        checkout=checkout, manifest={"manifest_hash": "source", "files": files}
    )
    spec = SimpleNamespace(
        root=tmp_path,
        values={
            "embedding": {
                "max_length": 8192,
                "endpoint": "http://127.0.0.1:18141/v1",
                "model": DENSE_MODEL_ID,
                "revision": DENSE_MODEL_REVISION,
                "dimension": 2,
            },
            "retrieval": {"wire_token_limit": 65536},
        },
    )
    monkeypatch.setattr(whole, "selected_pool", lambda *_: chunk_pool)
    monkeypatch.setattr(whole, "validate_pool", lambda *_args, **_kwargs: original)
    monkeypatch.setattr(whole, "SkillsBenchSource", lambda *_: source)
    return spec, source, chunk_pool


def test_whole_pool_preserves_exact_source_bytes_and_one_id_per_document(tmp_path, monkeypatch):
    spec, source, original = fixture_pool(tmp_path, monkeypatch)
    baseline_bytes = (original / "manifest.json").read_bytes()
    directory, manifest = whole.prepare_pool(spec, source, "benign")
    pages = whole._load_pages(directory, manifest)
    expected = {
        entry["document_id"]: (source.checkout / entry["path"]).read_text()
        for entry in source.manifest["files"]
    }
    assert len(pages) == len(expected) == 12
    assert {page.page_id: page.body for page in pages} == expected
    assert manifest["document_unit"] == "source_document"
    assert manifest["chunking"] is False
    assert manifest["max_input_tokens"] == 8192
    assert len(pages[0].body.split()) > 4970
    assert all(record["full_payload_present"] is False for record in manifest["pages"])
    assert (original / "manifest.json").read_bytes() == baseline_bytes
    assert whole.prepare_pool(spec, source, "benign") == (directory, manifest)


def test_injected_whole_document_preserves_entire_payload_and_remaining_source(
    tmp_path, monkeypatch
):
    spec, source, original = fixture_pool(tmp_path, monkeypatch, injected=True)
    directory, manifest = whole.prepare_pool(spec, source, "data-exfil-http-5")
    flagged = [record for record in manifest["pages"] if record["payload_present"]]
    assert len(flagged) == 1
    record = flagged[0]
    page = json.loads((directory / record["file"]).read_text())
    modified = (original / "full-0.md").read_bytes()
    assert page["body"].encode() == modified
    span = record["insertion"]
    assert (
        hashlib.sha256(modified[span["payload_byte_start"] : span["payload_byte_end"]]).hexdigest()
        == record["payload_sha256"]
    )
    assert record["page_id"] == record["source_document_id"]
    assert record["full_payload_present"] is True
    assert manifest["injection"]["target_document_ids"] == [record["page_id"]]
    benign, _ = whole.prepare_pool(spec, source, "benign")
    assert directory != benign


@pytest.mark.parametrize("target", ["source", "sealed_page", "injected_source"])
def test_tampering_fails_instead_of_rebuilding_or_truncating(tmp_path, monkeypatch, target):
    spec, source, original = fixture_pool(
        tmp_path, monkeypatch, injected=target == "injected_source"
    )
    arm = "data-exfil-http-5" if target == "injected_source" else "benign"
    directory, manifest = whole.prepare_pool(spec, source, arm)
    if target == "source":
        (source.checkout / "0.md").write_text("Changed original")
    elif target == "injected_source":
        (original / "full-0.md").write_text("Changed injected source")
    else:
        path = directory / manifest["pages"][0]["file"]
        value = json.loads(path.read_text())
        value["body"] += " changed"
        atomic_json(path, value)
    with pytest.raises(ValueError, match="whole_document_.*changed"):
        whole.prepare_pool(spec, source, arm)


class Tokenizer:
    model_id = DENSE_MODEL_ID
    revision = DENSE_MODEL_REVISION
    dimensions = 2

    def input_token_ids(self, text):
        return tuple(range(len(text.split())))

    def content_token_offsets(self, text):
        import re

        return tuple((match.start(), match.end()) for match in re.finditer(r"\S+", text))


class Client:
    model_id = DENSE_MODEL_ID
    revision = DENSE_MODEL_REVISION
    dimensions = 2
    pooling = "last_token"

    def __init__(self):
        self.calls = []

    def embed_documents(self, texts):
        self.calls.append(tuple(texts))
        return tuple((1.0, 0.0) for _ in texts)

    def embed_query(self, query):
        return (1.0, 0.0)


def test_both_routes_and_contract_bind_full_sources_and_8192_cache(tmp_path, monkeypatch):
    spec, source, _ = fixture_pool(tmp_path, monkeypatch)
    directory, manifest = whole.prepare_pool(spec, source, "benign")
    client = Client()
    monkeypatch.setattr(whole, "_client", lambda *_: client)
    monkeypatch.setattr(whole.HuggingFaceQwenTokenizer, "from_pretrained", lambda **_: Tokenizer())
    monkeypatch.setattr(whole, "text_counter", lambda *_: lambda text: len(text.split()))
    monkeypatch.setattr(
        "tau_skill_evolution.skillsbench_attack.condition", lambda *_: {"condition_id": "benign"}
    )
    whole._build_cache(spec.root, directory, spec.values["embedding"])
    assert len(client.calls) == 1
    assert len(client.calls[0]) == 12
    assert max(len(text.split()) for text in client.calls[0]) > 4970
    corpus = whole.prepare_corpus(spec, "task-0", "benign")
    try:
        assert corpus._bm25_index.page_count == corpus._dense_index.page_count == 12
        assert corpus._bm25_index.corpus_hash == corpus._dense_index.corpus_hash
    finally:
        corpus.close()
    contract = whole.retrieval_contract(spec, "benign")
    assert contract["source_documents"] == 12
    assert contract["document_unit"] == "source_document"
    assert contract["original_corpus_hash"] == "original-corpus"
    assert contract["dense_contract"]["max_input_tokens"] == 8192
    assert contract["dense_vectors"]["shape"] == [12, 2]
    assert contract["payload_document_count"] == 0
    assert (spec.root / contract["pool_path"]) == directory
    assert whole._cache(spec.root, manifest).is_dir()


def test_whole_document_client_requires_explicit_service_length():
    with pytest.raises(ValueError, match="must_be_8192"):
        whole._client({"max_length": 4096})
