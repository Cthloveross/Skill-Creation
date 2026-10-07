---
name: receipt-ocr-to-xlsx
description: Extract normalized receipt dates and label-prioritized payable totals from scanned images into a strict one-sheet Excel workbook. Use for receipt OCR tasks requiring deterministic filename ordering, explicit uncertainty handling, and exact Excel schema.
---

# Receipt OCR to XLSX

Run `scripts/build_receipt_report.py` with one JSON object on standard input. It discovers receipt images at runtime, performs several bounded OCR layout passes, associates amounts with eligible total labels, normalizes dates and currency strings, and writes the report workbook.

## Runtime interface

Input JSON:

```json
{
  "input_dir": "/app/workspace/dataset/img",
  "output_path": "/app/workspace/stat_ocr.xlsx",
  "date_order": "auto"
}
```

- `input_dir` defaults to `/app/workspace/dataset/img`.
- `output_path` defaults to `/app/workspace/stat_ocr.xlsx`.
- `date_order` is `auto`, `day_first`, or `month_first`. In `auto`, ambiguous numeric dates are used only if the current collection supplies one consistent unambiguous numeric-order signal.

For example, provide the object above to `python scripts/build_receipt_report.py`. The script writes JSON to stdout containing the output path, record count, selected date policy, and per-image diagnostics. Diagnostics are never written to Excel.

## Extraction method

1. OCR every image using autocontrasted grayscale under both block (`--psm 6`) and sparse (`--psm 11`) layout assumptions. Enlarged sparse and thresholded sparse recovery passes are also retained for difficult or spatially fragmented receipts.
2. Locate eligible total labels by the required priority: `GRAND TOTAL`; `TOTAL RM`/`TOTAL: RM`; `TOTAL AMOUNT`; then `TOTAL DUE`, `AMOUNT DUE`, `BALANCE DUE`, `NETT TOTAL`, `NET TOTAL`, `TOTAL`, or `AMOUNT`. Ignore labels on lines containing subtotal, tax, discount, change, or tendered-cash exclusions.
3. Associate the label with the last monetary value on its line, or with the last monetary value on the immediate next line when the label line contains none. Select the best label priority before comparing OCR variants. Agreement wins; for fragmented receipts, sparse-layout evidence is used when block layout has no eligible candidate. Conflicting unsupported readings remain blank rather than being guessed.
4. Parse ISO, textual-month, and numeric dates. Write only real calendar dates in ISO format. Do not impose a date order on ambiguous numeric dates without an explicit policy or collection-level evidence.
5. Produce exactly one `results` worksheet with headers `filename`, `date`, and `total_amount`; one lexically filename-sorted row per image; string dates and two-decimal string totals; and blank Excel cells for unresolved fields.

## Validation and failure behavior

After saving, the script reloads the workbook and validates its sole sheet, headers, dimensions, filename coverage/order, ISO date validity, and total formatting. Invalid JSON, invalid options, missing input directory, duplicate source basenames, write failures, and workbook validation failures are run-level errors. An OCR failure for one image still produces that image's required row with blank extracted fields.
