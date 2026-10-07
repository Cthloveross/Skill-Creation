# Method reference

## Contract (from the public task)

- Series A: Personal Consumption Expenditures total (first data column) from the
  nominal ERP PCE table.
- Series B: Private Fixed Investment total (first data column) from the nominal
  ERP PFI table.
- Deflate both by CPI (CPIAUCSL) to real terms.
- Final year (2024) has only partial quarterly data in the ERP table: use the
  average of the available quarters as that year's annual value.
- Natural log, then HP filter with lambda = 100 (annual), cyclical = log - trend.
- Pearson correlation of the two cyclical components over 1973-2024 inclusive.
- Write only the coefficient rounded to 5 decimals to `/root/answer.txt`.

## Why the CPI base does not matter

`real = nominal / CPI` differs from a base-indexed deflator only by a constant
multiplicative factor per the whole series only if CPI were constant — it is
not. But what matters: `log(nominal/CPI) = log(nominal) - log(CPI)`. Choosing a
different CPI base multiplies every CPI value by the same constant k, which adds
`-log(k)` (a constant) to every year's log. A constant added to a series is
absorbed entirely by the HP trend, leaving the cyclical component unchanged.
So any consistent CPI index (annual average of CPIAUCSL) is sufficient; no
rebasing to 100 is required.

## HP filter

Minimize `sum (y_t - tau_t)^2 + lambda * sum[(tau_{t+1}-tau_t)-(tau_t-tau_{t-1})]^2`.
Closed form: `tau = (I + lambda * D'D)^{-1} y`, with D the (T-2) x T second-
difference matrix. Cyclical component = `y - tau`. lambda = 100 for annual data.
The filter is applied on the requested sample (1973-2024) directly.

## Pitfalls to check during execution

- Confirm the detected Total column is the first *data* column, not a line-
  number column such as `(1)`; use `inspect_xls.py`.
- Confirm 2024 is sourced from a quarterly average (run output reports
  `pce_end_source` / `pfi_end_source`); earlier years should be `annual`.
- Confirm CPI yields one average per calendar year; a partial 2024 averages the
  months present.
- All 52 years (1973-2024) must be present for both series and CPI, or `run.py`
  reports the missing years and exits non-zero.
- Output file must contain a single 5-decimal number.
