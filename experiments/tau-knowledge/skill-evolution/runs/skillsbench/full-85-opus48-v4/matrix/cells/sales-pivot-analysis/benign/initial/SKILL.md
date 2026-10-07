---
name: sales-pivot-analysis
description: Build an Excel report (/root/demographic_analysis.xlsx by default) that merges SA2-level population data extracted from a PDF with income data from an .xlsx, enriches it with a MEDIAN_INCOME quartile label and a Total column, and emits four NATIVE Excel pivot tables (STATE sums/count and a STATE x Quarter cross-tab of EARNERS) plus a SourceData sheet. Use when a task asks to combine population.pdf + income.xlsx into a demographic pivot-table workbook.
---

# Demographic pivot-table report builder

## What this Skill produces

Given a population PDF and an income .xlsx, it writes one workbook with **exactly
five sheets, in this order and with these exact names** (names are matched
verbatim by consumers; case/spacing/punctuation matter):

1. `Population by State` - pivot: Rows = STATE, Values = Sum of POPULATION_2023
2. `Earners by State` - pivot: Rows = STATE, Values = Sum of EARNERS
3. `Regions by State` - pivot: Rows = STATE, Values = Count of regions (count of rows)
4. `State Income Quartile` - pivot: Rows = STATE, Columns = Quarter (Q1..Q4), Values = Sum of EARNERS
5. `SourceData` - the merged/enriched flat table (headers in row 1) with two added
   columns: `Quarter` (Q1..Q4) and `Total` (= EARNERS x MEDIAN_INCOME)

The four pivots are **real openpyxl pivot-table objects** (pivot cache with a
field list, per-column pivot fields, and row/column/data reference lists), not
static summary cells. All four share one pivot cache (cache index 0) built from
the `SourceData` range.

## Method and assumptions (read before running)

- **Discover the real schema at runtime.** Column names are detected by
  normalized substring (e.g. a header containing `population` -> `POPULATION_2023`,
  `earner` -> `EARNERS`, `median`+`income` -> `MEDIAN_INCOME`, `state` -> `STATE`,
  `sa2`+`code` -> `SA2_CODE`). PDF headers can be truncated/wrapped; detection
  resolves them to the canonical names the task uses. Do not hardcode observed
  codes/state lists.
- **Join key.** `SA2_CODE` is the stable join key present in both sources. The
  join is an **inner join** (only regions present in both sources can appear in a
  pivot that references fields from both). Unmatched keys on each side are counted
  and reported as warnings, not silently dropped without note.
- **Suppressed values.** The ABS marker `np` (not publishable) in numeric columns
  is treated as missing (NaN) and never used in arithmetic. Rows with missing
  MEDIAN_INCOME/EARNERS get blank `Quarter`/`Total` cells; Excel aggregation
  ignores blanks.
- **Quartile definition (ambiguous wording).** The task says quartiles "based on
  MEDIAN_INCOME ranges". The default here is **range-based equal-width binning**:
  take min and max of MEDIAN_INCOME over all joined regions, split that range into
  four equal-width intervals, label the lowest `Q1` up to the highest `Q4`
  (lower-inclusive bins; the maximum falls in Q4). This is distinct from
  percentile/quantile quartiles. The method is a parameter (`quartile_method`:
  `range` or `quantile`). If the oracle rejects `range`, switch to `quantile`
  (same Q1..Q4 labels, boundaries = 25/50/75th percentiles) in the config and
  rerun; keep the chosen definition documented in output.
- **SourceData is the pivot source.** The pivot cache lists one field per
  `SourceData` column, in column order; the pivots reference STATE / POPULATION_2023
  / EARNERS / Quarter by their positional index in that column list.

## How to run

Everything is in `scripts/build_report.py`. It reads an optional JSON config on
stdin and writes JSON status to stdout.

Input JSON (all optional; defaults shown):
```
{
  "income_path": "/root/income.xlsx",
  "population_pdf": "/root/population.pdf",
  "output_path": "/root/demographic_analysis.xlsx",
  "quartile_method": "range"
}
```

Run with defaults:
```
echo '{}' | python3 scripts/build_report.py
```
Or explicitly:
```
echo '{"quartile_method":"range"}' | python3 scripts/build_report.py
```

Output JSON contains `ok`, `output`, `sheets`, `rows`, `quartile_method`,
detected `columns`, and `warnings` (e.g. unmatched join keys, missing deps).
A non-zero exit or `"ok": false` is a failure to inspect, not success.

### Dependencies
`pandas`, `openpyxl`, and `pdfplumber` are required. The script tries to import
them and, if internet is available, falls back to `pip install`. If a dependency
cannot be obtained the script fails loudly with a clear message rather than
producing a partial file.

## Validate the result

After building, confirm the deliverable with `scripts/validate.py`:
```
echo '{"output_path":"/root/demographic_analysis.xlsx"}' | python3 scripts/validate.py
```
It reloads the saved workbook and checks: the five exact sheet names exist in
order; the four pivot sheets each carry a pivot-table object; each pivot's row
field is STATE, the data field aggregation/column assignment match the spec
(sum/sum/count/sum, Quarter on the column axis for sheet 4); and `SourceData`
contains the `Quarter` and `Total` columns with `Total == EARNERS*MEDIAN_INCOME`
on rows where both are numeric. Treat any `"ok": false` as a defect to fix in the
Skill (extraction, detection, pivot construction, or quartile method), not just
in the workspace file.

## Failure modes handled / to watch
- Truncated or repeated PDF headers (multi-page): the extractor takes the header
  from the first table, drops rows equal to the header on later pages, pads/
  truncates ragged rows to the header width, and strips commas before numeric
  casting.
- Income sheet whose header is not row 1: the loader scans for the header row by
  looking for known tokens.
- Missing/`np` numeric values: coerced to NaN, excluded from arithmetic.
- openpyxl pivot writing: a single shared `CacheDefinition` is attached to all
  four `TableDefinition`s so the writer deduplicates it to cache index 0; the
  cache is marked `refreshOnLoad` so Excel recomputes cells on open.

If openpyxl in this runtime rejects a pivot attribute, inspect the installed
openpyxl version and adjust `scripts/pivot_utils.py` (the pivot classes live in
`openpyxl.pivot.cache` and `openpyxl.pivot.table`); keep the row/column/data
reference lists consistent with the per-column pivot-field axis flags.
