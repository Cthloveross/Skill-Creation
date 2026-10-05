---
name: parallel-tfidf-search
version: 1.0.0
description: Implement and validate a multiprocessing TF-IDF index builder and batched similarity search that is behaviorally identical to an existing sequential Python implementation. Use when the reference source is available locally and the required artifact is a parallel_solution.py module.
---

# Parallel TF-IDF Search

## Goal

Create `/root/workspace/parallel_solution.py` implementing:

```python
build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500)
batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None)
```

The implementation must return the reference engine's expected index/result types and preserve its observable behavior exactly, while using multiple CPU processes for sufficiently large workloads.

## Required discovery before implementation

Read `/root/workspace/sequential.py` completely before writing the implementation. Treat it as the executable specification. Also inspect `/root/workspace/document_generator.py` to learn the real document and query shapes used for benchmarking.

Record the following from the reference source:

1. All exported classes, especially `TFIDFIndex`, any indexing-result wrapper, and `SearchResult`.
2. Exact tokenization/normalization rules and the document fields from which text and identifiers are obtained.
3. Term-frequency formula, document-frequency formula, IDF formula, vector normalization, and all floating-point operation ordering relevant to equality.
4. The concrete types and ordering of vocabulary, postings, document IDs, document vectors, norms, and result lists.
5. Empty-corpus, empty-query, unknown-term, duplicate-document-ID, and `top_k <= 0` behavior.
6. Ranking ordering, particularly whether ties use document ID, corpus position, insertion order, or another key, and whether zero-score documents are returned.
7. Sequential function names and whether functions return `(value, elapsed_time)` wrappers.

Do not guess these details from generic TF-IDF conventions. Import and reuse reference types and pure helpers where that preserves exact semantics.

## Implementation plan

### 1. Module compatibility

* Put the artifact at exactly `/root/workspace/parallel_solution.py`.
* Import the reference model/result classes from `sequential` rather than defining look-alike classes, unless the reference itself requires another arrangement.
* Match the required public signatures exactly. Resolve `num_workers=None` to a positive, sensible CPU-based count; treat values below one consistently with the reference/error policy rather than silently creating an invalid executor.
* Keep all process worker functions at module scope so they are pickleable. Protect any standalone diagnostic code with `if __name__ == "__main__":`.

### 2. Parallel index construction

Parallelize only document-local work. A worker should receive a bounded, ordered chunk such as `(start_offset, documents_chunk)` and return, for each document in its original order, the exact local information needed by the reference construction: token/count data and any reference-defined local statistics.

In the parent process:

1. Enumerate chunks in original corpus order; do not let completion order define output order.
2. Collect worker outputs keyed by chunk offset and merge them in ascending offset order.
3. Derive corpus document frequencies from the fully merged corpus view, using one contribution per document per term.
4. Compute IDF once from the complete corpus using the exact reference expression.
5. Construct postings, weights, norms, and all index fields in the same iteration/order and using the same class constructors as the sequential implementation.

This structure prevents the common incorrect design of averaging chunk-local IDFs or merging unordered postings. It also preserves deterministic floating-point accumulation and stable vocabulary/posting order.

Choose chunking carefully. Do not submit one future per document: that makes IPC dominate. Honor `chunk_size`, ensure it is positive or explicitly reject invalid values, and use a sequential fallback for tiny corpora or one worker when process startup cannot amortize. Empty documents/corpora must return the reference-compatible empty structure without deadlock.

If the sequential builder has separable helper functions, it is often safest to factor a worker around precisely its document-local preprocessing and leave global index assembly in the parent. Never mutate a shared index concurrently.

### 3. Parallel batched searching

Use process-level parallelism, not threads, for CPU-bound scoring. Build worker state once per `batch_search_parallel` call (or safely cache it only if lifecycle, invalidation, and cleanup are unambiguous): initialize the worker with the index and any immutable supporting data, then submit compact batches of query positions/queries. Do **not** send the full index with every query task.

A good pattern is:

* module-global read-only worker state;
* an executor `initializer` receiving the index once per worker;
* each task receives a contiguous batch of `(query_position, query)` pairs;
* each worker calls/refactors the reference scoring logic for each query and returns indexed results;
* the parent restores original query order by query position.

Batch queries so startup and IPC are amortized, but preserve result order even when futures finish in another order. Use the reference query-tokenization, query weighting, score accumulation, zero-score policy, ranking key, and result constructor. In particular, avoid unordered set/dict iteration in tie-sensitive code and use the same final sort key as the sequential implementation.

If the reference query scorer is pure and pickleable, call it from workers. If it is an instance method or relies on index state, write a module-level worker wrapper that invokes it against initialized state. For very small query batches or one worker, a direct sequential-compatible path is usually faster and avoids needless startup.

`documents` is optional only according to the public signature: inspect how the sequential search uses corpus documents and forward it whenever needed to obtain identical results. Do not infer text from an index if the reference obtains it from `documents`.

Measure elapsed time with `time.perf_counter()` around the work defined by the sequential counterpart, and return `(results, elapsed_time)` with results in the same nested-list and `SearchResult` structure as the reference.

### 4. Failure and resource handling

Use context-managed executors so normal completion and exceptions shut workers down. Let worker exceptions surface to the caller with context; do not return partial indexes/results or wait indefinitely. Ensure empty task lists do not create a blocking wait. Avoid module import side effects that spawn workers.

## Validation workflow

After creating the artifact, run functional comparisons before performance measurements. The bundled validator accepts JSON on stdin and prints JSON on stdout; it compares canonicalized complete index structures and query results, then reports repeated wall-clock timing ratios.

Example (replace sequential function names if source inspection finds different names):

```bash
python /path/to/skill/scripts/validate_parallel.py <<'JSON'
{
  "workspace": "/root/workspace",
  "documents": [],
  "queries": [],
  "sequential_build": "build_tfidf_index",
  "sequential_search": "batch_search",
  "workers": 4,
  "chunk_size": 500,
  "top_k": 10,
  "repetitions": 3
}
JSON
```

For useful timing, obtain representative nonempty documents and queries using the supplied generator or its documented interface, pass those JSON-serializable values to the validator, and use several repetitions. Review these conditions:

* `index_equal` and `results_equal` are true.
* Test representative data plus explicit empty corpus/query cases only when the sequential reference supports them.
* Test unknown terms, tied scores, zero scores, different `top_k` values, and worker counts one and four.
* Benchmark end-to-end calls after correctness. The validator reports median speedup and reports whether the requested 1.5x build / 2x search thresholds were met for that workload.
* Do not claim speedup from a tiny workload where process startup dominates. Profile document-local preprocessing and query scoring first; reduce task serialization and increase meaningful batch size before changing math or ranking behavior.

The validator is a comparison aid, not a substitute for source inspection: if reference names or invocation conventions differ, specify their names in its JSON input or adapt the call as indicated by the source.
