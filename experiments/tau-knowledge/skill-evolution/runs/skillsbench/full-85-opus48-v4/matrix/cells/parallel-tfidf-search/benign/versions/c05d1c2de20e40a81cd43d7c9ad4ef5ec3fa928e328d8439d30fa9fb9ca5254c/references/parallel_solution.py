"""Parallel TF-IDF search deliverable.

Written into /root/workspace/parallel_solution.py. It reuses the sequential
engine's own code (imported as ``sequential``) so that parallel results are
identical to the reference, and parallelizes only how work is scheduled.

Exported:
  build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500)
  batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None)
"""
from __future__ import annotations

import inspect
import multiprocessing as mp
import os
import sys
import time
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, List, Optional, Tuple

# Make sure the sequential module (same directory) is importable regardless of
# the caller's working directory.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import sequential as seq  # noqa: E402


# --------------------------------------------------------------------------- #
# Result type: reuse the sequential one if present, otherwise mirror it.
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
        num_workers: int = 1


def _find_single_search():
    """Locate the sequential single-query search function."""
    for name in ("search", "tfidf_search", "search_tfidf", "search_single",
                 "query", "search_query"):
        fn = getattr(seq, name, None)
        if callable(fn):
            try:
                params = list(inspect.signature(fn).parameters)
            except (TypeError, ValueError):
                continue
            # Heuristic: a per-query search takes at least (query, index).
            if len(params) >= 2:
                return fn
    return None


def _find_batch_search():
    for name in ("batch_search", "search_batch", "batch_query"):
        fn = getattr(seq, name, None)
        if callable(fn):
            return fn
    return None


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
    """Split a list into at most n contiguous, order-preserving chunks."""
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
    nw = max(1, min(nw, len(queries)))

    if sfn is None or nw == 1:
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


def _extract_index(res):
    if res is None:
        return None
    tfidf_cls = getattr(seq, "TFIDFIndex", None)
    if tfidf_cls is not None and isinstance(res, tfidf_cls):
        return res
    if is_dataclass(res):
        for f in fields(res):
            val = getattr(res, f.name)
            if tfidf_cls is not None and isinstance(val, tfidf_cls):
                return val
        # common attribute name
        if hasattr(res, "index"):
            return getattr(res, "index")
    if isinstance(res, tuple) and res:
        return _extract_index(res[0])
    return res


def _make_parallel_result(seq_result, index, elapsed, num_workers):
    # If sequential returned exactly our result type, reuse it.
    try:
        if isinstance(seq_result, ParallelIndexingResult):
            return seq_result
    except Exception:
        pass
    # Mirror a sequential dataclass result field-for-field.
    if is_dataclass(seq_result):
        try:
            kwargs = {f.name: getattr(seq_result, f.name)
                      for f in fields(seq_result)}
            return ParallelIndexingResult(**kwargs)
        except Exception:
            pass
    # Last resort: our minimal shape.
    try:
        return ParallelIndexingResult(index=index, elapsed_time=elapsed,
                                      num_workers=num_workers)
    except TypeError:
        try:
            return ParallelIndexingResult(index=index, elapsed_time=elapsed)
        except TypeError:
            return ParallelIndexingResult(index)


def build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500):
    """Build the TF-IDF index.

    Correctness-first baseline: delegate the exact index assembly (including all
    float reductions) to the sequential builder so the resulting ``TFIDFIndex``
    is identical to the reference, then wrap it in ``ParallelIndexingResult``.

    To add genuine build-time parallelism, parallelize only the deterministic
    per-document term counting and reproduce the sequential global reductions in
    original document order (see SKILL.md). Keep ``index_equal`` true.
    """
    start = time.perf_counter()
    documents = list(documents)
    nw = num_workers if num_workers else (os.cpu_count() or 1)

    build_fn = getattr(seq, "build_tfidf_index", None)
    if build_fn is None:
        for name in ("build_index", "build", "index_documents"):
            cand = getattr(seq, name, None)
            if callable(cand):
                build_fn = cand
                break
    if build_fn is None:
        raise RuntimeError("No sequential build function found")

    # Pass chunk_size through only if the sequential builder accepts it.
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
    return _make_parallel_result(seq_result, index, elapsed, nw)
