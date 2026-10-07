---
name: parallel-tfidf-compatibility
version: 1.0.0
description: Implement and validate a multiprocessing TF-IDF index builder and batched search adapter when a sequential Python implementation is the compatibility oracle. Use for tasks requiring a parallel artifact with identical index/result semantics and deterministic ordering.
---

# Parallel TF-IDF Compatibility

## Purpose

Produce the required parallel artifact in the task workspace (for this task, `/root/workspace/parallel_solution.py`) while treating the supplied sequential module as the authoritative specification. Do not invent a replacement TF-IDF definition, document model, result type, tokenization rule, timing field, or tie-break rule.

The required public exports are:

```python
build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500)
batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None)
```

They must return the task's existing result types and preserve the sequential engine's observable behavior.

## Inputs and packaged helpers

* The task supplies the sequential engine and, where applicable, a document generator in the workspace. Read those files before implementation.
* `scripts/inspect_python_api.py` reads a Python source file and reports its declared imports, functions, classes, methods, and signatures without importing it.
* `scripts/check_artifact.py` imports the sequential and completed parallel modules and verifies the two required callable signatures. It is an interface check, not a semantic proof.

Both helpers take one JSON object on standard input and emit one JSON object on standard output. They use only the Python standard library.

Example inspection:

```sh
python scripts/inspect_python_api.py <<'JSON'
{"path":"/root/workspace/sequential.py"}
JSON
```

Example post-write interface check:

```sh
python scripts/check_artifact.py <<'JSON'
{"solution_path":"/root/workspace/parallel_solution.py","sequential_path":"/root/workspace/sequential.py"}
JSON
```

The executor must actually create `/root/workspace/parallel_solution.py`; helper output alone is not the artifact.

## Implementation procedure

1. **Recover the real contract first.** Inspect and read the sequential source in full. Identify:
   * public document, index, indexing-result, and search-result classes, including constructor fields and mutability;
   * the sequential index-build entry point and every stage it uses: document normalization/tokenization, local term frequencies, document frequency, IDF, document vectors/norms, vocabulary/postings, and elapsed-time handling;
   * the single-query or batch-query scoring path, query normalization, zero-score inclusion/exclusion, `top_k` behavior, and sorting key;
   * behavior for empty documents, empty corpus, empty query batch, unknown terms, duplicate documents/queries, and `None` arguments.

   Import and reuse these types and stable helpers rather than defining lookalike classes. Preserve any module-level exports that tests may import.

2. **Choose a parallel boundary that leaves global math canonical.** Only document-local work belongs in index-build workers. Make a top-level, pickleable worker that receives a numbered chunk and executes exactly the sequential document-local preprocessing. It should return plain serializable records tagged with original document positions. Never let workers independently calculate corpus-wide IDF or assemble unordered postings.

   In the parent, collect by chunk/document ordinal (not completion order), then calculate document frequencies, IDF, vocabulary ordering, posting lists, vectors, norms, and the final `TFIDFIndex` using the same loops, data structures, reduction order, and constructors as the sequential implementation. If the sequential module exposes a reusable global assembly helper, call it with the ordered local records. If it does not, port that logic exactly, retaining iteration order and float operation order. Do not use sets or unordered completion order where the reference has a defined order.

   A practical compatibility option for empty input and very small workloads is to call the sequential builder directly, provided the returned indexing-result type and timing semantics remain correct. This also avoids fragile assumptions about special empty-index fields.

3. **Use safe multiprocessing mechanics.** Put all process target functions and pool initializer functions at module scope in `parallel_solution.py`, with no nested functions, lambdas, or captured state. Validate `chunk_size` before range creation. Materialize a one-shot document or query iterable once only if the reference accepts such an iterable; otherwise follow its input expectations exactly.

   Resolve `num_workers=None` to a sensible CPU-count-based positive number, cap it to useful work, and avoid a pool for no work. Preserve caller order by submitting ordinal-tagged chunks and placing returned data at their original positions. Use `multiprocessing.Pool`/a context-managed pool or equivalent cleanup discipline so exceptions terminate/join workers and are re-raised rather than causing a deadlock. Do not silently replace worker exceptions with partial results.

4. **Parallelize search by query batches, not index fragments.** The entire finished index is read-only worker state. Create one pool for a `batch_search_parallel` invocation, initialize each worker once with the index and any needed immutable document data, and send compact `(batch_ordinal, query_slice)` work units. A worker must use the same extracted sequential single-query scoring helper or an exact port of that routine for each query. It returns results tagged by original query position.

   Do not create a pool per query and do not serialize the index with every query task. Use chunking/batching to amortize IPC. Reassemble outputs in input-query order. Let the sequential scoring/ranking code remain the source of truth for score calculation, inclusion of zero scores, score precision, `top_k`, and deterministic ties. In particular, never sort solely by score unless that is precisely the reference key.

   If the source only exposes a batch routine, carefully extract its per-query pure portion into the parallel module while preserving all surrounding semantics. Do not call a timed sequential batch API once per worker batch if that changes result objects or timing behavior.

5. **Honor timings and compatibility details.** Measure the elapsed value with the timing convention discovered in the sequential module. Measure the work performed by the parallel public call with a monotonic clock; do not return fabricated speedup estimates. Pool startup should be accounted for consistently with the intended public timing contract. Avoid prints, logging, progress bars, randomization, and import-time process creation.

6. **Validate before delivery.** Run the interface checker, then create a temporary harness using representative documents generated by the supplied generator or the same document classes used by the sequential module. Compare, rather than merely spot-check:
   * type and fields of the parallel indexing result and its contained index;
   * vocabulary order, document-frequency and IDF mappings, posting lists, document vectors/norms, and every other index field against sequential output;
   * every `SearchResult` field and ordered result list for multiple queries and several `top_k` values;
   * empty corpus, empty query list, unknown-term query, ties, zero-score behavior, and worker counts of one and several.

   Benchmark only after exact comparisons pass. Use corpus/query sizes large enough to amortize process startup, run repeated trials, and compare equivalent work with four workers. Profile serialization and chunk size before changing algorithmic semantics. A speed target is not permission to weaken compatibility.

## Failure handling

* If the supplied module does not expose enough reusable helpers, read its implementation and make a faithful local port of only the necessary stages. Do not guess missing behavior.
* If a class cannot be pickled, workers should return primitive intermediate data and the parent should construct the source module's class instances.
* If an index contains unpickleable state, prefer a platform-appropriate inherited read-only state only when it is safe in the declared runtime; otherwise initialize a serializable compact representation once per worker and reconstruct source result types in the parent.
* If process startup or serialization makes a small workload slower, use the sequential-equivalent path for that workload while retaining the parallel path for substantial independent work.
* Worker errors must be visible to the caller after pool cleanup. Empty inputs must return the reference-compatible empty result without starting a pointless pool.

## Completion criteria

Deliver `/root/workspace/parallel_solution.py` with both exact signatures, imports that resolve from the workspace, top-level worker functions, and no changes required to `sequential.py`. The finished implementation must be directly importable and must match the sequential implementation's complete index and ranked-search results deterministically.
