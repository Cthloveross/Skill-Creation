---
name: demand-shock-excel-workbook
summary: Build and validate a formula-driven Excel demand-side investment-shock workbook from official WEO and supply-use source files.
description: Use when a supplied Excel template must be completed with official macroeconomic source observations, copied SUPPLY and USE tables, a supply-use-based import-content calculation, and comparable demand-shock scenarios.
---

# Demand-Shock Excel Workbook

## Scope and prerequisites

This Skill completes a workbook only when the following source material is available and has been checked by the executor:

1. an IMF WEO extract for the requested economy containing annual real GDP, real GDP growth, and GDP-deflator observations through 2027; and
2. the latest official national supply-use workbook containing substantive worksheets named `SUPPLY` and `USE`.

The supplied template alone is not evidence for either source. Do not invent WEO observations, construct placeholder supply-use tables, use an economy-wide imports ratio in place of project import content, or silently substitute an unverified source. If the runtime has no network and no local official source files, source acquisition is a blocking prerequisite; report that fact rather than claiming the workbook is completed.

The task requires Excel-only work. For this task, use the manual Excel procedure below. The packaged Python builder is an optional reusable implementation for a different execution context where automation is explicitly permitted and verified source inputs are supplied; it is not permission to disregard an Excel-only instruction.

## Required delivered workbook

Save the completed workbook at the requested output path. It must contain these exact sheet names:

- `WEO_Data`: visible source/release note, identifiable real GDP, real GDP growth, GDP deflator, and deflator-growth rows, including 2027 and every year through 2043;
- `SUPPLY` and `USE`: complete, internally copied official source worksheets, each substantive and at least 38 by 38;
- `SUT Calc`: formula links in columns C:H to the copied source tables, with `C46` calculated by an Excel formula; and
- `NA`: populated assumptions in `D30:D33`, linked macro inputs, formula-driven calculations, and three labelled scenario blocks.

The final workbook must not contain external-workbook formula links (`[other-book.xlsx]...`) or Excel error values.

## Excel-only completion procedure

### 1. Preserve the template and copy source sheets

1. Open the template and use **Save As** to create the requested output workbook.
2. Open the verified Geostat supply-use source workbook. Use **Move or Copy Sheet** to copy its `SUPPLY` and `USE` worksheets into the output workbook. Keep those names exactly and ensure formulas, if any, do not retain external-book references.
3. Verify that both copied sheets have at least 38 rows and 38 columns and contain table labels and numeric source values.
4. Do not replace the existing `NA` sheet. Create `WEO_Data` and `SUT Calc` if they are absent.

### 2. Populate WEO_Data

Create a horizontal year axis covering the official observation years through 2027 and projections from 2028 through 2043. Label the rows clearly, including units and source/release note. Paste official observations as values and visibly mark 2027 as the last official WEO period.

Use formulas, beginning only after 2027:

```excel
real growth[t] = real growth[2027]
real GDP[t]    = real GDP[t-1] * (1 + real growth[t] / 100)
deflator growth[t] = $<2027-anchor-cell>$
deflator[t]   = deflator[t-1] * (1 + deflator growth[t] / 100)
```

Calculate source-period deflator growth from adjacent deflator levels when it is not supplied:

```excel
=(current_deflator/prior_deflator-1)*100
```

The 2027 anchor must itself be a formula averaging the recent four valid annual deflator-growth observations, for example `=AVERAGE(X7:AA7)`. Do not type the resulting average as a value.

### 3. Populate SUT Calc

Identify the commodity rows and the relevant imports, total-supply, and use/composition cells by reading the source-table labels. Do not assume a commodity row or source column merely from its ordinal position.

For each mapped commodity row, put internal formulas in columns C:H:

- C: imports linked to `SUPPLY`;
- D: total supply linked to `SUPPLY`;
- E: import share (`=Crow/Drow`);
- F: project/use weight linked to `USE`;
- G: weighted import share (`=Erow*Frow`); and
- H: a linked `USE` check or relevant use reference.

Calculate the estimate in `SUT Calc!C46` by formula from the mapped rows, e.g.:

```excel
=SUMPRODUCT(E8:E45,F8:F45)/SUM(F8:F45)
```

