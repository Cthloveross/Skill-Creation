---
name: product-taxonomy-tree-merge
description: Build and validate a five-level unified product taxonomy from Amazon, Facebook, and Google Shopping category CSVs. Use when source files contain hierarchical category paths and the required deliverables are a source mapping CSV and its deduplicated unified-path hierarchy projection.
---

# Product Taxonomy Tree Merge

Use `scripts/build_taxonomy.py` to read the three supplied source CSVs, retain source-local leaf paths, normalize category text, assign semantically broad product domains, construct a bounded five-level tree, and write both required CSV artifacts.

The implementation is deterministic and uses only the Python standard library. It deliberately preserves source attribution and original `category_path` values in the full mapping. Unified labels are standardized, title-cased labels of at most five terms, written with ` | ` between terms. The broad-domain routing vocabulary is generic product-taxonomy policy rather than an input-specific lookup table; lower-level labels always come from observed source-path terms.

## Runtime interface

The script accepts one JSON object on stdin and emits one JSON summary object on stdout.

Input schema:

```json
{
  "input_files": {
    "amazon": "/root/data/amazon_product_categories.csv",
    "facebook": "/root/data/fb_product_categories.csv",
    "google": "/root/data/google_shopping_product_categories.csv"
  },
  "output_dir": "/root/output",
  "keep_leaf_paths": true
}
```

`input_files` and `output_dir` are optional; the shown task paths are the defaults. The parser prefers a `category_path` column, but can identify common path-column variants and delimiter-containing columns in heterogeneous source files. `keep_leaf_paths` defaults to `true`: if both a path and a more-specific extension occur in the same source, the prefix path is omitted. Set it to `false` only when the requester explicitly requires a mapping row for every non-leaf source node.

Runnable call example:

```bash
python3 scripts/build_taxonomy.py <<'JSON'
{"output_dir":"/root/output"}
JSON
```

## Method

1. Read the three requested files, detect their hierarchy-path column, normalize Unicode/case/punctuation, apply conservative English singular normalization, and split paths on `>`.
2. Remove source-local prefix paths by default, retaining the most-specific source paths. Deduplicate exact repeated source paths.
3. Route each path to a generic broad product domain using its normalized path tokens. Unrecognized domains retain a normalized observed top-level label. If needed, a deterministic overflow grouping keeps the root count at no more than 20.
4. Insert the residual observed path components into a trie below the domain root, compacting paths to at most five unified levels. Nodes with more than 20 children are merged using representative observed terms; no blank, numeric-cluster, `Other`, or `Misc` labels are generated.
5. Remove parent terms and frequently shared sibling terms from child display labels when doing so leaves a meaningful observed term. This improves parent-child independence and sibling distinction while preserving the underlying tree.
6. Write `unified_taxonomy_full.csv` with the requested columns. Derive `unified_taxonomy_hierarchy.csv` solely by deduplicating the five unified-level columns of the full mapping. Thus every hierarchy row is traceable to at least one mapping row.
7. Validate headers, path contiguity, depth, hierarchy projection equality, name formatting, child maxima, root count, parent-child token overlap, sibling token overlap, and source proportions per top-level category. Structural failures are reported in `errors`; quality constraint exceptions caused by sparse or source-exclusive data are reported in `warnings` and must be reviewed rather than silently hidden.

## Expected outputs

The supplied `output_dir` receives:

- `unified_taxonomy_full.csv`: `source`, original `category_path`, `depth`, and `unified_level_1` through `unified_level_5`.
- `unified_taxonomy_hierarchy.csv`: unique combinations of `unified_level_1` through `unified_level_5` found in the full mapping.

Inspect the JSON summary before delivery. `errors` must be empty. Review `warnings`, especially root-count, low-child-count, sibling-overlap, and source-exclusive distribution messages. A parent with fewer than three observed children is reported rather than padded with fabricated categories; fabricating nodes would violate the requirement that names be representative of available category names. Likewise, source-exclusive domains are retained and measured, rather than being incorrectly reassigned merely to force equal source counts.
