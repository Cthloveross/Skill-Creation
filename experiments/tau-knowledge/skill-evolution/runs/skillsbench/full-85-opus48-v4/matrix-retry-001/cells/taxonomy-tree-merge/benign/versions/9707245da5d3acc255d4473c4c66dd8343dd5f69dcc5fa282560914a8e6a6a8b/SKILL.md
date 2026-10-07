---
name: taxonomy-tree-merge
description: >-
  Merge multiple e-commerce product category taxonomies (e.g. Amazon, Facebook,
  Google Shopping CSVs each with a hierarchical `category_path` column) into a
  single unified 5-level taxonomy. Produces a full mapping CSV (source,
  category_path, depth, unified_level_1..5) and a deduplicated hierarchy CSV
  (unified_level_1..5). Use this Skill whenever the task supplies several source
  taxonomy CSVs and asks for a unified multi-level category tree with naming,
  normalization, parent/child/sibling and pyramid-balance constraints.
---

# Taxonomy Tree Merge

## When to use
The task gives several CSV files, each containing hierarchical category paths
(segments joined by `>`), and asks you to build **one** unified 5-level taxonomy
and write two CSV outputs. The method is lexical+semantic clustering of the
normalized leaf paths into a recursive tree, with representative naming.

## Public contract this Skill satisfies
From the task opening (treat the live request as authoritative; re-read it):
1. Top level has 10-20 broad categories; each deeper level has 3-20 subcategories per parent.
2. Category names come from the available category words, use `" | "` as the
   separator between words, use no more than 5 words, and each category should be
   representative (>=70% token coverage) of its members.
3. Standardize category text (lowercase, strip punctuation `& / - ' , ( )`, drop
   the pipe char from source text, lemmatize each word).
4. A subcategory name must not repeat its parent's words.
5. Sibling categories must be distinct (<30% word overlap).
6. Balance cluster sizes into a reasonable pyramid.
7. Distribute the different sources relatively evenly.

Outputs to `/root/output/`:
- `unified_taxonomy_full.csv`: `source,category_path,depth,unified_level_1,unified_level_2,unified_level_3,unified_level_4,unified_level_5`
  where `source` is `amazon`/`facebook`/`google` and `depth` (1-5) is the number
  of populated unified levels for that row (the unified-taxonomy depth, NOT the
  original source path depth, which can exceed 5).
- `unified_taxonomy_hierarchy.csv`: `unified_level_1,...,unified_level_5` — the
  unique node paths from low granularity (level 1 only) up to the deepest path
  that appear in the full mapping, deduplicated. Missing deeper levels are empty.

## Method (implemented in `scripts/`)
Phase 1 Preprocessing (`taxonomy_lib.load_sources`, `remove_prefix_paths`):
load each CSV, detect the path column, split on `>`, normalize+lemmatize each
segment, and remove redundant prefix paths within a source (keep only leaf
paths). Original `category_path` and `source` are preserved for the full CSV.

Phase 2 Representation (`taxonomy_lib.get_embeddings`): embed each unique
normalized full-path string **once**. Tries `sentence-transformers`
(all-MiniLM-L6-v2) if available/online, otherwise falls back to a deterministic
TF-IDF (word 1-2grams) + TruncatedSVD vector. Vectors are L2-normalized so cosine
~= dot product.

Phase 3 Recursive construction (`taxonomy_lib.recurse`): agglomerative (average,
cosine) clustering, falling back to (MiniBatch)KMeans for very large sets. Top
level picks k in [10,20]; deeper levels pick k in [3,20] (never more than the
member count) and only subdivide groups with >= 6 members and depth < 5.
Each cluster is named by `generate_sibling_names`, which enforces the task's
naming rules as hard constraints:
  * single-character tokens are dropped (removes stray `s` from `women's` etc);
  * all ancestor-name tokens are excluded from candidates AND fallbacks, so a
    child name can never repeat a parent/grandparent word (parent/child
    independence, rule 4);
  * tokens appearing in > ~60% of the sibling groups (>=5 siblings) are treated
    as non-distinctive "local theme" words and excluded, keeping siblings
    distinct (rule 5 <30% word overlap). This is NOT applied at the top level,
    which cannot drop clusters;
  * a greedy set-cover picks the fewest tokens (<=5) that cover >=70% of members
    (rule 2 representativeness), tie-broken by distinctiveness;
  * a differentiation pass adds a distinguishing token to any sibling pair whose
    word Jaccard is still >=0.30;
  * names are made unique among siblings; a group that cannot earn a
    representative, parent-distinct, unique name returns `None`.
`recurse` keeps a child only if its coverage >= 0.70 (the top level is exempt so
every source row gets a level-1 category). `None`/under-covered children merge
back up (members become leaves at the parent). If a node cannot yield >= 3
representative children it is not split at all, so every parent has either 0 or
3-20 children (rule 1).

Phase 4 Output (`scripts/pipeline.py`): every retained source row inherits its
unique path's name list, padded to 5 levels, and its `depth` is the count of
populated unified levels (1-5). The hierarchy CSV is built from the
unique prefixes of every assigned path (length 1..L), deduplicated and sorted,
guaranteeing structural integrity (every node's ancestors are present).

## Running it
```bash
mkdir -p /root/output
echo '{"data_dir":"/root/data","output_dir":"/root/output",
       "files":{"amazon":"amazon_product_categories.csv",
                "facebook":"fb_product_categories.csv",
                "google":"google_shopping_product_categories.csv"}}' \
  | python3 /app/environment/skills/current/scripts/pipeline.py
```
With no stdin (or empty JSON) it defaults to `data_dir=/root/data`,
`output_dir=/root/output` and the three file names above. Adjust `files`/paths
to match the live task if they differ (re-read the opening and
`/root/data/README.md`). `embedding` may be `"auto"` (default), `"tfidf"`, or
`"st"`.

### stdin / stdout schema
stdin JSON (all keys optional):
`{"data_dir":str,"output_dir":str,"files":{source_label:filename,...},"embedding":str}`
stdout JSON:
`{"status":"ok"|"error","full_csv":path,"hierarchy_csv":path,`
` "stats":{...},"validation":{...warnings...}}`. On error, `status="error"` and
`message` explain the failure; inspect and fix inputs/paths rather than assuming
success.

## Executor checklist
1. Confirm the three (or actual) input CSVs exist under `data_dir` and have a
   path-like column; `pipeline.py` auto-detects `category_path` or the column
   with the most `>` separators.
2. Run the pipeline; confirm both CSVs were written and `status=="ok"`.
3. Read the printed `validation` block: `n_level1` must be in [10,20];
   `child_count_violations` should be 0 or small; `min_name_coverage` should be
   >= 0.70 (enforced by the coverage floor) and `parent_child_overlap`,
   `names_over_5_words`, `structural_breaks` should be 0; `sibling_overlap_pairs`
   should be a small fraction of `sibling_pairs_total` (a few stubborn 5-word
   pairs may remain). Treat non-zero as quality issues to tune
   (e.g. k ranges, coverage target, token scoring) — do not fabricate outputs.
4. Verify the hierarchy CSV is a subset projection of the full CSV and that
   every row's ancestors exist (the generator enforces this; re-run the
   validator if you edit outputs).

## Notes / failure handling
- If `sentence-transformers` cannot load (offline/no model), the TF-IDF fallback
  is used automatically and the pipeline still completes deterministically.
- If a source file is missing it is skipped with a warning; if none load the
  script returns `status="error"`.
- Do not hardcode any instance-specific category names, counts, or answers; the
  pipeline derives everything from the supplied CSVs at runtime.
