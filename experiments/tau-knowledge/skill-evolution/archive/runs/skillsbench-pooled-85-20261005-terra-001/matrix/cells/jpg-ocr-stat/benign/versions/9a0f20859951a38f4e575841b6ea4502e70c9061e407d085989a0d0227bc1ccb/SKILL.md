---
name: receipt-ocr-to-xlsx
description: Extract ISO dates and labelled final totals from scanned receipt images and produce a strict one-sheet Excel report. Use when receipt fields require OCR, label-priority interpretation, normalized text output, and blank cells for unresolved values.
---

# Receipt OCR to XLSX

Run `scripts/build_receipt_report.py` with a JSON object on standard input. The script reads receipt images at runtime, applies multiple OCR preparations, interprets totals using the supplied label-priority and exclusion rules, and writes the required workbook.

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
- `date_order` may be `auto`, `day_first`, or `month_first`. In `auto`, ambiguous numeric dates are resolved only when the current input supplies one consistent date-order signal.
- `workers` is a positive OCR worker limit.

For example, run `python scripts/build_receipt_report.py` from the package directory and provide the object above on stdin. The script emits JSON containing the output path, record count, resolved date-order policy, and per-file diagnostics. Diagnostics are not added to the workbook.

## Extraction method

1. Perform two baseline OCR passes using autocontrasted, enlarged grayscale and a moderate thresholded version. These baseline passes intentionally preserve ordinary receipt text for independent label-priority selection. Use additional enlarged/contrast/sparse-text passes only as recovery evidence.
2. Select a total only from a non-excluded line with an eligible label: `GRAND TOTAL`, then `TOTAL RM`/`TOTAL: RM`, then `TOTAL AMOUNT`, then the remaining provided total/due/amount labels. If the label has no amount, inspect the following line and use its last amount.
3. For baseline evidence, use literal label matching and two-decimal amounts. If the best baseline label yields exactly one normalized amount across both baseline readings, select it directly. This prevents OCR label-repair heuristics or lower-priority values such as cash tendered, change, tax, and subtotal from overriding a clearly grounded final total. Conflicting baseline OCR is inconclusive and is resolved using the broader labelled candidate ensemble.
4. Parse ISO, textual-month, and numeric dates. Preserve ambiguous numeric dates as null unless an explicit date-order option or consistent current-input evidence resolves them.
5. Create exactly one `results` sheet with the exact headers `filename`, `date`, `total_amount`; write rows in lexical filename order. Null values are empty Excel cells. Non-null dates and totals are strings, and totals have exactly two decimal places.

## Validation and failures

After saving, the script reloads and validates the workbook: exactly one `results` sheet, exact headers, three columns, one row per discovered image, lexical filename order, valid ISO date strings, and valid two-decimal total strings. OCR failure for one image retains its row with blank fields. Invalid JSON, absent input directories, invalid settings, duplicate basenames, unwritable output paths, and workbook validation errors are run-level failures.
