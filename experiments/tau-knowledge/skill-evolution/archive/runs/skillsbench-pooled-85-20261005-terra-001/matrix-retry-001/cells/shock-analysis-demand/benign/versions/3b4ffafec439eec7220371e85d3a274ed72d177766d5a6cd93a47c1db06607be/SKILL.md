---
name: formula-driven-demand-shock-workbook
description: Build and validate a demand-side investment-shock Excel workbook from supplied official WEO and supply-use source files. Use for templates that require internal WEO_Data, SUT Calc, SUPPLY, USE, and NA sheets; formula-driven GDP/deflator extensions; a SUT import-content calculation; and comparable baseline and alternative demand scenarios.
---

# Formula-Driven Demand-Shock Workbook

## Scope and constraints

This Skill completes the supplied workbook rather than returning a narrative. It preserves calculations as Excel formulas and uses source observations only from the official WEO release and the mandated national statistical authority supply-use workbook.

The public task may require Excel-only work. In that case, use the manual Excel procedure below. `scripts/build_demand_workbook.py` is an optional reproducible workbook-construction helper: it writes source values and Excel formula strings but does **not** calculate the economic model externally or invent source observations. Do not use it where the task's Excel-only restriction prohibits automation.

Never substitute fabricated, guessed, or economy-wide proxy data for required WEO or commodity-level SUT observations. If official files cannot be obtained in the runtime, report that prerequisite failure rather than claim completion.

## Required source inputs

Before editing, acquire and verify:

1. The applicable WEO release for the requested economy, including annual real GDP level, real GDP growth, and GDP-deflator level through the task's final WEO year.
2. The latest qualifying official supply-use workbook, containing substantive `SUPPLY` and `USE` tables with the task-required classification and dimensions.
3. A label-verified mapping of each project commodity to supply-table imports, total supply, and use-table project weight cells. Do not infer rows by their ordinal position.
4. The supplied target workbook path and the required output path.

Confirm source economy, units, price basis, release date, year headers, and table dimensions before importing data. Record sources in the workbook.

## Manual Excel procedure

### 1. Establish sheets and source tables

1. Open the target in Excel and inspect the `NA` layout, formulas, names, and formatting.
2. Add sheets named exactly `WEO_Data` and `SUT Calc` if they are absent.
3. Use Excel's **Move or Copy Sheet** command to copy the complete official source sheets into the target, named exactly `SUPPLY` and `USE`. Do not paste a hand-made excerpt. Verify each copied sheet has at least the required 38 rows and 38 columns and contains the full substantive source table.
4. Keep copied source values separate from formula-driven calculation sheets. Do not create external-workbook links.

### 2. Populate WEO_Data

Use a horizontal year axis that includes the last WEO year (explicitly 2027 when required) and continues through the requested final year (explicitly 2043 when required). Clearly label rows for:

- real GDP, constant prices;
- real GDP growth, percent;
- GDP deflator, index or ratio as identified by source metadata; and
- GDP-deflator growth, percent.

Paste WEO source observations as values only. For every year after the final WEO year, retain formulas:

```excel
real GDP growth[t] = final WEO real GDP growth
real GDP[t]        = real GDP[t-1] * (1 + real GDP growth[t] / 100)
deflator growth[t] = average of the most recent four valid deflator-growth observations
deflator[t]        = deflator[t-1] * (1 + deflator growth[t] / 100)
```

Calculate observed deflator growth from adjacent source deflator levels where it is not supplied. The four-year anchor must be an `AVERAGE(...)` formula over the four latest valid annual deflator-growth cells, not a typed rate. Include a visible WEO release/source note and observed-versus-extension boundary.

### 3. Populate SUT Calc

For each verified project commodity, enter formulas in `SUT Calc` columns C:H that link to the copied sheets. A typical auditable layout is:

- C: source imports, linked to `SUPPLY`;
- D: total supply, linked to `SUPPLY`;
- E: commodity import share, `=C/D`;
- F: project composition weight, linked to `USE`;
- G: weighted import share, `=E*F`; and
- H: a linked project/use reference or source check.

Use the task's source headings where they differ. Ensure project weights are comparable, non-negative, and cover the required project composition. Calculate the designated import-content output, such as `SUT Calc!C46`, with a formula such as:

```excel
=SUMPRODUCT(E8:E45,F8:F45)/SUM(F8:F45)
```

The exact range must cover the runtime-mapped commodities, not an assumed classification. The result must remain a proportion where downstream formulas use `1-import_content`.

### 4. Populate NA and scenarios

Use direct internal formulas or year-keyed lookups to link NA macro rows to `WEO_Data`; do not retype GDP or deflator values. Link baseline import content to `SUT Calc!C46`.

Fill the explicitly requested `NA!D30:D33` assumptions according to their visible labels. For the supplied task they must include the declared GEL/USD exchange rate and baseline demand multiplier as numeric inputs, and import content must remain linked to SUT Calc.

