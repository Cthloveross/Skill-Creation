---
name: annual-real-series-hp-correlation
description: Calculate a Pearson correlation between HP-filtered log real annual macroeconomic series stored in ERP-style Excel tables and a dated CPI workbook. Use when annual rows and quarterly fallback rows must be interpreted from their labels rather than fixed cell coordinates.
---

# Annual real-series HP correlation

This Skill extracts two nominal annual series from ERP-style `.xls` tables, deflates them using annual-average CPI, computes HP-filter cycles of their natural logs, and writes their Pearson correlation.

## Method

1. Read every worksheet without assuming a header row or fixed sheet/cell coordinates.
2. Identify the column that contains annual year labels and identify the first consistently numeric data column to its right. In ERP tables this is the requested `Total` series column. Use explicit annual observations where available; where an annual observation is absent, average available quarterly observations for that year.
3. Parse dated CPI observations, average CPI by calendar year, and align both nominal series and CPI strictly by year.
4. Form real levels as `nominal / CPI`. The CPI index base cancels in logged cyclical components, but the same annual CPI definition must be used for both series.
5. Apply the annual HP filter to `log(real)` with `lambda=100`. The implementation solves the joint objective
   `sum((x-trend)^2) + lambda*sum(second_difference(trend)^2)`.
6. Correlate the two cycle vectors over their common requested year range. Write only the rounded correlation value to the requested answer file.

The script validates complete year coverage and finite positive values. It fails rather than silently replacing missing observations, mixing quarterly observations with annual observations, or using a different frequency.

## Runtime prerequisites

The runtime needs Python 3 with `pandas`, `numpy`, and an `.xls` reader supported by pandas (normally `xlrd`). These are used only to read the supplied workbooks; no network access is required.

## Runnable entrypoint

Pass a JSON object on standard input. Paths may be changed for similarly structured inputs; the defaults are the public task paths.

```sh
printf '%s' '{"pce_path":"/root/ERP-2025-table10.xls","pfi_path":"/root/ERP-2025-table12.xls","cpi_path":"/root/CPI.xlsx","answer_path":"/root/answer.txt","start_year":1973,"end_year":2024,"lambda":100}' | python /app/environment/skills/current/scripts/compute_correlation.py
```

Input schema:

- `pce_path`, `pfi_path`, `cpi_path`: readable workbook paths.
- `answer_path`: output text path (default `/root/answer.txt`).
- `start_year`, `end_year`: inclusive integer period bounds (defaults 1973 and 2024).
- `lambda`: positive HP smoothing value (default 100 for annual data).

The script emits a JSON execution summary to stdout. `answer_path` contains exactly one five-decimal numeric coefficient followed by a newline. Check the summary's `years_used` equals the requested inclusive range length, `quarterly_fallback_years` only lists genuinely unavailable annual observations, and that the answer file has no labels or extra text.

Do not use a spreadsheet coordinate from a prior workbook as an extraction rule. If workbook labels or units show that the first numeric column is not a total nominal level series, stop and inspect the source structure before applying this Skill.
