---
name: ecommerce-trend-anomaly-did
version: 1.0.0
description: Clean linked e-commerce survey and purchase CSV exports, estimate pre-March counterfactual daily category spending anomalies, and produce reproducible intensive/extensive-margin demographic DiD artifacts and report.
---

# E-commerce trend anomaly and demographic DiD

Use this Skill when supplied a dirty customer-survey CSV and a dirty purchase CSV and the requested analysis compares January--February 2020 with March 2020. It creates all seven requested artifacts under an output directory without relying on source-specific column names.

## Method and assumptions

1. The runner discovers likely identifier, date, category, and spending columns from normalized source headers. It requires a shared stable customer identifier; it does not join on names.
2. Survey rows are normalized, blank identifiers are removed, and duplicate IDs retain the most complete row. Purchase rows are normalized, invalid IDs/dates/categories/non-numeric or negative spend are removed, unmatched IDs are excluded, and exact normalized transaction duplicates are removed. The cleaned purchase artifact has canonical `Survey ResponseID`, `Purchase_Date`, `Category`, and `Spend` fields.
3. Demographics are converted to usable numeric standardized features and bounded-cardinality one-hot features. Missing numeric values are median-imputed with a missingness indicator; categorical missingness is represented explicitly. High-cardinality free text is deliberately excluded rather than treated as a demographic attribute.
4. For each category, a least-squares daily-spend counterfactual is trained only on dates before 2020-03-01. The model has a time trend and day-of-week effects and includes zero-sales historical days. March mean forecast residuals are scaled by pre-period residual variation and transformed with `100*tanh(z/3)`, giving a signed, finite anomaly index in [-100, 100]. Positive indices rank as surges and negative indices as slumps.
5. The selected top ten high-index and top ten low-index categories are expanded to an at-risk panel of every cleaned survey respondent, category, and period. `Total_Spend` is zero for no purchase; `Has_Purchase` is its corresponding extensive-margin indicator. Intensive estimates are conditional on purchaser-period observations, while extensive estimates use all at-risk observations.
6. Feature effects are observational heterogeneous DiD associations, not proof of causality. A feature's estimate is the treatment-by-feature coefficient. Intensive effects use a univariate OLS DiD; extensive effects use a multivariate OLS heterogeneous DiD after removing non-identifiable columns. Normal-approximation OLS p-values are descriptive and do not account for repeated-user clustering.

The runner fails clearly when required semantic columns cannot be identified or no usable demographic features can be engineered. Categories with inadequate pre-March history remain in the anomaly file with index zero rather than receiving an invented forecast.

## Run

Ensure the two input files exist (use the task-supplied acquisition mechanism first if necessary), then invoke the script with JSON on stdin:

```bash
python scripts/run_analysis.py <<'JSON'
{"survey_path":"/app/data/survey_dirty.csv","purchase_path":"/app/data/amazon-purchases-2019-2020_dirty.csv","output_dir":"/app/output"}
JSON
```

All keys are optional and default to the task paths above. The script emits a JSON status object to stdout and writes:

- `survey_cleaned.csv`
- `amazon-purchases-2019-2020-filtered.csv`
- `category_anomaly_index.csv`
- `survey_feature_engineered.csv`
- `user_category_period_aggregated_intensive.csv`
- `user_category_period_aggregated_extensive.csv`
- `causal_analysis_report.json`

## Validation

The entrypoint validates required files and columns, unique survey IDs, finite anomaly scores and report numbers, category provenance, complete two-period at-risk panels, and ranking direction for the driver arrays. Its stdout includes counts and selected category counts. Review the cleaned artifacts and the report before interpreting drivers: the DiD comparison requires stable population composition and no differential concurrent shocks.

### JSON interface

Input is an object with optional strings `survey_path`, `purchase_path`, and `output_dir`. Output is either `{"ok":true,"output_dir":...,"n_survey":...,"n_purchase":...,"n_features":...,"n_categories":...,"n_surge":...,"n_slump":...}` or `{"ok":false,"error":...}`. The script depends only on Python, pandas, and numpy.
