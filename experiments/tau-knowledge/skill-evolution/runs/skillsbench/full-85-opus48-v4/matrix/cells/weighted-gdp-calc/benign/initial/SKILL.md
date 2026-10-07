---
name: weighted-gdp-net-exports
description: >
  Fill the "Task" sheet of an Excel workbook (e.g. gdp.xlsx) with two-key lookup
  formulas, net-exports-as-percent-of-GDP formulas, cross-sectional descriptive
  statistics (min, max, median, mean, 25th/75th percentile), and a GDP-weighted
  mean via SUMPRODUCT. Use when a task asks to populate highlighted (yellow)
  formula ranges from a source "Data" sheet using series-code + year lookups,
  compute net exports / GDP, and a GDP-weighted average, while preserving the
  workbook's original formatting (colors, fonts, no macros/new sheets).
---

# Weighted GDP net-exports workbook filler

## What this task requires (public contract)

The workbook has a `Task` sheet (where formulas are entered) and a `Data` sheet
(source matrix). Working only within those existing sheets, you must:

1. **Step 1 — two-key lookup.** Fill three yellow blocks (by default
   `H12:L17`, `H19:L24`, `H26:L31`) using a lookup keyed on BOTH a *series code*
   (Task column `D`) and a *year* (Task row `10`). Use `INDEX&MATCH`,
   `VLOOKUP&MATCH`, `HLOOKUP&MATCH`, or `XLOOKUP&MATCH`. Source values live in the
   `Data` sheet (instruction mentions rows ~21-40).
2. **Step 2 — net exports % of GDP.** In the yellow result block (default
   `H35:L40`, 6 GCC countries x 5 years) compute `(exports - imports) / GDP * 100`
   per country/year, then compute **min, max, median, simple mean, 25th
   percentile, 75th percentile** across the six countries for each year.
3. **Step 3 — GDP-weighted mean.** Compute the net-exports-%-of-GDP weighted mean
   for the GCC per year using `SUMPRODUCT`, weighting each country by its GDP.

Constraints: **do not change the original format** (colors, fonts, column widths,
etc.), **do not add sheets/macros/VBA**, and only write into the designated blank
(yellow) cells. Write real **formulas**, not literals.

## Method and assumptions

* All coordinates, series codes, year headers, and the `Data` layout are
  **discovered at runtime** from the actual workbook. The ranges above are
  defaults taken from the task instruction and are overridable; the scripts
  verify them against the live file.
* Lookups use `INDEX(MATCH(code), MATCH(year))` with absolute/mixed references so
  each formula resolves the correct row (code in `Data`) and column (year header
  in `Data`). A requested code/year that does not match **exactly once** is a
  validation failure, not a silent nearest match.
* Net exports = exports - imports; divide by GDP; multiply by `100` for percent
  (`scale`, configurable). The three source blocks are mapped to
  exports/imports/GDP by label text near each block, defaulting to the block
  order exports, imports, GDP.
* Statistics operate over the 6-country result column for each year. Percentile
  uses the inclusive variant (`PERCENTILE.INC`) by default; switch to the
  exclusive/legacy form only if the workbook/instruction demands it.
* Weighted mean per year = `SUMPRODUCT(netexp_col, gdp_col) / SUM(gdp_col)`.
* Formulas are written with `openpyxl`, which **preserves styles/formatting** and
  does **not** compute values. Because consumers may read cached values, the
  pipeline then recalculates a copy with a headless LibreOffice engine (forcing
  recalc-on-load) so the saved file carries both formulas and fresh cached
  values, and it checks that fills were preserved and no formula errors remain.

## Files

* `scripts/common.py` — shared helpers (workbook load, column letters, value
  normalization, LibreOffice recalc, label search).
* `scripts/inspect_workbook.py` — dump the live workbook structure (sheets,
  dimensions, labels, fills, candidate `Data` layout). Run this FIRST to confirm
  the defaults match the real file.
* `scripts/fill_gdp.py` — end-to-end entrypoint: discover layout, write all
  formulas, recalc, and validate. Reads a JSON config on stdin, writes a JSON
  report on stdout.

## How to run

All scripts read JSON from **stdin** and emit JSON to **stdout**.

1. Inspect the workbook:
   ```bash
   echo '{"path": "/root/gdp.xlsx"}' | python3 scripts/inspect_workbook.py
   ```
   Confirm sheet names, that row 10 holds the years, that column D holds the
   series codes in each block, where the stat/weighted-mean labels sit, and the
   `Data` sheet's code column + year row. Adjust the config below if anything
   differs from the defaults.

2. Fill, recalc, and validate (defaults overwrite `/root/gdp.xlsx` in place):
   ```bash
   echo '{"input_path": "/root/gdp.xlsx"}' | python3 scripts/fill_gdp.py
   ```
   Full config (all optional; shown with task defaults):
   ```json
   {
     "input_path": "/root/gdp.xlsx",
     "output_path": "/root/gdp.xlsx",
     "task_sheet": "Task",
     "data_sheet": "Data",
     "year_row": 10,
     "year_cols": [8,9,10,11,12],
     "code_col": 4,
     "blocks": [[12,17],[19,24],[26,31]],
     "block_roles": ["exports","imports","gdp"],
     "result_rows": [35,40],
     "data_rows": [21,40],
     "data_year_row": null,
     "data_code_col": null,
     "scale": 100,
     "percentile_func": "PERCENTILE.INC",
     "recalc": true
   }
   ```

## Interpreting the report

`fill_gdp.py` prints a JSON report. Treat the run as successful only when:

* `data_layout` has a resolved `code_col`, `year_row`, and value-column span, and
  every requested series code / year resolved **uniquely** (`unresolved_keys`
  empty).
* `wrote` shows the expected counts (3 lookup blocks fully filled, result block
  filled, every requested statistic row found, weighted-mean row found).
* `labels_found` lists min/max/median/mean/p25/p75/weighted (none `null`). A
  `null` label means the script could not locate that output row — re-inspect and
  pass explicit rows if needed.
* `errors_found` is empty (no `#DIV/0!`, `#N/A`, `#REF!`, `#VALUE!`).
* `format_preserved` is `true` (sampled yellow/blue fills unchanged). If recalc
  changed formatting, rerun with `"recalc": false` to keep the exact
  openpyxl-written file (formulas preserved, values left for the consumer's
  engine) and note the trade-off.
* `values_sample` shows plausible percentage-scale numbers after recalc.

## Handling missing / unsupported cases

* If `openpyxl` is missing: `pip install openpyxl` (internet is allowed).
* If LibreOffice (`soffice`/`libreoffice`) is unavailable, recalc is skipped and
  the report flags `recalc_used=false`; the formulas are still correct and
  format is untouched.
* If a block role cannot be inferred from labels, the default order
  exports/imports/GDP is used — verify against the inspected labels and override
  `block_roles` if the sheet orders them differently.
* If any requested key is missing or duplicated in `Data`, the script records it
  under `unresolved_keys`/`duplicate_keys` and does not fabricate a value.
* Do not hardcode computed numbers into the workbook; only formulas are written,
  and only the designated blank cells are touched.
