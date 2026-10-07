---
name: receipt-ocr-to-xlsx
description: Extract normalized receipt dates and label-prioritized payable totals from scanned receipt images into a strict one-sheet Excel workbook. Use when the output requires deterministic source coverage, ISO dates, two-decimal text amounts, and blank cells for unresolved fields.
---

# Receipt OCR to XLSX

Run `scripts/build_receipt_report.py` with one JSON object on standard input. The program discovers images at runtime, performs bounded OCR under ordinary and sparse receipt-layout assumptions, interprets nearby labels using the supplied total-priority rules, and creates the requested workbook.

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
- `date_order` is `auto`, `day_first`, or `month_first`. `auto` only applies a numeric date order when the collection has one consistent unambiguous range-based signal.

For example, pass the object above to `python scripts/build_receipt_report.py`. It emits a JSON summary on stdout. The summary contains extraction diagnostics and is not added to the workbook.

## Method

1. OCR each image with autocontrasted grayscale under ordinary receipt-block (`--psm 6`) and sparse-text (`--psm 11`) layouts. Enlarged and thresholded sparse recovery OCR is used only as supporting evidence.
2. Find total labels in this public priority order: `GRAND TOTAL`; `TOTAL RM` or `TOTAL: RM`; `TOTAL AMOUNT`; then `TOTAL DUE`, `AMOUNT DUE`, `BALANCE DUE`, `NETT TOTAL`, `NET TOTAL`, `TOTAL`, or `AMOUNT`. Lines containing subtotal, tax, GST/SST, discount, change, or tendered-cash exclusions are ignored.
3. Take the last monetary amount on an eligible label line. If no amount is on that line, take the last amount from the immediate next OCR line. Select the strongest label tier before selecting a value. A unique ordinary block-layout candidate is retained rather than allowing more aggressive transformed OCR to overwrite it; sparse OCR is used when ordinary block OCR provides no eligible value. Conflicting unsupported evidence is left blank.
4. Parse ISO, textual-month, and valid numeric dates. Do not guess the order of an ambiguous numeric date unless the configured policy or collection-level evidence establishes it.
5. Write exactly one `results` worksheet with headers `filename`, `date`, and `total_amount`; one lexically sorted row per image; ISO dates and monetary values as strings; and blank Excel cells for null fields.

## Validation and failure behavior

The script reloads the saved workbook and checks that it has exactly one sheet, the exact header row, exactly three columns, deterministic complete filename coverage, valid ISO dates, and non-grouped two-decimal amount strings. Invalid JSON/options, inaccessible directories, duplicate source basenames, write errors, and validation failures are run-level errors. If OCR fails for an individual image, that image still receives a required row with blank extracted fields.
