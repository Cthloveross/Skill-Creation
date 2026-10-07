---
name: gcc-gdp-weighted-net-exports
version: 1.0.0
description: Fill a two-key economic-data lookup table and calculate GCC net exports as a share of GDP, descriptive statistics, and GDP-weighted means in an existing Excel workbook without changing its layout or styles.
---

# GCC GDP-weighted net-exports workbook

Use this Skill when an existing `.xlsx` workbook has a `Task` sheet for formulas and a `Data` sheet containing series observations, and the requested result is net exports `(exports - imports) / GDP * 100` for six entities across periods, summary statistics, and a GDP-weighted mean.

The packaged script discovers the Data-series-code column and year-header row from the keys already present in the Task sheet. It writes only formulas into the declared yellow task areas and does not create sheets, styles, macros, VBA, or values calculated outside Excel.

## Runtime interface

`scripts/complete_workbook.py` reads one JSON object from standard input and emits a JSON report to standard output.

Input schema:

```json
{
  "input_path": "/root/gdp.xlsx",
  "output_path": "/root/gdp.xlsx"
}
```

- `input_path` must be an existing `.xlsx` workbook with sheets named `Task` and `Data`.
- `output_path` may equal `input_path` to update the provided workbook in place. If different, it is the saved result path.

Output schema:

```json
{
  "ok": true,
  "output_path": "/root/gdp.xlsx",
  "lookup_source": {"code_column": "D", "header_row": 10},
  "written": {"lookup": 90, "net_export": 30, "summary": 30, "weighted": 5}
}
```

On an unsupported workbook layout, missing/ambiguous source keys, unavailable requested statistic label, or invalid source period, it emits `{"ok": false, "error": "..."}` and exits nonzero rather than guessing a formula.

## Procedure

1. Run the script against the supplied workbook. For example:

   ```sh
   printf '%s' '{"input_path":"/root/gdp.xlsx","output_path":"/root/gdp.xlsx"}' | python3 scripts/complete_workbook.py
   ```

2. The script fills `H12:L17`, `H19:L24`, and `H26:L31` with `INDEX`/`MATCH` formulas. Each formula matches the row's series code in Task column D and the period in Task row 10 against the discovered source keys in `Data` rows 21:40.
3. It fills `H35:L40` with net-exports-as-percent-of-GDP formulas using the aligned export, import, and GDP blocks.
4. It locates the labeled rows for minimum, maximum, median, simple mean, 25th percentile, 75th percentile, and weighted mean on `Task`, then fills their period cells H:L. The weighted formula uses `SUMPRODUCT` on the net-export and same-period GDP ranges.
5. The workbook is saved and reopened in formula mode. The script verifies every target contains a formula and that no worksheet was added or removed. It requests full recalculation when the workbook is opened by a spreadsheet engine.

`openpyxl` writes formulas but does not calculate cached values. If the execution environment has a compatible spreadsheet engine, open/save the completed workbook there only to refresh formula caches; do not replace formulas with literals. The authoritative deliverable remains the saved workbook with its formulas intact.

## Formula assumptions and validation

- The three input blocks correspond in order to exports, imports, and nominal GDP, respectively.
- The six output rows map directly to the six rows in each input block.
- Source observations must be in `Data` rows 21 through 40, source series identifiers must uniquely resolve there, and each requested period must occur exactly once in the detected source header row.
- Statistics are calculated independently per period from that period's six net-export percentages. Percentiles use Excel's inclusive `PERCENTILE.INC` convention.
- The script preserves existing cells outside the formula destinations, including sheet names, formatting, colors, merged ranges, and formulas.