Make project timing formula-driven. For an eight-year bell-shaped allocation, calculate a normalized bell/gaussian (or another visibly rising-then-falling formula profile) over the task's active project years, zero outside the window, and verify shares sum to one. Calculate annual effects in formulas:

```excel
nominal local investment = total USD investment * exchange rate * allocation share
real investment          = nominal local investment / (GDP deflator / deflator index base)
domestic impulse         = real investment * (1 - import content)
GDP increment            = domestic impulse * demand multiplier
with-shock GDP           = baseline real GDP + GDP increment
```

Replicate the entire first scenario table twice below it, with visible labels for all three blocks. Scenario 2 changes only the stated demand multiplier. Scenario 3 changes only the stated import-content share. All common GDP, deflator, allocation, cost, exchange-rate, and duration inputs remain linked to the same cells.

## Optional reproducible builder

`scripts/build_demand_workbook.py` accepts JSON on stdin and emits JSON on stdout. It requires `openpyxl` and official input files already available locally. It does not download data.

Input schema:

```json
{
  "template_path": "/root/test_demand.xlsx",
  "output_path": "/root/test_demand.xlsx",
  "supply_use_workbook": "/root/official_sut.xlsx",
  "weo_source": "Official IMF WEO release and retrieval date",
  "sut_source_note": "Official statistical authority release and retrieval date",
  "weo": {
    "years": [2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027],
    "real_gdp": ["official numeric observations in the same order"],
    "real_growth": ["official numeric observations in the same order"],
    "gdp_deflator": ["official numeric observations in the same order"]
  },
  "sut_mapping": [
    {
      "label": "official commodity label",
      "imports_cell": "source SUPPLY cell",
      "total_supply_cell": "source SUPPLY cell",
      "project_weight_cell": "source USE cell",
      "use_check_cell": "optional source USE cell"
    }
  ],
  "project": {
    "exchange_rate": "task-declared numeric rate",
    "amount_usd": "task-declared numeric total",
    "start_year": "task-declared integer year",
    "duration": "task-declared integer duration",
    "baseline_multiplier": "task-declared numeric multiplier",
    "scenario2_multiplier": "task-declared numeric multiplier",
    "scenario3_import_share": "task-declared numeric proportion",
    "deflator_index_base": "100 for an index base of 100, or 1 for a ratio"
  }
}
```

`weo.years` must end at the final WEO year and contain at least five consecutive valid deflator observations. `sut_mapping` must contain at least 38 label-verified commodities for a 38-by-38 request. Values in WEO arrays must be source observations, not model outputs.

The helper copies complete `SUPPLY` and `USE` sheets, writes internal source links, creates formula-driven extensions through 2043 or the requested `end_year`, and saves the workbook. It marks the workbook for full recalculation on opening. Open and save the generated file in Excel or another compatible spreadsheet engine before delivery so cached formula values are current.

Example invocation, after preparing the official-source JSON file:

```text
python scripts/build_demand_workbook.py < official_inputs.json
```

## Validation and delivery

After Excel recalculation, run the structural validator:

```text
python scripts/validate_workbook.py <<'JSON'
{"workbook_path":"/root/test_demand.xlsx","required_last_year":2043}
JSON
```

The validator emits JSON with `ok`, failures, formula counts, and detected sheets. It checks structural requirements; it does not establish the authenticity of inputs, so source verification remains mandatory.

Before delivery, reopen the output workbook and verify:

- required sheets are named exactly `WEO_Data`, `SUT Calc`, `NA`, `SUPPLY`, and `USE`;
- `SUPPLY` and `USE` are substantive complete source copies;
- post-final-WEO GDP and deflator columns contain formulas through the requested horizon;
- SUT Calc C:H has internal links and `C46` is a formula-derived import-content share;
- NA contains formulas linked to both WEO_Data and SUT Calc;
- the three scenario blocks are visibly labelled and alternatives differ only in their declared assumption;
- allocation shares sum to one and active years form the required bell-shaped window;
- there are no formula-error literals, `#REF!`, or external workbook references; and
- the final saved path is exactly the requested output file.

## Observable failure handling

- **No access to official source data:** stop and report the missing prerequisite; do not fabricate WEO or SUT observations.
- **Source sheets not named or not dimensioned as required:** resolve this from official metadata before copy; do not create a partial substitute.
- **Commodity mapping ambiguous or incomplete:** obtain an authoritative mapping; do not select rows by guessed offsets.
- **WEO values lack the four latest deflator observations:** report the insufficiency rather than calculate an unsupported anchor.
- **No spreadsheet recalculation engine:** retain formulas but state that cached-value validation could not be completed.
- **Validator failure:** repair the workbook formulas/links and rerun validation before final delivery.
