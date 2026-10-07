# Method rationale and assumptions

This documents the analytical choices in `scripts/pipeline.py`. All concrete
values (categories, feature names, estimates) are produced from the current
cleaned data, never copied from any prior run.

## 1. Cleaning
- Trim whitespace on all fields; normalize missing markers (``""``, `NA`, `N/A`,
  `None`, `null`, `nan`) to true NaN.
- Purchases: parse the order-date column to datetime; strip currency symbols and
  thousands separators from price; coerce quantity to numeric; uppercase+trim the
  category to merge case/whitespace variants of the same product type; drop exact
  duplicate rows; drop rows missing date/price/quantity/category/id or with
  non-positive price or quantity. `Line_Total = price * quantity`.
- Survey: de-duplicate on `Survey ResponseID` (keep first), drop rows with no id.

## 2. Counterfactual anomaly index
- Build a per-category daily total-spend series over the full observed range,
  reindexing to every calendar day and filling absent days with 0 so a drop to
  no-sales is modeled, not dropped.
- Train an OLS counterfactual on **days strictly before 2020-03-01** only
  (background: forecast using pre-event information). Features: scaled linear
  time trend + day-of-week dummies + month dummies (one level dropped each to
  avoid collinearity with the intercept).
- Forecast March 2020, compute `z = mean(actual - forecast over March) /
  std(training residuals)`, and map through `100 * tanh(z)`, clipped to
  [-100, 100]. The transform/scale is declared and identical for every
  category (background: declare and apply the index consistently). Degenerate
  cases (zero residual std) fall back to +/-100 by the sign of the deviation.
- Categories need >= 10 pre-period days and some pre-period activity to be
  eligible for ranking; all categories still appear in the output CSV.

## 3. Feature engineering
- Categorical demographic columns are one-hot encoded with an explicit `Missing`
  level (high-cardinality columns capped). Numeric demographic columns are
  z-standardized. Zero-variance features are dropped. `total_features_analyzed`
  is the resulting feature count. Feature names are identical in
  `survey_feature_engineered.csv` and in the report (background: consistent
  encoding and consistency between reported summaries and underlying data).

## 4. DiD panels and estimation
- Baseline = 2020-01-01..2020-02-29 (leap year), treatment = 2020-03-01..03-31,
  encoded `Period`=0/1. The at-risk universe is users present in both the
  cleaned survey and the purchases (so extensive non-purchasers are included).
- Intensive panel: purchaser-level `Total_Spend` per user x category x period
  (intensive margin = spend conditional on purchasing).
- Extensive panel: full user x category x period grid with `Has_Purchase` 0/1
  (extensive margin = probability of purchasing). Intensive and extensive are
  kept distinct (background: do not mix the two margins).
- Intensive driver = per-feature **Univariate DiD**: OLS
  `Total_Spend ~ 1 + Period + Feature + Period*Feature`; the interaction coef is
  the DiD estimate with its OLS p-value.
- Extensive driver = one **Multivariate Heterogeneous DiD** per category: linear
  probability model `Has_Purchase ~ 1 + Period + sum(Feature_i) +
  sum(Period*Feature_i)`; each `Period*Feature_i` coefficient is that feature's
  DiD estimate. Features with no within-subset variance are dropped first.
- Sorting: surge categories sort drivers by `did_estimate` descending (largest
  positives), slump categories ascending (largest negatives); the top 3 per
  margin are reported. These are **associational** DiD contributions; parallel
  trends and repeated-transaction independence are assumptions, not guarantees
  (background caveats).

## Known limitations / tuning points for evolution
- The anomaly index scaling (`tanh`) is monotonic for ranking; if the grader
  expects a different bounded normalization, adjust only
  `helpers.category_anomaly_index` and rerun the whole pipeline + validator.
- Feature naming uses an `ENG_<column>__<level>` convention. If the grader
  requires literal `ENG_FEATURE1..N` headers, rename in `engineer_features`
  while keeping report `feature` names consistent with the CSV columns.
- `n_at_risk` is the shared survey-and-purchases user universe. If the task
  intends a per-category risk set, change only the universe/`n_at_risk` logic.
