---
name: receipt-ocr-to-xlsx
description: >-
  Extract the transaction date (normalized to ISO YYYY-MM-DD) and the final
  payable total amount (as a string with exactly two decimal places) from a
  folder of scanned receipt JPG/PNG images using Tesseract OCR, and write one
  deterministic single-sheet .xlsx file. Use this skill when a task supplies a
  directory of receipt images and asks for a per-file spreadsheet of
  filename/date/total_amount with a strict header schema, filename ordering,
  nulls for failed fields, and no extra rows/columns/sheets.
---

# Receipt OCR to XLSX

## When to use

The public task gives a directory of scanned receipt images (digits + English
text) and wants an Excel file whose single sheet `results` has exactly three
columns `filename`, `date`, `total_amount`, one data row per discovered image,
ordered by filename, header row first, and `null` (empty cell) whenever a field
cannot be extracted. The test compares the workbook with an oracle line by line,
so the schema, ordering and value formatting must match exactly.

This skill is task-independent: it reads the image directory and output path at
runtime (defaults match the current task) and never hardcodes extracted values.

## Method (recognition -> interpretation -> normalization -> output)

1. **Discover inputs.** List every file in the image directory with a known
   image extension (`.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp`), sorted by
   filename. There must be exactly one output row per discovered image.
2. **Recognize text.** For each image run Tesseract via `pytesseract` on a
   lightly preprocessed image (grayscale + autocontrast + moderate upscale) with
   a small set of page-segmentation modes (`--psm 6` and `--psm 4`). Keep all raw
   lines from every pass; more candidate text is better for field search and no
   global character substitution is applied (corrections stay local to parsers).
3. **Interpret the total amount** using the task's keyword priority tiers
   (most specific first): `GRAND TOTAL`; then `TOTAL RM`/`TOTAL: RM`; then
   `TOTAL AMOUNT`; then the generic group `TOTAL`, `AMOUNT`, `TOTAL DUE`,
   `AMOUNT DUE`, `BALANCE DUE`, `NETT TOTAL`, `NET TOTAL`. Lines containing any
   exclusion keyword (`SUBTOTAL`, `SUB TOTAL`, `TAX`, `GST`, `SST`, `DISCOUNT`,
   `CHANGE`, `CASH TENDERED`) are skipped. The amount is taken from the matching
   line; if that line has no number, fall back to the last number on the next
   line. Comma grouping (`1,234.56`) is handled. A value with two decimals is
   preferred over a bare integer.
4. **Interpret the date** from numeric (`DD/MM/YYYY`, `YYYY-MM-DD`, etc.) and
   month-name forms, validating ranges. Ambiguous day/month is resolved by
   evidence (a component > 12 is the day) and otherwise day-first, which matches
   typical receipt layouts; two-digit years map to 20xx. Output ISO
   `YYYY-MM-DD`.
5. **Normalize + validate output.** `total_amount` is emitted as a string with
   exactly two decimals (e.g. `47.70`). Failed fields become `None` (empty
   cell, i.e. null). Write a fresh workbook whose only sheet is renamed to
   `results`, write the header row, then data rows sorted by filename. Do not
   add extra columns, rows, summary cells or sheets.

When evidence is insufficient, leave the field null rather than inventing a
value (as the background advises).

## Files

- `scripts/run_pipeline.py` — end-to-end entrypoint. Reads JSON on stdin, writes
  the xlsx, prints a JSON summary on stdout.
- `scripts/ocr_receipt.py` — importable helpers: image discovery, OCR,
  amount parsing, date parsing/normalization, amount formatting.
- `references/field_rules.md` — the exact keyword/exclusion lists and formatting
  rules, kept separate so they can be audited and tuned.

## Running

From the task container (Tesseract, pytesseract, Pillow, openpyxl available):

```bash
echo '{"img_dir": "/app/workspace/dataset/img", "output": "/app/workspace/stat_ocr.xlsx"}' \
  | python3 /app/environment/skills/current/scripts/run_pipeline.py
```

With no stdin (or empty JSON) the script uses those same defaults, so a bare
`python3 scripts/run_pipeline.py` also works for the current task.

### stdin schema

```json
{
  "img_dir": "/app/workspace/dataset/img",   // optional, dir of receipt images
  "output":  "/app/workspace/stat_ocr.xlsx", // optional, xlsx path to write
  "debug_json": "/tmp/ocr_debug.json"         // optional, dump per-file OCR text + candidates
}
```

### stdout schema

```json
{
  "output": "/app/workspace/stat_ocr.xlsx",
  "count": 22,
  "rows": [{"filename": "007.jpg", "date": "2018-01-01", "total_amount": "47.70"}, ...],
  "n_date_null": 2,
  "n_amount_null": 1
}
```

## Executor guidance

1. Confirm the image directory exists and openpyxl + pytesseract import. If
   `tesseract` is missing, install `tesseract-ocr` (the task states it is
   pre-installed) or report the unsupported dependency explicitly.
2. Run `scripts/run_pipeline.py` with the task's paths. It overwrites any prior
   output, so re-running regenerates the deliverable from scratch.
3. Verify the produced workbook: exactly one sheet named `results`; header
   `['filename','date','total_amount']`; one row per image sorted by filename;
   amounts are two-decimal strings or empty; dates are ISO or empty. The
   `debug_json` dump lets you inspect which OCR line produced each field when a
   value looks wrong, so a second recognition pass can be targeted.
4. Treat empty cells as the required null. Do not fabricate values the OCR could
   not support.

## Assumptions and limits

- Receipts resemble Malaysian retail slips (currency `RM`), so day-first date
  parsing is the default tie-breaker; genuine evidence (component > 12, 4-digit
  leading year, month names) always overrides it.
- OCR output is noisy; some fields will legitimately be null. The skill favors
  correct schema/formatting/ordering over guessing, because grading is a strict
  line-by-line comparison.
