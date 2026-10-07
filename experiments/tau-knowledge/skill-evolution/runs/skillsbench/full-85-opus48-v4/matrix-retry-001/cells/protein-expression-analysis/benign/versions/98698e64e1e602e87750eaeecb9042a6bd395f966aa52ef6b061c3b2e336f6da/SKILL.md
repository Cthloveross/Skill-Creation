---
name: protein-expression-workbook
description: >
  Fill a two-sheet proteomics Excel workbook (a "Task" sheet and a raw "Data"
  sheet) with formula-based results: a two-way (protein x sample) INDEX/MATCH
  lookup block, per-protein control/treated group mean and standard deviation,
  and log2 fold-change / fold-change. Use this Skill whenever a task asks you to
  look up quantitative expression values by both a protein-row key and a
  sample-column key, compute log-scale group statistics for Control vs Treated
  samples, and write everything as live spreadsheet formulas (not hard-coded
  numbers) while preserving the workbook's fonts, fills and format.
---

# Protein expression workbook filler

## What the task requires

The public task supplies an `.xlsx` workbook (default `/root/protein_expression.xlsx`)
with two sheets:

- **Data**: raw log2-transformed expression values, proteins down one column,
  sample names across one header row (prefixed names like
  `MDAMB468_BREAST_TenPx01`).
- **Task**: the working sheet. You must, using **formulas only**:
  1. **Lookup block** – for the target proteins listed in column A (default rows
     11-20) and the sample names in the sample header row (default row 10,
     columns C-L), fill the value block (default `C11:L20`) with a two-way
     lookup that matches on *both* protein ID and sample name
     (INDEX + two MATCH).
  2. **Group statistics** – a group-label row (default row 9) marks each sample
     column as `Control` or `Treated`. For each protein write the Control mean,
     Control standard deviation, Treated mean and Treated standard deviation
     into the stats block (default rows 24-27, columns B-K; proteins across the
     columns, the four statistics down the rows). Data is already
     log2-transformed, so use ordinary AVERAGE / STDEV.
  3. **Fold change** – for each protein (default fold rows 32-41): column C =
     `Treated mean - Control mean` (log2 fold change), column D = `2^(log2 fold
     change)`.

Constraints: no hard-coded numbers (write real formulas), no macros/VBA, do not
change file format, colors or fonts, do not add sheets.

## Important method notes

- Treat protein IDs and sample names as **opaque keys** and match on both
  dimensions; never assume Data rows are in the same order as the Task targets.
- Build the stats as explicit `AVERAGE(...)` / `STDEV(...)` over exactly the
  Control (or Treated) sample columns discovered from the group-label row, so no
  array formulas or `*IF` guessing is needed.
- openpyxl writes formula *text* but does **not** compute cached values. The
  entrypoint therefore (a) sets `fullCalcOnLoad` so an opening spreadsheet engine
  recalculates, and (b) tries to recalculate in place with LibreOffice
  (`soffice`/`libreoffice`) so a value-reading (`data_only`) reader also sees
  numbers. It then reopens in value mode and checks that the target cells are
  numeric and error-free, and cross-checks them against an independent Python
  recomputation from the Data sheet.
- All coordinates and the Data layout are **discovered at runtime**. The
  documented cell addresses above are only defaults; pass overrides if a future
  workbook differs. Nothing about the current instance's protein IDs, sample
  names or expected numbers is baked into the scripts.

## Files

- `scripts/inspect_workbook.py` – dump the structure of a workbook (sheets,
  dimensions, and a labelled preview of a chosen sheet) so you can confirm the
  layout before writing.
- `scripts/fill_protein_workbook.py` – the end-to-end entrypoint: discover
  layout, write all formulas, set recalculation, recalc with LibreOffice if
  available, then verify.
- `scripts/lib_xlsx.py` – shared helpers.

All scripts read a single JSON object on **stdin** and print a JSON report on
**stdout**.

## How to run (executor)

1. Inspect first (optional but recommended):

   ```bash
   echo '{"path":"/root/protein_expression.xlsx","sheet":"Task"}' \
     | python3 /app/environment/skills/current/scripts/inspect_workbook.py
   ```

   Confirm that column A holds the target protein IDs, the sample header row
   holds sample names, the group-label row holds `Control`/`Treated`, and the
   stats / fold-change yellow blocks are where expected. If they differ from the
   defaults, pass overrides (see the parameter list at the top of
   `fill_protein_workbook.py`).

2. Fill the workbook in place:

   ```bash
   echo '{"path":"/root/protein_expression.xlsx"}' \
     | python3 /app/environment/skills/current/scripts/fill_protein_workbook.py
   ```

   The task edits `protein_expression.xlsx` directly (output_path defaults to the
   input path).

3. Read the printed report. It contains:
   - `discovered`: the Data layout and ranges that were used;
   - `written`: counts of lookup / stats / fold formulas written;
   - `recalc`: whether LibreOffice recalculation succeeded;
   - `verify`: for each target block, how many cells are numeric, blank or
     error, plus `reference_mismatches` comparing cached values with an
     independent Python computation.

   The run is good when every target block reports `errors: 0`, no required cell
   is unexpectedly blank, and `reference_mismatches` is empty (within floating
   tolerance). If `recalc.ok` is false (no LibreOffice), the formulas and
   `fullCalcOnLoad` are still written, so a spreadsheet engine that opens the
   file will recompute; the Python reference check still confirms the formula
   logic is correct.

## Interpreting failures

- Non-numeric / `#...` error cells in the lookup block usually mean a key did
  not match: re-check the discovered protein column and sample header row with
  `inspect_workbook.py`, and that the Task sample header row contains the exact
  prefixed sample strings.
- A `reference_mismatch` on the stats block may indicate the wrong standard
  deviation convention; the default is sample `STDEV`. If evidence shows the
  population form is required, rerun with `{"stdev_func":"STDEV.P"}`.
- If LibreOffice is missing and the grader reads cached values, install/enable a
  spreadsheet engine or rely on `fullCalcOnLoad`; do **not** replace formulas
  with literal numbers (that violates the task).
