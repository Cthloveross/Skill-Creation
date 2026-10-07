---
name: recover-missing-xlsx-values
description: Recover cells marked with a textual placeholder (such as ???) in an Excel workbook by inspecting its actual sheets, labels, formulas, formats, and cross-sheet numerical constraints. Use when the required deliverable is a minimally changed recovered .xlsx workbook.
---

# Recover Missing Spreadsheet Values

Use this Skill to recover numerically determined placeholder cells without assuming sheet names, coordinates, time periods, or a particular financial model. It uses `openpyxl`, preserves the source workbook structure, and writes only validated numeric replacements.

## Runtime inputs and deliverable

The executor must identify the supplied source workbook and requested output path from the task. For this task, use the supplied workbook as input and create the requested recovered workbook; do not modify the input in place.

The supplied scripts receive one JSON object on standard input and emit one JSON object on standard output. Run them from this Skill directory or provide their full paths.

## 1. Inventory before deriving anything

Inspect the source workbook first. This includes all populated cells, formulas, displayed number formats, merged regions, hidden rows/columns, and every cell whose value is `"???"`.

```sh
python scripts/inspect_workbook.py <<'JSON'
{"input_path":"/root/nasa_budget_incomplete.xlsx","placeholder":"???"}
JSON
```

The JSON response has a `sheets` list. Each sheet includes dimensions, nonempty cells (`coordinate`, `value`, `data_type`, `number_format`, and formula text where applicable), merged ranges, and `placeholders`. Formula cells are shown as formulas rather than calculated values because `openpyxl` does not calculate formulas. Read the full output if it is redirected to a file.

Use labels as anchors, not absolute coordinates. Inspect all sheets for duplicate facts and summaries. Check whether a displayed percent uses a decimal Excel value (for example, `0.12` displayed as `12%`) or an already scaled value (`12`). Number formats and neighboring formulas provide that evidence.

## 2. Build and solve evidenced constraints

For every placeholder, write down its sheet, coordinate, semantic row/column labels, number format, and each independent relationship that constrains it. Common relationships are valid only if the workbook labels, existing formulas, or repeated facts evidence them:

- component = total minus known components;
- current = prior * (1 + percent_change / 100) when the percentage is expressed in percent;
- component = total * share / 100;
- percentage change = 100 * (current - prior) / prior;
- CAGR = 100 * ((end / start) ** (1 / interval_count) - 1), using the number of labeled intervals;
- a labeled mean, difference, or cross-sheet repeated value.

Keep full Python/decimal precision during calculations. Only round a result when nearby stored values, a formula, or its number format establishes a rounding convention. A percentage that is visibly rounded is not by itself sufficient evidence to choose among multiple source values. Use another independent constraint. If a cell is not uniquely determined by the workbook, stop and report that ambiguity rather than inventing a number.

Solve in dependency order: first values with known inputs, then newly unlocked values. For mutually dependent values, solve the small simultaneous algebraic system and verify every equation. Treat blanks, errors, and text as nonnumeric unless their labels specifically establish another meaning.

Prepare replacements as JSON numbers, never quoted numeric strings. For example, the replacement file schema is:

```json
{
  "input_path": "/root/nasa_budget_incomplete.xlsx",
  "output_path": "/root/nasa_budget_recovered.xlsx",
  "placeholder": "???",
  "updates": [
    {"sheet": "actual sheet name", "cell": "A1", "value": 123.45}
  ]
}
```

This is a schema illustration only. Obtain every sheet name, coordinate, and value from the runtime workbook; do not copy example values.

## 3. Apply only validated replacements

After independently checking the proposed numbers against all applicable constraints, pass all replacements to the writer:

```sh
python scripts/apply_recovery.py < replacements.json
```

The writer rejects nonexistent sheets/cells, duplicate updates, targets that did not originally contain the placeholder, nonnumeric or non-finite values, missing placeholder replacements, and output paths equal to the input path. It copies the source workbook, writes numeric cell values while retaining their existing styles/formats, saves to the requested output path, reloads it, and verifies that every original placeholder was replaced and no non-target cell value or formula changed.

Its success JSON reports the saved path, replacement count, and each updated location. A failure means do not claim completion; correct the derivation or input schema and rerun it.

## 4. Final verification

In addition to the writer's structural verification, recompute every workbook-evidenced total, ratio, growth rate, mean, difference, and repeated cross-sheet fact using the saved values. Confirm the inserted number has an appropriate numeric type and its original number format remains. Remember that formulas may retain stale cached results until a spreadsheet application recalculates them; do not use an uncalculated formula cache as sole evidence.

Deliver the saved workbook at the exact requested output path.
