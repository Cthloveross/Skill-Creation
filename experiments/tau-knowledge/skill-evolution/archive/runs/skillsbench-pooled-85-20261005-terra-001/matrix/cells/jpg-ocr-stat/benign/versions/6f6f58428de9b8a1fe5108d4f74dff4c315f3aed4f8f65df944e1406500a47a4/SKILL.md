---
name: receipt-ocr-to-xlsx
description: Extract ISO dates and semantically labelled final totals from receipt images and create a strict one-sheet Excel workbook. Use for scanned receipt directories where uncertain fields must be blank rather than invented.
---

# Receipt OCR to XLSX

Run `scripts/build_receipt_report.py` with JSON on stdin. It reads the supplied receipt directory, uses conservative OCR plus recovery variants, selects totals according to the supplied label priority and exclusions, and writes the required workbook.

## Runtime interface

Input is one JSON object:

```json
{
  "input_dir": "/app/workspace/dataset/img",
  "output_path": "/app/workspace/stat_ocr.xlsx",
  "date_order": "auto",
  "workers": 4
}
```

- `input_dir` defaults to `/app/workspace/dataset/img`.
- `output_path` defaults to `/app/workspace/stat_ocr.xlsx`.
- `date_order` is `auto`, `day_first`, or `month_first`. `auto` resolves ambiguous numeric dates only from a consistent date-order signal in the current input.
- `workers` is a positive OCR worker limit.

For example, invoke `python scripts/build_receipt_report.py` from the package directory and provide the JSON object above on standard input. The script emits JSON containing `output_path`, `record_count`, `date_order_used`, and per-file diagnostic records. Diagnostics are not written to Excel.

## Method

1. OCR each image with two conservative, block-layout variants: autocontrasted 2x grayscale and a moderate thresholded version. It also uses limited recovery variants for receipts whose conservative OCR is unclear.
2. Find totals only on non-excluded lines bearing eligible labels. Priority is `GRAND TOTAL`, then `TOTAL RM`/`TOTAL: RM`, then `TOTAL AMOUNT`, then all remaining supplied total/due/amount labels. When an eligible label line lacks a monetary token, inspect the following line and use its last amount.
3. Before broader recovery voting, reproduce the conservative evidence rule: if the best explicit label across the two conservative readings has exactly one normalized decimal amount, use it. This prevents a lower-priority tendered, change, or OCR-hallucinated value from overriding directly grounded final-total evidence. When conservative evidence conflicts, retain the wider OCR ensemble result rather than forcing one OCR reading.
4. Parse valid dates from ISO, textual-month, and numeric forms. Do not assume an order for ambiguous numeric dates without current-input evidence. Leave unsupported or unresolved values null.
5. Write exactly one `results` sheet containing the exact header row `filename`, `date`, `total_amount`; output rows are lexical filename order. Null fields are empty Excel cells. Dates and totals are strings, with totals normalized to two decimal places.

## Validation and failure handling

The script reloads the saved workbook and verifies: exactly one `results` sheet, exact headers, one row per discovered input image, three columns only, lexical filename order, valid ISO date strings, and two-decimal total strings. A failed image leaves its fields null but retains its row. Invalid JSON, an absent input directory, invalid date-order setting, duplicate output basenames, unwritable output, or failed workbook validation is a run-level error.
