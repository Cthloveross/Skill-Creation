---
name: receipt-ocr-to-excel
description: Extract receipt dates and final payable totals from a directory of scanned receipt images using multi-pass Tesseract OCR, then create a strict three-column Excel workbook. Use when the required output is one sorted record per image with ISO dates, two-decimal monetary strings, and blank values for fields that cannot be supported by the OCR evidence.
---

# Receipt OCR to strict Excel

Use `scripts/extract_receipts.py` for receipt-image directories when Tesseract, Pillow, and openpyxl are available. The script discovers image files at runtime, performs several conservative OCR preparations, selects totals using receipt-label semantics rather than choosing the largest number, normalizes supported dates, and writes a workbook with no extra sheets or fields.

## Run

The script reads one JSON object from standard input and writes one JSON status object to standard output:

```bash
python /app/environment/skills/current/scripts/extract_receipts.py <<'JSON'
{"input_dir":"/app/workspace/dataset/img","output_path":"/app/workspace/stat_ocr.xlsx"}
JSON
```

Input schema:

- `input_dir` (required string): directory recursively containing receipt images.
- `output_path` (required string): `.xlsx` path to create; parent directories are created if needed.
- `debug_dir` (optional string): if set, saves OCR transcripts named after inputs for review. It is not used in the output workbook.

Successful stdout schema is `{"ok": true, "output_path": "...", "records": <integer>, "missing_dates": <integer>, "missing_totals": <integer>}`. On a configuration or processing error it emits `{"ok": false, "error": "..."}` and exits nonzero.

## Method

1. Discover supported raster images (`.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp`, `.webp`) and sort by filename using a deterministic case-insensitive key.
2. OCR each receipt with a small set of grayscale, contrast, and threshold variants and Tesseract page modes suitable for text blocks and sparse receipt text. The script retains every transcript only long enough to compare field candidates; `debug_dir` can preserve them when manual review is needed.
3. Parse candidate totals from lines. Priority is `GRAND TOTAL`, `TOTAL RM`/`TOTAL: RM`, `TOTAL AMOUNT`, then the other supplied total/due/net labels. Lines containing subtotal, tax, discount, change, or tendered-cash exclusions are not used. Amounts on the following line are considered only as a fallback. Comma grouping and decimal punctuation are normalized with `Decimal`, and results are formatted exactly to two decimal places.
4. Parse explicitly labeled dates first. It accepts year-first, separated numeric, and English month-name dates. Ambiguous numeric ordering is not guessed solely from a hard-coded locale: the script uses unambiguous dates in the current collection and, where present, RM currency evidence as a locale signal. If no supported interpretation exists, it writes a blank cell.
5. Write exactly one sheet named `results`, with `filename`, `date`, and `total_amount` in row 1. `None` fields become blank Excel cells. Reload and structurally validate the generated workbook before reporting success.

The executor should inspect the status JSON and, if a value is missing or a suspicious OCR result needs adjudication, inspect the corresponding image and optional transcript rather than inventing a value. Do not add review notes, confidence columns, sheets, or summary rows to the deliverable.
