---
name: lake-warming-attribution
description: >
  Analyze lake surface-temperature data for a long-term warming trend and attribute
  that warming to physical driver categories (Heat, Flow, Wind, Human). Use this Skill
  when a user supplies separate CSV tables for water temperature, climate, hydrology,
  and land cover and asks for (1) a trend_result.csv with a slope and p-value and
  (2) a dominant_factor.csv naming the most important driver variable and its
  percentage contribution. Reusable for any similar multi-table lake dataset.
---

# Lake warming trend analysis and driver attribution

## When to use
The public task supplies four tables under a data directory (default `/root/data`):
`water_temperature.csv` (lake surface temperature, the target), `climate.csv`,
`hydrology.csv`, and `land_cover.csv` (driver predictors). It asks for two output
files under an output directory (default `/root/output`):

1. `trend_result.csv` with columns **`slope`** and **`p-value`** (one row): the
   estimated long-term warming rate and its statistical significance.
2. `dominant_factor.csv` with columns **`variable`** and **`contribution`** (one row):
   the single most important driver variable and the percentage contribution of its
   driver category to the warming signal.

Do not assume any category, variable, slope, or percentage in advance. Everything is
derived from the data actually present at runtime.

## Method (what the scripts do)

### Data practice first
Always inspect the real schemas before trusting column names. Run
`scripts/inspect.py` to print each table's columns, dtypes, row counts, detected
temporal key, year coverage, and missingness. Tables are aligned by their actual
temporal key (a detected `year`/`date`/`time` column), **not** by row position.
All tables are aggregated to annual means per year and merged on `year`. Aggregating
to annual values suppresses seasonality before trend/attribution.

### Trend analysis
The annual-mean water temperature is regressed on the integer calendar year with
ordinary least squares (`scipy.stats.linregress`). This separates the two requested
quantities:
- `slope` = rate of change in temperature units per **year** (e.g. °C/yr).
- `p-value` = two-sided significance of the slope under the null of zero trend.
Using annual means (one value per year) reduces seasonality and short-lag serial
dependence. A Mann-Kendall non-parametric check is also computed and reported in the
JSON summary as a cross-check, but the OLS slope/p-value are what is written to
`trend_result.csv` (they match the requested "slope" + "p-value" contract and carry
explicit per-year units).

### Driver attribution
Predictors are every numeric column from `climate.csv`, `hydrology.csv`, and
`land_cover.csv` (constant columns dropped). Each predictor is mapped to a physical
category by the pathway it represents (see `references/category_mapping.json`):
- `land_cover.csv` columns → **Human** (land-use change).
- `hydrology.csv` columns → **Flow** (inflow/outflow/discharge/level).
- `climate.csv` columns whose name matches a wind keyword → **Wind**; all other
  climate columns → **Heat** (air temperature, radiation, etc.).
Source file + keyword mapping is used because the physical pathway is best indicated
by which measurement table the variable comes from.

Relative importance uses **Johnson's relative weights**, which explicitly partition
the model R² (variance of annual temperature explained by all drivers jointly) among
the predictors while handling multicollinearity, then normalizes each predictor's
raw weight to a percentage of the total explained variance (percentages sum to 100%).
This states what is partitioned (R²) and how values are normalized (share of R²),
as the background requires. If relative weights are numerically unstable (too few
rows, singular correlation matrix), the script falls back to normalized squared
semi-partial / zero-order correlations and records the fallback in `warnings`.

Per-variable percentages are summed by category to find the dominant category. The
`variable` written to `dominant_factor.csv` is the top-ranked variable **within that
dominant category**. The `contribution` written is, by default, the dominant
category's total percentage contribution (the "percentage of this category"
requested). Set `"contribution_mode": "variable"` in the script input to instead
write that single variable's own percentage. Both the category total and the
variable's own share are always included in the JSON summary so the executor can
confirm which value the task wants.

## How to run (executor)
From the task container (paths default to the task layout):

```bash
# 1. Inspect the supplied tables
echo '{"data_dir": "/root/data"}' | python3 /app/environment/skills/current/scripts/inspect.py

# 2. Run the full analysis and write both output files
echo '{"data_dir": "/root/data", "output_dir": "/root/output"}' \
  | python3 /app/environment/skills/current/scripts/analyze.py
```

`analyze.py` creates `output_dir`, writes `trend_result.csv` and
`dominant_factor.csv`, and prints a JSON summary to stdout:

```json
{
  "trend": {"slope": <float>, "p_value": <float>, "mann_kendall_p": <float>, "n_years": <int>},
  "attribution": {
    "dominant_category": "Heat|Flow|Wind|Human",
    "dominant_category_contribution_pct": <float>,
    "top_variable": "<name>",
    "top_variable_contribution_pct": <float>,
    "per_variable_pct": {"<col>": <float>, ...},
    "per_category_pct": {"Heat": <float>, ...},
    "r_squared": <float>, "method": "relative_weights|fallback"
  },
  "files": ["/root/output/trend_result.csv", "/root/output/dominant_factor.csv"],
  "warnings": [...]
}
```

### Script input schema (stdin JSON)
- `data_dir` (str, default `/root/data`): directory holding the four CSVs.
- `output_dir` (str, default `/root/output`): where output CSVs are written.
- `category_keywords` (object, optional): override wind-keyword / per-file mapping.
- `contribution_mode` (str, optional): `"category"` (default) or `"variable"`.

## Validation the executor should perform
After running, confirm:
- Both files exist under `output_dir`.
- `trend_result.csv` has exactly the columns `slope` and `p-value`, one data row,
  with finite numeric values; the sign of `slope` is consistent with the JSON
  summary and with a warming trend if present (positive slope).
- `dominant_factor.csv` has exactly the columns `variable` and `contribution`, one
  data row; `variable` is a real predictor column name and `contribution` is a finite
  percentage in (0, 100].
- `dominant_category` is one of Heat/Flow/Wind/Human and `per_category_pct` sums to
  ~100.

If a required table or temporal key is missing, `analyze.py` raises with a clear
message listing what was found; fix the `data_dir` or mapping rather than guessing.

## Notes / assumptions
- Trend units are per calendar year because the time axis is the integer year.
- The specific slope, p-value, dominant category, variable, and percentage are
  computed from the current data and must never be hardcoded.
- Reads only the user-supplied CSVs; writes only the two requested outputs.
