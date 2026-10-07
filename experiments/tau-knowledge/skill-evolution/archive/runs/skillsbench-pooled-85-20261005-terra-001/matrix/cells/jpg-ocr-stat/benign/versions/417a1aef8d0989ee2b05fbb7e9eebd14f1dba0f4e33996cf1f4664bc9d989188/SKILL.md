---
name: receipt-ocr-to-xlsx
description: Extract ISO dates and label-prioritized final totals from scanned receipt images and create a strict one-sheet Excel report. Use for receipt OCR tasks requiring normalized strings, blank unresolved fields, deterministic image ordering, and no workbook metadata tables.
---

# Receipt OCR to XLSX

Run `scripts/build_receipt_report.py` with one JSON object on standard input. The script discovers receipt images at runtime, performs OCR, interprets totals using the supplied label priority and exclusions, and writes the required workbook.

## Runtime interface

Input schema:

```json
{
  "input_dir": "/app/workspace/dataset/img",
  "output_path": "/app/workspace/stat_ocr.xlsx",
  "date_order": "auto"
}
```

- `input_dir` defaults to `/app/workspace/dataset/img`.
- `output_path` defaults to `/app/workspace/stat_ocr.xlsx`.
- `date_order` is `auto`, `day_first`, or `month_first`. In `auto`, an ambiguous all-numeric date is resolved only if the current collection supplies one consistent unambiguous ordering signal.

For example, from the package directory, provide the JSON object above to `python scripts/build_receipt_report.py`. The script emits a JSON summary with its output path, count, date policy, and per-image diagnostics. Diagnostics are not written to Excel.

## Method

1. Run a canonical OCR pass on each receipt using autocontrasted grayscale at original resolution. This pass is preferred whenever it provides one explicit, eligible labelled total, because it minimizes preprocessing-induced digit changes.
2. If the canonical pass cannot establish one labelled total or a usable date, use enlarged, thresholded, and sparse-layout OCR only as targeted recovery evidence.
3. Interpret totals in this order: `GRAND TOTAL`; `TOTAL RM`/`TOTAL: RM`; `TOTAL AMOUNT`; then `TOTAL DUE`, `AMOUNT DUE`, `BALANCE DUE`, `NETT TOTAL`, `NET TOTAL`, `TOTAL`, or `AMOUNT`. Ignore labelled lines containing `SUBTOTAL`, `SUB TOTAL`, `TAX`, `GST`, `SST`, `DISCOUNT`, `CHANGE`, or `CASH TENDERED`. If a qualifying label has no amount, use the last amount from its next OCR line.
4. Parse ISO, textual-month, and numeric dates. Preserve invalid or unresolved date evidence as an empty cell rather than guessing.
5. Create exactly one sheet named `results` with exactly `filename`, `date`, and `total_amount` as its headers. Write one lexically filename-sorted row per discovered image. Dates and totals are strings; totals use exactly two decimal places; unresolved fields are empty Excel cells.

## Validation and failures

The script reloads its workbook and checks the exact sheet set, headers, dimensions, source coverage/order, ISO date validity, and monetary string format. A per-image OCR error leaves that image represented by a row with blank fields. Invalid JSON, an invalid date policy, unavailable input directory, duplicate basenames, output write failure, and validation failure are run-level errors.
