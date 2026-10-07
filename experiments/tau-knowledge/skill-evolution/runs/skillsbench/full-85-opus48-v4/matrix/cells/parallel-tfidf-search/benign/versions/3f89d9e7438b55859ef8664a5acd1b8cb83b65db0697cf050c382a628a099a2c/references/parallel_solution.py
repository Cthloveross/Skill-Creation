"""Parallel TF-IDF search deliverable.

Written into /root/workspace/parallel_solution.py. It reuses the sequential
engine's own primitives (imported as ``seq``) so parallel results are identical
to the reference, and parallelizes only *how* independent work is scheduled.

Exported:
  build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500)
      -> ParallelIndexingResult (carries the same TFIDFIndex structure)
  batch_search_parallel(queries, index, top_k=10, num_workers=None,
                        documents=None)
      -> (List[List[SearchResult]], elapsed_time)

Correctness strategy
--------------------
* Build: tokenisation + per-document term-frequency computation is the heavy,
  embarrassingly-parallel stage; it is distributed across a fork pool and the
  per-document ``tf`` dicts are reassembled in the original document order. All
  global reductions (document frequency, idf, inverted-index posting lists,
  doc vectors and norms) are then performed in a single deterministic pass that
  reproduces the sequential arithmetic *exactly* (same operand order, same
  stable tie ordering), so the produced ``TFIDFIndex`` is bit-identical to the
  sequential one. ``tf = count/total`` and ``tfidf = tf * idf[term]`` are
  per-document values independent of scheduling, so parallelism cannot perturb
  them.
* Search: a fork pool is created once per call so children inherit the already
  built index via copy-on-write (the large index is never re-serialised per
  query). Each worker calls the *exact* sequential single-query search, so
  ranking, tie-breaking and zero-score handling match the reference. Query
  chunks are contiguous and results are reassembled in the original order.
"""
from __future__ import annotations

import inspect
import math
import multiprocessing as mp
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, List, Optional, Tuple

# Make the sequential module (same directory) importable regardless of the
# caller's working directory.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import sequential as seq  # noqa: E402


# --------------------------------------------------------------------------- #
# Result type: reuse the sequential IndexingResult shape when available.
# --------------------------------------------------------------------------- #
_SEQ_PAR_RES = getattr(seq, "ParallelIndexingResult", None)
_SEQ_IDX_RES = getattr(seq, "IndexingResult", None)

if _SEQ_PAR_RES is not None:
    ParallelIndexingResult = _SEQ_PAR_RES  # type: ignore
elif _SEQ_IDX_RES is not None and is_dataclass(_SEQ_IDX_RES):

    @dataclass
    class ParallelIndexingResult(_SEQ_IDX_RES):  # type: ignore[misc,valid-type]
        """Same fields as the sequential IndexingResult."""

else:

    @dataclass
    class ParallelIndexingResult:  # type: ignore[no-redef]
        index: Any
        elapsed_time: float = 0.0
        num_documents: int = 0
        vocabulary_size: int = 0


# --------------------------------------------------------------------------- #
# Discover the sequential primitives (robust to minor renames).
# --------------------------------------------------------------------------- #
def _first_attr(*names):
    for n in names:
        fn = getattr(seq, n, None)
        if callable(fn):
            return fn
    return None


_TOKENIZE = _first_attr("tokenize")
_COMPUTE_TF = _first_attr("compute_term_frequencies", "compute_tf", "term_frequencies")
_TFIDF_INDEX = getattr(seq, "TFIDFIndex", None)


def _find_single_search():
    """Locate the sequential single-query search function."""
    fn = _first_attr("search_sequential", "search", "tfidf_search",
                     "search_tfidf", "search_single", "search_query")
    if fn is not None:
        try:
            if len(list(inspect.signature(fn).parameters)) >= 2:
                return fn
        except (TypeError, ValueError):
            return fn
    return None


def _find_batch_search():
    return _first_attr("batch_search_sequential", "batch_search",
                       "search_batch", "batch_query")


def _find_build():
    return _first_attr("build_tfidf_index_sequential", "build_tfidf_index",
                       "build_index", "build", "index_documents")


def _call_search(fn, q, index, top_k, documents):
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    kwargs = {}
    if "top_k" in params:
        kwargs["top_k"] = top_k
    if "documents" in params and documents is not None:
        kwargs["documents"] = documents
    return fn(q, index, **kwargs)


def _chunk(seqitems, n):
    """Split a list into at most ``n`` contiguous, order-preserving chunks."""
    items = list(seqitems)
    if n <= 1 or len(items) <= 1:
        return [items]
    n = min(n, len(items))
    size, rem = divmod(len(items), n)
    out, i = [], 0
    for k in range(n):
        step = size + (1 if k < rem else 0)
        out.append(items[i:i + step])
        i += step
    return [c for c in out if c]


