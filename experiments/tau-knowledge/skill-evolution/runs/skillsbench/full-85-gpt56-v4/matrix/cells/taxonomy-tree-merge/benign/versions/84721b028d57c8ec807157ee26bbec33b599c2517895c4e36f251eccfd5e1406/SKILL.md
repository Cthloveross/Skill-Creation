---
name: product-taxonomy-unifier
description: Build and validate a traceable, normalized unified product taxonomy from Amazon, Facebook, Google Shopping, or similarly shaped CSV category-path exports. Use when every input category must be retained in a full mapping and a deduplicated hierarchy CSV is required.
---

# Product Taxonomy Unifier

This Skill creates the two required taxonomy CSV artifacts while retaining one mapping row for every non-empty source `category_path`. It uses only the Python standard library, so it is suitable for constrained runtime environments.

## Method

1. Load each CSV and locate `category_path` case-insensitively. Source identity comes from the input file mapping, not from a source column that may be absent or inconsistent.
2. Normalize labels consistently: Unicode normalization, case folding, punctuation cleanup (`&` becomes `and`), whitespace cleanup, and conservative English singularization. Input paths remain unchanged in the output `category_path` column for traceability.
3. Assign every path to a reusable broad product domain. The domain classifier uses category terms rather than source-specific identifiers, yielding up to 16 shared roots. It then assigns a distinct, semantic second-level merchandise family. A bounded `Specialty | Goods` family contains unmatched long-tail labels rather than creating unlimited one-off siblings. These labels are intentionally source-neutral so a comparable item from different platforms is assigned the same branch.
4. Where an occupied family has between 3 and 20 clearly distinct normalized terminal labels, retain those labels as a third level. This adds detail only when it can meet the sibling-width constraint without inventing buckets. Otherwise the branch correctly terminates at level 2. All five output columns are still present; unused deeper levels are blank.
5. Derive the hierarchy strictly by deduplicating the five unified-level columns in the full mapping. It cannot contain an unmapped path.
6. Validate row coverage, headers, rooted/no-gap paths, hierarchy projection equality, duplicate hierarchy rows, root count, child widths, label length, parent/child word overlap, and sibling overlap. Structural failures stop the run. Quality constraints are returned as warnings because sparse real source domains cannot truthfully be padded with fabricated categories.

The design does not use source-dependent reassignment to force balance: doing so would put semantically unrelated products together. Instead, the shared semantic rules allow each source to populate common branches naturally. The JSON summary reports per-root source counts so an executor can inspect actual cross-source representation.

## Run

The script receives one JSON object on standard input and emits one JSON result on standard output.

```bash
python3 /app/environment/skills/current/scripts/build_taxonomy.py <<'JSON'
{
  "input_dir": "/root/data",
  "output_dir": "/root/output",
  "source_files": {
    "amazon": "amazon_product_categories.csv",
    "facebook": "fb_product_categories.csv",
    "google": "google_shopping_product_categories.csv"
  }
}
JSON
```

`source_files` is optional when the three filenames above are present. Use explicit `source_files` for differently named exports. Input schema:

- `input_dir` (string): directory containing source CSVs.
- `output_dir` (string): destination directory, created if necessary.
- `source_files` (object, optional): `{source_name: filename}`.
- `strict_quality` (boolean, optional, default `false`): make quality warnings fail the run after both files are written.

Output JSON contains `ok`, output paths, input/mapping/hierarchy row counts, roots, source distribution by root, and validation warnings. It fails with a clear error for missing files, missing/empty `category_path`, malformed structural output, or an unsupported root count.

## Produced files

- `unified_taxonomy_full.csv`: `source`, original `category_path`, computed `depth`, then `unified_level_1` through `unified_level_5`.
- `unified_taxonomy_hierarchy.csv`: exactly the distinct five-level tuples from the full mapping, in the required column order.

The executor should inspect the returned warning list and distribution before accepting a run. In particular, sparse domains with fewer than three observed families are reported rather than padded with artificial paths. Any semantic review or manual enrichment should update reusable classification rules in the script, then rerun the script so both artifacts are regenerated together.
