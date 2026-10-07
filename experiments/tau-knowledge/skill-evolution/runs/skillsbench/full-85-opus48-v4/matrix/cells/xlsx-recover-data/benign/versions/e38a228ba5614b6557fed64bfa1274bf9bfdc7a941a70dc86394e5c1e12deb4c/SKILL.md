---
name: xlsx-missing-value-recovery
description: >-
  Recover missing numeric values marked with a placeholder (e.g. "???") in an
  .xlsx workbook by inspecting its real structure, modeling cross-sheet and
  intra-sheet algebraic relationships (totals, percentages/shares, relative or
  compound growth, means, differences, repeated cross-sheet facts), solving the
  resulting constraint system, and writing the computed numeric values back
  while preserving sheets, formulas, styles and structure. Use when a task asks
  to fill placeholders in a spreadsheet and save a recovered copy.
---

# Excel Missing-Value Recovery

## When to use
A task supplies an `.xlsx` with cells holding a textual placeholder (the current
task uses `"???"`) and asks you to replace each placeholder with the correct
*numeric* value derived from relationships in the workbook, then save to a new
path. The current task: read `/root/nasa_budget_incomplete.xlsx`, recover every
`"???"`, save as `/root/nasa_budget_recovered.xlsx`.

Nothing about the sheet names, cell addresses, year range, which values are
missing, the rounding policy, or the solution order is known in advance. Derive
all of it at runtime with the scripts below. Do **not** hardcode answers.

## Method (follow in order)

1. **Inspect, never assume.** Run `scripts/inspect.py` to dump every sheet's
   dimensions, labels, number formats, formulas, cached values, and the exact
   locations of placeholder cells. Read labels as anchors; equivalent facts can
   live at different coordinates on different sheets.

2. **Identify constraints from evidence only.** For each placeholder, look for a
   relationship that is actually present in the workbook (an existing formula, a
   row/column that sums to a labeled total, a percentage-of-total column, a
   year-over-year growth column, a mean/difference, or the *same* entity+period
   fact repeated on another sheet). Common public relationships:
   - Total/component: `x = total - sum(other components)`.
   - Share of total: `s = 100*x/T`  ->  `x = T*s/100`.
   - Relative change: `g = 100*(c-p)/p`  ->  `c = p*(1+g/100)`, `p = c/(1+g/100)`.
   - Compound growth over `n` inferred intervals: `CAGR = 100*((b/a)**(1/n)-1)`.
   - Mean = sum of included observations / count; difference = one minus another.
   Only apply a relationship when a label or existing formula justifies it. The
   number of intervals/observations must come from the labels, not a calendar
   assumption.

3. **Solve.** Treat each placeholder as a variable. Solve variables whose inputs
   are already known, add each result to the known set, and repeat. For linear
   simultaneous constraints feed them to `scripts/linsolve.py` instead of
   guessing an order. For non-linear relations (growth, CAGR, share inversions)
   compute directly in Python using full floating precision; keep intermediate
   values unrounded. A rounded percentage can admit several source values — use
   an independent workbook constraint to pick the unique one; if evidence is
   insufficient for a unique value, do not invent one.

4. **Decide precision from evidence.** Infer rounding from each target cell's
   number format and from neighboring/known values. Round only at write time,
   under the evidenced convention; keep full precision while solving.

5. **Write back safely.** Use `scripts/writeback.py` to copy the original
   workbook to the output path and overwrite only the recovered cells with
   *numeric* values. It preserves sheet names, formulas, styles, merged ranges,
   and other metadata. Never write a number as text.

6. **Verify.** Run `scripts/inspect.py` on the output to confirm no placeholder
   remains, then independently recheck that each inserted value satisfies all
   applicable constraints within the evidenced precision, that cell types stay
   numeric, and that no unrelated cell/structure changed.

## Scripts
All scripts read a JSON object on stdin and print a JSON object on stdout.

### scripts/inspect.py
Input: `{"path": "/root/nasa_budget_incomplete.xlsx", "placeholder": "???"}`
(`placeholder` optional, default `"???"`). Output: `{"sheets": [{"name",
"max_row", "max_col", "merged": [...], "cells": [{"coord","row","col",
"value","data_type","is_formula","number_format","is_placeholder"}...]}],
"placeholders": [{"sheet","coord","row","col"}...]}`. Formulas are read with
`data_only=False`; it also reports cached values with a second pass. Empty cells
are omitted to keep output compact.

Example: `echo '{"path":"/root/nasa_budget_incomplete.xlsx"}' | python3 scripts/inspect.py`

### scripts/linsolve.py
Solves a system of linear equations for the unknown placeholder variables.
Input: `{"equations": [{"terms": {"VARNAME": coeff, ...}, "const": number}],
"knowns": {"VARNAME": value, ...}}`. Each equation means
`sum(coeff*var) == const`. Known variables are substituted automatically. Output:
`{"solution": {"VARNAME": value}, "unique": true|false, "residual": number}`.
Use any string (e.g. `"Budget!C5"`) as a variable name so results map directly
back to cells. `unique` is false when the system is rank-deficient — do not
guess in that case; find another workbook constraint.

### scripts/writeback.py
Input: `{"input_path": "...", "output_path": "...", "values": [{"sheet":
"Name", "cell": "C5", "value": 1234.5}], "placeholder": "???"}`. Copies the
workbook (keeping formulas/styles), writes each `value` as a numeric cell, saves
to `output_path`, and returns `{"written": N, "remaining_placeholders":
[{"sheet","coord"}...]}`. A non-empty `remaining_placeholders` means recovery is
incomplete.

Example end-to-end: inspect -> build equations in your own short Python using the
inspect output -> optionally call linsolve -> call writeback with the final
numeric values -> inspect the output file to confirm zero remaining placeholders.

## Failure handling
- If a placeholder has no evidenced relationship, report it and stop rather than
  inventing a value.
- If `linsolve` reports `unique=false`, add an independent constraint before
  trusting any value.
- If the output still contains placeholders, the task is not complete.

See `references/recovery-notes.md` for the detailed relationship catalogue and
verification checklist.
