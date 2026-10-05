---
name: receipt-ocr-to-xlsx
description: Extract ISO dates and labelled final totals from scanned receipt images and produce a strict one-sheet Excel report. Use when receipt fields require OCR, label-priority interpretation, normalized text output, and blank cells for unresolved values.
---

# Receipt OCR to XLSX

Run `scripts/build_receipt_report.py` with a JSON object on standard input. It discovers receipt images at runtime, performs stable OCR preprocessing, selects labelled final totals according to the supplied priority and exclusion rules, and writes the required workbook.

## Runtime interface

Input is one JSON object:

```json
{
  "input_dir": "/app/workspace/dataset/img",
  "output_path": "/app/workspace/stat_ocr.xlsx",
  "date_order": "auto"
}
```

- `input_dir` defaults to `/app/workspace/dataset/img`.
- `output_path` defaults to `/app/workspace/stat_ocr.xlsx`.
- `date_order` is `auto`, `day_first`, or `month_first`. `auto` resolves an ambiguous numeric date only when the current receipt collection has one consistent unambiguous numeric-date ordering signal.

For example, run `python scripts/build_receipt_report.py` from the package directory and provide the object above on stdin. The script emits JSON containing the output path, record count, date-order policy, and per-file diagnostics. Diagnostics are never written to the workbook.

## Extraction method

1. OCR every image with two stable baseline preparations: autocontrasted enlarged grayscale and a moderate threshold version. Baseline OCR is serialized so that the primary label evidence is reproducible and remains directly comparable with an independent OCR review.
2. Read total labels in this priority: `GRAND TOTAL`; `TOTAL RM`/`TOTAL: RM`; `TOTAL AMOUNT`; then `TOTAL`, `AMOUNT`, `TOTAL DUE`, `AMOUNT DUE`, `BALANCE DUE`, `NETT TOTAL`, or `NET TOTAL`. Ignore any matching line containing an exclusion label: `SUBTOTAL`, `SUB TOTAL`, `TAX`, `GST`, `SST`, `DISCOUNT`, `CHANGE`, or `CASH TENDERED`.
3. Select an amount on the best eligible labelled line. When the amount is on the following line, use that line's last amount. The baseline result is preferred when it gives one candidate at the highest observed explicit label priority. If baseline readings conflict, use additional contrast and sparse-layout OCR as recovery evidence and choose the most repeatedly supported candidate at the same best label priority. Lower-priority tender, change, tax, subtotal, and item prices do not override an eligible final total.
4. Parse ISO, textual-month, and numeric dates. Invalid dates and unresolved date-order ambiguity are blank rather than guessed.
5. Create exactly one sheet named `results` with exactly the headers `filename`, `date`, and `total_amount`. Rows are lexical filename order. Missing fields become empty Excel cells; non-null dates and totals are strings, and totals have exactly two decimal places.

## Validation and failures

The script reloads the saved workbook and validates its one-sheet structure, exact headers, three-column shape, one lexical-order row per discovered image, ISO date validity, and monetary-string format. A single-image OCR failure leaves that image's row present with blank fields. Invalid JSON, invalid date policy, absent input directory, duplicate basenames, unwritable output, and workbook validation failures are run-level errors.
