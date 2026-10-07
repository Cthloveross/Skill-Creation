---
name: protein-expression-workbook-formulas
description: Populate a quantitative proteomics Excel task sheet with exact two-key expression lookup formulas, Control/Treated log2-scale summary formulas, and log2 fold-change/fold-change formulas. Use for .xlsx workbooks whose task layout follows the stated target/sample/statistic regions while source-table coordinates must be discovered at runtime.
---

# Protein expression workbook formulas

Use `scripts/populate_protein_expression.py` to edit the supplied workbook without hard-coding protein IDs, sample IDs, source coordinates, or calculated values. The script preserves the existing sheets and cell formatting; it changes only the task cells requested by the task.

## Runtime assumptions and discovery

The default layout is the public task layout:

- targets: `Task!A11:A20`
- requested samples: `Task!C10:L10`
- requested lookup output: `Task!C11:L20`
- group labels: `Task!C9:L9`
- statistics output: `Task!B24:K27`
- fold-change output: `Task!C32:D41`

The source `Data` sheet is not assumed to start at a particular row or column. The script locates one source column containing every target protein exactly once and one source row containing every requested sample exactly once. It then writes `INDEX`/`MATCH` formulas using both opaque keys.

For statistics it derives the Control and Treated sample columns from row 9. It writes `AVERAGE` and sample-standard-deviation (`STDEV.S`) formulas over exactly those columns. It identifies statistic rows from their labels when possible; if all four labels are absent, it uses the declared row order: Control mean, Control standard deviation, Treated mean, Treated standard deviation. Statistic columns are aligned to target IDs from headers above the statistics region when those headers are complete; otherwise the declared target order is used. Fold-change rows are aligned by IDs in column B when present.

The workbook values are already on the log2 scale, so the script writes:

- `log2 fold change = treated mean - control mean`
- `fold change = 2 ^ log2 fold change`

## Run

Scripts accept JSON on standard input and emit one JSON object on standard output. For example:

```json
{"input_path":"/root/protein_expression.xlsx","output_path":"/root/protein_expression_completed.xlsx","recalculate":true}
```

Run with:

```bash
python scripts/populate_protein_expression.py <<'JSON'
{"input_path":"/root/protein_expression.xlsx","output_path":"/root/protein_expression_completed.xlsx","recalculate":true}
JSON
```

Input schema:

- `input_path` (string, default `/root/protein_expression.xlsx`): existing `.xlsx` workbook.
- `output_path` (string, default `/root/protein_expression_completed.xlsx`): destination `.xlsx` path. It may equal `input_path`.
- `recalculate` (boolean, default `false`): when true, use an installed LibreOffice/soffice executable to recalculate formulas after the safe `openpyxl` write.
- `recalc_timeout_sec` (positive integer, default `120`): timeout used only when `recalculate` is true.

Output schema on success:

```json
{"ok":true,"output_path":"...","source_key_column":"...","source_header_row":1,"recalculated":false,"details":{"lookup_formula_cells":100,"statistic_formula_cells":40,"fold_formula_cells":20}}
```

## Validation and failure handling

Before writing, the script rejects blank or duplicate requested keys, missing/non-unique source matches, unsupported group labels, groups with fewer than two observations, contradictory output mappings, and non-`.xlsx` paths. It snapshots all source cells and all Task cells outside the specified output regions, then verifies those snapshots and output formulas after saving. It also marks the workbook for full recalculation on load.

With `recalculate: true`, the script additionally reopens the recalculated workbook in value-reading mode and requires every requested formula result to be a finite numeric value. If no compatible LibreOffice executable is available, it fails rather than claiming that cached formula values were verified. Formula recalculation is optional because a formula-writing library does not itself calculate cached Excel results.
