---
name: demand-shock-excel-workbook
summary: Complete and validate a formula-driven Excel demand-side investment-shock workbook using verified local IMF WEO and official supply-use source files.
description: Use when an Excel template must receive WEO GDP/deflator data, copied SUPPLY and USE source sheets, a SUT-based import-content calculation, and comparable baseline/alternative demand scenarios. The Skill preserves source observations and formula dependencies rather than substituting guessed data.
---

# Demand-Shock Excel Workbook

## Preconditions

This task has two required source inputs in addition to the target workbook:

1. an official IMF WEO extract for the requested economy, with annual real GDP, real GDP growth, and GDP-deflator observations through the final WEO forecast year; and
2. the latest official national supply-use workbook containing substantive `SUPPLY` and `USE` sheets.

Verify economy, release, units, year headers, and the 38-by-38 source-table requirement before writing anything. The runtime may have no network access. In that case, obtain official files through the permitted Excel/browser workflow before attempting completion. Never fill source sheets with placeholders, fabricated values, or economy-wide import-ratio proxies.

The user requires Excel-only work. Therefore the **manual Excel procedure is the required procedure for this task**. The packaged Python builder is provided for reusable tasks that explicitly permit workbook automation; it is not a substitute for Excel where the task prohibits Python.

## Required final structure

The completed workbook must contain, with exactly these names:

- `WEO_Data` — identifiable real GDP, real GDP growth, GDP deflator, and deflator-growth series, including the final WEO year and the requested extension horizon;
- `SUPPLY` and `USE` — complete copied official source worksheets, each substantive and at least 38 rows by 38 columns;
- `SUT Calc` — columns C:H formula-linked to the two copied tables, with the import-content share calculated by a formula in `C46`; and
- `NA` — the existing model populated with linked macro data, assumptions in `D30:D33`, formulas for the demand shock, and three visibly labelled scenario blocks.

No formula may contain an external-workbook link such as `[source.xlsx]Sheet!A1`.

## Excel-only procedure

### 1. Copy and preserve sources

1. Open the supplied template and immediately save a working copy at the requested output path.
2. Use **Move or Copy Sheet** to copy the official `SUPPLY` and `USE` worksheets into the target workbook. Preserve their exact sheet names. If the source workbook is open, paste values within the same target workbook or break links only after confirming the copied cells retain their values; final formulas must not reference the source workbook externally.
3. Confirm each copied table has at least 38 rows, 38 columns, and substantive labels and values.
4. Add `WEO_Data` and `SUT Calc` only if absent. Keep the original `NA` sheet and its formatting.

### 2. Populate `WEO_Data`

Create a horizontal annual axis including the source years, 2027, and every year through 2043. Clearly label rows for real GDP, real GDP growth, GDP deflator, and GDP-deflator growth. Include a visible source/release note and mark where official observations end.

Paste official WEO observations as values. Do not overwrite them with projection formulas. For each year after 2027, use formulas equivalent to:

```excel
real GDP growth[t] = real GDP growth[2027]
real GDP[t]        = real GDP[t-1] * (1 + real GDP growth[t] / 100)
deflator anchor    = AVERAGE(last four valid annual deflator-growth cells)
deflator growth[t] = deflator anchor
deflator[t]        = deflator[t-1] * (1 + deflator growth[t] / 100)
```

Where source deflator growth is absent, calculate it from two adjacent source deflator levels:

```excel
=(current_deflator / prior_deflator - 1) * 100
```

The four-year anchor must remain an `AVERAGE(...)` formula, not a typed growth rate.

### 3. Build `SUT Calc`

Map commodities using source labels and the documented project composition; do not guess row positions from their ordinal number. For every mapped commodity, use formulas in columns C:H that reference the copied tables internally:

- C: imports from `SUPPLY`;
- D: total supply from `SUPPLY`;
- E: `=Crow/Drow` import share;
- F: project/use weight from `USE`;
- G: `=Erow*Frow`; and
- H: a `USE` source check or relevant use reference.

Keep at least the 38 mapped commodity rows necessary for the task. In `SUT Calc!C46`, calculate the project import-content share using a formula, for example:

```excel
=SUMPRODUCT(E8:E45,F8:F45)/SUM(F8:F45)
```

Adapt row boundaries only when the verified mapped range differs. The result must be a proportion, not a percentage-point number, because downstream formulas use `1-import_content_share`.

