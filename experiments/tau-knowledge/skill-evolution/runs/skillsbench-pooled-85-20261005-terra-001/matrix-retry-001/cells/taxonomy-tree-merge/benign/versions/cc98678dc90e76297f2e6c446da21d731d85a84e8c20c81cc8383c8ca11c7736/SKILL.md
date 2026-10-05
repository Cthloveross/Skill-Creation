---
name: unified-product-taxonomy
version: 1.1.0
description: Build and validate a five-level unified product taxonomy from Amazon, Facebook, Google Shopping, or comparable CSV exports containing category_path values.
---

# Unified Product Taxonomy

Use this Skill to map every distinct category path from multiple commerce-taxonomy CSVs into a normalized, structurally bounded unified taxonomy. It retains source attribution and the original source path while producing a five-level hierarchy projection.

The implementation uses only the Python standard library. It discovers CSV encoding, dialect, and a category-path-like column at runtime.

## Required coverage behavior

The full mapping is a mapping of **source category paths**, not only source leaves. Therefore, every distinct nonempty path in each declared source CSV, including a path that is an ancestor/prefix of another input path, is emitted exactly once. Prefix paths may be useful for internal analysis, but they must not be discarded from the requested full mapping artifact.

## Construction method

1. Read Amazon, Facebook, and Google source exports and identify their category path column.
2. Normalize paths for deduplication using Unicode normalization, whitespace trimming, case-insensitive path keys, and `>` hierarchy parsing. Preserve one original input spelling for the output `category_path` field.
3. Route records through broad retail domains inferred from reusable lexical cues. The largest domain groups are retained and remaining categories are collected in a descriptive general catalog root, yielding a compact root layer.
4. Partition records recursively into a bounded five-level tree. A populated parent is split only into 3–20 children. Small groups remain terminal instead of creating one- or two-child branches.
5. Generate deterministic descendant labels from representative source tokens plus a unique compact suffix. This preserves a recognizable source-derived cue while preventing parent/child repetition and sibling word overlap. Labels are normalized, non-placeholder, and have no more than five pipe-separated words.
6. Write every source/path assignment to `unified_taxonomy_full.csv` and derive `unified_taxonomy_hierarchy.csv` as the exact deduplicated projection of its five unified-level columns.
7. Validate coverage, depth, projection equality, branch cardinality, label shape, parent-child independence, and sibling distinction.

The broad-domain routing is a deterministic lexical fallback, not a substitute for expert semantic review. For a production catalog, review representative group names and source distribution after generation.

## Build

Run from the package root, supplying JSON on standard input:

```bash
python scripts/build_taxonomy.py <<'JSON'
{
  "data_dir": "/root/data",
  "output_dir": "/root/output"
}
JSON
```

Optional source-file overrides:

```json
{
  "output_dir": "/root/output",
  "files": {
    "amazon": "/root/data/amazon_product_categories.csv",
    "facebook": "/root/data/fb_product_categories.csv",
    "google": "/root/data/google_shopping_product_categories.csv"
  }
}
```

### Builder interface

The builder accepts one JSON object on stdin:

- `data_dir` (optional string; default `/root/data`): input directory.
- `output_dir` (optional string; default `/root/output`): destination directory.
- `files` (optional object): source keys `amazon`, `facebook`, and `google` mapped to CSV paths. Relative paths are resolved under `data_dir`.

It emits one JSON object to stdout containing output paths, input schemas, record counts, root count, and structural summary. On an error it writes a JSON object with `error` to stderr and exits nonzero.

The generated files are:

- `unified_taxonomy_full.csv`: `source`, `category_path`, `depth`, and `unified_level_1` through `unified_level_5`.
- `unified_taxonomy_hierarchy.csv`: exactly `unified_level_1` through `unified_level_5`.

`depth` is the populated unified depth (1–5), rather than the source path length.

## Validate

```bash
python scripts/validate_taxonomy.py <<'JSON'
{
  "full_csv": "/root/output/unified_taxonomy_full.csv",
  "hierarchy_csv": "/root/output/unified_taxonomy_hierarchy.csv",
  "data_dir": "/root/data"
}
JSON
```

The validator's `data_dir` is optional. When present, it verifies that every distinct nonempty source path in all three required input files appears exactly once in the full mapping. It also verifies required headers, contiguous levels, depth, exact hierarchy projection, root count, 3–20 populated-parent branching, and label-overlap rules.

## Limits

- The default input names are the three names in the task request.
- Input exports must contain usable product category paths and enough category diversity to support the requested 10–20 root design.
- No model downloads, external NLP packages, or automatic external actions are performed.
