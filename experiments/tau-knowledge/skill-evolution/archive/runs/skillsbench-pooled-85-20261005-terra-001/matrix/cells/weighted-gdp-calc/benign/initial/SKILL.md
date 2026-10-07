---
name: gcc-gdp-weighted-net-exports
version: 1.0.0
description: Fill the GCC trade/GDP lookup template in an existing XLSX workbook, calculate net exports as a percent of GDP, descriptive statistics, and GDP-weighted means while preserving the two-sheet workbook layout and formatting.
---

# GCC GDP-weighted net-exports workbook

Use this Skill when a workbook has existing `Task` and `Data` sheets and the task requests formulas for GCC exports, imports, GDP, net exports as a share of GDP, descriptive statistics, and a GDP-weighted mean.

The packaged script uses the task's declared target areas and source rows, but discovers the source series-code column and year-header row from the runtime workbook. It does not use row-order matching: each lookup is an `INDEX` plus two `MATCH` operations, one for the series code and one for the year.

## Preconditions

- Python has `openpyxl` available.
- The workbook is an `.xlsx` file with sheets named exactly `Task` and `Data`.
- `Task!D12:D17`, `D19:D24`, and `D26:D31` contain nonblank series codes.
- `Task!H10:L10` contains the requested period keys.
- `Data` rows 21 through 40 contain exactly one source match for each requested series code, and one header row above row 21 has exactly one native-type-compatible match for each requested period.
- Summary labels for minimum, maximum, median, simple/arithmetic mean, 25th percentile, 75th percentile, and weighted mean appear uniquely below row 40 on `Task`.

The script fails rather than guessing if those conditions are not met. In particular, it rejects a text-vs-number mismatch between matching period headers because an Excel `MATCH` formula would not reliably resolve it.

## Run

Scripts read one JSON object from standard input and write one JSON object to standard output.

```json
{"input_path":"/root/gdp.xlsx","output_path":"/root/gdp.xlsx"}
```

Run `scripts/fill_gcc_trade.py` with that object. `output_path` is optional and defaults to `input_path`; use a distinct output path if the task requires retaining the input file separately.

The script writes only formulas into existing cells on `Task`:

- `H12:L17`, `H19:L24`, and `H26:L31`: two-key `INDEX/MATCH` lookup formulas into `Data` rows 21:40.
- `H35:L40`: `(exports - imports) / GDP` formulas. If the pre-existing net-export cells have a percentage number format, the stored value remains a ratio; otherwise it is multiplied by 100 to produce percentage points. This keeps display units and all subsequent summaries consistent.
- The five year columns on the labeled descriptive-statistic rows: `MIN`, `MAX`, `MEDIAN`, `AVERAGE`, and `PERCENTILE.INC` formulas over the six net-export observations.
- The five year columns on the labeled weighted-mean row: `SUMPRODUCT(net-export range, GDP range) / SUM(GDP range)`.

The workbook's fills, fonts, dimensions, sheet names, and other unedited cell formatting are retained. The script does not add sheets, VBA, macros, or customizations. It sets workbook calculation properties to recalculate formulas when opened by a compatible spreadsheet engine; `openpyxl` itself does not calculate formula results.

## Validate

After saving, run `scripts/validate_gcc_trade.py`:

```json
{"workbook_path":"/root/gdp.xlsx"}
```

It checks the required sheets, confirms every target lookup formula is an `INDEX/MATCH` formula, verifies all net-export cells contain formulas, finds the seven required summary rows, and checks the weighted formulas use `SUMPRODUCT` and a positive-denominator `SUM` expression. This is structural validation, not calculation validation. If cached numeric results are required, open/save the completed workbook in a compatible spreadsheet engine and then rerun the validator; do not replace the requested formulas with literals.

## Failure handling

Do not manually substitute a neighboring source row or a hard-coded value after a source-key, year-key, label, or unit ambiguity failure. Inspect the workbook labels and source data, correct the schema issue if authorized, then rerun. A missing or duplicate source match means the requested two-key lookup cannot be established safely.
