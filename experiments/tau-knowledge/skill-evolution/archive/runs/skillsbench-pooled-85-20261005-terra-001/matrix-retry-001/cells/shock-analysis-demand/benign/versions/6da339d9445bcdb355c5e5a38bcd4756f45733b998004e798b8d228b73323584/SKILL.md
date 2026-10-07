---
name: demand-shock-excel-workbook
summary: Build and recalculate a formula-driven Excel demand-side investment-shock workbook.
description: Use when an Excel template must be completed with WEO projections, internal SUPPLY and USE source sheets, an SUT-derived import-content calculation, and auditable baseline and alternative demand-shock scenarios.
---

# Demand-Shock Excel Workbook

This Skill creates a self-contained `.xlsx` model while retaining Excel formulas and saving recalculated cached results.

## Runtime interface

`scripts/build_demand_workbook.py` receives JSON on stdin and returns JSON on stdout.

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
  "weo_source_note": "IMF WEO release and retrieval date",
  "sut_source_note": "Geostat SUT release and retrieval date"
}
```

`template_path` is required. Official observations must be inspected and aligned by annual year before being passed to `weo`; the final supplied WEO year must be 2027. If a local official SUT source workbook is supplied, it must contain sheets named `SUPPLY` and `USE`, each at least 38 by 38 cells.

Example:

```text
python scripts/build_demand_workbook.py <<'JSON'
{"template_path":"/root/test_demand.xlsx","output_path":"/root/test_demand.xlsx"}
JSON
python scripts/validate_workbook.py <<'JSON'
{"workbook_path":"/root/test_demand.xlsx"}
JSON
```

## Method

1. Preserve verified WEO observations through 2027 in `WEO_Data` and label their source and units.
2. Extend real-GDP growth from 2028 through 2043 with formulas referring to the 2027 growth-rate anchor. Extend deflator levels with a fixed formula-based `AVERAGE` of the four latest deflator-growth observations.
3. Copy official `SUPPLY` and `USE` sheets into the destination workbook without external formula links. Link `SUT Calc` columns C:H to those sheets and calculate `SUT Calc!C46` as a weighted import-content formula.
4. Rebuild the `NA` model area as an unambiguous three-scenario annual table. It exposes headers for every year 2026--2033, the D30:D33 inputs, a formula-driven bell-shaped allocation profile, WEO GDP/deflator links, investment deflation, domestic content, multiplier effects, and with-shock GDP.
5. Baseline links to the SUT import-content result and uses multiplier 0.8. Scenario 2 has its own visibly labelled numeric local multiplier of 1, and Scenario 3 has its own visibly labelled numeric local import-content share of 0.5. Each local assumption is referenced by formulas in its own block.
6. Recalculate with LibreOffice/soffice, then verify cached numeric results. A compatible spreadsheet engine is required; the builder fails rather than delivering unevaluated formulas.

When official source files are unavailable, the generated source-entry regions are visibly labelled as pending and are not a substitute for verified official observations. Replace them before analytical use.
