#!/usr/bin/env python3
"""Compare a sequential TF-IDF module to parallel_solution.

Input is one JSON object on stdin:
{
  "workspace": "/root/workspace",
  "documents": [...], "queries": [...],
  "sequential_build": "build_tfidf_index",        # optional
  "sequential_search": "batch_search",             # optional
  "workers": 4, "chunk_size": 500, "top_k": 10,
  "repetitions": 3
}

The document/query values must be JSON-serializable values accepted by the local
reference implementation.  Output is JSON with structural/result equality and
median wall-clock timings.  The utility does not modify the workspace.
"""
import importlib
import inspect
import json
import math
import os
import statistics
import sys
import time
from collections.abc import Mapping


def canonical(value, seen=None):
    """Produce a deterministic, type-aware representation for comparisons."""
    if seen is None:
        seen = set()
    if value is None or isinstance(value, (bool, int, str)):
        return (type(value).__name__, value)
    if isinstance(value, float):
        if math.isnan(value):
            return ("float", "nan")
        if math.isinf(value):
            return ("float", "inf" if value > 0 else "-inf")
        return ("float", value.hex())
    identity = id(value)
    if identity in seen:
        return ("cycle", type(value).__module__, type(value).__qualname__)
    if isinstance(value, Mapping):
        seen.add(identity)
        items = [(canonical(k, seen), canonical(v, seen)) for k, v in value.items()]
        seen.remove(identity)
        return (type(value).__module__, type(value).__qualname__, tuple(items))
    if isinstance(value, (list, tuple)):
        seen.add(identity)
        out = tuple(canonical(item, seen) for item in value)
        seen.remove(identity)
        return (type(value).__name__, out)
    if isinstance(value, (set, frozenset)):
        seen.add(identity)
        out = sorted((canonical(item, seen) for item in value), key=repr)
        seen.remove(identity)
        return (type(value).__name__, tuple(out))
    if hasattr(value, "__dict__"):
        seen.add(identity)
        out = canonical(vars(value), seen)
        seen.remove(identity)
        return (type(value).__module__, type(value).__qualname__, out)
    return (type(value).__module__, type(value).__qualname__, repr(value))


def pick(module, requested, candidates):
    if requested:
        return getattr(module, requested)
    for name in candidates:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    raise AttributeError("No suitable function found; supply its name in JSON input")


def invoke_search(fn, queries, index, top_k, documents, parallel=False, workers=None):
    params = inspect.signature(fn).parameters
    kwargs = {}
    if "top_k" in params:
        kwargs["top_k"] = top_k
    if "documents" in params:
        kwargs["documents"] = documents
    if parallel and "num_workers" in params:
        kwargs["num_workers"] = workers
    return fn(queries, index, **kwargs)


def value_part(returned):
    """Extract value from conventional (value, elapsed_seconds) APIs."""
    if (isinstance(returned, tuple) and len(returned) == 2 and
            isinstance(returned[1], (int, float))):
        return returned[0]
    return returned


def timed(repetitions, func):
    values = []
    last = None
    for _ in range(repetitions):
        start = time.perf_counter()
        last = func()
        values.append(time.perf_counter() - start)
    return last, statistics.median(values), values


def main(config):
    workspace = config.get("workspace", "/root/workspace")
    if workspace not in sys.path:
        sys.path.insert(0, workspace)
    # Avoid a stale module if this helper is embedded in a larger Python process.
    for name in ("sequential", "parallel_solution"):
        sys.modules.pop(name, None)
    sequential = importlib.import_module("sequential")
    parallel = importlib.import_module("parallel_solution")
    documents = config["documents"]
    queries = config["queries"]
    workers = int(config.get("workers", os.cpu_count() or 1))
    chunk_size = int(config.get("chunk_size", 500))
    top_k = int(config.get("top_k", 10))
    repetitions = max(1, int(config.get("repetitions", 3)))

    seq_build = pick(sequential, config.get("sequential_build"),
                     ("build_tfidf_index", "build_index", "build_tfidf_index_sequential"))
    seq_search = pick(sequential, config.get("sequential_search"),
                      ("batch_search", "batch_search_sequential", "search_batch"))
    par_build = getattr(parallel, "build_tfidf_index_parallel")
    par_search = getattr(parallel, "batch_search_parallel")

    seq_index, seq_build_median, seq_build_samples = timed(
        repetitions, lambda: seq_build(documents))
    par_index, par_build_median, par_build_samples = timed(
        repetitions, lambda: par_build(documents, num_workers=workers, chunk_size=chunk_size))

    seq_return, seq_search_median, seq_search_samples = timed(
        repetitions, lambda: invoke_search(seq_search, queries, seq_index, top_k, documents))
    par_return, par_search_median, par_search_samples = timed(
        repetitions, lambda: invoke_search(par_search, queries, par_index, top_k, documents,
                                            parallel=True, workers=workers))
    seq_results = value_part(seq_return)
    par_results = value_part(par_return)

    index_equal = canonical(seq_index) == canonical(par_index)
    results_equal = canonical(seq_results) == canonical(par_results)
    build_speedup = (seq_build_median / par_build_median) if par_build_median else None
    search_speedup = (seq_search_median / par_search_median) if par_search_median else None
    return {
        "ok": index_equal and results_equal,
        "index_equal": index_equal,
        "results_equal": results_equal,
        "workers": workers,
        "repetitions": repetitions,
        "build_seconds_median": seq_build_median,
        "parallel_build_seconds_median": par_build_median,
        "search_seconds_median": seq_search_median,
        "parallel_search_seconds_median": par_search_median,
        "build_speedup": build_speedup,
        "search_speedup": search_speedup,
        "build_target_1_5x_met": build_speedup is not None and build_speedup >= 1.5,
        "search_target_2x_met": search_speedup is not None and search_speedup >= 2.0,
        "build_samples": seq_build_samples,
        "parallel_build_samples": par_build_samples,
        "search_samples": seq_search_samples,
        "parallel_search_samples": par_search_samples,
        "parallel_reported_elapsed": (par_return[1] if isinstance(par_return, tuple) and
                                        len(par_return) == 2 else None),
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True, default=repr))
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "error": str(exc)}))
        raise
