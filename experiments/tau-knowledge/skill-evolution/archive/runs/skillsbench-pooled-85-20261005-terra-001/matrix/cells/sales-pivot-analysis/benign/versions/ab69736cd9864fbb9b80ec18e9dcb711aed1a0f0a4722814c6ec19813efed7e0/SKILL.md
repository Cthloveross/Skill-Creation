---
name: demographic-pivot-report
version: 1.1.0
description: Build an Excel demographic report from an SA2 population PDF and income workbook, retaining supplied income values (including suppression markers), deriving equal-width income-range quarters, and creating real OOXML pivot-table objects.
---

# Demographic Pivot Report

Use this Skill when a population PDF and income `.xlsx` workbook share an SA2 identifier and the requested result is an Excel report with state-level pivot tables.

## Preconditions

- Python has `openpyxl` and `pdfplumber` installed.
- The income workbook has a table with an SA2 identifier, an earners measure, and a median-income measure. `STATE` may be in either source.
- The PDF has extractable text tables containing an SA2 identifier and a population measure.
- Both sources use compatible SA2 codes.

## Runtime interface

`scripts/create_demographic_report.py` consumes one JSON object on standard input and emits one JSON object on standard output.

```json
{
  "income_path": "/root/income.xlsx",
  "population_pdf_path": "/root/population.pdf",
  "output_path": "/root/demographic_analysis.xlsx"
}
```

All fields are optional and default to the paths shown above. Success output includes `ok`, the output path, joined/unmatched-key audit counts, generated source headers, and income-range boundaries. Invalid inputs, extraction failures, duplicate keys, or missing required schema produce `{ "ok": false, "error": "..." }` and a nonzero exit status.

Example:

```bash
python scripts/create_demographic_report.py <<'JSON'
{"income_path":"/root/income.xlsx","population_pdf_path":"/root/population.pdf","output_path":"/root/demographic_analysis.xlsx"}
JSON
```

## Method and data handling

1. Inspect input sheets and header rows at runtime rather than relying on sheet positions or fixed column letters.
2. Extract tables from all PDF pages, identify tables with SA2 and population headers, discard repeated headers and unusable fragments, and require numeric population values.
3. Normalize SA2 identifiers only for joining, reject duplicate identifiers, report unmatched keys, and use the overlapping SA2 records for the combined analysis.
4. Build `SourceData` with canonical analysis columns `SA2_CODE`, `STATE`, `POPULATION_2023`, `EARNERS`, and `MEDIAN_INCOME`, retaining remaining source columns with deterministic provenance names if needed.
5. Preserve supplied `EARNERS` and `MEDIAN_INCOME` cell values faithfully in `SourceData`, including `np` and other suppression/missing markers. Parse values only in the separate derivation step; never replace a supplied suppression marker with a fabricated numeric or blank source value.
6. Calculate four equal-width `MEDIAN_INCOME` ranges. Valid incomes use Q1 `[min,b1)`, Q2 `[b1,b2)`, Q3 `[b2,b3)`, and Q4 `[b3,max]`. Rows with missing/suppressed income have blank `Quarter`; `Total` is blank unless both numeric inputs are available.
7. Create exactly five sheets: `Population by State`, `Earners by State`, `Regions by State`, `State Income Quartile`, and `SourceData`. Add an ordinary Excel table to `SourceData`.
8. Register one real pivot object on each of the first four sheets. Each pivot uses a cache sourced from `SourceData`, has cache fields and pivot fields for every source column, and has consistent row, column, and data-field references. The pivots respectively sum population, sum earners, count SA2 records, and sum earners by state and quarter.
9. Reload the saved workbook and validate sheet names, source headers, registered pivots, cache schema, and role/reference structures.

The script fails instead of guessing when it cannot establish a usable schema, extraction result, join, state, or numeric income range.
