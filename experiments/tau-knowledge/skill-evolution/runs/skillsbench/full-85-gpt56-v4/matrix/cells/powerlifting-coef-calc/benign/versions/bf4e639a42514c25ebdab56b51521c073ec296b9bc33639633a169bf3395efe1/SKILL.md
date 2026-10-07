---
name: ipf-dots-workbook
version: 1.0.0
description: Populate an empty Dots worksheet from a powerlifting results worksheet by discovering required headers, copying the needed athlete fields in source order, and writing Excel formulas for total kilograms and IPF Dots scores.
---

# IPF Dots workbook preparation

Use this Skill when a workbook contains powerlifting performance records and an output sheet must contain the fields required for an IPF Dots calculation, followed by formula-based `TotalKg` and `Dots` columns.

The Dots score uses bodyweight, sex, and best squat, bench, and deadlift. The script identifies these fields by header names rather than fixed source coordinates. It copies `Name` as well, and preserves the selected source columns' relative order and exact header text.

The score formula is:

`ROUND(TotalKg * 500 / polynomial(bodyweight, sex), 3)`

where the published male and female IPF Dots polynomials are embedded in the generated Excel formula. Calculations retain the published coefficient precision; totals and reported Dots results are rounded to three decimal places.

## Run

The script reads one JSON object from standard input and emits one JSON report on standard output.

```bash
python /app/environment/skills/current/scripts/build_dots.py <<'JSON'
{
  "input_path": "/root/data/openipf.xlsx",
  "output_path": "/root/data/openipf.xlsx",
  "readme_path": "/root/data/data-readme.md",
  "source_sheet": "Data",
  "destination_sheet": "Dots",
  "recalculate": true
}
JSON
```

### Input schema

- `input_path` (required): source `.xlsx` workbook.
- `output_path` (required): destination `.xlsx` path. It may equal `input_path` for an in-place task deliverable.
- `readme_path` (optional): supplied data dictionary/readme. It is read for diagnostic context; worksheet headers remain the authoritative mapping.
- `source_sheet` (optional, default `Data`): records worksheet.
- `destination_sheet` (optional, default `Dots`): worksheet to rebuild.
- `recalculate` (optional, default `true`): attempt a LibreOffice/soffice recalculation after formulas are written.

The script requires `openpyxl`. It optionally uses an installed `libreoffice` or `soffice` executable to populate formula caches. Formula text is retained even if no compatible spreadsheet engine is available.

## Header requirements and failure handling

Supported header aliases include `Name`/`LifterName`/`AthleteName`, `Sex`/`Gender`, `BodyweightKg`, and the `Best3...Kg` lift headers commonly used by OpenIPF exports. The tool reports all available headers and fails without editing the source when a required field cannot be uniquely resolved. It also fails for missing/non-numeric bodyweight or best-lift values, or sex values outside common male/female encodings. This avoids silently treating missing data as zero or selecting an attempt column instead of a best-lift column.

`Dots` is intentionally rebuilt because it is the requested output sheet. `Data` is never edited. Header names and selected source ordering are retained; values are copied as values, while the two derived columns are formulas.

## Validation

The JSON report includes the discovered headers, copied headers, row count, formula locations, recalculation status, and validations. The script verifies after save that:

1. `Data` cell values are unchanged;
2. the output headers are the selected source headers followed by `TotalKg` and `Dots`;
3. every output record has both requested formulas; and
4. after successful spreadsheet-engine recalculation, derived cells have numeric cached values and no formula-error strings.

If recalculation is unavailable, deliver the workbook with formulas intact and use the report's `recalculated: false` status to make that limitation explicit.
