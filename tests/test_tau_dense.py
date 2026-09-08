from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.error

import pytest

from r2sp_common.protocol import Page, PageSnippet
from r2sp_tau_knowledge.dense import (
    DENSE_CACHE_MANIFEST,
    DENSE_CACHE_SCHEMA_VERSION,
    DENSE_CACHE_VECTORS,
    DENSE_DOCUMENT_FORMAT,
    DENSE_EMBEDDING_DIMENSIONS,
    DENSE_MAX_INPUT_TOKENS,
    DENSE_MODEL_ID,
    DENSE_MODEL_REVISION,
    DENSE_SNIPPET_TOKENS,
    QUERY_INSTRUCTION,
    DenseContractError,
    DenseIndex,
    DenseInputTooLongError,
    DenseServiceError,
    HuggingFaceQwenTokenizer,
    OpenAICompatibleEmbeddingClient,
    format_query,
)


def _vector(*values: tuple[int, float]) -> tuple[float, ...]:
    result = [0.0] * DENSE_EMBEDDING_DIMENSIONS
    for index, value in values:
        result[index] = value
    return tuple(result)


class _Tokenizer:
    model_id = DENSE_MODEL_ID
    revision = DENSE_MODEL_REVISION
    dimensions = DENSE_EMBEDDING_DIMENSIONS

    def __init__(self) -> None:
        self.inputs: list[str] = []

    def input_token_ids(self, text: str) -> tuple[int, ...]:
        self.inputs.append(text)
        return tuple(range(len(tuple(re.finditer(r"\S+", text)))))

    def content_token_offsets(self, text: str) -> tuple[tuple[int, int], ...]:
        return tuple((match.start(), match.end()) for match in re.finditer(r"\S+", text))


class _Client:
    model_id = DENSE_MODEL_ID
    revision = DENSE_MODEL_REVISION
    pooling = "last_token"
    dimensions = DENSE_EMBEDDING_DIMENSIONS

    def __init__(
        self,
        document_vectors: dict[str, tuple[float, ...]] | None = None,
        query_vector: tuple[float, ...] | None = None,
    ) -> None:
        self.document_vectors = document_vectors or {}
        self.query_vector = query_vector or _vector((0, 1.0))
        self.document_calls: list[tuple[str, ...]] = []
        self.query_calls: list[str] = []
        self.instructed_queries: list[str] = []

    def embed_documents(self, texts):
        values = tuple(texts)
        self.document_calls.append(values)
        return tuple(self.document_vectors.get(text, _vector((0, 1.0))) for text in values)

    def embed_query(self, query):
        self.query_calls.append(query)
        self.instructed_queries.append(format_query(query))
        return self.query_vector


def _pages(*bodies: str) -> tuple[Page, ...]:
    return tuple(Page(f"doc-{index}", f"Title {index}", body) for index, body in enumerate(bodies))


def test_fixed_query_instruction_has_no_space_after_query_colon() -> None:
    assert format_query("gold card") == (
        "Instruct: Given a web search query, retrieve relevant passages that answer the query\n"
        "Query:gold card"
    )
    assert QUERY_INSTRUCTION.endswith("Query:")
    with pytest.raises(ValueError):
        format_query("   ")


def test_build_preflights_every_document_before_any_embedding_call() -> None:
    client = _Client()
    tokenizer = _Tokenizer()
    # The two-token title plus this body exceed the limit by one token.
    too_long = " ".join("token" for _ in range(DENSE_MAX_INPUT_TOKENS - 1))

    with pytest.raises(DenseInputTooLongError, match="doc-1 has 4097 tokens"):
        DenseIndex.build(_pages("short", too_long), client=client, tokenizer=tokenizer)

    assert client.document_calls == []
    assert tokenizer.inputs == ["Title 0\n\nshort", f"Title 1\n\n{too_long}"]


def test_build_embeds_exact_titles_and_whole_bodies_and_records_pinned_manifest() -> None:
    bodies = ("alpha body\nwith formatting", "beta body")
    client = _Client()
    index = DenseIndex.build(_pages(*bodies), client=client, tokenizer=_Tokenizer())

    assert client.document_calls == [
        (
            "Title 0\n\nalpha body\nwith formatting",
            "Title 1\n\nbeta body",
        )
    ]
    assert index.page_count == 2
    assert index.manifest["schema_version"] == DENSE_CACHE_SCHEMA_VERSION
    assert index.manifest["model_id"] == DENSE_MODEL_ID
    assert index.manifest["model_revision"] == DENSE_MODEL_REVISION
    assert index.manifest["tokenizer_revision"] == DENSE_MODEL_REVISION
    assert index.manifest["max_input_tokens"] == 4096
    assert index.manifest["document_format"] == DENSE_DOCUMENT_FORMAT
    assert index.manifest["whole_document"] is True
    assert index.manifest["chunking"] is False
    assert index.manifest["reranker"] is False
    assert index.manifest["approximate_index"] is False


