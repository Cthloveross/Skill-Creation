---
name: recover-missing-xlsx-values
description: Recover `???` markers in a supplied Excel workbook using formula-evidenced totals, repeated labeled facts, and fiscal-year budget-to-YoY relationships, then create a verified recovered workbook without changing unrelated cells.
---

# Recover Missing Excel Values

Use this Skill when a runtime `.xlsx` workbook contains textual missing-value markers (normally `???`) that must be replaced with numeric values and saved under a required output name. All cell locations and values are discovered from the supplied workbook at runtime; this Skill does not encode a workbook layout or answers.

## Prerequisites and safety

Python and `openpyxl` must be available. `openpyxl` preserves formula text but does not calculate formulas, so this Skill uses formula syntax plus pre-existing cached values only where the original workbook evidences them. It changes only original marker cells and preserves their styles and number formats.

Never overwrite the source workbook. Do not fill a cell merely because a number seems plausible. A repair needs an evidenced formula, a unique repeated fact, or a uniquely determined budget/change relationship.

## Recommended end-to-end workflow

1. Inspect the supplied workbook before making assumptions:

   ```bash
   python scripts/recover_xlsx.py <<'JSON'
   {"action":"inspect","input_path":"/root/nasa_budget_incomplete.xlsx"}
   JSON
   ```

   Review sheet names, marker locations, labels, header years, number formats, formulas, hidden rows/columns, and merged ranges. Labels and years—not assumed coordinates—are the anchors.

2. Ask the derivation engine to construct a conservative repair proposal:

   ```bash
   python scripts/recover_xlsx.py <<'JSON'
   {"action":"derive","input_path":"/root/nasa_budget_incomplete.xlsx"}
   JSON
   ```

   `derive` returns `repairs`, `evidence`, and `unresolved_targets`. It recognizes:
   - a component in an original simple `SUM(...)` formula when the formula has an original cached numeric total;
   - a unique numeric repeated fact with the same row and column labels on another sheet; and
   - a marker in a YoY/change/rate sheet whose row entity and fiscal-year headers uniquely match budget observations for that year and its predecessor.

   A YoY rate is calculated as `100 * (current - previous) / previous`. The engine writes the rate as a percent fraction only if the target number format is an Excel percent format; otherwise it writes percentage points. It rounds only to an explicit decimal precision in the target format. Inspect the supplied evidence, especially any fuzzy label match, before applying it.

3. If all markers were resolved, create the requested artifact directly:

   ```bash
   python scripts/recover_xlsx.py <<'JSON'
   {"action":"recover","input_path":"/root/nasa_budget_incomplete.xlsx","output_path":"/root/nasa_budget_recovered.xlsx"}
   JSON
   ```

   `recover` refuses to create a claimed complete output if any marker is unresolved. Alternatively, provide manually derived, reviewed numeric values to `apply`:

   ```bash
   python scripts/recover_xlsx.py <<'JSON'
   {
     "action":"apply",
     "input_path":"/root/nasa_budget_incomplete.xlsx",
     "output_path":"/root/nasa_budget_recovered.xlsx",
     "repairs":{"Actual worksheet name!A1":123.45}
   }
   JSON
   ```

   Addresses and values above are schema examples only. Repair values must be JSON numbers, never quoted numeric strings. By default every original marker must be covered.

4. Reload and validate the saved artifact:

   ```bash
   python scripts/recover_xlsx.py <<'JSON'
   {"action":"validate","input_path":"/root/nasa_budget_recovered.xlsx"}
   JSON
   ```

   Require `marker_count: 0`, numeric repaired cells, and no reported non-target changes from `apply`/`recover`. Independently review every applicable formula, repeated fact, and YoY computation. In particular, a row label such as “Total” is not evidence that percentage rates are additive; only an actual additive formula supports a total constraint.

## Script interface

`scripts/recover_xlsx.py` reads one JSON object from stdin and emits one JSON object on stdout.

- `inspect`: `{"action":"inspect","input_path":PATH,"marker":"???"}` returns a sparse workbook inventory and formulas.
- `derive`: `{"action":"derive","input_path":PATH,"marker":"???"}` returns numeric proposed `repairs`, per-cell evidence, and unresolved markers; it does not edit a file.
- `recover`: `{"action":"recover","input_path":PATH,"output_path":PATH,"marker":"???"}` derives and applies only when every marker is uniquely resolved.
- `apply`: `{"action":"apply","input_path":PATH,"output_path":PATH,"repairs":{"Sheet!A1":NUMBER},"marker":"???","allow_partial":false}` safely writes an explicit repair set.
- `validate`: `{"action":"validate","input_path":PATH,"marker":"???","expected_repairs":{"Sheet!A1":0}}` reports remaining markers and types of optional checked cells.

For an explicitly translated simultaneous linear system, `scripts/solve_linear.py` accepts `{"variables":[...],"equations":[{"coefficients":{"x":1},"rhs":2}]}` and emits a unique solution or an underdetermined/inconsistent error. Keep full precision through calculations and use the workbook’s demonstrated display convention only when writing the result.

## Failure handling

Stop and report missing files, malformed JSON, unsupported formulas, nonnumeric repairs, unknown sheets/cells, duplicate normalized addresses, unresolved markers, ambiguous label matches, zero prior-year values, or attempts to overwrite the input. If `derive` cannot establish a unique repair, inspect the workbook and add only independently evidenced constraints; do not guess.
