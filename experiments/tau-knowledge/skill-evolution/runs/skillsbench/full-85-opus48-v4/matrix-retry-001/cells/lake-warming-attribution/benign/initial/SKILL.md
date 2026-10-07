---
name: lake-warming-attribution
description: >-
  Analyze a lake's surface-temperature records plus climate, hydrology, and
  land-cover tables to (1) estimate a long-term warming trend (slope with units
  per year and a significance p-value) and (2) attribute the warming to physical
  driver categories (Heat, Flow, Wind, Human) using a relative-importance
  decomposition of explained variance. Use when a task supplies water-temperature
  and environmental CSVs and asks for a trend_result.csv (slope, p-value) and a
  dominant_factor.csv (variable, contribution).
---

# Lake warming trend & driver attribution

This Skill produces the two required deliverables for the lake-warming task:

* `/root/output/trend_result.csv` with columns **`slope`** and **`p-value`**.
* `/root/output/dominant_factor.csv` with columns **`variable`** and
  **`contribution`**.

The method and category mapping are reusable; the actual slope, p-value,
dominant category, and contribution are computed from the current data at
runtime. Do not hardcode any instance values.

## Inputs (read at runtime, do not assume exact schema)

The public task copies four CSVs into `/root/data/`:

* `water_temperature.csv` — lake surface temperature (0–5 m). This is the target.
* `climate.csv` — climate predictors (e.g. air temperature, radiation, wind…).
* `hydrology.csv` — flow predictors (e.g. inflow/outflow/discharge/precip…).
* `land_cover.csv` — human/land-use predictors.

Schemas, units, column names, and temporal frequency vary. The helper inspects
each table, detects the temporal key (a `date`/`year`/`month` style column),
aggregates to annual means, and joins all tables by **year** (never by row
position), per the frozen data-practice guidance.

## Method

**Trend (slope + p-value).** The target temperature is aggregated to an annual
mean series. An ordinary-least-squares linear regression of annual mean
temperature on calendar year is fit with `scipy.stats.linregress`. The reported
`slope` is in temperature units **per year** and `p-value` is the two-sided
significance of a nonzero slope. This deliberately separates the *rate of
change* (slope) from the *statistical evidence* (p-value), and the annual-mean
aggregation reduces seasonality and uneven within-year sampling.

**Driver attribution (relative importance).** Raw regression coefficients and
pairwise correlations are NOT used as contributions. Instead the full OLS model
is fit on all merged predictors and its R² is partitioned among predictors using
the LMG / Shapley averaging of incremental R² over variable orderings (exact
averaging for small predictor counts, Monte-Carlo permutation averaging for
large counts). These contributions sum to the model R² and are then normalized
to percent (summing to 100% across predictors). This explicitly declares what is
partitioned (explained variance) and how it is normalized (share of R²).

Each predictor is mapped to one physical-pathway category — **Heat, Flow, Wind,
Human** — by keyword on its column name (see `references/method.md`). Per-
variable percentages are summed within each category. The dominant category is
the one of the four with the largest summed percentage. No category is assumed
dominant in advance; it is decided from the current data.

## Output contract

* `trend_result.csv`: one row, columns exactly `slope,p-value`.
* `dominant_factor.csv`: one row, columns exactly `variable,contribution`.
  By default `variable` holds the dominant **category name** and `contribution`
  holds that category's percentage share of explained variance (a number, e.g.
  `62.5` meaning 62.5%). This matches the request to report *which category is
  most important and what percentage of it contributes*.
  If a run instead needs the single most important **individual variable**, pass
  `{"answer_level":"variable"}` on stdin; then `variable` is that column name and
  `contribution` is its own percentage.

## How to run

All logic is in `scripts/analyze.py`, which reads an optional JSON config on
stdin and writes both CSVs, printing a JSON summary (including the full per-
variable and per-category breakdown and the detected category mapping) to
stdout for inspection.

```bash
# defaults: data_dir=/root/data, output_dir=/root/output, answer_level=category
echo '{}' | python3 /app/environment/skills/current/scripts/analyze.py

# explicit paths / overrides
echo '{"data_dir":"/root/data","output_dir":"/root/output"}' \
  | python3 /app/environment/skills/current/scripts/analyze.py

# override category mapping for an unexpected column name
echo '{"category_map":{"cloud_cover":"Heat","precip_mm":"Flow"}}' \
  | python3 /app/environment/skills/current/scripts/analyze.py
```

Stdin JSON fields (all optional):

* `data_dir` (default `/root/data`)
* `output_dir` (default `/root/output`)
* `answer_level` — `"category"` (default) or `"variable"`
* `category_map` — dict `{column_name: "Heat"|"Flow"|"Wind"|"Human"}` to override
  or extend keyword classification
* `target_table` (default `water_temperature.csv`)

Stdout JSON schema (on success):
```
{"status":"ok",
 "trend":{"slope":float,"p_value":float,"n_years":int,"temp_units":str},
 "model_r2":float,
 "variable_contrib":{col:pct,...},
 "category_contrib":{"Heat":pct,"Flow":pct,"Wind":pct,"Human":pct,...},
 "category_map":{col:category,...},
 "dominant":{"variable":str,"contribution":float,"answer_level":str},
 "outputs":{"trend_result":path,"dominant_factor":path}}
```
On failure it prints `{"status":"error","message":...}` and exits nonzero.

## Executor checklist

1. Inspect the data first: `head` each CSV to confirm column names/units; this
   lets you verify or override the category mapping printed in the summary.
2. Run `scripts/analyze.py`.
3. Confirm both CSVs exist under `/root/output/`, have the exact required column
   headers, contain finite numeric values, and that the reported slope/p-value
   and dominant contribution in the files match the stdout summary
   (`scripts/validate.py` performs these checks).
4. If a column is misclassified (e.g. an ambiguous name), rerun with
   `category_map` to correct it, then re-validate.
5. If the data lacks a parseable time key or has no usable predictors, the
   script reports an error explaining what is missing instead of inventing
   values.

See `references/method.md` for the exact category keyword rules, normalization
definition, and failure handling.
