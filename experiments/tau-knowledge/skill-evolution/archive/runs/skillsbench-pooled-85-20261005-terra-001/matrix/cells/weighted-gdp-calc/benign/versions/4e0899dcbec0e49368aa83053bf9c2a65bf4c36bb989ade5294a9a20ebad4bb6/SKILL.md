---
name: gcc-gdp-weighted-net-exports
version: 1.1.0
description: Populate an existing Task/Data XLSX trade template with two-key lookup formulas, net exports as percent of GDP, descriptive statistics, and GCC GDP-weighted means without changing workbook layout or formatting.
---

# GCC GDP-weighted net-exports workbook

Use this Skill for the supplied `gdp.xlsx`-style workbook containing existing `Task` and `Data` sheets. It writes formulas only in the requested Task-sheet output areas and preserves the workbook's existing sheet structure, formatting, and source data.

## Method

1. Inspect the runtime workbook to identify the source-code column in `Data!21:40` from the Task series keys, rather than assuming source-row order.
2. Identify the relevant Data period-header row and, for every output column, its matching nonblank Task header/key cell. This supports templates whose visible period keys are in a merged or nearby header layout rather than assuming every `Task!H10:L10` cell contains a value.
3. Fill `H12:L17`, `H19:L24`, and `H26:L31` with `INDEX`/`MATCH` formulas using the row's Task series key and the applicable local Task period-header key.
4. Fill `H35:L40` with aligned row formulas: each output country uses exports from rows `12:17`, imports from `19:24`, and GDP from `26:31` at the same relative country row. Values are calculated in percentage points as `(exports-imports)/GDP*100`.
5. Find the labeled statistic rows and write `MIN`, `MAX`, `MEDIAN`, `AVERAGE`, `PERCENTILE.INC` at 0.25 and 0.75, and a `SUMPRODUCT` GDP-weighted mean for every period. All statistics use the same six-country period column.

The writer rejects missing, duplicate, or type-incompatible lookup keys instead of substituting a nearby row or hard-coded value.

## Preconditions

- Python has `openpyxl` available.
- The input is an `.xlsx` workbook with sheets named exactly `Task` and `Data`.
- Task series identifiers are present in `D12:D17`, `D19:D24`, and `D26:D31`.
- `Data` rows 21:40 contain one unique source match for each required series identifier.
- For each Task output column H:L, a nonblank period/header key in that same column, in rows 1:11, exactly matches one period in one Data header row above row 21.
- Unique labels below the country results identify minimum, maximum, median, simple/arithmetic mean, 25th percentile (or first quartile), 75th percentile (or third quartile), and weighted mean.

## Run

Scripts accept one JSON object on stdin and emit one JSON object on stdout.

```json
{"input_path":"/root/gdp.xlsx","output_path":"/root/gdp.xlsx"}
```

Run `scripts/fill_gcc_trade.py`. `output_path` is optional and defaults to `input_path`.

The result reports inferred source metadata, Task header references used by the formulas, and written formula counts. `openpyxl` writes formulas but does not calculate Excel cached values; the script requests full automatic recalculation when the file is opened in a compatible spreadsheet engine.

## Validate

```json
{"workbook_path":"/root/gdp.xlsx"}
```

Run `scripts/validate_gcc_trade.py` after writing. It structurally checks required sheets, all requested two-key lookup formulas, aligned net-export inputs, six-country descriptive-statistic ranges, and aligned `SUMPRODUCT`/GDP weighted-mean formulas. It does not claim to evaluate formula results.

## Integrity and failure handling

Do not add sheets, macros, VBA, values copied from source rows, or unrelated formatting changes. Do not alter `Data` merely to conform to an assumed layout. If schema discovery fails, inspect the workbook's actual labels, merged cells, source identifiers, and period headers; resolve an authorized source/template issue and rerun rather than guessing.
