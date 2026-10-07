---
name: protein-expression-workbook-formulas
description: Populate a quantitative proteomics Excel task sheet with exact two-key expression lookup formulas, Control/Treated log2-scale summary formulas, and log2 fold-change/fold-change formulas. Use for the supplied protein-expression .xlsx workbook while preserving sheets, formatting, and macro-free structure.
---

# Protein expression workbook formulas

Use `scripts/populate_protein_expression.py` to edit the supplied workbook **in place**. Its default output path is `/root/protein_expression.xlsx`, which is the required delivered artifact. The script reads protein and sample identifiers from the workbook at runtime and does not embed current IDs or expression values.

## Workbook layout handled

The script uses the declared task ranges:

- target protein IDs: `Task!A11:A20`
- requested sample IDs: `Task!C10:L10`
- sample group labels: `Task!C9:L9`
- expression lookup output: `Task!C11:L20`
- Control/Treated summaries: `Task!B24:K27`
- fold-change results: `Task!C32:D41`

It discovers the Data-sheet protein-key column and sample-header row by requiring every requested opaque key to occur exactly once on the respective source axis. It writes `INDEX`/`MATCH` formulas that depend on both the Task protein ID and Task sample ID.

Summary formulas use the group labels in `Task!C9:L9`, rather than assuming that controls and treated samples are contiguous. Mean formulas use `AVERAGEIF`; standard deviations use a sample-SD equivalent based on `SUMPRODUCT`, `COUNTIF`, and `SQRT`, so only samples whose row-9 label is the applicable group contribute. The underlying measurements are already log2 transformed.

Fold-change formulas link each result to the corresponding summary cells:

- log2 fold change: Treated mean minus Control mean
- fold change: `2 ^ log2 fold change`

## Run

Scripts receive one JSON object on standard input and emit one JSON object on standard output.

```bash
python scripts/populate_protein_expression.py <<'JSON'
{"input_path":"/root/protein_expression.xlsx","output_path":"/root/protein_expression.xlsx"}
JSON
```

The explicit identical paths are intentional: save the completed workbook at the required delivery path. Omitting both paths has the same in-place behavior.

Input schema:

- `input_path` (string, default `/root/protein_expression.xlsx`): existing source workbook.
- `output_path` (string, default `/root/protein_expression.xlsx`): completed workbook path; may equal the input path.
- `recalculate` (boolean, default `false`): use installed LibreOffice/soffice to recalculate after formula writing.
- `recalc_timeout_sec` (positive integer, default `120`): external calculation timeout when recalculation is requested.

Success output includes `ok: true`, the delivered `output_path`, discovered Data source coordinates, and formula counts.

## Validation and failure handling

Before writing, the script rejects missing or duplicated target/sample identifiers, ambiguous source axes, invalid group labels, groups with fewer than two samples, incompatible `.xlsx` paths, and absent required sheets. It snapshots the entire Data sheet and all Task cells outside the required formula regions, saves the workbook, then reloads it to verify that those cells and all targeted styles remain unchanged and every target cell contains a formula.

The workbook is marked for automatic full recalculation when opened in a spreadsheet application. If `recalculate` is true, the script requires an installed compatible office executable and verifies that all formula cells remain formulas and evaluate to finite numeric values. It never adds macros or VBA content.
