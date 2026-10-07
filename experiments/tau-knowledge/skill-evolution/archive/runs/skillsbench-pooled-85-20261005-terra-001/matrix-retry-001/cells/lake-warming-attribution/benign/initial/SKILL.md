---
name: lake-warming-trend-and-driver-attribution
description: Analyze supplied lake surface-temperature, climate, hydrology, and land-cover CSV files to produce the requested warming-trend and dominant-driver CSV artifacts. Use when tables must be discovered at runtime and aligned on their actual temporal keys.
---

# Lake warming trend and driver attribution

Run `scripts/analyze_lake.py` against the supplied data directory. It discovers CSV schemas rather than assuming column names, finds the water-temperature outcome and temporal key, aligns source records by that key, and creates both required files:

- `trend_result.csv` with exactly `slope,p-value`
- `dominant_factor.csv` with exactly `variable,contribution`

The trend is an OLS regression of observed surface temperature on decimal calendar year. The slope is therefore temperature units per year; the two-sided p-value tests the OLS null hypothesis of zero slope. This is statistical trend evidence, not a guarantee that serial dependence or seasonality has been modeled.

Driver attribution uses all discovered numeric non-key drivers after temporal alignment. Missing predictor values are median-imputed using the aligned analysis records; constant predictors are omitted. A standardized multiple linear regression is fitted. Each predictor's importance is its squared standardized coefficient; importances are summed within Heat, Flow, Wind, and Human and normalized to 100 percent. The output `variable` is the dominant **category**, not a raw coefficient or a causal conclusion.

## Category mapping

The default mapping is evidence-based on both source and variable labels:

- fields from `climate.csv` are Heat except labels indicating wind (Wind) or precipitation/runoff/flow (Flow);
- fields from `hydrology.csv` are Flow;
- fields from `land_cover.csv` are Human;
- explicit label cues such as `wind`, `discharge`, `inflow`, `urban`, or `impervious` take precedence.

If a dataset uses terminology for which this is unsuitable, provide `category_map` in the JSON input. Keys can be a bare column name or `source_file.column_name`; values must be one of `Heat`, `Flow`, `Wind`, or `Human`.

## Runnable call

From an environment containing this package and the public files:

```bash
python scripts/analyze_lake.py <<'JSON'
{"data_dir":"/root/data","output_dir":"/root/output"}
JSON
```

Optional explicit mapping example (the names are placeholders and must be replaced with discovered headers):

```json
{
  "data_dir": "/root/data",
  "output_dir": "/root/output",
  "category_map": {"climate.csv.some_column": "Heat"}
}
```

The script reads one JSON object from stdin and emits one JSON result object to stdout. On success it includes the output paths, selected target/date fields, aligned row count, dominant category, and contribution. On an unsupported or insufficient-data condition it emits `{ "ok": false, "error": ... }` and does not claim a result.

## Validation and interpretation

The script checks file existence, CSV headers, date-key availability, numeric target coverage, overlap among the tables, finite regression values, valid category assignments, and the final CSV headers, row counts, and numeric ranges. It aggregates duplicate records within a table/date by numeric mean before joining, preventing row-position joins or accidental multiplication. Review the returned metadata and, when appropriate, inspect schemas, units, temporal coverage, missingness, and whether the identified target is genuinely the 0--5 m surface-temperature measurement before reporting conclusions.
