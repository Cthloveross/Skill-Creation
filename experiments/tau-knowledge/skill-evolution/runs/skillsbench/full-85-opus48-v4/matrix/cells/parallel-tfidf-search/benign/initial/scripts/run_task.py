#!/usr/bin/env python3
"""Install the parallel solution and validate correctness + speedup.

stdin (optional):
  {"workspace":"/root/workspace","num_workers":4,"n_docs":2000,
   "n_queries":200,"top_k":10,"install":true}
stdout:
  {"ok":bool,"installed":bool,"index_equal":bool?,"search_equal":bool?,
   "build_speedup":float?,"search_speedup":float?,"notes":[...],"error"?}
"""
import importlib
import inspect
import json
import math
import os
import shutil
import sys
import time
from dataclasses import fields, is_dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
TEMPLATE = os.path.join(SKILL_ROOT, "references", "parallel_solution.py")


def deep_equal(a, b, tol=1e-6, _depth=0):
    if _depth > 200:
        return True
    if isinstance(a, float) or isinstance(b, float):
        try:
            if math.isnan(float(a)) and math.isnan(float(b)):
                return True
        except Exception:
            pass
        try:
            return abs(float(a) - float(b)) <= tol * (1 + abs(float(b)))
        except Exception:
            return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(deep_equal(a[k], b[k], tol, _depth + 1) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(deep_equal(x, y, tol, _depth + 1) for x, y in zip(a, b))
    if is_dataclass(a) and is_dataclass(b):
        fa = [f.name for f in fields(a)]
        fb = [f.name for f in fields(b)]
        if fa != fb:
            return False
        return all(deep_equal(getattr(a, n), getattr(b, n), tol, _depth + 1)
                   for n in fa)
    return a == b


def call_generator(gen, kind, n):
    """Best-effort call of a corpus/query generator function."""
    names = (("generate_documents", "make_documents", "generate_corpus",
              "create_documents", "documents")
             if kind == "docs" else
             ("generate_queries", "make_queries", "create_queries", "queries"))
    for name in names:
        fn = getattr(gen, name, None)
        if callable(fn):
            try:
                params = inspect.signature(fn).parameters
            except (TypeError, ValueError):
                params = {}
            for args in ((n,), ()):
                try:
                    return fn(*args)
                except TypeError:
                    continue
                except Exception:
                    continue
    return None


def extract_index(res, seq):
    tfidf = getattr(seq, "TFIDFIndex", None)
    if tfidf is not None and isinstance(res, tfidf):
        return res
    if is_dataclass(res):
        for f in fields(res):
            v = getattr(res, f.name)
            if tfidf is not None and isinstance(v, tfidf):
                return v
        if hasattr(res, "index"):
            return res.index
    if isinstance(res, tuple) and res:
        return extract_index(res[0], seq)
    return res


def main():
    try:
        raw = sys.stdin.read().strip()
        req = json.loads(raw) if raw else {}
    except Exception:
        req = {}
    workspace = req.get("workspace", "/root/workspace")
    num_workers = int(req.get("num_workers", 4))
    n_docs = int(req.get("n_docs", 2000))
    n_queries = int(req.get("n_queries", 200))
    top_k = int(req.get("top_k", 10))
    do_install = req.get("install", True)
    notes = []
    out = {"ok": True, "installed": False, "notes": notes}

    dest = os.path.join(workspace, "parallel_solution.py")
    if do_install:
        try:
            shutil.copyfile(TEMPLATE, dest)
            out["installed"] = True
        except Exception as e:
            out["ok"] = False
            out["error"] = "install failed: %s" % e
            print(json.dumps(out))
            return
    else:
        out["installed"] = os.path.exists(dest)

    if workspace not in sys.path:
        sys.path.insert(0, workspace)

    try:
        seq = importlib.import_module("sequential")
    except Exception as e:
        notes.append("cannot import sequential: %s" % e)
        print(json.dumps(out))
        return
    try:
        par = importlib.import_module("parallel_solution")
        importlib.reload(par)
    except Exception as e:
        out["ok"] = False
        out["error"] = "cannot import parallel_solution: %s" % e
        print(json.dumps(out))
        return

    docs = queries = None
    try:
        gen = importlib.import_module("document_generator")
        docs = call_generator(gen, "docs", n_docs)
        queries = call_generator(gen, "queries", n_queries)
    except Exception as e:
        notes.append("generator import failed: %s" % e)

    if docs is None:
        notes.append("could not generate documents; validation skipped")
        print(json.dumps(out))
        return

    # ---- build comparison ----
    try:
        t0 = time.perf_counter()
        seq_build = getattr(seq, "build_tfidf_index")(docs)
        seq_build_t = time.perf_counter() - t0
        seq_index = extract_index(seq_build, seq)

        t0 = time.perf_counter()
        par_build = par.build_tfidf_index_parallel(
            docs, num_workers=num_workers)
        par_build_t = time.perf_counter() - t0
        par_index = extract_index(par_build, seq)

        out["index_equal"] = bool(deep_equal(seq_index, par_index))
        out["build_speedup"] = round(seq_build_t / par_build_t, 3) \
            if par_build_t > 0 else None
    except Exception as e:
        notes.append("build validation error: %s" % e)
        seq_index = None

    # ---- search comparison ----
    if queries is not None and seq_index is not None:
        try:
            t0 = time.perf_counter()
            seq_res = par._sequential_batch(queries, seq_index, top_k, docs)
            seq_search_t = time.perf_counter() - t0

            t0 = time.perf_counter()
            par_res, _ = par.batch_search_parallel(
                queries, seq_index, top_k=top_k, num_workers=num_workers,
                documents=docs)
            par_search_t = time.perf_counter() - t0

            out["search_equal"] = bool(deep_equal(seq_res, par_res))
            out["search_speedup"] = round(seq_search_t / par_search_t, 3) \
                if par_search_t > 0 else None
        except Exception as e:
            notes.append("search validation error: %s" % e)
    else:
        notes.append("queries unavailable; search validation skipped")

    print(json.dumps(out))


if __name__ == "__main__":
    main()
