---
name: trend-anomaly-causal-inference
description: >-
  End-to-end pipeline for the e-commerce "trend anomaly + causal analysis" task.
  Cleans a dirty survey (demographics) CSV and a dirty Amazon purchases CSV,
  builds per-category counterfactual daily-sales forecasts to score March-2020
  surges/slumps on a bounded [-100,100] anomaly index, engineers demographic
  features, builds user x category x period DiD panels (intensive +
  extensive margin), and runs univariate / multivariate heterogeneous
  difference-in-differences to find the top intensive and extensive drivers.
  Produces the 7 required artifacts under /app/output/. Use whenever the task
  asks to detect anomalous category sales in a target month vs a prior baseline
  and attribute them to demographic factors via DiD.
---

# Trend Anomaly + Causal (DiD) Analysis Skill

## When to use
Use for the public task whose opening asks to (1) clean dirty transaction +
survey data, (2) detect category sales anomalies in **March 2020** vs the
**Jan-Feb 2020** baseline using counterfactual forecasts and a deviation index
in **[-100, 100]**, (3) feature-engineer demographics, and (4) run DiD to find
the top-3 intensive-margin and top-3 extensive-margin demographic drivers for
the top-10 surge and top-10 slump categories. Required outputs land in
`/app/output/`.

## Inputs (read at runtime, do not hard-code values)
- `/app/data/survey_dirty.csv` — demographic survey, join key `Survey ResponseID`.
- `/app/data/amazon-purchases-2019-2020_dirty.csv` — transactions with an order
  date, per-unit price, quantity, product category, and `Survey ResponseID`.
- If the files are absent, run the provided downloader first:
  `python /tmp/download_data.py` (writes into `/app/data/`).

Column names are detected by keyword (`response`, `date`, `price`,
`quantity`/`qty`, `category`) so minor naming/formatting drift is tolerated.
If a required column cannot be found the pipeline fails loudly with a clear
message instead of guessing.

## Outputs (all under `/app/output/`)
1. `survey_cleaned.csv`
2. `amazon-purchases-2019-2020-filtered.csv`
3. `category_anomaly_index.csv` — columns `Category`, `Anomaly_Index`
4. `survey_feature_engineered.csv` — `Survey ResponseID` + engineered feature cols
5. `user_category_period_aggregated_intensive.csv` — `Survey ResponseID`,`Category`,`Period`,`Total_Spend`
6. `user_category_period_aggregated_extensive.csv` — `Survey ResponseID`,`Category`,`Period`,`Has_Purchase`
7. `causal_analysis_report.json` — structure described in the task opening.

## Method (derived from the task + background, not from any prior dataset)
See `references/method.md` for the full rationale. Summary:

- **Cleaning**: trim whitespace, normalize missing markers, coerce price/qty to
  numeric (stripping `$`,`,`), parse dates, drop exact duplicates, drop rows
  missing essential fields or with non-positive price/quantity. Survey rows are
  de-duplicated on `Survey ResponseID`. Line total = price x quantity.
- **Counterfactual anomaly index**: for each category build a daily spend series
  over the full date range (missing days = 0). Train an OLS counterfactual
  (linear time trend + day-of-week + month dummies) **only on days before
  2020-03-01**. Forecast March 2020. `z = mean(actual-forecast over March) /
  training residual std`; `Anomaly_Index = round(100*tanh(z), 2)`, bounded to
  [-100,100]. +100 = unusual surge, 0 = normal, -100 = unusual slump. Scale and
  transform are declared and applied identically to every category.
- **Top categories**: among categories with enough pre-period history, the 10
  highest indices are surges; the 10 lowest are slumps.
- **Feature engineering**: one-hot encode categorical demographic columns
  (missing -> explicit `Missing` level) and standardize numeric demographic
  columns, producing binary/continuous moderators. `total_features_analyzed`
  equals the number of engineered feature columns. Feature names are kept
  **consistent** between `survey_feature_engineered.csv` and the report.
- **DiD panels**: baseline = 2020-01-01..2020-02-29, treatment =
  2020-03-01..2020-03-31. The at-risk universe is users present in both the
  cleaned survey and the purchases. Intensive panel = per purchaser x category x
  period total spend. Extensive panel = full user x category x period grid with
  `Has_Purchase` 0/1.
- **DiD estimation**: intensive margin uses a per-feature **Univariate DiD**
  (OLS of `Total_Spend ~ Period*Feature`, estimate = interaction coef).
  Extensive margin uses a single **Multivariate Heterogeneous DiD** per category
  (linear probability model of `Has_Purchase` on all feature main effects and
  `Period x Feature` interactions). For surge categories drivers are sorted by
  `did_estimate` descending, for slumps ascending; the top 3 of each margin are
  reported with `did_estimate`, `p_value`, and `method`.

## How the executor runs it
```bash
# ensure data exists
[ -f /app/data/survey_dirty.csv ] || python /tmp/download_data.py
# run full pipeline (defaults shown; override via stdin JSON if needed)
echo '{}' | python /app/environment/skills/current/scripts/pipeline.py
```
`pipeline.py` reads an optional JSON object on **stdin** with any of
`{"survey_path","purchases_path","output_dir"}` (all optional; defaults are the
`/app/data/*` inputs and `/app/output`). It writes the 7 artifacts and prints a
JSON summary on **stdout** (`{"status":"ok", "outputs":{...}, "n_categories":...,
"total_features_analyzed":...}`). A nonzero exit or `{"status":"error",...}`
indicates failure to inspect.

Validate the result:
```bash
echo '{"output_dir":"/app/output"}' | python /app/environment/skills/current/scripts/validate.py
```
`validate.py` checks that every file exists, required columns are present,
numeric fields are finite, the anomaly index is within [-100,100], panels have
the right column schema, and the report JSON matches the required shape
(metadata date format `MM-DD-YYYY`, 10 surge + 10 slump categories where data
allows, up to 3 drivers per margin, correct sort direction). It prints
`{"status":"ok"}` or a list of problems — treat problems as failures to fix in
the Skill, not in the workspace only.

## Failure handling / assumptions
- Missing input files -> instruct to run the downloader; the script errors
  clearly if still absent.
- Fewer than 10 qualifying surge/slump categories -> report as many as exist
  and set the `summary` counts to what was produced.
- Zero-variance or collinear features inside a category subset are dropped
  before OLS; estimates that are non-finite are skipped so sorting is stable.
- `statsmodels` is not required; OLS and p-values use NumPy + SciPy, with a
  normal-approximation fallback if SciPy is unavailable.
- Do not hard-code category names, feature values, counts, or indices: every
  number comes from the current cleaned data.
