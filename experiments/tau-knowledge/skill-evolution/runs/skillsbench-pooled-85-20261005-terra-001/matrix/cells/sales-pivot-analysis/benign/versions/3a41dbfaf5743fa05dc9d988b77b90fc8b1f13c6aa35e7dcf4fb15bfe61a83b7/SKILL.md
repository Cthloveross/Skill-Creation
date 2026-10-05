---
name: demographic-pivot-report
version: 1.0.0
description: Build an Excel demographic report by extracting an SA2 population table from a PDF, joining it to an income workbook, deriving equal-width income-range quarters and total estimated income, and creating real OOXML/openpyxl pivot-table objects.
---

# Demographic Pivot Report

Use this Skill when a task supplies a population PDF and an income `.xlsx` workbook that share an SA2 geographic identifier and requests an Excel workbook with state-level demographic pivot tables.

## Preconditions

- Python has `openpyxl` and `pdfplumber` available.
- The income workbook contains a header row with an SA2 identifier, `EARNERS`, and `MEDIAN_INCOME`; either input must provide `STATE`.
- The PDF contains an extractable (not image-only) table with an SA2 identifier and a population column.
- The source data uses a common SA2 coding scheme. The procedure performs an inner join and reports unmatched keys rather than inventing matches.

## Runtime interface

`scripts/create_demographic_report.py` reads one JSON object from standard input and emits one JSON result to standard output.

Input schema:

```json
{
  "income_path": "/root/income.xlsx",
  "population_pdf_path": "/root/population.pdf",
  "output_path": "/root/demographic_analysis.xlsx"
}
```

All properties are optional and default to the paths above. The output JSON contains `ok`, `output_path`, row and unmatched-key counts, source headers, and the selected equal-width boundaries. On invalid input or an extraction/schema failure, it emits `{ "ok": false, "error": "..." }` and exits nonzero.

Example:

```bash
python scripts/create_demographic_report.py <<'JSON'
{"income_path":"/root/income.xlsx","population_pdf_path":"/root/population.pdf","output_path":"/root/demographic_analysis.xlsx"}
JSON
```

## Method

1. Inspect workbook rows to find the actual header row and required columns; do not assume a particular worksheet or column address.
2. Extract tables from every PDF page, identify the table header containing both SA2 and population fields, remove repeated headers and malformed/artifact rows, and require a consistent usable table.
3. Normalize SA2 identifiers only for matching (including Excel numeric-looking identifiers) and audit duplicates and keys present in only one source. Join only records present in both sources.
4. Preserve available original fields while adding canonical analysis headers `STATE`, `POPULATION_2023`, `EARNERS`, and `MEDIAN_INCOME`. Convert numeric values safely; suppression markers such as `np` become missing values and are never used in arithmetic.
5. Compute equal-width range bins from the numeric `MEDIAN_INCOME` minimum and maximum. The intervals are Q1 `[min,b1)`, Q2 `[b1,b2)`, Q3 `[b2,b3)`, and Q4 `[b3,max]`; if all valid incomes are identical they are Q1. Compute `Total = EARNERS * MEDIAN_INCOME` only where both inputs are numeric.
6. Create exactly these sheets: `Population by State`, `Earners by State`, `Regions by State`, `State Income Quartile`, and `SourceData`. `SourceData` is a normal Excel table.
7. Create actual pivot-table definitions, not static summaries. Each pivot shares a cache referring to `SourceData`; cache fields, a per-source-column pivot-field list, axis references, and data-field references are all populated. The cache is marked to refresh when opened, so Excel builds the displayed aggregation from the source range.
8. Reload the saved workbook and verify sheet names, source headers, all four registered pivot objects, their cache field counts, and the relevant row/column/data field references.

The script deliberately fails rather than guessing when it cannot identify the input schema, cannot extract valid PDF rows, encounters duplicate SA2 keys, finds no join overlap, has no valid income values for range binning, or lacks a state value for joined rows. Review its JSON audit counts when deciding whether source-data exclusions are appropriate.
