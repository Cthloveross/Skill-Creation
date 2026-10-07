# Method notes and tuning levers

These notes record the design choices in `scripts/taxonomy_lib.py` /
`scripts/pipeline.py` and where to adjust them if validation flags problems.
They are task-independent; the live CSVs and the live task's constraints always
take precedence.

## Constraint -> implementation mapping
- 10-20 top categories / 3-20 per deeper parent -> `choose_k` clamps and the
  `min_split=6` / `k>=3` guards in `recurse`. If `child_count_violations` is
  high, lower `min_split` or widen/narrow the clamp ranges.
- Names from available words, `" | "` separator, <=5 words, >=70% coverage ->
  `generate_sibling_names` (greedy token selection with `target_cov=0.70`,
  `max_words=5`). If `min_name_coverage` is low, raise `max_words` or relax the
  distinctiveness penalty.
- Standardization -> `normalize_segment` (lowercase, `[^a-z0-9]+`->space,
  per-word lemmatization). The pipe char is stripped from source text so it only
  ever appears as the name separator.
- Parent/child independence -> ancestor name tokens are threaded through
  `recurse` and excluded from child candidates.
- Sibling distinctiveness (<30% overlap) -> token score divides in-group df by
  the number of siblings sharing the token; validator reports
  `sibling_overlap_pairs`.
- Pyramid balance -> `choose_k` uses sqrt-of-size so larger sets split into more
  children; agglomerative average linkage keeps clusters comparable.
- Source balance -> clustering is on semantic/lexical content, not source, so
  sources mix; `stats.source_counts` lets you confirm.

## Prefix removal
`remove_prefix_paths` keeps only leaf paths per source (a path that is a proper
prefix of a longer path in the same source is dropped) to avoid inflated counts.
The retained leaf rows are exactly the rows written to the full CSV.

## Hierarchy construction
The hierarchy CSV contains every unique prefix (length 1..L) of each assigned
path, padded to 5 columns with empty strings — "all paths from low granularity
to high". This guarantees structural integrity: a node never appears without its
ancestors. The validator's `structural_breaks` must be 0.

## Embedding fallback
`get_embeddings` prefers sentence-transformers (all-MiniLM-L6-v2) but silently
falls back to deterministic TF-IDF(1-2gram)+SVD when the model is unavailable or
offline. Both yield L2-normalized vectors used with cosine distance.

## If outputs look wrong
Re-run the exported entrypoint and read the stdout `validation`/`stats` block;
do not hand-edit the CSVs as a fix, change the reusable logic instead. Always
verify the entrypoint can regenerate both CSVs from the supplied data.
