---
name: lake-warming-trend-and-driver-attribution
description: Analyze supplied lake water-temperature, climate, hydrology, and land-cover CSV tables to create the requested long-term trend and dominant driver-category CSV outputs. Use when tables must be joined by a real temporal key and drivers are to be grouped into Heat, Flow, Wind, and Human.
---

# Lake warming trend and dominant-category analysis

This Skill produces two one-row CSV files:

* `trend_result.csv` with `slope,p-value`. The slope is an ordinary least-squares water-temperature trend per calendar year; `p-value` is the two-sided OLS slope test p-value.
* `dominant_factor.csv` with `variable,contribution`. `variable` is one of `Heat`, `Flow`, `Wind`, or `Human`; `contribution` is its percent share of explained variance under the category-level Shapley R-squared decomposition described below.

The method does **not** treat a raw coefficient or correlation as a percent contribution. After aligning observations on a temporal key, it fits intercept-inclusive least-squares models for every combination of available categories. For each category, it averages its incremental in-sample R-squared over all orders in which categories can be added (the exact Shapley decomposition). The winning category's share is its Shapley value divided by the full model R-squared, multiplied by 100. This is a relative explanatory-association attribution, not causal proof.

## Runtime inputs and call

The executable is `scripts/analyze_lake.py`. It accepts one JSON object on standard input and writes a JSON run summary to standard output. It creates output CSVs itself.

```sh
python /app/environment/skills/current/scripts/analyze_lake.py <<'JSON'
{
  "data_dir": "/root/data",
  "output_dir": "/root/output"
}
JSON
```

Optional `files` maps logical names (`water_temperature`, `climate`, `hydrology`, `land_cover`) to CSV paths. Optional `category_overrides` maps a column name to `Heat`, `Flow`, `Wind`, or `Human`; use it when a domain-specific name cannot be classified correctly from its name and source table. Optional `time_key` explicitly selects a shared temporal-key column.

## Procedure and checks

1. Read every supplied table, inspect columns, numeric availability, duplicate time records, and missingness. The script selects a shared date/year/time-like key, parses calendar dates when applicable, and aggregates duplicate numeric records by key before an inner temporal join. It never aligns by row position.
2. Select the water-temperature response from a temperature-like column in the water table. For the trend, use all finite response/time pairs and express parsed dates as elapsed calendar years.
3. Build driver predictors from numeric non-key columns in the three driver tables. Constant columns are removed and remaining missing values are median-imputed. Names containing wind terms are `Wind`; hydrologic/precipitation/flow terms are `Flow`; land-cover-table variables and human/urban/agricultural terms are `Human`; other climate variables are `Heat`. Overrides take precedence.
4. Require at least two finite observations for trend fitting, and at least two nonconstant driver categories with positive full-model R-squared for attribution. These prerequisites prevent fabricated statistics. If they fail, the program exits with a descriptive error rather than writing misleading output.
5. Validate that both output files have exactly the requested headers, one row, finite numeric values, a category label, and a contribution in `[0,100]`.

The JSON summary includes selected keys and columns, dropped/imputed columns, join row counts, R-squared, category shares, and output paths. Review it when selecting overrides or investigating sparse joins.
