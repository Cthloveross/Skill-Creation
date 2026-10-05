---
name: recover-missing-xlsx-values
description: Inspect an Excel workbook with numeric values replaced by a marker such as `???`, derive each replacement from evidenced worksheet formulas, labels, totals, percentages, and cross-sheet facts, then safely write and verify a recovered `.xlsx` workbook. Use for spreadsheet data-recovery tasks where the source workbook and required output path are supplied at runtime.
---

# Recover Missing Excel Values

This Skill recovers *only* values justified by the runtime workbook. It does not assume sheet names, cell addresses, year ranges, units, rounding, or a particular reporting layout.

## Prerequisite

The execution environment needs Python and `openpyxl`. The scripts do not run Excel or LibreOffice and therefore do not recalculate formulas; they preserve formula text while writing recovered numeric input cells.

## Workflow

1. **Inspect before editing.** Run the inspector against the supplied workbook:

   ```bash
   python scripts/recover_xlsx.py <<'JSON'
   {"action":"inspect","input_path":"/root/nasa_budget_incomplete.xlsx"}
   JSON
   ```

   The JSON result contains every nonempty cell (with coordinate, type, value, and number format), exact marker locations, merged ranges, hidden rows/columns, and formula references. Use labels and the formula/reference inventory rather than guessed coordinates.

2. **Build an evidence-backed dependency model.** For every marker, identify all relevant constraints, including:
   - a labeled total less its known components;
   - a proportion, percentage, or percentage change, accounting for Excel percent storage (for example, `0.15` displayed as `15%`);
   - an adjacent copied formula whose relative references establish the intended relationship;
   - repeated observations, labels, or independently reported totals on another sheet; and
   - means, differences, or compound-growth summaries only when workbook labels/formulas establish their included observations and interval count.

   Treat `???`, blanks, error cells, and textual values as nonnumeric. Keep unrounded intermediate values. If constraints form a simultaneous linear system, use `scripts/solve_linear.py`; it solves equations of the form `sum(coefficients[var] * var) = rhs` without rounding intermediate results.

   Example input shape (the symbols and numbers below are illustrative only and must be replaced with values derived from the inspected workbook):

   ```json
   {
     "variables": ["unknown_component", "unknown_total"],
     "equations": [
       {"coefficients": {"unknown_component": 1, "unknown_total": -1}, "rhs": -12},
       {"coefficients": {"unknown_component": 2, "unknown_total": -1}, "rhs": 0}
     ]
   }
   ```

3. **Resolve dependency order.** Solve cells whose inputs are known, add the result to the working model, and repeat. For ambiguous inverse calculations based on displayed rounded percentages, use independent constraints to select a unique value. Do not fill a marker if the workbook does not uniquely determine it; report the missing evidence instead of guessing.

4. **Choose write precision from workbook evidence.** Inspect target and neighboring `number_format` values. Preserve full precision for calculations. Write a numeric value with the precision supported by formulas, source values, and displayed conventions; do not convert it to a formatted string merely to match a display.

5. **Apply the complete repair set safely.** Supply all target repairs as `"Sheet name!A1": numeric_value`. Values must be JSON numbers, not strings. By default the script rejects incomplete repair sets and rejects an address that was not an original exact marker.

   ```bash
   python scripts/recover_xlsx.py <<'JSON'
   {
     "action": "apply",
     "input_path": "/root/nasa_budget_incomplete.xlsx",
     "output_path": "/root/nasa_budget_recovered.xlsx",
     "repairs": {
       "A worksheet name!B7": 123.45
     }
   }
   JSON
   ```

   The example address/value is a schema example only. Use the actual inspector output and derivations. The script copies the source workbook, changes only listed marker cells, writes numeric values, saves to the exact requested path, reloads it, and checks that non-target cell values/types and target formats were retained.

6. **Verify the result.** First run file-level verification:

   ```bash
   python scripts/recover_xlsx.py <<'JSON'
   {"action":"validate","input_path":"/root/nasa_budget_recovered.xlsx"}
   JSON
   ```

   It must report `marker_count: 0` and numeric repaired cells. Then independently recompute every applicable total, ratio, change, and cross-sheet repeated fact using the values written. Formulas remain formulas, and cached formula results may be stale until a compatible spreadsheet application recalculates the workbook; do not treat stale cached values as contrary evidence.

## Script interfaces

### `scripts/recover_xlsx.py`

Reads one JSON object from stdin and writes one JSON object to stdout.

- `{"action":"inspect", "input_path": PATH, "marker": "???"}`: returns workbook metadata, sparse cell inventory, target locations, and formula references. `marker` defaults to `???`.
- `{"action":"apply", "input_path": PATH, "output_path": PATH, "repairs": {"Sheet!A1": NUMBER}, "marker":"???", "allow_partial": false}`: applies only original marker cells. Returns repaired coordinates and reload verification. Set `allow_partial` only when a task explicitly calls for partial recovery.
- `{"action":"validate", "input_path": PATH, "marker":"???"}`: returns remaining marker locations and a type/format report for numeric cells formerly identified by the caller only when supplied through `expected_repairs`.

### `scripts/solve_linear.py`

Reads `{"variables":[...], "equations":[{"coefficients":{var:number}, "rhs":number}], "tolerance":number}` and writes either a unique numeric `solution` or a structured error for inconsistent/underdetermined systems. It is appropriate only after the executor has translated documented workbook constraints into linear equations.

## Failure handling

- Stop and report a missing workbook, missing `openpyxl`, malformed JSON, nonnumeric repair, unknown sheet/address, duplicate address, or incomplete repair set.
- Do not overwrite the input path. The output path must differ from it.
- Do not claim a value is recovered merely because a plausible number makes one rounded display look right. Require the workbook's independent evidence.
- Preserve sheet names, formulas, styles, merges, and unrelated cell contents. The repair script explicitly checks all non-target populated cell values and types after save/reload.
