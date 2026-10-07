---
name: protein-expression-workbook-formulas
description: Populate a proteomics Excel template with two-key expression lookup formulas, control/treated log2 summary statistics, and log2 fold-change/fold-change formulas while preserving the workbook layout and formatting. Use for workbooks whose Task sheet has the specified target regions and whose Data sheet stores protein-by-sample expression data.
---

# Protein expression workbook formulas

This Skill writes formulas (not calculated constants) into an existing `.xlsx` template. It treats protein IDs and sample labels as opaque keys. At runtime it discovers the Data-sheet protein-ID column and sample-header row from the Task targets, including Data headers that end with a shorter Task sample label.

## Interface

Run the entrypoint with JSON on standard input:

```bash
python3 scripts/populate_protein_expression.py <<'JSON'
{"input_path":"/root/protein_expression.xlsx","output_path":"/root/protein_expression.xlsx"}
JSON
```

Input fields:

- `input_path` (required): existing `.xlsx` workbook.
- `output_path` (required): destination `.xlsx`; it may equal `input_path`.
- `recalculate` (optional, default `true`): require LibreOffice/soffice headless recalculation before publishing the output.

The script emits one JSON object to stdout containing the output path, the discovered Data layout, and whether recalculation occurred. It raises a clear error rather than guessing if required sheets, targets, group labels, unique Data matches, or expected summary labels cannot be established.

## What it writes

The workbook template is expected to use these requested regions:

- Task `C11:L20`: `INDEX`/`MATCH` formulas matching each Task protein ID and sample label against Data. A Data sample header may have a prefix; the lookup uses the Task label as an exact suffix wildcard.
- Task `B24:K27`: formulas for Control mean, Control sample standard deviation, Treated mean, and Treated sample standard deviation. The four rows are identified from their labels in column A, and the columns are the ordered target proteins from Task `A11:A20` (B corresponds to row 11).
- Task `C32:D41`: fold-change and log2-fold-change formulas for the same ordered target proteins; the row-31 headings determine which of C/D receives each metric.

The Task row-9 group labels must contain exactly the Control and Treated labels for the ten selected sample columns. Since measurements are already log2 transformed, the statistical formulas use arithmetic means and sample standard deviations on that scale. Fold change is `2^(treated mean - control mean)`. Blank Data measurements are kept blank by the lookup formula and are excluded by `AVERAGE`/`STDEV`; a sample standard deviation with fewer than two observed values naturally remains `#DIV/0!`.

Only cell values/formulas in the required output regions are changed; existing styles, fonts, sheet names, merged cells, and other template content are retained.

## Validation and recalculation

`openpyxl` does not calculate formula caches. By default the script therefore saves a staging workbook, opens and converts it with an installed `libreoffice` or `soffice` headless executable, then verifies formula presence and cached results after reopening the final workbook with `data_only=True`: lookup blanks are allowed for missing source measurements, and `#DIV/0!` is allowed only for a standard deviation with fewer than two observations. All other results must be finite numbers. If a spreadsheet engine is unavailable or unexpected formulas do not calculate, it fails instead of delivering stale cached formulas.

Use `"recalculate": false` only when another compatible spreadsheet engine will recalculate the saved workbook; formula-structure validation is still performed, but cached-value validation is skipped.
