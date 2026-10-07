---
name: annual-real-series-hp-correlation
description: Extract two nominal annual economic series from spreadsheet tables, deflate them with annual-average CPI, use an HP filter on log real values, and write their aligned cyclical-component Pearson correlation. Use for tasks with explicitly supplied source files, years, CPI, and smoothing parameter.
---

# Annual real-series HP correlation

Use `scripts/compute_correlation.py` when a task requires a correlation between cyclical components of two annual nominal series. The script discovers table locations from period labels rather than relying on sheet names or fixed cells. It expects the first numeric column to the right of the recognized period column to be the requested total series, which is appropriate only when the task identifies that column as the total.

## Inputs and prerequisites

The runtime must provide Python with `pandas` and `numpy`; reading a binary `.xls` workbook also requires a pandas-compatible `.xls` reader (normally `xlrd`). The CPI file must be a readable Excel workbook containing a date column and a numeric CPI column. Inputs must be official/source copies supplied to the task; do not substitute data from another release or frequency.

The program receives one JSON object on stdin:

```json
{
  "pce_xls": "/path/to/consumption.xls",
  "pfi_xls": "/path/to/investment.xls",
  "cpi_xlsx": "/path/to/cpi.xlsx",
  "output": "/path/to/answer.txt",
  "start_year": 1973,
  "end_year": 2024,
  "lambda": 100
}
```

All fields are required. `pce_xls` and `pfi_xls` are generic names for the first and second source table. `start_year`, `end_year`, and `lambda` are analysis-contract inputs, not assumptions made by the script.

For the supplied task, invoke the script with the three supplied source paths, output `/root/answer.txt`, years 1973 through 2024, and lambda 100.

## Method

1. Inspect every source sheet without assuming a header row. Identify the column with the most exact annual or `year:quarter` labels, then use the first numeric column to its right as the requested Total column.
2. Build annual nominal values from annual rows. For the final target year, if quarter observations exist, replace any annual row with the arithmetic mean of all available quarters, as required for a partial-year source.
3. Identify dated CPI observations, average CPI within each calendar year, and construct real values as `nominal / annual_CPI * 100`. The constant 100 only selects a price-base scale and cannot alter log HP cycles or their correlation.
4. Require a complete, explicitly year-aligned sample over the requested inclusive interval. Take natural logs, compute the HP trend by solving `(I + lambda * D' D) trend = log_real`, and use `log_real - trend` as the cycle.
5. Calculate the ordinary Pearson correlation of the two cycles and write only the five-decimal coefficient plus a newline to the requested output path.

## Validation and failure handling

The script rejects nonpositive values, missing target years, missing CPI years, duplicate conflicting period observations, absent usable numeric Total columns, nonfinite results, a nonpositive cycle variance, and files that cannot be read with the installed spreadsheet readers. It also verifies that the requested target years are contiguous and that the final-year quarterly average is actually used whenever quarter labels are present. A failure is reported as a JSON error on stdout and no successful result should be treated as produced.

On success stdout is a JSON audit summary containing the unrounded coefficient, rounded text, sample years, and the final-year quarter counts. The required artifact itself remains `output` and contains no labels or explanatory text.
