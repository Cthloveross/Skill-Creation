---
name: parallel-tfidf-search
version: 1.0.0
description: Implement and validate a drop-in parallel TF-IDF index builder and batched search module when a reference sequential.py defines the canonical data structures, tokenization, scoring, and ranking semantics. Use for Python artifact tasks requiring identical sequential results plus multicore acceleration.
---

# Parallel TF-IDF Search

## Applicability and contract

Use this Skill when the task supplies a sequential TF-IDF implementation and asks for a parallel replacement. The reference module is the specification: its public classes, return objects, tokenization, IDF formula, weight formula, document-ID behavior, score arithmetic, and result ordering all take precedence over any generic TF-IDF convention.

For the current task, create `/root/workspace/parallel_solution.py` exporting:

```python
build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500)
batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None)
```

The first must return the reference-compatible indexing-result type and index structure. The second must return `(list_of_result_lists, elapsed_time)` with one list per input query.

Do not hardcode corpus contents, query values, document IDs, benchmark outputs, or expected scores.

## Runtime procedure

1. Read `/root/workspace/sequential.py` completely before writing code. Use `scripts/inspect_sequential.py` for a concise AST inventory, but inspect the source itself for algorithm details.
2. Identify all imported and public types used by the reference, especially `TFIDFIndex`, `ParallelIndexingResult` (if present), `SearchResult`, tokenizer/preprocessor functions, the sequential build function, and single-query/batch search functions.
3. Record the reference behavior for empty documents, empty corpus, empty query, unknown terms, duplicate document IDs, `top_k <= 0`, zero scores, and equal scores. Match it exactly rather than adding new validation rules.
4. Write `/root/workspace/parallel_solution.py`. Import reference types and pure shared helpers rather than re-declaring incompatible dataclasses. It must be importable both from the workspace and from common test working directories.
5. Run focused equivalence and timing checks on representative generated or locally constructed corpora. Use `scripts/compare_values.py` for deep structural comparison where useful. Diagnose any mismatch against the reference before optimizing.

## Implementation design

### Index construction

Parallelize only independent document-local work. A robust layout is:

1. Normalize worker count: when `num_workers is None`, choose a sensible bounded CPU-derived value; use a single sequential-compatible path for one worker or a tiny corpus. Clamp nonpositive/oversized values safely according to reference expectations.
2. Enumerate documents in their original order and form contiguous chunks no larger than `chunk_size` (after handling invalid chunk sizes consistently with the reference).
3. A module-level, pickleable worker receives a chunk and computes only document-local values needed by the reference: original ordinal/ID, token sequence or term counts, document length, and local document-frequency contributions. Never calculate final IDF inside a chunk.
4. Submit chunks once to a `ProcessPoolExecutor` or `multiprocessing.Pool`, collect results tagged with chunk ordinal, and merge in ordinal order. This is required even if workers happen to finish in a different order.
5. Reduce document frequencies using the globally merged corpus, calculate IDF exactly with the reference formula and numeric operation ordering where equality is required, then build postings/document vectors/norms in reference order. Reuse the reference's pure weighting or index-assembly helpers when they exist.
6. Construct the exact reference `TFIDFIndex` and indexing-result wrapper with all expected fields populated. Do not return an approximate dictionary in place of a class instance.

Do not mutate caller-owned documents or the supplied index. Protect the pool lifecycle with a context manager so a worker exception is propagated and resources are shut down; empty input must return promptly without creating a deadlock.

### Query search

First reproduce the reference single-query algorithm exactly in a module-level worker: tokenization, query TF/weights/norm, sparse postings traversal or document-vector traversal, score equation, zero-score inclusion/exclusion, ranking key, result constructor, and top-k slicing. Never infer a tie rule such as ascending ID unless the reference uses it.

Avoid creating a process pool per query. For a multi-query call:

1. Return the reference-consistent result immediately for an empty `queries` sequence.
2. Use a pool initializer to install a read-only index and any document lookup in worker process state once. Send compact work units `(query_ordinal, query, top_k)` or batches of them, not the full index with every task.
3. Batch adjacent queries enough to amortize IPC, while retaining their ordinals. A worker may process a batch sequentially and return `(ordinal, results)` pairs.
4. Merge returned results by ordinal so output order is exactly input-query order. Set `elapsed_time` using a monotonic clock around the actual search operation, compatible with the reference's timing convention.
5. For a single worker, small batch, unpickleable index, or platform start-method issue, use the exact local worker logic rather than failing or silently changing semantics.

If the reference already provides a correct optimized primitive, it may be called inside each worker. Do not call the entire reference batch function once per query if it creates repeated setup or changes timing semantics.

### Performance safeguards

Process startup and Python serialization can dominate small workloads. Do not claim speedup based on tiny samples. Keep workers alive for all chunks or all query batches within one public call, initialize query state once, use contiguous batches, and avoid nested process pools. Do not use threads for CPU-bound Python token/count work when processes are available. Keep deterministic merge order even when it costs a small amount of coordination.

## Required validation

Validate with the actual reference module, not manually estimated TF-IDF values.

- Import `parallel_solution.py` in a fresh Python process.
- Compare sequential and parallel index results field by field: corpus/document count, vocabulary ordering, IDF values, document frequencies, postings, per-document weights, and norms, including types and ordering.
- Compare every `SearchResult` field and ordering for a batch containing normal queries, duplicate queries, no-match queries, empty queries if supported, ties, and multiple `top_k` values.
- Exercise empty inputs and worker counts of 1, 2, and 4 (where the corpus is sufficient).
- Time repeated representative indexing and search workloads after imports; include startup in measurements if that is how the public API is measured. Only report measured behavior, and prioritize exactness if target hardware/workload does not produce the requested ratio.

## Failure handling

Do not conceal exceptions from reference tokenization or malformed documents by dropping data. Preserve reference-visible failures whenever possible. A worker exception must reach the caller instead of leaving executor processes running. If source inspection reveals non-pickleable closures or objects, move worker functions to module scope and pass only serializable data, or use a deterministic sequential fallback with a documented reason.

## Helper scripts

`scripts/inspect_sequential.py` reads JSON from stdin and emits a JSON AST inventory:

```json
{"path": "/root/workspace/sequential.py"}
```

`scripts/compare_values.py` deeply compares two JSON-compatible saved representations, or reports where they differ:

```json
{"left": "/tmp/reference.json", "right": "/tmp/parallel.json", "float_tolerance": 0.0}
```

These scripts do not execute the task solution or generate instance-specific answers; they support inspection and validation.
