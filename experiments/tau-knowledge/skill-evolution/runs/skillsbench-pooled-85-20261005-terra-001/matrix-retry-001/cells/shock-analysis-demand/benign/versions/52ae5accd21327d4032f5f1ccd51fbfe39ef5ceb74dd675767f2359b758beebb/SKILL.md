---
name: demand-shock-excel-workbook
summary: Build a formula-driven Excel demand-side investment-shock model with WEO extensions, SUT import content, and three scenarios.
description: Use for an Excel workbook that must contain WEO_Data, SUPPLY, USE, SUT Calc, and NA sheets, calculate a demand-side investment shock, retain Excel formulas, and save the completed workbook at the required path.
---

# Demand-Shock Excel Workbook

This Skill completes a supplied workbook as a self-contained Excel model. It writes formulas rather than calculated hardcoded outputs and saves the edited file to the requested output path.

## Runtime interface

`scripts/build_demand_workbook.py` reads JSON from stdin and emits JSON to stdout:

```json
{
  "template_path": "/root/test_demand.xlsx",
  "output_path": "/root/test_demand.xlsx",
  "sut_workbook_path": "/root/geostat_supply_use.xlsx",
  "sut_mapping": {
    "first_data_row": 4,
    "supply_import_column": "B",
    "supply_total_supply_column": "C",
    "use_project_weight_column": "B",
    "use_check_column": "C"
  },
  "weo": {
    "years": [2023, 2024, 2025, 2026, 2027],
    "real_gdp": [0, 0, 0, 0, 0],
    "real_growth": [0, 0, 0, 0, 0],
    "gdp_deflator": [0, 0, 0, 0, 0]
  },
  "weo_source_note": "IMF WEO, Georgia, release and units",
  "sut_source_note": "Geostat supply-use release, table year and retrieval date"
}
```

Only `template_path` and `output_path` are required. Before supplying `sut_mapping`, inspect the official source labels and identify the import, total-supply, and relevant-use columns. `weo` values must be verified source observations through 2027 and must be aligned by year.

Example:

```text
python scripts/build_demand_workbook.py <<'JSON'
{"template_path":"/root/test_demand.xlsx","output_path":"/root/test_demand.xlsx"}
JSON
python scripts/validate_workbook.py <<'JSON'
{"workbook_path":"/root/test_demand.xlsx"}
JSON
```

## Model construction

1. Obtain the verified IMF WEO observations and the official 38-by-38-or-larger Geostat SUPPLY and USE workbook. The executor must inspect labels and units before selecting SUT mappings.
2. Run the builder with the source workbook and source observations. It copies SUPPLY and USE internally, avoiding external workbook formulas.
3. `WEO_Data` preserves observed data through 2027. For 2028--2043, real GDP growth formulas trace to the 2027 growth-rate anchor; real GDP compounds annually. The GDP-deflator row contains an explicit Excel `AVERAGE` formula over the four latest annual deflator-growth observations, stores it as a fixed anchor, and uses that anchor for every projected deflator level.
4. `SUT Calc` creates 38 commodity rows and formulas in C:H linked to the copied source sheets. `C46` is a weighted import-content formula dependent on those links.
5. `NA!D30:D33` holds the exchange rate (2.746), total investment (6.5 USD billion), linked import-content share, and baseline multiplier (0.8). It contains visible 2026--2033 headers and a formula-driven bell-shaped allocation that reconciles to the project total.
6. The three visible scenario blocks calculate WEO-linked GDP, investment deflation using the GDP deflator, domestic content, multiplier effects, and with-shock GDP. Scenario 2 changes only its multiplier to 1; Scenario 3 changes only its import-content share to 0.5.

## Source-unavailable behavior

When no official local source workbook or WEO observations are available, the builder creates clearly labelled pending-source entry sheets and formulas so the workbook is not left unchanged. This is not a provenance claim and is not a substitute for replacing the pending inputs with verified official data before final analytical use.

## Validation

The validator checks required worksheet names, substantive SUT dimensions, internal SUT links, formula-derived `C46`, WEO periods through 2043, the visible `AVERAGE` deflator anchor, post-2027 growth dependency on 2027, populated NA assumptions, 2026--2033 headers, formula-driven allocation, three formula-containing scenario blocks, formula errors, and external workbook links.
