# Method reference: lake warming trend & driver attribution

## 1. Temporal alignment

Every supplied table is inspected for a temporal key in this priority order:
`date`/`datetime`/`timestamp`/`time` (parsed to datetime), then a `year`
column, then any column containing `year`, then the first column parsed as a
date. Records are aligned by the derived integer **year**, never by row
position. Numeric value columns are aggregated to annual means before joining,
so tables of different frequency (monthly climate vs. annual hydrology) still
merge correctly. Tables are inner-joined on year, so the attribution model only
uses years present in every needed table.

## 2. Trend (slope + p-value)

* Target = annual mean of the lake surface-temperature column(s) in
  `water_temperature.csv` (columns whose name contains `temp` are preferred; if
  several, they are averaged).
* Fit OLS of annual mean temperature on calendar year via
  `scipy.stats.linregress`.
* `slope` = temperature units per **year**; `p-value` = two-sided significance
  of a nonzero slope.
* The slope (rate) and the p-value (evidence) are reported as distinct
  quantities. Annual-mean aggregation controls seasonality and uneven
  within-year sampling. At least 3 annual points are required.

## 3. Driver attribution (relative importance)

* Predictors = all numeric value columns from the non-target tables
  (`climate.csv`, `hydrology.csv`, `land_cover.csv`), merged by year.
* Constant columns (no variance) are dropped.
* The full OLS model R² is partitioned among predictors with LMG / Shapley
  averaging of incremental R² across all variable orderings (exact averaging
  when ≤8 predictors, otherwise Monte-Carlo permutation averaging). These
  contributions sum to the model R².
* **Normalization declared:** per-variable contribution = (its LMG share) /
  (sum of LMG shares) × 100, so variable percentages sum to 100. Negatives are
  clipped to 0 before normalization.
* Raw regression coefficients and pairwise correlations are never used as
  contributions, per the frozen attribution guidance.

## 4. Category mapping (Heat / Flow / Wind / Human)

Each predictor column is mapped to a physical pathway by keyword on its name,
first match wins in this order:

* **Wind**: wind, gust
* **Flow**: inflow, outflow, discharge, flow, runoff, precip, rain, river,
  stage, level, hydro, stream, evap
* **Human**: land, urban, agri, crop, forest, pop, built, impervious,
  developed, lulc, land_use, vegetation, pasture, settlement, human
* **Heat**: temp, solar, radiation, shortwave, longwave, sunshine, insolation,
  cloud, heat, rad, air, irradiance
* otherwise **Other** (excluded from the dominant-category choice; override it
  if it is really one of the four).

The mapping is printed in the stdout summary so the executor can verify it
against the real column names (`head data/*.csv`) and correct any ambiguous
case with the `category_map` override. No category is presumed dominant; the
winner is the one of the four requested categories with the largest summed
percentage from the current data.

## 5. Output

* `trend_result.csv`: columns `slope,p-value`, one row.
* `dominant_factor.csv`: columns `variable,contribution`, one row.
  Default (`answer_level=category`): `variable` = dominant category name,
  `contribution` = that category's percentage share of explained variance
  (e.g. `62.5`). With `answer_level=variable`: `variable` = top single column,
  `contribution` = its own percentage.

## 6. Failure handling

The script emits `{"status":"error",...}` and a nonzero exit when: the target
table or its temporal key is missing, no temperature column exists, fewer than
3 annual points exist for the trend, no usable predictors are found, or the
merged modeling frame is too small. These are reported explicitly rather than
producing fabricated values. Run `scripts/validate.py` after generation to
confirm both files meet the exact schema and contain finite values.
