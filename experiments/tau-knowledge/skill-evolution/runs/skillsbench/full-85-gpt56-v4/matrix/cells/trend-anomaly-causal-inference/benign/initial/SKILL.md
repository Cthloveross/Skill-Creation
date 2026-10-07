---
name: ecommerce-trend-anomaly-did
description: Clean e-commerce survey and transaction CSV exports, estimate pre-period daily category counterfactuals for a specified treatment month, construct demographic features, and produce intensive/extensive heterogeneous difference-in-differences artifacts and a JSON report.
---

# E-commerce Trend Anomaly and Demographic DiD

Use this Skill when two dirty CSV exports contain customer demographics and dated purchase transactions and the requested result is a treatment-period category anomaly ranking plus demographic drivers. It discovers columns from the supplied files rather than relying on a fixed export schema.

## Method

1. Read both CSV files with tolerant encoding and normalize column labels, identifiers, categorical text, dates, and numeric amounts. Exact duplicate transactions are removed; duplicate survey IDs retain the most complete record. Rows missing a usable customer ID, date, category, or positive finite amount cannot support the joined analysis and are excluded from the filtered purchase artifact.
2. Aggregate each category to a complete daily pre-treatment series (including no-sale days). Fit a deterministic OLS counterfactual using only dates before treatment, with trend and day-of-week controls. Compare treatment-day sales with its forecast. The signed aggregate residual is standardized by the pre-period residual scale and then linearly rescaled across categories to the declared bounded `[-100, 100]` anomaly index. Thus rankings are relative to the supplied data and use no March observations for training.
3. Feature-engineer demographic columns: numeric fields become median-imputed standardized values plus missingness indicators; modest-cardinality categoricals become one-hot features with an explicit missing level. Identifier-like/high-cardinality fields are excluded. Constant features are removed.
4. For each selected category and feature, estimate a two-group, two-period heterogeneous DiD: `(feature=1 treatment-baseline) - (feature=0 treatment-baseline)`. Intensive results use purchaser-period spend; extensive results use a complete at-risk respondent/category/period panel and purchase indicators. Approximate two-sided normal p-values use the independent group-period mean variance calculation. These are observational associations, not proof of causation.

## Run

Ensure the requested input files are present first (if the task supplies a data-download prerequisite, run it before this command). The script receives JSON on stdin and writes a short JSON execution summary to stdout:

```bash
python /app/environment/skills/current/scripts/run_analysis.py <<'JSON'
{
  "survey_path": "/app/data/survey_dirty.csv",
  "purchase_path": "/app/data/amazon-purchases-2019-2020_dirty.csv",
  "output_dir": "/app/output",
  "baseline_start": "2020-01-01",
  "baseline_end": "2020-02-29",
  "treatment_start": "2020-03-01",
  "treatment_end": "2020-03-31",
  "top_n": 10
}
JSON
```

All keys except the three paths are optional; the shown dates and `top_n=10` are defaults. The required outputs are written to `output_dir`:

- `survey_cleaned.csv`
- `amazon-purchases-2019-2020-filtered.csv`
- `category_anomaly_index.csv`
- `survey_feature_engineered.csv`
- `user_category_period_aggregated_intensive.csv`
- `user_category_period_aggregated_extensive.csv`
- `causal_analysis_report.json`

The script fails clearly if it cannot identify required transaction fields (customer ID, date, category, amount) or a survey identifier. Inspect source headers and provide exports with unambiguous names in that case. Category groups may contain fewer than `top_n` only when the data has too few distinct eligible categories; the report states the actual totals.

## Validation

The entrypoint validates output schemas, finite bounded anomaly values, category uniqueness, panel period coverage, and report/category consistency before reporting success. Re-run it from the raw supplied inputs to regenerate every artifact; do not treat files from an earlier run as validation.