The result must be a proportion (such as 0.35), not a percentage-point amount, because it is used as `1-import_content_share` downstream.

### 4. Populate the NA baseline

Fill the designated assumptions in `D30:D33` according to their labels:

- GEL per USD: `2.746`;
- total project investment: `6.5` billion USD in the workbook's stated units;
- import-content share: an internal formula link to `='SUT Calc'!$C$46`;
- baseline demand multiplier: `0.8`.

Link the requested NA macro cells, including its Column C and Column J source fields, to `WEO_Data` by formulas. Do not retype linked GDP or deflator observations.

Use the GDP deflator as investment deflator, with an explicit base-index conversion. For each year, keep formula dependencies equivalent to:

```excel
nominal GEL investment = USD investment * GEL_per_USD * allocation_share
real investment        = nominal GEL investment / (GDP_deflator / deflator_base)
domestic impulse       = real investment * (1 - import_content_share)
GDP increment          = domestic impulse * demand_multiplier
with-shock GDP         = baseline real GDP + GDP increment
```

Allocate the project over 2026–2033 only. The allocation must be bell-shaped (ramp up, central peak, ramp down), zero outside those eight years, and formula-driven so that the active-year shares sum to one.

### 5. Add scenarios

Copy the full baseline table twice below the first block and provide visible titles such as `Scenario 1: baseline`, `Scenario 2: multiplier = 1`, and `Scenario 3: import content = 0.5`.

- Scenario 1 uses the SUT-linked import share and multiplier 0.8.
- Scenario 2 changes only the multiplier to numeric value 1.
- Scenario 3 changes only import-content share to numeric value 0.5.

All other inputs, WEO links, deflator logic, spending amount, exchange rate, timing, and formulas must remain aligned with the baseline.

### 6. Excel validation before delivery

Set calculation to Automatic, calculate, save, close, and reopen the workbook. Check that:

- WEO observations remain values while post-2027 extensions are formulas;
- the deflator anchor remains an `AVERAGE` formula;
- `SUT Calc!C46` is a formula and SUT Calc links are internal;
- `NA!D30:D33` are all populated, with 2.746 and 0.8 present;
- allocation shares total one over 2026–2033;
- all three scenario headings are visible; and
- there are no `#REF!`, `#DIV/0!`, `#VALUE!`, `#N/A`, `#NAME?`, `#NUM!`, or external workbook references.

## Optional automation in permitted runtimes

`scripts/build_demand_workbook.py` receives JSON on stdin and writes JSON on stdout. It writes the requested structure only from explicitly supplied, verified local source data; it does not download, guess, or fabricate inputs. It writes formulas but does not calculate their cached results.

Input schema:

```json
{
  "template_path": "/path/template.xlsx",
  "output_path": "/path/test_demand.xlsx",
  "sut_workbook_path": "/path/official_sut.xlsx",
  "weo_source_note": "IMF WEO release, economy, and retrieval note",
  "sut_source_note": "Official SUT release and retrieval note",
  "weo": {
    "years": [2023, 2024, 2025, 2026, 2027],
    "real_gdp": [0, 0, 0, 0, 0],
    "real_growth": [0, 0, 0, 0, 0],
    "gdp_deflator": [0, 0, 0, 0, 0]
  },
  "sut_mapping": [
    {"label": "verified commodity", "imports_cell": "B8", "total_supply_cell": "C8", "weight_cell": "D8", "check_cell": "E8"}
  ],
  "project": {
    "exchange_rate": 2.746,
    "amount_usd": 6.5,
    "baseline_multiplier": 0.8,
    "scenario2_multiplier": 1,
    "scenario3_import_share": 0.5,
    "deflator_base": 100
  },
  "end_year": 2043
}
```

The numeric zeroes and cell addresses in this schema are type illustrations, not source data or a mapping. The actual payload must contain verified observations and at least 38 verified commodity mappings.

Run the structural check after producing a workbook:

```text
python scripts/validate_workbook.py <<'JSON'
{"workbook_path":"/path/test_demand.xlsx","required_last_year":2043}
JSON
```

The validator checks workbook structure and formulas, not source provenance or cached formula values.
