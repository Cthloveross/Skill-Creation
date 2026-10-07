---
name: demand-shock-excel-workbook
summary: Build and recalculate a formula-driven Excel demand-side investment-shock workbook.
description: Use when an Excel template must be completed with WEO macroeconomic projections, internal SUPPLY and USE source sheets, an SUT-derived import-content calculation, and auditable baseline and alternative demand-shock scenarios.
---

# Demand-Shock Excel Workbook

Build a self-contained `.xlsx` workbook with retained Excel formulas **and** cached calculated results. The model uses runtime-supplied official observations and source-workbook mappings; it does not embed country-specific source observations in the Skill.

## Runtime interface

`scripts/build_demand_workbook.py` receives one JSON object on stdin and writes a result object to stdout.

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

`template_path` is required. `weo`, when supplied, must be consecutive annual verified observations ending in 2027. A supplied SUT workbook must contain `SUPPLY` and `USE` sheets, each at least 38 by 38. The script emits either `{"ok": true, ...}` or `{"ok": false, "error": ...}`.

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

1. Preserve supplied WEO observations through 2027 and visibly label real GDP, real GDP growth, and GDP deflator. Store free-form source metadata outside the series-label search area so source prose cannot be mistaken for a data row.
2. Fill every 2028--2043 real-GDP-growth cell with an Excel formula directly referring to the 2027 growth anchor. Extend GDP-deflator levels with formulas. The first projected deflator cell visibly uses `AVERAGE` of the four latest observed annual deflator-growth rates; subsequent cells use the same fixed anchor.
3. Copy verified source SUT sheets internally, with no external workbook links. Fill SUT Calc columns C:H with formulas linked to `SUPPLY`/`USE` and calculate `SUT Calc!C46` as a weighted import-content formula.
4. Create exactly three visibly labelled, formula-driven annual scenario blocks covering 2026--2033. Keep generic horizon labels free of the word “scenario” so the three actual blocks remain unambiguous to workbook readers and validators.
5. Each block uses WEO GDP and deflator links, investment deflation, domestic content, multiplier effects, and with-shock GDP. The allocation formula derives a symmetric positive bell profile from the local project start and duration assumptions and normalizes the eight annual shares to one. Scenario 2 has a labelled numeric multiplier of `1`; Scenario 3 has a labelled numeric import-content share of `0.5`.
6. Recalculate twice with LibreOffice/soffice, then reopen in formula and value modes. The process rejects a workbook if `C46`, WEO projection formulas, NA project-period formulas, or the normalized bell-shaped allocation lack cached numeric results.

If verified official source data are unavailable, the generated source-entry areas are explicitly marked pending. Replace those entries with verified WEO and Geostat data before analytical use.
