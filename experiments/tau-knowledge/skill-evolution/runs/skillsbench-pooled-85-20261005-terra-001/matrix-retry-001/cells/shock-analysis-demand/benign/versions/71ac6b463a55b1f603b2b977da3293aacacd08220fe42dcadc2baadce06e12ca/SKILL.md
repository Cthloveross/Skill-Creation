---
name: demand-shock-excel-workbook
summary: Build and validate an auditable Excel demand-side investment-shock model using verified local IMF WEO and official supply-use source files.
description: Apply when a workbook must contain WEO macroeconomic data extended with Excel formulas, internally copied SUPPLY and USE sheets, a supply-use-based import-content calculation, and three formula-driven demand-shock scenarios.
---

# Demand-Shock Excel Workbook

## Preconditions

This Skill produces a completed workbook only after the executor has obtained and verified source data. The runtime task file alone is a template, not a source of IMF WEO observations or official supply-use-table values.

Required local inputs are:

1. the target template workbook;
2. a verified IMF WEO extract for the requested economy, with consecutive annual real-GDP level, real-GDP-growth, and GDP-deflator observations ending in 2027; and
3. a verified official supply-use workbook containing substantive `SUPPLY` and `USE` worksheets, each at least 38 by 38.

The executor must inspect sources and map commodities by labels and metadata. Do not invent WEO observations, create synthetic supply/use data, substitute an economy-wide imports ratio, or deliver an untouched template when source data are unavailable. In a no-network environment with no local verified sources, report the acquisition blocker rather than falsely representing a workbook as completed.

The task's numeric assumptions (exchange rate, project amount, baseline multiplier, scenario-2 multiplier, and scenario-3 import share) belong in the runtime JSON payload. All calculated workbook outputs remain Excel formulas.

## Build procedure

1. Inspect the template, source release metadata, WEO units, and source-sheet labels.
2. Prepare the JSON input below using actual verified observations and 38 label-based commodity mappings.
3. Run `scripts/build_demand_workbook.py`. It reads JSON from stdin and prints JSON to stdout.
4. Recalculate the saved file in Excel or another compatible spreadsheet engine when available. Formula strings are preserved even if the construction library cannot populate cached values.
5. Run `scripts/validate_workbook.py` and submit the file at `output_path`.

The build script writes to a temporary file and atomically replaces `output_path`, so `template_path` and `output_path` may be the same file.

## Builder input schema

```json
{
  "template_path": "/root/test_demand.xlsx",
  "output_path": "/root/test_demand.xlsx",
  "sut_workbook_path": "/root/official_geostat_sut.xlsx",
  "weo_source_note": "IMF WEO release/version, Georgia, retrieval date, series definitions and units",
  "sut_source_note": "Geostat release/table year/retrieval date",
  "weo": {
    "years": [2023, 2024, 2025, 2026, 2027],
    "real_gdp": [0, 0, 0, 0, 0],
    "real_growth": [0, 0, 0, 0, 0],
    "gdp_deflator": [0, 0, 0, 0, 0]
  },
  "sut_mapping": [
    {
      "label": "official commodity label",
      "imports_cell": "official imports cell in SUPPLY",
      "total_supply_cell": "official total-supply cell in SUPPLY",
      "weight_cell": "project-relevant commodity/use cell in USE",
      "check_cell": "optional related USE source cell"
    }
  ],
  "project": {
    "exchange_rate": 2.746,
    "amount_usd": 6.5,
    "baseline_multiplier": 0.8,
    "scenario2_multiplier": 1.0,
    "scenario3_import_share": 0.5,
    "deflator_base": 100
  }
}
```

The numeric zeroes and addresses in this schema are placeholders, not source values. Supply exactly 38 mappings. A mapping must be identified from source labels, not an assumed fixed row order. `check_cell` is optional and defaults to `weight_cell`.

## Workbook behavior

The builder retains verified WEO observations through 2027 as values and creates a `WEO_Data` sheet extending through 2043. For every post-2027 period it uses formulas that:

- hold real GDP growth at the 2027 rate;
- compound real GDP from the prior year; and
- compound the GDP deflator using an anchor equal to the `AVERAGE` of the four most recent observed deflator-growth formulas.

It copies `SUPPLY` and `USE` into the output without external references, then builds `SUT Calc` columns C:H with internal links. `SUT Calc!C46` is an Excel `SUMPRODUCT` formula for the project-weighted import-content share.

The original `NA` sheet is retained. Cells `D30:D33` contain, respectively, exchange rate, USD project total, formula-linked import content, and the baseline multiplier. The sheet contains three visibly labelled scenario blocks: baseline, scenario 2 (multiplier 1), and scenario 3 (import share 0.5). All blocks link GDP and deflator series to `WEO_Data`; allocations over 2026–2033 use a normalized bell-shaped formula; nominal spending is deflated with the GDP deflator; and domestic impulse, multiplier effect, and with-shock GDP are formula-driven.

## Validation

```text
python scripts/validate_workbook.py <<'JSON'
{"workbook_path":"/root/test_demand.xlsx"}
JSON
```

The validator checks structure and formulas, but does not establish official-source provenance or evaluate formula caches. Before delivery confirm that all required sheet names exist, `SUPPLY` and `USE` are substantive, `WEO_Data` reaches 2043, `C46` remains a formula, `D30:D33` are filled, all three scenarios are visible, and there are no external-workbook links or formula-error literals.