# --------------------------------------------------------------------------- #
# Batch search.
# --------------------------------------------------------------------------- #
# Globals inherited by fork children (avoids pickling the index per query).
_G: dict = {}


def _search_chunk(queries):
    fn = _G["fn"]
    index = _G["index"]
    tk = _G["top_k"]
    docs = _G["docs"]
    return [_call_search(fn, q, index, tk, docs) for q in queries]


def _sequential_batch(queries, index, top_k, documents):
    bfn = _find_batch_search()
    if bfn is not None:
        try:
            params = inspect.signature(bfn).parameters
        except (TypeError, ValueError):
            params = {}
        kwargs = {}
        if "top_k" in params:
            kwargs["top_k"] = top_k
        if "documents" in params and documents is not None:
            kwargs["documents"] = documents
        res = bfn(queries, index, **kwargs)
        if isinstance(res, tuple):
            return list(res[0])
        return list(res)
    sfn = _find_single_search()
    if sfn is None:
        raise RuntimeError("No sequential search function found")
    return [_call_search(sfn, q, index, top_k, documents) for q in queries]


def batch_search_parallel(queries, index, top_k=10, num_workers=None,
                          documents=None):
    """Parallel batch search. Returns (List[List[SearchResult]], elapsed)."""
    start = time.perf_counter()
    queries = list(queries)
    if not queries:
        return [], time.perf_counter() - start

    sfn = _find_single_search()
    nw = num_workers if num_workers else (os.cpu_count() or 1)
    nw = max(1, min(int(nw), len(queries)))

    # Tiny workloads / single worker: run inline (pool overhead not worth it).
    if sfn is None or nw == 1 or len(queries) < 4:
        results = _sequential_batch(queries, index, top_k, documents)
        return results, time.perf_counter() - start

    chunks = _chunk(queries, nw)

    # Preferred path: fork so children inherit the built index via COW.
    try:
        _G["fn"] = sfn
        _G["index"] = index
        _G["top_k"] = top_k
        _G["docs"] = documents
        ctx = mp.get_context("fork")
        with ctx.Pool(processes=len(chunks)) as pool:
            parts = pool.map(_search_chunk, chunks)
        results = [r for part in parts for r in part]
        if len(results) == len(queries):
            return results, time.perf_counter() - start
    except Exception:
        pass

    # Robust fallback: run inline (correctness over speed).
    results = _sequential_batch(queries, index, top_k, documents)
    return results, time.perf_counter() - start


# --------------------------------------------------------------------------- #
# Index building.
# --------------------------------------------------------------------------- #
def _doc_text(doc):
    """Reproduce the sequential text assembly: title + ' ' + content."""
    title = getattr(doc, "title", "") or ""
    content = getattr(doc, "content", "") or ""
    return title + " " + content


def _tokenize_tf(doc):
    """Return (doc_id, tf_dict) using the sequential tokenizer and TF code."""
    tokens = _TOKENIZE(_doc_text(doc))
    tf = _COMPUTE_TF(tokens)
    return getattr(doc, "doc_id"), tf


def _tf_chunk(docs):
    return [_tokenize_tf(d) for d in docs]


