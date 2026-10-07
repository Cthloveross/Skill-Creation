---
name: lab-unit-harmonization
description: >
  Harmonize clinical lab CSV data that mixes conventional (US) and alternative
  (SI/other) units across many analytes. Use when a dataset of lab features must
  be cleaned (drop incomplete rows, fix scientific notation and decimal-comma
  formatting) and converted so every value is expressed in US conventional units,
  within physiologic plausibility ranges, and formatted to exactly two decimals.
  Designed for the CKD lab-data harmonization task but reusable for any analyte
  table resolved through feature descriptions.
---

# Clinical Lab Unit Harmonization

## What this Skill does

Given an input lab CSV and a feature-description CSV, it produces a harmonized
CSV where:

1. rows containing any missing/incomplete field are dropped;
2. scientific notation (`1.23e2`) is expanded to a plain number;
3. decimal commas (`12,34` -> `12.34`) and inconsistent decimal places are
   normalized;
4. values that fall outside an analyte's physiologic range (i.e. that were almost
   certainly reported in an alternative unit) are converted to US conventional
   units with a derived factor, when and only when the converted value lands back
   inside the range;
5. every numeric value is written as `X.XX` (two decimals), with no scientific
   notation and no commas; the column count is preserved.

The method follows the frozen background: resolve analyte identity first (from
column name **and** its description), retrieve only the unit pairs that are valid
for that analyte from a reviewed registry, then decide identity-vs-conversion
using the physiologic range as the independent signal. Plausibility ranges and
conversion factors live in a versioned, cited config (`references/lab_registry.json`)
kept separate from the formatting/parsing logic. Nothing in the registry encodes
this dataset's rows, thresholds-as-answers, or expected outputs.

## Files

- `scripts/harmonize.py` - end-to-end entrypoint. Reads JSON config on stdin,
  writes the harmonized CSV, prints a JSON summary on stdout.
- `scripts/validate.py` - checks a produced CSV against the output contract and
  the registry ranges; prints a JSON report on stdout.
- `scripts/lab_lib.py` - shared helpers (delimiter sniffing, numeric parsing,
  analyte resolution, conversion decision).
- `references/lab_registry.json` - analyte registry: aliases/keywords, US
  conventional unit, plausibility `min`/`max`, and candidate `alt_factors`
  (multipliers that turn an alternative-unit value into the conventional unit).

## How to run (executor)

Defaults already match the task paths, so an empty config works:

```bash
echo '{}' | python3 scripts/harmonize.py
```

Explicit form / overrides:

```bash
echo '{
  "input_csv": "/root/environment/data/ckd_lab_data.csv",
  "descriptions_csv": "/root/environment/data/ckd_feature_descriptions.csv",
  "output_csv": "/root/ckd_lab_data_harmonized.csv"
}' | python3 scripts/harmonize.py
```

Then verify the deliverable can be regenerated and that it satisfies the
contract:

```bash
echo '{"output_csv": "/root/ckd_lab_data_harmonized.csv",
       "input_csv": "/root/environment/data/ckd_lab_data.csv",
       "descriptions_csv": "/root/environment/data/ckd_feature_descriptions.csv"}' \
  | python3 scripts/validate.py
```

### stdin / stdout schema

`harmonize.py` input JSON (all optional; defaults shown above are used when a key
is absent):

```json
{"input_csv": "path", "descriptions_csv": "path", "output_csv": "path",
 "registry": "path-to-registry.json"}
```

`harmonize.py` output JSON summary:

```json
{"ok": true, "input_rows": N, "output_rows": M, "dropped_rows": D,
 "columns": C, "numeric_columns": [...], "resolved": {"col": "analyte"},
 "conversions": {"col": count}, "output_csv": "path"}
```

`validate.py` output JSON: `{"ok": bool, "column_count_match": bool,
"bad_format_cells": [...], "out_of_range": {"col": count}, "issues": [...]}`.

## Interpreting results

- `ok:true` from `harmonize.py` means the file was written. Always then run
  `validate.py`.
- `bad_format_cells` must be empty: every numeric cell must match
  `^-?\d+\.\d{2}$` (two decimals, no `e`/`E`, no comma).
- `column_count_match` must be true (same number of columns as input).
- `out_of_range` lists analytes whose values still sit outside the configured
  plausibility range after conversion. A small residue can be legitimate
  (diseased patients, or an analyte with no alternative unit); a large residue
  for an analyte that has an `alt_factor` suggests the range or factor needs
  tuning in `references/lab_registry.json`, not a change to the parsing code.

## Assumptions and failure modes

- Analyte identity is resolved from the lowercased `column name + description`.
  The longest matching keyword wins, so specific entries (e.g. `direct
  bilirubin`) override general ones (`bilirubin`); `exclude` keywords prevent
  cross-matching (urine vs serum, total vs ionized/direct). Unresolved numeric
  columns are only reformatted, never converted (safe default).
- A conversion is applied only if the raw value is outside `[min,max]` **and**
  exactly one tried factor brings it inside `[min,max]`; otherwise the value is
  left as parsed. This keeps identity values and genuine (but in-range) results
  untouched and avoids forcing ambiguous records through a factor.
- Missing is any empty cell or one of `?`, `na`, `nan`, `null`, `none`, `n/a`
  (case-insensitive). Rows with any missing cell are dropped per the task.
- The CSV delimiter is sniffed (`, ; \t |`) by picking the one that yields the
  most consistent, widest column count; decimal commas inside quoted fields are
  respected by the `csv` module.
- If a required input file is absent, `harmonize.py` prints
  `{"ok": false, "error": ...}` and exits non-zero.

## Tuning safely (for revision)

Edit only `references/lab_registry.json`. Before changing a range/factor,
identify which analyte/column it serves; after editing, rerun `harmonize.py`
then `validate.py` and confirm you did not increase `out_of_range` for other
analytes. Keep each analyte's unit, direction and range independent - do not
apply one correction globally. Do not paste this instance's converted values or
per-row decisions into any packaged file.
