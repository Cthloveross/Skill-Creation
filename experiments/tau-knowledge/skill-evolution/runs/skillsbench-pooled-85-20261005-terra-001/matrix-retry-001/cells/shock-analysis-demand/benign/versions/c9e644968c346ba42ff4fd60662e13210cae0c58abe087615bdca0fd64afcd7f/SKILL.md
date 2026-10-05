---
name: demand-shock-excel-workbook
summary: Complete an Excel demand-side investment-shock workbook with internal WEO/SUT links, formula-driven projections, and three scenarios.
description: Use when a supplied Excel template must be saved as a completed demand-shock model containing WEO_Data, SUPPLY, USE, SUT Calc, and NA scenario calculations. The Skill writes an Excel-compatible workbook and preserves calculated cells as formulas.
---

# Demand-Shock Excel Workbook

Use this Skill for the Georgia demand-side shock task or another workbook with the same required outputs. It produces the required workbook at the requested path rather than returning an unchanged template.

## Runtime inputs

The builder reads one JSON object from stdin and emits a result object to stdout.

```json
{
  "template_path": "/root/test_demand.xlsx",
  "output_path": "/root/test_demand.xlsx",
  "sut_workbook_path": "/root/geostat_supply_use.xlsx",
  "weo": {
    "years": [2023, 2024, 2025, 2026, 2027],
    "real_gdp": ["official value", "official value", "official value", "official value", "official value"],
    "real_growth": ["official value", "official value", "official value", "official value", "official value"],
    "gdp_deflator": ["official value", "official value", "official value", "official value", "official value"]
  },
  "weo_source_note": "IMF WEO release, Georgia, date, units",
  "sut_source_note": "Geostat supply/use release, table year, date"
}
```

Only `template_path` and `output_path` are required. `sut_workbook_path` is optional, but when it is available it must be an official workbook with sheets named `SUPPLY` and `USE`; those sheets are copied internally with no external links. `weo` is optional but should be supplied whenever verified local WEO observations are available. Its values are source observations, not calculated model outputs.

Run:

```text
python scripts/build_demand_workbook.py <<'JSON'
{"template_path":"/root/test_demand.xlsx","output_path":"/root/test_demand.xlsx"}
JSON
```

Then inspect the returned JSON and run:

```text
python scripts/validate_workbook.py <<'JSON'
{"workbook_path":"/root/test_demand.xlsx"}
JSON
```

## Method

1. Obtain verified WEO observations and the official Geostat SUT locally whenever sources are available. Record release and unit metadata in the supplied notes.
2. Run the builder. It always saves a changed, valid `.xlsx` to `output_path` and creates the required sheets.
3. The `WEO_Data` sheet retains supplied observations through 2027. It extends 2028--2043 with Excel formulas: real GDP growth is fixed at the 2027 rate, real GDP compounds from the preceding period, and the GDP deflator uses the average growth rate over the four latest observed years as a fixed anchor.
4. `SUT Calc` contains 38 commodity rows. Columns C:H use internal formulas linked to `SUPPLY` and `USE`; `C46` is a formula-derived, project-weighted import-content share.
5. `NA!D30:D33` contains the exchange rate (2.746), project total (6.5 USD bn), formula-linked import content, and baseline demand multiplier (0.8). The three visible scenario blocks use bell-shaped allocations across 2026--2033, GDP-deflator investment deflation, domestic-content adjustment, multiplier effects, and WEO-linked baseline GDP.
6. Scenario 2 explicitly uses a multiplier of 1. Scenario 3 explicitly uses an import-content share of 0.5. All other scenario logic is shared by formulas.

## Source-unavailable behavior

The runtime may contain only the blank template and have no network access. In that case the builder creates clearly labelled internal source-entry tables and a fully formula-linked model rather than leaving the template untouched. These cells are marked as pending source replacement. This enables workbook completion and formula auditing without inventing official observations. Replace pending WEO/SUT source-entry values with verified official data and rerun before making a provenance claim.

## Validation

The validator checks required sheet names, substantive 38-by-38 source sheets, 2027 and 2043 WEO periods, post-2027 formulas, internal SUT links, formula-driven `C46`, populated NA assumptions, WEO/SUT formula links, three scenario labels, formula errors, and external workbook links. It does not independently establish that local source files are the latest official releases.
