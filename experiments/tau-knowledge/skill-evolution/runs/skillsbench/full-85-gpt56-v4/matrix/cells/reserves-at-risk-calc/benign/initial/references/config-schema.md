# `xlsx_rar.py build` configuration

The builder reads JSON from `--config`. All cell coordinates are Excel A1 coordinates and all table bounds include both endpoints. Supply discovered workbook coordinates; these examples are schemas, not workbook-specific values.

```json
{
  "imf_candidate": 0,
  "price": {
    "sheet": "Gold price", "first_row": 2,
    "date_col": "A", "price_col": "B", "return_col": "C",
    "vol3_col": "D", "vol12_col": "E"
  },
  "answer": {
    "step1": {
      "latest_price": "B3", "vol3": "B4",
      "annualized_vol3": "B5", "vol12": "B6"
    },
    "step2": {"country_row": 11, "value_row": 12, "exposure_row": 13, "first_col": 2},
    "step3": {"country_row": 20, "value_row": 21, "volatility_row": 22,
              "total_row": 23, "rar_row": 24, "first_col": 2}
  },
  "tables": {
    "value": {"sheet": "Value", "orientation": "rows", "country_col": "A",
              "header_row": 1, "first_data_row": 2, "last_data_row": 200},
    "volume": {"sheet": "Volume", "orientation": "rows", "country_col": "A",
               "header_row": 1, "first_data_row": 2, "last_data_row": 200},
    "total": {"sheet": "Total Reserves", "orientation": "rows", "country_col": "A",
              "header_row": 1, "first_data_row": 2, "last_data_row": 200}
  },
  "conversion": {"ounces_per_volume_unit": 32150.7466, "value_scale_divisor": 1000000},
  "templates": {
    "exposure": "={value}*{volatility}",
    "rar": "={value}*{volatility}/{total}",
    "confidence_multiplier": null
  }
}
```

`orientation` currently supports `rows`: countries in one column and periods across the header row. The script finds the `2025` header accepting numeric `2025`, text `2025`, or a date in calendar year 2025. This must resolve exactly once.

`value_scale_divisor` converts the dollar result of `volume × ounces × USD/ounce` to the scale used by the Value and Total Reserves sheets. For example, use `1000000` only after confirming all compared values are USD millions. Never use the example conversion values without checking source headers.

Templates accept `{value}`, `{volatility}`, `{total}`, and `{z}` and must include an initial `=`. If a confidence multiplier is required, put its numeric value in `confidence_multiplier` and use `{z}` in the RaR template. Formulas written by the builder use only ordinary Excel constructs and `INDEX`/`MATCH`.
