# Reusable method notes

## Two-key lookup
`INDEX(value_matrix, MATCH(code, code_column, 0), MATCH(year, year_header_row, 0))`
- `value_matrix`, `code_column`, and `year_header_row` must be aligned: the
  matrix rows start at the same row as `code_column`, and matrix columns start at
  the same column as `year_header_row`.
- Use absolute column + relative row for the code key (`$D12`) and absolute row
  for the year key (`H$10`) so copied formulas stay correct.
- Every requested code/year must match exactly once; a missing or duplicate match
  is a failure, not a nearest-row guess.
- Equivalent forms allowed by the task: `VLOOKUP&MATCH`, `HLOOKUP&MATCH`,
  `XLOOKUP&MATCH`.

## Net exports as percent of GDP
`(exports - imports) / GDP * 100`
- Keep source series in the same units; multiply by 100 for percentage points.
- Identify which source block is exports / imports / GDP from labels, not from
  magnitude.

## Descriptive statistics (per year, across the countries)
- min = `MIN(range)`, max = `MAX(range)`, median = `MEDIAN(range)`,
  simple mean = `AVERAGE(range)`.
- 25th / 75th percentile = `PERCENTILE.INC(range, 0.25|0.75)` (inclusive variant).
  Use the exclusive variant only if the workbook/instruction says so.
- Keep the observation set identical across the related statistics.

## GDP-weighted mean (per year)
`SUMPRODUCT(netexports_column, gdp_column) / SUM(gdp_column)`
- The two SUMPRODUCT ranges must cover matching countries in matching order.
- Weight sum must be positive.

## Formula / workbook integrity
- Preserve formulas rather than writing literals; preserve styles, colors, fonts,
  merged ranges, and layout; add no sheets/macros.
- `openpyxl` writes formulas but does not compute them. Recalculate with a
  compatible engine (headless LibreOffice, recalc-on-load forced) so cached
  values are fresh, then reopen to confirm no `#DIV/0!`, `#N/A`, `#REF!`, etc.
- After recalc, confirm the saved workbook reopens cleanly with its original
  layout intact; if the engine altered formatting, prefer the formulas-only file.