def test_snippet_is_exact_original_prefix_through_qwen_token_256() -> None:
    body = "  " + " \n ".join(f"token-{index:03d}" for index in range(300)) + "  tail-space"
    index = DenseIndex.build(_pages(body), client=_Client(), tokenizer=_Tokenizer())
    expected_end = tuple(re.finditer(r"\S+", body))[DENSE_SNIPPET_TOKENS - 1].end()

    snippet = index.snippet_for("doc-0")

    assert snippet == PageSnippet(text=body[:expected_end], truncated=True)
    assert index.snippet_for(index.get_page("doc-0")) == snippet
    assert body.startswith(snippet.text)
    assert len(tuple(re.finditer(r"\S+", snippet.text))) == 256


def test_short_snippet_returns_exact_complete_body() -> None:
    body = "  preserve leading and trailing whitespace  "
    index = DenseIndex.build(_pages(body), client=_Client(), tokenizer=_Tokenizer())

    assert index.snippet_for("doc-0") == PageSnippet(text=body, truncated=False)


def test_search_is_exhaustive_normalized_cosine_with_page_id_tie_break() -> None:
    bodies = ("same-a", "orthogonal", "same-b")
    client = _Client(
        {
            "A\n\nsame-a": _vector((0, 7.0)),
            "M\n\northogonal": _vector((1, 11.0)),
            "Query term only in title\n\nsame-b": _vector((0, 2.0)),
        },
        query_vector=_vector((0, 19.0)),
    )
    # Supply deliberately unordered pages; construction fixes page_id ordering.
    pages = (
        Page("z", "Query term only in title", bodies[2]),
        Page("a", "A", bodies[0]),
        Page("m", "M", bodies[1]),
    )
    index = DenseIndex.build(pages, client=client, tokenizer=_Tokenizer())

    hits = index.search("find same", limit=3)

    assert [hit.page_id for hit in hits] == ["a", "z", "m"]
    assert hits[0].score == pytest.approx(1.0)
    assert hits[1].score == pytest.approx(1.0)
    assert hits[2].score == pytest.approx(0.0)
    assert client.query_calls == ["find same"]
    assert client.instructed_queries == [format_query("find same")]
    assert all(math.isfinite(hit.score) for hit in hits)


@pytest.mark.parametrize(
    "vector",
    [
        (0.0,) * (DENSE_EMBEDDING_DIMENSIONS - 1),
        (0.0,) * DENSE_EMBEDDING_DIMENSIONS,
        (math.nan,) + (0.0,) * (DENSE_EMBEDDING_DIMENSIONS - 1),
        (math.inf,) + (0.0,) * (DENSE_EMBEDDING_DIMENSIONS - 1),
    ],
)
def test_malformed_or_zero_document_embedding_is_rejected(vector) -> None:
    client = _Client({"Title 0\n\nbody": vector})
    with pytest.raises(DenseContractError):
        DenseIndex.build(_pages("body"), client=client, tokenizer=_Tokenizer())


def test_query_length_is_checked_before_query_embedding_request() -> None:
    client = _Client()
    index = DenseIndex.build(_pages("body"), client=client, tokenizer=_Tokenizer())
    long_query = " ".join("query" for _ in range(DENSE_MAX_INPUT_TOKENS + 1))

    with pytest.raises(DenseInputTooLongError):
        index.search(long_query)

    assert client.query_calls == []


