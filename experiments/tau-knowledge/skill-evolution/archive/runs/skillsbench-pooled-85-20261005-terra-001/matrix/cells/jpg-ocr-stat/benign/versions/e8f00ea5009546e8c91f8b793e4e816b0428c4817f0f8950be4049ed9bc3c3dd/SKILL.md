---
name: receipt-ocr-to-xlsx
description: Extract ISO receipt dates and labelled payable totals from a directory of scanned receipt images, then generate a strict one-sheet Excel result workbook. Use when receipt images must be converted to filename/date/total_amount rows and OCR uncertainty must remain null rather than guessed.
---

# Receipt OCR to XLSX

Use `scripts/build_receipt_report.py` to process a supplied image directory. The script separates OCR from field parsing, tries a small set of image/layout variants, chooses totals only from task-specified semantic labels, and writes the required workbook.

## Runtime interface

The script receives one JSON object on stdin and emits a JSON summary on stdout.

Input schema:

```json
{
  "input_dir": "/app/workspace/dataset/img",
  "output_path": "/app/workspace/stat_ocr.xlsx",
  "date_order": "auto",
  "workers": 4
}
```

- `input_dir` is recursively scanned for common raster-image extensions. It defaults to `/app/workspace/dataset/img`.
- `output_path` defaults to `/app/workspace/stat_ocr.xlsx`.
- `date_order` is `auto`, `day_first`, or `month_first`. In `auto`, ambiguous numeric dates are only resolved when unambiguous dates in the current input establish one consistent ordering. Use an explicit order only if the current receipts provide that evidence through visual/OCR review.
- `workers` is an optional positive process-count limit for independent OCR jobs.

For example, provide the JSON above to `python scripts/build_receipt_report.py` from the packaged-skill directory.

The JSON response has `output_path`, `record_count`, `date_order_used`, and `records`. Each record reports `filename`, extracted values (or JSON null), and diagnostic flags. Diagnostics are for review only and are not placed in the workbook.

## Extraction method

1. Run OCR on moderately upscaled grayscale and contrast/threshold preparations using plausible Tesseract page segmentation modes. Keep each raw OCR result isolated; do not globally replace OCR characters.
2. Parse monetary candidates from lines containing the supplied priority labels. Lines containing subtotal, tax, discount, change, or cash-tendered exclusions are never total candidates. If the label has no amount, inspect the next OCR line and use its last monetary number. Normalize the selected decimal with `Decimal` and emit exactly two places.
3. Parse dates from labelled and ordinary OCR lines. Validate actual calendar dates. Numeric date ordering is not assumed: use year-first forms directly, textual months directly, value ranges when one component exceeds 12, or the documented input-wide convention. Leave unresolved ambiguity null.
4. Create one workbook sheet named `results`, append exactly `filename`, `date`, and `total_amount`, then rows sorted by filename. Missing extractions are written as empty Excel cells (`None`), representing null.

## Output validation

The script reloads its saved workbook and verifies all of the following before reporting success:

- exactly one sheet named `results` exists;
- the header is exactly `filename`, `date`, `total_amount`;
- row count matches discovered image count plus the header;
- there are exactly three used columns;
- filenames are deterministic lexical order;
- present dates are valid ISO `YYYY-MM-DD` strings; and
- present totals match `^-?\d+\.\d{2}$` and are stored as strings.

If an individual image cannot be opened or OCR cannot establish a requested field, its row remains present and the affected value is null. A missing input directory, unwritable output path, unsupported `date_order`, or failed structural validation is a run-level error and must be corrected rather than silently producing a partial workbook.
