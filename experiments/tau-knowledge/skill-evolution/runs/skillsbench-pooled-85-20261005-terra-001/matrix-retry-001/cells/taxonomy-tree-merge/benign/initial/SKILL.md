---
name: unified-product-taxonomy
version: 1.0.0
description: Build and validate a normalized five-level unified product taxonomy from Amazon, Facebook, Google Shopping, or similarly named CSV exports that contain hierarchical category paths.
---

# Unified Product Taxonomy

Use this Skill when several product-category CSV exports must be mapped into one readable, normalized hierarchy while retaining the original source and category path.

The implementation discovers CSV dialects and the category-path column at runtime. It does not assume a particular input header beyond looking for a category/path-like field, and it uses only Python's standard library.

## Method

1. Read the requested source files, detect CSV dialect and text encoding, and discover the path column.
2. Normalize category text consistently: Unicode normalization, punctuation cleanup, tokenization, lightweight English singularization, and title-cased ` | ` output names.
3. Remove source-local redundant prefix paths, retaining the most specific paths while retaining all equivalent original rows for selected leaves.
4. Place paths in broad, reusable retail domains using transparent lexical domain cues. Unknown domains retain a label inferred from their input root. The active roots are limited to at most 20.
5. Construct a source-independent tree from the remaining path labels, truncate/compress it to at most five unified levels, remove redundant unary/binary intermediate branches where possible, and cap excessive sibling branches through descriptive representative group nodes.
6. Remove inherited parent words and unnecessary sibling-shared words from generated labels to improve parent-child independence and sibling distinctiveness.
7. Write the full source mapping and derive the hierarchy strictly by deduplicating the five unified columns from that mapping.
8. Run the supplied validator and inspect its JSON report. Warnings identify unavoidable sparse branches, weak root-count coverage, or breadth that merits human taxonomy review.

The lexical grouping is deliberately a deterministic fallback rather than a claim that every label is a semantic synonym. For especially ambiguous catalogs, inspect the report and the resulting CSVs and refine the taxonomy with domain expertise before production use.

## Build

Run from the package root (or provide absolute paths):

```bash
python scripts/build_taxonomy.py <<'JSON'
{
  "data_dir": "/root/data",
  "output_dir": "/root/output"
}
JSON
```

Optional `files` overrides use a source key and CSV path:

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

### Builder JSON interface

**stdin object**

- `data_dir` (optional string, default `/root/data`): directory containing the three expected input files.
- `output_dir` (optional string, default `/root/output`): directory to create/write.
- `files` (optional object): overrides with keys `amazon`, `facebook`, and/or `google` and CSV path values.

**stdout object** includes `full_csv`, `hierarchy_csv`, record/root counts, selected input schemas, and a structural report. Errors are emitted as a JSON object with an `error` key and a nonzero exit code.

The files created are:

- `unified_taxonomy_full.csv` with `source`, `category_path`, `depth`, and `unified_level_1` through `unified_level_5`.
- `unified_taxonomy_hierarchy.csv` with exactly the five unified-level columns.

`category_path` is retained from the input for traceability. `depth` is the final unified depth, from 1 through 5, not necessarily the source path depth.

## Validate

```bash
python scripts/validate_taxonomy.py <<'JSON'
{
  "full_csv": "/root/output/unified_taxonomy_full.csv",
  "hierarchy_csv": "/root/output/unified_taxonomy_hierarchy.csv"
}
JSON
```

The validator checks required columns, allowed source names, depth/ragged-path consistency, normalized label shape, duplicate hierarchy rows, and the critical invariant that hierarchy rows equal the deduplicated projection of the full mapping. It reports rather than rejects sparse non-leaf branches because real source data can contain short or source-exclusive paths; these warnings should be reviewed against the requested 3–20 child design goal.

## Assumptions and limits

- Paths are normally delimited by `>`; common alternate hierarchy delimiters are also recognized.
- The task inputs should contain product categories, not arbitrary prose.
- Source-local prefixes are excluded as redundant leaves. If a business process requires mappings for prefixes too, retain the source rows separately before applying this Skill or adapt `remove_prefixes` deliberately.
- The package does not download embedding models or perform banking/tool actions. It is deterministic and executable in an offline standard-library Python runtime.