### 4. Populate `NA`

Use formulas to link macro rows, including the required Column C and Column J values, to `WEO_Data`; do not retype GDP or deflator figures. Fill the designated assumptions in `D30:D33` according to their labels:

- GEL per USD: `2.746`;
- project amount: `6.5` billion USD, in the model's stated units;
- import-content share: an internal formula linked to `='SUT Calc'!$C$46`;
- baseline demand multiplier: `0.8`.

Use the GDP deflator as the investment deflator, maintaining a visible conversion for its index base. For each year calculate with formulas:

```excel
nominal GEL investment = total USD investment * GEL per USD * allocation share
real investment        = nominal GEL investment / (GDP deflator / deflator base)
domestic impulse       = real investment * (1 - import content share)
GDP increment          = domestic impulse * demand multiplier
with-shock GDP         = baseline real GDP + GDP increment
```

Distribute the eight annual allocations from 2026 through 2033 in a bell shape: rising initially, peaking centrally, then declining. Shares outside that range are zero and active-year shares sum to one. Use a normalized worksheet formula, rather than entering calculated shares manually.

### 5. Add scenarios

Copy the first complete scenario table twice below it. Each block must be visibly titled, for example `Scenario 1`, `Scenario 2`, and `Scenario 3`.

- Scenario 1 is the baseline case with multiplier `0.8` and SUT-linked import content.
- Scenario 2 changes only the demand multiplier, to numeric value `1`.
- Scenario 3 changes only import-content share, to numeric value `0.5`.

All other scenario inputs must link to the same exchange rate, investment total, WEO rows, deflator, and allocation logic. Retain formulas in all calculated cells.

### 6. Recalculate and validate

Use Excel calculation mode Automatic, calculate the workbook, save it, close it, and reopen it. Check that there are no `#REF!`, `#DIV/0!`, `#VALUE!`, `#N/A`, or external workbook links. Confirm the allocation shares total one and that scenario changes reconcile to only the stated changed assumption.

If Python is allowed in a different task, run the packaged structural validator after saving:

```text
python scripts/validate_workbook.py <<'JSON'
{"workbook_path":"/root/test_demand.xlsx","required_last_year":2043}
JSON
```

## Optional reusable builder

`scripts/build_demand_workbook.py` reads JSON from stdin and emits JSON to stdout. It requires `openpyxl`, a local target workbook, a local official SUT workbook, source WEO observations supplied in the input, and a label-verified SUT mapping. It never downloads data and rejects incomplete, nonnumeric, or non-substantive sources.

Input schema:

```json
{
  "template_path": "path to target workbook",
  "output_path": "path to completed workbook",
  "sut_workbook_path": "path to official supply-use workbook",
  "weo_source_note": "official release and retrieval note",
  "sut_source_note": "official release and retrieval note",
  "weo": {
    "years": ["consecutive official annual years ending in 2027"],
    "real_gdp": ["one numeric official value per year"],
    "real_growth": ["one numeric official value per year"],
    "gdp_deflator": ["one numeric official value per year"]
  },
  "sut_mapping": [{
    "label": "verified commodity label",
    "imports_cell": "SUPPLY source cell",
    "total_supply_cell": "SUPPLY source cell",
    "weight_cell": "USE source cell",
    "check_cell": "optional USE source cell"
  }],
  "project": {
    "exchange_rate": 2.746,
    "amount_usd": "numeric amount in workbook units",
    "start_year": 2026,
    "duration": 8,
    "baseline_multiplier": 0.8,
    "scenario2_multiplier": 1,
    "scenario3_import_share": 0.5,
    "deflator_base": "numeric index base"
  },
  "end_year": 2043
}
```

The mapping must contain at least 38 verified commodities. The builder writes formulas but does not evaluate them; recalculate the file in Excel before delivery.

## Failure handling

- If official files cannot be accessed, report the unavailable source prerequisite rather than inventing observations or source tables.
- If the official SUT does not have the required sheets/dimensions, do not construct a fake substitute; obtain the correct release.
- If commodity composition cannot be mapped unambiguously, retain the source and resolve the mapping before calculating `C46`.
- If no calculation engine is available, keep formulas but do not claim cached values have been checked.
- If validation identifies broken formulas, links, missing sheets, or blank assumptions, repair them in the workbook before delivery.
