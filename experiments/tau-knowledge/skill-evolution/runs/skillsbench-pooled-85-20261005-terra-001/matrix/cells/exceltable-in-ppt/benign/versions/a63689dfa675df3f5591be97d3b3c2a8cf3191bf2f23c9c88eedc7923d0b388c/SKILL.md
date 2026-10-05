---
name: update-embedded-excel-exchange-rate
version: 1.0.0
description: Safely updates one explicitly stated exchange rate in an Excel workbook embedded in a PowerPoint OOXML package. Use when a nearby PowerPoint text box supplies a row-currency-to-column-currency rate and formula cells must remain formulas.
---

# Update an embedded Excel exchange-rate table

Use `scripts/update_embedded_fx.py` to update an `.xlsx` embedded in a `.pptx` without rebuilding the presentation or workbook. The script uses only Python's standard library and directly patches the required worksheet cell inside the embedded OOXML package. Thus, styles, merged cells, formulas, workbook metadata, and all unrelated presentation parts are retained.

## Runtime input and output

The script receives one JSON object on standard input:

```json
{
  "input_pptx": "/root/input.pptx",
  "output_pptx": "/root/results.pptx"
}
```

Optional `max_text_candidates` (positive integer, default `12`) controls how many nearby text shapes are considered for a clearly formatted rate instruction.

It emits a JSON audit object on standard output. On success it has `ok: true` and reports the discovered embedded workbook part, text box content, currency pair, changed worksheet/cell, and validation results. On failure it emits `ok: false` with an explicit error and exits nonzero. Do not use a failed output artifact.

Example execution:

```bash
python3 scripts/update_embedded_fx.py <<'JSON'
{"input_pptx":"/root/input.pptx","output_pptx":"/root/results.pptx"}
JSON
```

## Method

1. Discover embedded workbooks from actual slide relationship targets; do not assume a slide, shape, workbook filename, sheet, range, or cell address.
2. Read slide text and geometry from OOXML. Associate a text instruction with the nearest embedded workbook object on its slide.
3. Accept an unambiguous, explicit rate expression such as `USD/EUR: 0.92`, `USD to EUR = 0.92`, or `1 USD = 0.92 EUR`. The source currency is the row key and the destination currency is the column key.
4. Inspect every worksheet and locate the target data cell using worksheet labels: a matching source-currency label to its left in the same row and destination-currency label above it in the same column.
5. Refuse to overwrite a formula, ambiguous label mapping, missing target cell, nonnumeric rate, or unsupported embedded workbook format. This protects the required formula cells rather than silently substituting constants.
6. Patch only the target cell's stored numeric value in the worksheet XML, then replace only the corresponding embedded workbook bytes in a copied PowerPoint package.
7. Reopen and validate the output: ZIP integrity, relationship targets, formula text preservation, expected updated numeric value, and byte identity of all non-embedded presentation parts.

Formula cached results are not recalculated by this standard-library tool. Formula definitions and their existing calculation settings are deliberately preserved. If the presentation requires refreshed formula display caches, open the completed artifact in a compatible spreadsheet engine and save it, while verifying that formulas remain intact.

The executor should deliver the output only after the script reports successful validation and should use the required destination path (`/root/results.pptx` for this task).