---
name: demand-shock-excel-workbook
summary: Complete a formula-driven Excel demand-shock model from verified local WEO and supply-use source files.
description: Use when an Excel workbook must be populated with official macroeconomic observations, copied SUPPLY and USE tables, a supply-use-based import-content calculation, and three auditable demand-shock scenarios.
---

# Demand-Shock Excel Workbook

## Required inputs and execution rule

The executor must **create and save the output workbook**, rather than returning the untouched template. Start by inventorying `/root` for the template and verified local source files, then run `scripts/build_demand_workbook.py` with the actual source paths and mappings.

This task requires all of the following before a completed workbook can be truthfully produced:

1. a local verified IMF WEO extract for the requested economy, containing consecutive annual observations through 2027 for real GDP, real GDP growth, and the GDP deflator; and
2. a local verified official supply-use workbook whose `SUPPLY` and `USE` sheets are substantive 38-by-38-or-larger tables.

Do not invent WEO observations, manufacture substitute supply/use tables, or use an economy-wide imports ratio. If sources are unavailable in a no-network runtime, record that as a source-acquisition failure; it is not valid to deliver the untouched template as a completed workbook.

Although the analytical task requests Excel formulas, the supplied builder is a permitted workbook-construction helper: it writes formulas into the delivered `.xlsx`; it does not replace calculation logic with externally calculated outputs. Recalculate the saved workbook in Excel or another compatible spreadsheet engine before final delivery when one is available.

## Builder input

`scripts/build_demand_workbook.py` reads one JSON object from stdin and emits a JSON result to stdout.

```json
{
  "template_path": "/root/test_demand.xlsx",
  "output_path": "/root/test_demand.xlsx",
  "sut_workbook_path": "/root/verified_geostat_sut.xlsx",
  "weo_source_note": "IMF WEO release, Georgia, retrieval date and series metadata",
  "sut_source_note": "Geostat supply-use release, table year and retrieval date",
  "weo": {
    "years": [2023, 2024, 2025, 2026, 2027],
    "real_gdp": ["verified numeric observation for each year"],
    "real_growth": ["verified percent observation for each year"],
    "gdp_deflator": ["verified index observation for each year"]
  },
  "sut_mapping": [
    {
      "label": "commodity label copied from source",
      "imports_cell": "source imports cell on SUPPLY",
      "total_supply_cell": "source total-supply cell on SUPPLY",
      "weight_cell": "source project-composition/use cell on USE",
      "check_cell": "optional source USE check cell"
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

The displayed array contents and addresses are schema descriptions, not data. Supply exactly 38 verified commodity mappings, identified from source labels and metadata. Values for `exchange_rate`, `amount_usd`, and scenario assumptions are task inputs; all other numeric source data must be supplied from the verified source extract.

Example execution pattern:

```text
python scripts/build_demand_workbook.py <<'JSON'
{...actual JSON payload...}
JSON
```

A successful result means the file at `output_path` has been modified. It must be the file submitted as `test_demand.xlsx`.

## What the builder writes

### WEO_Data

The builder creates `WEO_Data` with clearly labelled real GDP, real GDP growth, GDP deflator, and deflator-growth rows. It retains supplied observations as values through 2027 and marks that boundary. It then writes Excel formulas through 2043:

- post-2027 growth equals the 2027 growth cell;
- real GDP compounds from the preceding level and growth;
- observed deflator growth is calculated from adjacent deflator levels;
- the 2027 deflator-growth anchor is an `AVERAGE` formula over the most recent four observed deflator-growth rates; and
- post-2027 deflator levels compound using that anchor.

### SUPPLY, USE, and SUT Calc

The builder copies source values and presentation from the verified `SUPPLY` and `USE` worksheets without external workbook links. It writes 38 mapped rows to `SUT Calc` columns C:H:

- C imports linked internally to `SUPPLY`;
- D total supply linked internally to `SUPPLY`;
- E row import share;
- F project/use weight linked internally to `USE`;
- G weighted import share; and
- H an internal USE reference/check.

`SUT Calc!C46` is an Excel `SUMPRODUCT` formula deriving the weighted import-content share from the mapped rows.

### NA and scenarios

The original `NA` sheet is retained. The builder fills `D30:D33` with labelled assumptions: 2.746 GEL/USD, 6.5 USD-billion in the workbook's stated units, an internal formula to `SUT Calc!C46`, and the 0.8 baseline multiplier. It then builds three visibly labelled tables:

1. baseline;
2. scenario 2, where only the multiplier is 1; and
3. scenario 3, where only import-content share is 0.5.

Each table links baseline GDP and the GDP deflator directly to `WEO_Data`, allocates the project over 2026–2033 with a normalized formula-driven bell-shaped profile, deflates nominal investment using the GDP deflator, calculates domestic content, applies the scenario multiplier, and calculates with-shock real GDP.

## Delivery validation

Run the structural validator after saving:

```text
python scripts/validate_workbook.py <<'JSON'
{"workbook_path":"/root/test_demand.xlsx"}
JSON
```

Before delivery, reopen the workbook and confirm:

- sheets are named exactly `WEO_Data`, `SUT Calc`, `NA`, `SUPPLY`, and `USE`;
- `SUPPLY` and `USE` are substantive and at least 38 by 38;
- `WEO_Data` reaches 2043 and has post-2027 formulas;
- `SUT Calc!C46` remains a formula;
- `NA!D30:D33` are populated, including 2.746 and 0.8;
- all three scenario labels are visible; and
- formulas have no external-workbook references or Excel error values.
