---
name: ipf-dots-workbook
version: 1.0.0
description: Populate an empty Dots worksheet in an IPF/OpenIPF-style Excel workbook by discovering the required performance columns, copying them in source order, and writing Excel formulas for TotalKg and sex-specific Dots scores.
---

# IPF Dots workbook builder

Use this Skill when a workbook has a source performance-record sheet and an empty output sheet that must contain the fields needed for IPF Dots scoring, followed by formula-driven `TotalKg` and `Dots` columns.

## Method

1. Read the supplied data dictionary/readme and inspect the workbook rather than assuming column letters.
2. The builder locates headers for name, sex, bodyweight, best-three squat, best-three bench, and best-three deadlift using normalized header aliases. It fails if a required field is missing or ambiguous.
3. It copies precisely those source columns to the output sheet in their original left-to-right order, preserving displayed header names and source row order.
4. It appends:
   - `TotalKg`, using an Excel formula that sums all three lifts and rounds the result to three decimal places;
   - `Dots`, using an Excel formula with the published IPF DOTS fourth-degree polynomials, bodyweight bounds, and a final three-decimal rounding step.
5. It marks the workbook for full recalculation when opened in Excel or another compatible spreadsheet engine. Formula-writing libraries do not calculate cached formula values themselves.

The formulas support `M`/`Male` and `F`/`Female`. Unsupported nonblank sex labels are rejected because no coefficient set can be selected safely. Records with missing/non-numeric lift or bodyweight data are retained, but their applicable formula result is blank rather than a fabricated score.

The Dots formula uses the conventional bodyweight domains: 40--210 kg for men and 40--150 kg for women. Values outside those domains are clamped to the published endpoint before evaluation.

## Run

The scripts accept JSON on stdin and emit a JSON status object on stdout. `openpyxl` is required.

```bash
python scripts/build_dots_workbook.py <<'JSON'
{
  "input_path": "/root/data/openipf.xlsx",
  "output_path": "/root/data/openipf.xlsx",
  "readme_path": "/root/data/data-readme.md",
  "source_sheet": "Data",
  "output_sheet": "Dots",
  "recalculate": false
}
JSON
```

`input_path` and `output_path` may be different paths. To force formula cached values when LibreOffice is installed, set `recalculate` to `true`; the script will fail explicitly rather than claim recalculation if no compatible `libreoffice`/`soffice` executable is available.

## Validate

After building, inspect the returned column and row counts, then run:

```bash
python scripts/validate_dots_workbook.py <<'JSON'
{
  "workbook_path": "/root/data/openipf.xlsx",
  "source_sheet": "Data",
  "output_sheet": "Dots",
  "require_cached_values": false
}
JSON
```

The validator checks discovery consistency, copied header order, source-to-output values, required formula presence, numeric display formats, and the presence of formula cells for every copied record. Set `require_cached_values` to `true` only after recalculating with Excel or the builder's optional LibreOffice mode.

Do not replace the formulas with literals: the requested workbook artifact requires Excel formulas. Do not edit the source sheet or add unrelated worksheets.