def _parallel_tokenize(documents, nw, chunk_size):
    """Compute [(doc_id, tf_dict), ...] in document order, in parallel."""
    n = len(documents)
    if _TOKENIZE is None or _COMPUTE_TF is None:
        return None  # signal: cannot do the deterministic fast path
    # Inline for small corpora / single worker.
    if nw <= 1 or n < 50:
        return [_tokenize_tf(d) for d in documents]

    # Decide chunking: enough chunks to use the workers, but not so small that
    # IPC dominates. ``chunk_size`` caps per-task size.
    nproc = max(1, min(int(nw), n))
    target_chunks = nproc
    if chunk_size and chunk_size > 0:
        target_chunks = max(target_chunks, (n + chunk_size - 1) // chunk_size)
    chunks = _chunk(documents, target_chunks)
    try:
        ctx = mp.get_context("fork")
        with ctx.Pool(processes=nproc) as pool:
            parts = pool.map(_tf_chunk, chunks)
        out = [item for part in parts for item in part]
        if len(out) == n:
            return out
    except Exception:
        pass
    # Fallback inline.
    return [_tokenize_tf(d) for d in documents]


def _assemble_index(doc_items, num_documents):
    """Build a TFIDFIndex identical to the sequential one from (doc_id, tf)."""
    index = _TFIDF_INDEX()
    index.num_documents = num_documents

    # Vocabulary (set equality is order-independent).
    for _doc_id, tf in doc_items:
        index.vocabulary.update(tf.keys())

    # Document frequencies: integer counts, identical regardless of method.
    df = defaultdict(int)
    for _doc_id, tf in doc_items:
        for term in tf:
            df[term] += 1
    for term in index.vocabulary:
        index.document_frequencies[term] = df[term]

    # IDF: log(N / df) + 1, matching the sequential (smoothed) formula.
    N = num_documents
    for term, dfv in index.document_frequencies.items():
        index.idf[term] = math.log(N / dfv) + 1

    # Inverted index: posting lists built in document order (same as the
    # sequential loop) then sorted by score descending (stable -> identical
    # tie ordering).
    posting = defaultdict(list)
    for doc_id, tf in doc_items:
        for term, tfv in tf.items():
            posting[term].append((doc_id, tfv * index.idf[term]))
    for term in index.vocabulary:
        pl = posting[term]
        pl.sort(key=lambda x: x[1], reverse=True)
        index.inverted_index[term] = pl

    # Document vectors + L2 norms, computed per document in tf order.
    for doc_id, tf in doc_items:
        doc_vector = {}
        norm_squared = 0.0
        for term, tfv in tf.items():
            tfidf = tfv * index.idf[term]
            doc_vector[term] = tfidf
            norm_squared += tfidf * tfidf
        index.doc_vectors[doc_id] = doc_vector
        index.doc_norms[doc_id] = math.sqrt(norm_squared)

    return index


def _extract_index(res):
    if res is None:
        return None
    if _TFIDF_INDEX is not None and isinstance(res, _TFIDF_INDEX):
        return res
    if is_dataclass(res):
        for f in fields(res):
            val = getattr(res, f.name)
            if _TFIDF_INDEX is not None and isinstance(val, _TFIDF_INDEX):
                return val
        if hasattr(res, "index"):
            return getattr(res, "index")
    if isinstance(res, tuple) and res:
        return _extract_index(res[0])
    return res


def _make_result(index, elapsed, num_documents, vocab_size):
    """Wrap the index in ParallelIndexingResult, matching its field names."""
    try:
        return ParallelIndexingResult(index=index, elapsed_time=elapsed,
                                      num_documents=num_documents,
                                      vocabulary_size=vocab_size)
    except TypeError:
        pass
    # Field names differ: fill by position/name defensively.
    try:
        flds = [f.name for f in fields(ParallelIndexingResult)]
        kwargs = {}
        for name in flds:
            if name == "index":
                kwargs[name] = index
            elif "elapsed" in name or name in ("time", "duration"):
                kwargs[name] = elapsed
            elif "vocab" in name:
                kwargs[name] = vocab_size
            elif "doc" in name or name in ("n", "count", "num"):
                kwargs[name] = num_documents
        return ParallelIndexingResult(**kwargs)
    except Exception:
        return ParallelIndexingResult(index)  # minimal fallback


def build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500):
    """Build a TF-IDF index whose structure is identical to the sequential one.

    The heavy per-document tokenisation / term-frequency stage is parallelised
    across a fork pool; the deterministic global reductions are then applied in
    document order so the result is bit-identical to the sequential builder.
    """
    start = time.perf_counter()
    documents = list(documents)
    nw = num_workers if num_workers else (os.cpu_count() or 1)
    N = len(documents)

    # Empty corpus: return an empty-but-valid index without a pool.
    if N == 0:
        if _TFIDF_INDEX is not None:
            index = _TFIDF_INDEX()
            index.num_documents = 0
            return _make_result(index, time.perf_counter() - start, 0, 0)

    # Fast deterministic path: parallel tokenisation + exact reductions.
    if _TFIDF_INDEX is not None and _TOKENIZE is not None and _COMPUTE_TF is not None:
        doc_items = _parallel_tokenize(documents, int(nw), chunk_size)
        if doc_items is not None:
            index = _assemble_index(doc_items, N)
            elapsed = time.perf_counter() - start
            return _make_result(index, elapsed, N, len(index.vocabulary))

    # Fallback: delegate to the sequential builder (always identical, slower).
    build_fn = _find_build()
    if build_fn is None:
        raise RuntimeError("No sequential build function found")
    try:
        params = inspect.signature(build_fn).parameters
    except (TypeError, ValueError):
        params = {}
    kwargs = {}
    if "chunk_size" in params:
        kwargs["chunk_size"] = chunk_size
    seq_result = build_fn(documents, **kwargs)
    index = _extract_index(seq_result)
    elapsed = time.perf_counter() - start
    vocab = len(getattr(index, "vocabulary", []) or [])
    if isinstance(seq_result, ParallelIndexingResult):
        return seq_result
    return _make_result(index, elapsed, N, vocab)