def test_canonical_cache_load_skips_document_embedding_and_supports_no_tokenizer(
    tmp_path,
) -> None:
    pages = _pages("alpha", "beta")
    built = DenseIndex.build(pages, client=_Client(), tokenizer=_Tokenizer())
    cache_dir = tmp_path / "dense-cache"

    manifest = built.save_cache(cache_dir)
    manifest_bytes = (cache_dir / DENSE_CACHE_MANIFEST).read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    query_client = _Client(query_vector=_vector((0, 1.0)))
    loaded = DenseIndex.load_cache(
        cache_dir,
        pages,
        client=query_client,
        tokenizer=None,
        expected_manifest_sha256=manifest_sha256,
    )

    assert manifest["contract"]["page_count"] == 2
    assert (
        manifest_bytes
        == json.dumps(
            manifest,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    assert (cache_dir / DENSE_CACHE_VECTORS).stat().st_size == (2 * DENSE_EMBEDDING_DIMENSIONS * 4)
    assert loaded.corpus_hash == built.corpus_hash
    assert loaded.snippet_for("doc-0") == built.snippet_for("doc-0")
    assert query_client.document_calls == []
    assert loaded.search("alpha", limit=1)[0].page_id == "doc-0"
    assert query_client.query_calls == ["alpha"]


def test_cache_can_optionally_revalidate_token_counts_and_snippets(tmp_path) -> None:
    pages = _pages("alpha beta", "gamma delta")
    built = DenseIndex.build(pages, client=_Client(), tokenizer=_Tokenizer())
    cache_dir = tmp_path / "dense-cache"
    built.save_cache(cache_dir)

    tokenizer = _Tokenizer()
    loaded = DenseIndex.load_cache(
        cache_dir,
        pages,
        client=_Client(),
        tokenizer=tokenizer,
    )

    assert loaded.page_count == 2
    assert tokenizer.inputs == ["Title 0\n\nalpha beta", "Title 1\n\ngamma delta"]


def test_cache_rejects_vector_manifest_or_current_corpus_tampering(tmp_path) -> None:
    pages = _pages("alpha", "beta")
    built = DenseIndex.build(pages, client=_Client(), tokenizer=_Tokenizer())

    vector_cache = tmp_path / "vectors-tampered"
    built.save_cache(vector_cache)
    vector_path = vector_cache / DENSE_CACHE_VECTORS
    raw = bytearray(vector_path.read_bytes())
    raw[0] ^= 1
    vector_path.write_bytes(raw)
    with pytest.raises(DenseContractError, match="vector hash mismatch"):
        DenseIndex.load_cache(vector_cache, pages, client=_Client())

    manifest_cache = tmp_path / "manifest-tampered"
    built.save_cache(manifest_cache)
    manifest_path = manifest_cache / DENSE_CACHE_MANIFEST
    sealed_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    with pytest.raises(DenseContractError, match="manifest file hash mismatch"):
        DenseIndex.load_cache(
            manifest_cache,
            pages,
            client=_Client(),
            expected_manifest_sha256=sealed_hash,
        )

    corpus_cache = tmp_path / "corpus-tampered"
    built.save_cache(corpus_cache)
    changed_pages = (Page("doc-0", "Title 0", "changed"), pages[1])
    with pytest.raises(DenseContractError, match="corpus hash"):
        DenseIndex.load_cache(corpus_cache, changed_pages, client=_Client())


def test_cache_refuses_to_overwrite_existing_artifacts(tmp_path) -> None:
    index = DenseIndex.build(_pages("body"), client=_Client(), tokenizer=_Tokenizer())
    cache_dir = tmp_path / "cache"
    index.save_cache(cache_dir)

    with pytest.raises(DenseContractError, match="refusing to overwrite"):
        index.save_cache(cache_dir)


def test_index_rejects_client_tokenizer_identity_mismatch() -> None:
    client = _Client()
    client.revision = "moving-main"
    with pytest.raises(DenseContractError, match="tokenizer revision"):
        DenseIndex.build(_pages("body"), client=client, tokenizer=_Tokenizer())

    tokenizer = _Tokenizer()
    tokenizer.revision = "moving-main"
    with pytest.raises(DenseContractError, match="tokenizer revision"):
        DenseIndex.build(_pages("body"), client=_Client(), tokenizer=tokenizer)


def test_custom_model_identity_and_dimensions_are_bound_to_cache(tmp_path) -> None:
    model_id = "Qwen/Qwen3-Embedding-4B"
    revision = "5cf2132abc99cad020ac570b19d031efec650f2b"
    dimensions = 4
    document_text = "Title 0\n\nbody"
    client = _Client(
        {document_text: (3.0, 0.0, 0.0, 0.0)},
        query_vector=(2.0, 0.0, 0.0, 0.0),
    )
    client.model_id = model_id
    client.revision = revision
    client.dimensions = dimensions
    tokenizer = _Tokenizer()
    tokenizer.model_id = model_id
    tokenizer.revision = revision
    tokenizer.dimensions = dimensions

    index = DenseIndex.build(_pages("body"), client=client, tokenizer=tokenizer)
    cache = tmp_path / "4b-cache"
    manifest = index.save_cache(cache)

    assert index.manifest["model_id"] == model_id
    assert index.manifest["model_revision"] == revision
    assert index.manifest["dimensions"] == dimensions
    assert manifest["vectors"]["shape"] == [1, dimensions]
    assert (cache / DENSE_CACHE_VECTORS).stat().st_size == dimensions * 4
    with pytest.raises(DenseContractError, match="different retrieval contract"):
        DenseIndex.load_cache(cache, _pages("body"), client=_Client())


def test_concrete_tokenizer_and_client_accept_explicit_model_identity() -> None:
    class _FastTokenizer:
        is_fast = True

        def encode(self, *_args, **_kwargs):
            return [1]

        def __call__(self, *_args, **_kwargs):
            return {"input_ids": [1], "offset_mapping": [(0, 1)]}

    identity = {
        "model_id": "Qwen/Qwen3-Embedding-4B",
        "revision": "5cf2132abc99cad020ac570b19d031efec650f2b",
        "dimensions": 2560,
    }
    tokenizer = HuggingFaceQwenTokenizer(_FastTokenizer(), **identity)
    client = OpenAICompatibleEmbeddingClient(**identity)

    assert (tokenizer.model_id, tokenizer.revision, tokenizer.dimensions) == (
        client.model_id,
        client.revision,
        client.dimensions,
    )


class _Response:
    def __init__(self, payload) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


def test_loopback_client_applies_instruction_batches_and_reorders_indices() -> None:
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        payload = json.loads(request.data)
        data = [
            {"index": index, "embedding": list(_vector((index, 1.0)))}
            for index in reversed(range(len(payload["input"])))
        ]
        return _Response({"object": "list", "data": data})

    client = OpenAICompatibleEmbeddingClient(
        "http://127.0.0.1:18140/v1", batch_size=2, opener=opener
    )

    documents = client.embed_documents(("one", "two", "three"))
    query = client.embed_query("banking query")

    assert len(documents) == 3
    assert documents[0][0] == 1.0
    assert documents[1][1] == 1.0
    assert documents[2][0] == 1.0
    assert query[0] == 1.0
    assert [item[0].full_url for item in requests] == [
        "http://127.0.0.1:18140/v1/embeddings",
        "http://127.0.0.1:18140/v1/embeddings",
        "http://127.0.0.1:18140/v1/embeddings",
    ]
    assert json.loads(requests[-1][0].data)["input"] == [format_query("banking query")]
    assert json.loads(requests[0][0].data)["input"] == ["one", "two"]
    assert json.loads(requests[0][0].data)["model"] == DENSE_MODEL_ID
    assert json.loads(requests[0][0].data)["encoding_format"] == "float"
    assert "dimensions" not in json.loads(requests[0][0].data)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:18140/v1",
        "http://localhost:18140/v1",
        "http://192.0.2.1:18140/v1",
        "http://user:secret@127.0.0.1:18140/v1",
        "http://127.0.0.1/v1",
    ],
)
def test_embedding_client_rejects_every_nonliteral_loopback_endpoint(url: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        OpenAICompatibleEmbeddingClient(url)


def test_embedding_client_fails_closed_on_transport_or_malformed_response() -> None:
    def transport_failure(*_args, **_kwargs):
        raise urllib.error.URLError("offline")

    with pytest.raises(DenseServiceError, match="offline") as transport:
        OpenAICompatibleEmbeddingClient(opener=transport_failure).embed_query("query")
    assert transport.value.code == "transport_error"

    client = OpenAICompatibleEmbeddingClient(opener=lambda *_args, **_kwargs: _Response(b"{"))
    with pytest.raises(DenseServiceError, match="invalid JSON") as invalid_json:
        client.embed_query("query")
    assert invalid_json.value.code == "invalid_json"

    malformed = {"data": [{"index": 0, "embedding": [1.0, 2.0]}]}
    client = OpenAICompatibleEmbeddingClient(opener=lambda *_args, **_kwargs: _Response(malformed))
    with pytest.raises(DenseServiceError, match="dimension") as invalid_vector:
        client.embed_query("query")
    assert invalid_vector.value.code == "invalid_response"
