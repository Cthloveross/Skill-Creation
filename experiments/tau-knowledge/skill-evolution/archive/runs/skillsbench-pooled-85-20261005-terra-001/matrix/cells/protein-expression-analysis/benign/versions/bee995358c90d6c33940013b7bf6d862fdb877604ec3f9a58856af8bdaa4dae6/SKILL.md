---
name: protein-expression-workbook-formulas
description: Populate a quantitative proteomics Excel task sheet with exact two-key expression lookup formulas, Control/Treated log2-scale summary formulas, and linked log2 fold-change/fold-change formulas. Use for the supplied protein-expression .xlsx workbook while preserving its two sheets, styles, and macro-free structure.
---

# Protein expression workbook formulas

Use `scripts/populate_protein_expression.py` to edit the supplied workbook **in place**. Its default output path is `/root/protein_expression.xlsx`, the required delivered artifact. The script reads protein IDs, sample IDs, group labels, and raw-data orientation from the workbook at runtime; it does not embed instance-specific IDs or expression values.

## Required workbook regions

The task layout is:

- target protein IDs: `Task!A11:A20`
- requested sample IDs: `Task!C10:L10`
- sample groups: `Task!C9:L9`
- expression lookups: `Task!C11:L20`
- Control/Treated summaries: `Task!B24:K27`
- fold changes: `Task!C32:D41`

The source detector locates every requested opaque identifier exactly once on `Data`, recognizes either conventional matrix orientation (proteins down rows/samples across columns or samples down rows/proteins across columns), and requires the resulting 10×10 intersections to be finite numeric values. It then writes `INDEX`/`MATCH` formulas whose two matches depend on the Task protein ID and sample header.

Summary formulas use the Control/Treated labels in row 9 rather than assuming sample order. Means use `AVERAGEIF`; standard deviations use a sample-standard-deviation formula based on `SUMPRODUCT`, `COUNTIF`, and `SQRT`. Summary columns `B:K` and fold-change rows `32:41` follow the declared target order. Log2 fold change is Treated Mean minus Control Mean; fold change is `2 ^ log2 fold change`.

## Run

Scripts receive one JSON object on standard input and emit one JSON object on standard output.

```bash
python scripts/populate_protein_expression.py <<'JSON'
{"input_path":"/root/protein_expression.xlsx","output_path":"/root/protein_expression.xlsx"}
JSON
```

Input schema:

- `input_path` (string, default `/root/protein_expression.xlsx`): existing `.xlsx` workbook.
- `output_path` (string, default `/root/protein_expression.xlsx`): destination `.xlsx` workbook. It may equal `input_path`.
- `recalculate` (boolean, default `false`): when true, recalculate with installed LibreOffice/soffice after formulas are written and require finite numeric caches.
- `recalc_timeout_sec` (positive integer, default `120`): timeout for requested external recalculation.

The success JSON includes the output path, discovered Data orientation and axis coordinates, and formula counts.

## Validation and failure handling

Before editing, the script rejects missing or duplicate IDs, unsupported raw matrix orientation, nonnumeric source intersections, invalid group labels, groups with fewer than two samples, missing required sheets, and non-`.xlsx` paths. It snapshots `Data` and all Task cells outside the requested formula cells. After saving, it reloads the file and verifies that `Data`, unrelated Task cells, and target-cell styles did not change and that every target cell contains a formula.

The workbook is marked for full automatic recalculation when opened. If recalculation is explicitly requested, a compatible office executable must be available; formulas must be preserved and all result caches must be finite numeric values. The script does not add sheets, macros, or VBA content.
