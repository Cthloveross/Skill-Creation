---
name: parallel-tfidf-search
description: >-
  Parallelize an existing single-threaded TF-IDF document search engine so that
  index building and batch query search run across multiple CPU cores while
  producing results that are identical to the sequential reference. Use this
  Skill for the task that asks you to implement
  `build_tfidf_index_parallel(...)` and `batch_search_parallel(...)` in
  `/root/workspace/parallel_solution.py`, reusing the sequential module's own
  classes (`TFIDFIndex`, `SearchResult`, indexing-result object) and hitting
  the stated speedup targets (>=1.5x build, >=2x search with 4 workers).
---

# Parallel TF-IDF Similarity Search

## What the task requires

The sandbox contains a working sequential search engine under
`/root/workspace/` (`sequential.py`) plus a corpus/query generator
(`document_generator.py`). You must write `/root/workspace/parallel_solution.py`
exporting two functions with these exact signatures:

1. `build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500)`
   returning a `ParallelIndexingResult` that carries the **same `TFIDFIndex`
   structure** the sequential builder produces.
2. `batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None)`
   returning `(List[List[SearchResult]], elapsed_time)`.

Hard constraints:
- **Identical results**: the parallel index and the parallel ranked results
  must equal the sequential engine's output (same posting lists / vocabulary /
  idf floats, same top-k ordering, same tie breaking, same treatment of zero
  scores).
- **Speedup**: >=1.5x on index building and >=2x on batch search with 4
  workers, measured on a representative corpus.

The grader imports your module from the workspace; it is **not** given anything
from this Skill directory. Everything the solution needs at grading time must
live inside the file written to `/root/workspace/parallel_solution.py`.

## Method (why this works)

The frozen background is explicit: *preserve the sequential algorithm's
mathematical definitions and change only how independent work is scheduled and
combined*, and *initialize reusable worker state outside the per-query hot path
and send compact work units*.

The reusable, correctness-safe strategy encoded in this Skill:

- **Reuse the sequential code, do not reimplement it.** `parallel_solution.py`
  imports the sequential module and calls its own single-query search function
  and its own builder. Reusing the exact code is what guarantees bit-identical
  results; parallelism only changes scheduling.
- **Batch search**: fork a worker pool once per call. On Linux the `fork` start
  method lets children inherit the already-built index through copy-on-write, so
  the large index is **not** re-serialized per query or per worker. Queries are
  split into contiguous chunks (compact work units) and results reassembled in
  the original order. Each worker calls the sequential single-query search, so
  ranking/ties/zero handling match exactly.
- **Index building**: the shipped S0 is correctness-first — it produces an index
  that is provably identical to the sequential one (it delegates the merge to
  the sequential builder) and wraps it in the required result type. See
  "Evolving the build parallelism" below: a true parallel build must preserve
  the exact float reductions, so it is implemented only after reading the real
  `sequential.py`.

## Files in this Skill

- `references/parallel_solution.py` — the solution written into the workspace.
  It discovers the sequential API by introspection (function and class names
  can vary) and degrades to sequential behaviour on any unexpected shape rather
  than deadlocking or crashing.
- `scripts/inspect_sequential.py` — prints the sequential module's public
  classes (with dataclass fields) and function signatures, plus the generator's
  functions, so you can confirm the real API before trusting assumptions.
- `scripts/run_task.py` — the entrypoint. Installs
  `references/parallel_solution.py` into `/root/workspace/parallel_solution.py`,
  then builds/searches both ways and reports equality + measured speedups.

### scripts/inspect_sequential.py
Input (stdin JSON, all optional): `{"workspace": "/root/workspace"}`.
Output (stdout JSON): `{"ok": bool, "sequential": {...}, "document_generator": {...}, "error": str?}`
where each module maps names to `"function(sig)"` strings or
`{"dataclass_fields": [...]}` for classes.

### scripts/run_task.py
Input (stdin JSON, all optional):
`{"workspace": "/root/workspace", "num_workers": 4, "n_docs": 2000, "n_queries": 200, "top_k": 10, "install": true}`.
Behaviour:
1. If `install` (default true) copy `references/parallel_solution.py` to
   `<workspace>/parallel_solution.py` (the deliverable).
2. Try to generate a corpus and queries via `document_generator`, run both the
   sequential and the parallel paths, deep-compare the indices and ranked
   results (float tolerance for floats), and time both.
Output (stdout JSON):
`{"ok": bool, "installed": bool, "index_equal": bool?, "search_equal": bool?,`
` "build_speedup": float?, "search_speedup": float?, "notes": [...], "error": str?}`.
Non-fatal validation problems appear in `notes`; the file is still written so the
deliverable exists even if the generator API differs from expectations.

## How to run (executor)

```bash
cd /app/environment/skills/current
echo '{}' | python3 scripts/inspect_sequential.py       # learn the real API
echo '{"num_workers":4}' | python3 scripts/run_task.py   # write + validate
cat /root/workspace/parallel_solution.py | head           # confirm deliverable
```

Interpret `run_task.py` output:
- `installed:true` means the deliverable file now exists at the required path.
- `index_equal`/`search_equal` must be true. If false, the parallel path diverged
  from the sequential reference and must be fixed before anything else.
- `build_speedup` / `search_speedup` report observed ratios; `search_speedup`
  should reach >=2x with 4 workers on a non-trivial corpus. `build_speedup`
  is where S0 is weak (see below).

Always re-run `run_task.py` after editing the reference solution so you verify
the exported entrypoint actually regenerates a correct, fast deliverable — not
just that an old file is present.

## Evolving the build parallelism (important)

S0 guarantees identical build output but delegates the heavy merge to the
sequential builder, so it will not meet the 1.5x build target. To add real build
parallelism **without breaking identical results**:

1. Run `inspect_sequential.py` and open `sequential.py`. Identify precisely how
   the index is assembled: the tokenizer, how per-document term frequencies are
   stored, how document frequency is accumulated, the exact idf formula, and how
   document norms/weights are computed.
2. Parallelize only the embarrassingly-parallel, deterministic stage — typically
   per-document tokenization and term counting across `chunk_size` chunks using
   a `fork` pool — and keep the global reductions (document frequency sum, idf,
   norms) in a single deterministic pass that reproduces the sequential
   arithmetic in the original document order. Float reductions must be combined
   in the same order/way as the reference so results stay bit-identical.
3. After each change, rerun `run_task.py` and require `index_equal:true` before
   trusting any `build_speedup`. Never trade correctness for speed; a correct
   but slow build is strictly better than a fast but divergent one.

Do not hardcode any instance's generated documents, indices, or expected scores
into the deliverable — read the real inputs/sequential module at runtime.

## Failure handling

- Empty `queries` or `documents`: return empty results / an empty-but-valid
  index without creating a pool (avoids deadlock).
- `num_workers in (None,1)` or tiny inputs: run inline, no pool.
- Missing/renamed sequential functions: the reference discovers names by
  introspection and falls back to sequential behaviour, preserving correctness.
- If the generator API in `document_generator.py` differs from what
  `run_task.py` expects, validation is reported in `notes` and skipped, but the
  deliverable is still written; inspect the generator and adjust the validation
  inputs you pass on stdin.
