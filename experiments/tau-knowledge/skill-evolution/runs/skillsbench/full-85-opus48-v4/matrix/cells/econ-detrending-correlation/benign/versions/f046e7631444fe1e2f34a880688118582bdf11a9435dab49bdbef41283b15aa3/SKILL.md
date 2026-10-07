---
name: econ-detrending-correlation
description: >-
  Compute the Pearson correlation between the HP-filter cyclical components of
  two real (CPI-deflated) US macro series from Economic Report of the President
  (ERP) .xls tables. Use when a task supplies nominal ERP tables plus a CPI
  index and asks for the correlation of detrended real series over a stated year
  range (e.g. real PCE vs real private fixed investment, 1973-2024). Deflates
  nominal totals with annual CPI, takes natural logs, applies the HP filter with
  the annual smoothing parameter lambda=100, and writes the rounded coefficient.
---

# Detrended real-series correlation (ERP + CPI, HP filter)

## What this Skill does

Given two nominal annual series in ERP `.xls` tables and a CPI index workbook,
it produces the Pearson correlation between the two series' business-cycle
(cyclical) components:

1. Extract each series' **Total (first data column)** per year from its ERP table.
2. For a year that has only partial quarterly data at the bottom of the table
   (e.g. the final year), use the **average of the available quarters** as the
   annual value.
3. Deflate each nominal annual value by the **annual-average CPI** of the same
   year to get a real series (the deflation base cancels later, so any
   consistent CPI index works).
4. Take the **natural log** of each real series over the requested year range.
5. Apply the **Hodrick-Prescott filter with lambda = 100** (standard for annual
   data); the cyclical component is `log(real) - trend`.
6. Compute the **Pearson correlation** of the two cyclical components on the
   common sample.
7. Write the coefficient, **rounded to 5 decimals**, to the output file (default
   `/root/answer.txt`), one number only.

This matches the frozen background: convert nominal to real with the specified
index, align by actual period labels, parse mixed annual/quarterly rows by their
semantics, and compute the association on the common sample; the HP objective
combines fit and smoothness penalties with lambda=100 for annual frequency.

## Inputs (read at runtime; do not hardcode values)

The current task supplies, in `/root/`:
- an ERP nominal table for the first series (PCE) — `ERP-2025-table10.xls`,
- an ERP nominal table for the second series (PFI) — `ERP-2025-table12.xls`,
- a CPI index workbook — `CPI.xlsx` (FRED CPIAUCSL, monthly).

The requested range here is **1973-2024 inclusive**. Read the exact filenames,
year range, and column meaning from the live task text rather than assuming.

## How to run

Dependencies: `pandas numpy xlrd openpyxl`. If missing, install them
(`pip install pandas numpy xlrd openpyxl`; internet is allowed).

End-to-end entrypoint (reads optional JSON overrides on stdin, emits JSON on
stdout, and writes the answer file):

```bash
python3 scripts/run.py <<'JSON'
{"pce_file":"/root/ERP-2025-table10.xls",
 "pfi_file":"/root/ERP-2025-table12.xls",
 "cpi_file":"/root/CPI.xlsx",
 "start_year":1973, "end_year":2024,
 "lam":100, "output":"/root/answer.txt"}
JSON
```

Running with no stdin uses those same defaults:

```bash
python3 scripts/run.py
```

Stdout JSON schema:
```
{"correlation": float, "rounded": "0.NNNNN", "years": [int,...],
 "n": int, "output_path": str,
 "debug": {"pce_cols": [...], "pfi_cols": [...], "cpi_years": int,
           "pce_2024_source": "annual|quarterly-avg", ...}}
```
`run.py` exits non-zero and reports which years are missing if any series lacks
a value in the range.

## Inspecting an unfamiliar workbook

If extraction looks wrong, dump a sheet to understand its real layout before
changing anything:

```bash
python3 scripts/inspect_xls.py <<'JSON'
{"path":"/root/ERP-2025-table10.xls", "max_rows": 400}
JSON
```
It prints each row index with its cells (JSON), plus the auto-detected year and
total columns. Use it to confirm the Total column is "column 1" (first data
column) and that quarterly rows for the final year are detected.

## Method details / assumptions

- **Column mapping is derived at runtime** from the actual sheet: the year
  column is the column with the most year-like labels; the Total column is the
  first numeric data column to its right. Verify with `inspect_xls.py`.
- **Annual vs quarterly:** a plain year row supplies the annual Total. Rows
  carrying a quarter marker (I/II/III/IV, Q1-Q4, or `YYYY:I` style) are grouped
  by their year; a year with no annual row uses the mean of its quarters. A year
  with both keeps the annual value.
- **CPI** is reduced to an annual average per calendar year from whatever
  monthly rows are present (a partial final year averages the months present).
- **Deflation base is irrelevant**: because the series are logged and HP-
  detrended, multiplying real values by a constant only shifts the trend, so
  `real = nominal / CPI` is sufficient.
- **HP filter** solves `tau = (I + lam * D'D)^{-1} y` with `D` the (T-2)xT
  second-difference matrix; cyclical = `y - tau`. This equals statsmodels'
  `hpfilter`. The filter is applied on the requested year range itself.
- **Rounding:** `f"{round(corr,5):.5f}"`, written as the sole file content.

## Validation to run after producing the answer

- Confirm 52 years (1973-2024) are present for both series and for CPI.
- Re-read `/root/answer.txt`: it must contain one number with 5 decimals.
- Sanity-check magnitudes with `inspect_xls.py` (PCE/PFI totals grow over time;
  the Total column is the first data column, not a line-number column).
- Independently recompute the correlation from the printed `years`/levels if a
  cross-check is desired. If the detected columns look like line numbers or a
  component instead of the Total, re-run with the correct `total_col` override
  (see `run.py` optional keys) rather than editing values by hand.
