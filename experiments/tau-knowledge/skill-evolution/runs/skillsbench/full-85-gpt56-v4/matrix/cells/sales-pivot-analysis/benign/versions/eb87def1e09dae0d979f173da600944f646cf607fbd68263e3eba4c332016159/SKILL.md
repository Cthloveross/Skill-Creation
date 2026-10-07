---
name: demographic-pivot-report
version: 1.0.0
description: Build an Excel demographic report from an SA2 population PDF and an income workbook. Use when the requested result needs an enriched joined SourceData sheet and real OOXML pivot-table objects summarising population, earners, regions, and income-range quarters by state.
---

# Demographic pivot report

This Skill creates `/root/demographic_analysis.xlsx` (or caller-supplied paths) from a population PDF and an income `.xlsx` file. It discovers headers at runtime, joins the two sources by their SA2 identifier, excludes rows that cannot participate in required numeric calculations, adds `Quarter` and `Total`, and creates four registered pivot tables backed by a shared pivot cache.

## Assumptions and handling

- The PDF must contain an extractable text table with an SA2 identifier, state, and a population field. `pdfplumber` is required. A scanned PDF or an unrecognisable table is reported as an error rather than guessed.
- The income workbook must have a tabular sheet with an SA2 identifier, `EARNERS`, and `MEDIAN_INCOME`. The script locates a header row by aliases instead of assuming a sheet or row number.
- The sources are inner-joined on normalized SA2 codes. Rows missing from either source, duplicate join keys, `np`, blanks, or nonnumeric required measures are excluded and reported in the JSON audit.
- “quartile range” is interpreted as four equal-width ranges over the observed `MEDIAN_INCOME` values: Q1 includes the minimum through the first boundary, Q2 and Q3 include their upper boundaries, and Q4 includes the remaining values through the maximum. This is range binning, not percentile/quantile binning.
- `Total` is numeric `EARNERS * MEDIAN_INCOME`.

The emitted pivot tables are not flat summary tables: each target worksheet has a `TableDefinition` registered in its internal pivot collection, a shared worksheet pivot cache, cache fields, one pivot field per SourceData column, and explicit row/column/data field references. Cache refresh is requested on workbook open so Excel can populate the displayed pivot result from the source range.

## Run

Scripts receive one JSON object on stdin and return one JSON object on stdout. Run from the Skill directory so the script can be located:

```sh
printf '%s' '{"population_pdf":"/root/population.pdf","income_xlsx":"/root/income.xlsx","output_xlsx":"/root/demographic_analysis.xlsx"}' | python3 scripts/build_report.py
```

Input schema:

- `population_pdf` (optional string): population PDF path; default `/root/population.pdf`.
- `income_xlsx` (optional string): income workbook path; default `/root/income.xlsx`.
- `output_xlsx` (optional string): report path; default `/root/demographic_analysis.xlsx`.

Success output has `ok: true`, the output path, source-row count, excluded-row counts, detected source fields, and the four pivot definitions. Invalid input or an unsupported extraction/schema condition yields `ok: false` and a descriptive `error`; no successful report should be represented in that case.

## Validation performed

After saving, the script reloads the workbook and checks all five exact sheet names, SourceData headers and numeric derived values, the presence of four registered pivots, their shared source range/cache linkage, one pivot field per source column, and the requested row/column/data field roles and aggregations. It also checks the saved OOXML package has pivot table and pivot cache parts. Review the JSON audit before delivery, especially excluded keys, because an unexpected exclusion can indicate a source-schema or PDF-extraction problem.
