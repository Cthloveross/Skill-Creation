---
name: demand-shock-excel-workbook
summary: Build and recalculate a formula-driven Excel demand-side investment-shock workbook.
description: Use when a supplied Excel template must be completed with IMF WEO extensions, internal SUPPLY and USE source sheets, a traceable SUT import-content calculation, and three demand-shock scenarios with retained Excel formulas and cached results.
---

# Demand-Shock Excel Workbook

This Skill builds a self-contained Excel model and saves it at the requested output path. It retains Excel formulas for calculated cells, copies source SUT sheets internally, and **recalculates the saved workbook** so reopening it in value-reading mode returns numeric answers.

## Runtime interface

`scripts/build_demand_workbook.py` reads JSON from stdin and writes JSON to stdout:

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
  "weo_source_note": "IMF WEO Georgia release, series definitions, units, and retrieval date",
  "sut_source_note": "Geostat supply-use release, table year, and retrieval date"
}
```

`template_path` and `output_path` are required. When official local source files are supplied, the executor must inspect their labels and metadata before setting `sut_mapping`; the mapping identifies the imported-supply, total-supply, and project-use fields. WEO observations must be verified, aligned by explicit annual year keys, and end in 2027.

Example:

```text
python scripts/build_demand_workbook.py <<'JSON'
{"template_path":"/root/test_demand.xlsx","output_path":"/root/test_demand.xlsx"}
JSON
python scripts/validate_workbook.py <<'JSON'
{"workbook_path":"/root/test_demand.xlsx"}
JSON
```

## Construction method

1. Acquire the applicable official IMF WEO observations and latest official Geostat supply/use workbook. Preserve source notes, units, and release dates in the workbook.
2. Run the builder. It copies `SUPPLY` and `USE` into the output workbook, so calculation formulas have no external-workbook links.
3. `WEO_Data` preserves supplied source observations through 2027. Every 2028--2043 real-GDP-growth cell is an Excel formula that traces directly to the 2027 growth anchor. GDP-deflator growth has a fixed four-observation `AVERAGE` anchor, and projected GDP-deflator levels use that anchor.
4. `SUT Calc` contains 38 commodity rows. Columns C:H link to internal `SUPPLY` and `USE`; `C46` calculates the use-weighted import-content share from those links.
5. `NA!D30:D33` holds the 2.746 GEL/USD exchange rate, USD 6.5 billion project value, formula-linked SUT import content, and 0.8 baseline multiplier. All three scenarios expose 2026--2033 headers, formula-driven bell-shaped allocation, GDP-deflator investment deflation, domestic impulse, multiplier effect, and with-shock GDP.
6. Scenario 2 changes only the local multiplier to 1. Scenario 3 changes only the local import-content share to 0.5.
7. The builder invokes `scripts/recalculate_workbook.py`. A compatible LibreOffice/soffice executable is therefore a delivery prerequisite. The build fails rather than silently delivering formulas with missing cached values.

## Source-unavailable behavior

If official source data are unavailable at runtime, the workbook identifies the relevant source-entry regions as pending. This preserves the formula model and prevents an unchanged template, but it is not a claim that neutral placeholders are official data. Replace pending entries with verified WEO and Geostat data before analytical use.

## Validation

The validator checks worksheet names, SUT dimensions and internal links, WEO horizon and formula anchors, NA assumptions and scenarios, absence of formula errors/external links, and calculated cached numeric results including `SUT Calc!C46`. A successful delivery must have a numeric `C46` import-content share from 0 through 1 when reopened with `data_only=True`.
