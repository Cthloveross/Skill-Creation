---
name: powerlifting-dots-formula-writer
description: >-
  Build the "Dots" sheet of an IPF/OpenPowerlifting-style .xlsx workbook. It
  copies the input columns needed to compute the DOTS coefficient (lifter name,
  sex, bodyweight, and the three best lifts) from the "Data" sheet into the
  empty "Dots" sheet (same column order and names), then appends a "TotalKg"
  column and a "Dots" column, each filled with a real Excel formula. Formulas
  are recalculated with a spreadsheet engine so cached values are correct. Use
  this when a task asks to compute bodyweight-normalized powerlifting (DOTS)
  scores with Excel formulas at a stated decimal precision.
---

# Powerlifting DOTS formula writer

## What this task requires

The public task (`/root/data/openipf.xlsx`, sheets `Data` and `Dots`, with
`/root/data/data-readme.md`) asks for three steps:

1. Find the columns needed to compute DOTS and copy them, **with the lifter's
   name**, into the empty `Dots` sheet, keeping the **same order and header
   names** as in `Data`.
2. Append a new column `TotalKg` after the copied columns, computed with an
   **Excel formula** (sum of the three best lifts).
3. Append a new column `Dots` after `TotalKg`, computed with an **Excel
   formula** (the DOTS coefficient).

Keep **3 digits of precision** for computation (interpreted as 3 decimal
places; exposed as the `precision` parameter so it can be changed).

## Method and assumptions

- **Columns needed to compute DOTS**: `Name`, `Sex`, `BodyweightKg`,
  `Best3SquatKg`, `Best3BenchKg`, `Best3DeadliftKg`. These are resolved from the
  `Data` header row by normalized name matching (case/space/underscore
  insensitive, with a few aliases), **not** by fixed column letters. The copy
  order follows the order the columns appear in `Data`.
- **TotalKg** = `Best3SquatKg + Best3BenchKg + Best3DeadliftKg` (Excel treats
  blank lift cells as 0, matching the source).
- **DOTS** uses the published equation
  `Dots = 500 / (A + B*x + C*x^2 + D*x^3 + E*x^4) * TotalKg`, where `x` is the
  bodyweight (kg) clamped to the published domain. The coefficients and clamp
  ranges differ by sex (see `references/dots.md`). The written Excel formula
  selects the sex branch with `IF(Sex="M", maleDenom, femaleDenom)` and clamps
  the bodyweight inline with `MIN(MAX(bw,40),210)` (men) / `MIN(MAX(bw,40),150)`
  (women). Any sex that is not exactly `"M"` uses the female equation.
- The `Dots` result is wrapped in `ROUND(...,precision)`. `TotalKg` is written
  as a plain sum (an exact value already at the data's precision).
- Formula-writing libraries (openpyxl) do **not** compute cached values, so the
  workbook is recalculated with LibreOffice headless (always-recalc profile).
  If LibreOffice is unavailable, the script injects the Python-computed cached
  values directly into the sheet XML so value readers still see numbers. The
  cells remain real formulas either way.

All workbook coordinates, header names, sheet names, and the number of data
rows are discovered at runtime. Nothing instance-specific is hardcoded.

## How to run

The entrypoint reads a JSON object from stdin and writes a JSON report to
stdout. All keys are optional.

```bash
echo '{}' | python3 /app/environment/skills/current/scripts/write_dots.py
```

Typical explicit call:

```bash
echo '{"xlsx_path":"/root/data/openipf.xlsx","precision":3}' \
  | python3 /app/environment/skills/current/scripts/write_dots.py
```

Input schema:
- `xlsx_path` (string, default `/root/data/openipf.xlsx`)
- `output_path` (string, default = `xlsx_path`, writes in place)
- `data_sheet` (string, default auto: a sheet named `Data`, else the first)
- `dots_sheet` (string, default auto: a sheet named `Dots`, else the second)
- `precision` (int, default 3)

Output schema (stdout JSON): `ok`, `output_path`, `columns_copied`,
`rows_written`, `total_formula_example`, `dots_formula_example`,
`recalc_method`, `verified`, `value_mismatches`, `missing_cached_values`,
`warnings`, and `error` (on failure).

To inspect the workbook first (no changes):

```bash
echo '{"xlsx_path":"/root/data/openipf.xlsx"}' \
  | python3 /app/environment/skills/current/scripts/inspect_workbook.py
```

## Interpreting the result and finishing the task

- Confirm `ok` is true, `rows_written` matches the number of lifters in `Data`,
  and `columns_copied` contains Name/Sex/BodyweightKg and the three Best3
  columns in the same order as Data.
- `recalc_method` should be `libreoffice` or `xml-injection`; `verified` should
  be true with `value_mismatches` = 0 and `missing_cached_values` = 0. The
  report compares the recalculated `Dots` cells against an independent Python
  computation of the same equation.
- The deliverable is the saved workbook at `output_path` (default the input
  path). Do not replace formulas with literals; the task requires formulas.

## Failure handling

- If a required column cannot be matched, the script fails with an explicit
  `error` listing the headers it found; inspect `data-readme.md` and the header
  row and adjust the alias list in `scripts/write_dots.py` (`NEEDED`).
- If LibreOffice is missing, the script falls back to XML cached-value
  injection and sets `recalc_method` accordingly; formulas are still present.
- If `value_mismatches` > 0, re-check the coefficients/clamp ranges in
  `references/dots.md` and the sex-branch logic before any broad rewrite.
