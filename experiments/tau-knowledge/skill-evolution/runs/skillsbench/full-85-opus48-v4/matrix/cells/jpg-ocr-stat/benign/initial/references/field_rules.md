# Field extraction rules

## Output schema (strict, line-by-line graded)
- Single sheet named exactly `results`.
- Row 1 header, exactly: `filename`, `date`, `total_amount`.
- One data row per discovered image, ordered ascending by filename string.
- No extra columns, rows, summary cells, or sheets.

## filename
- Base name of the image file, e.g. `007.jpg`.

## date
- ISO `YYYY-MM-DD`.
- Supported inputs: numeric `D/M/Y`, `D-M-Y`, `D.M.Y`, `Y-M-D`, `Y/M/D`, and
  month-name forms like `01 Jan 2018`, `Jan 01, 2018`.
- Two-digit year -> 2000 + yy.
- Ambiguous day/month: a component > 12 is the day; otherwise assume day-first.
- Invalid (month not 1-12, day not valid for month) -> reject; try next match.
- If no valid date -> null (empty cell).

## total_amount
- String with exactly two decimals, e.g. `47.70`, `1234.56` (commas stripped).
- Keyword priority tiers, most specific first:
  1. `GRAND TOTAL`
  2. `TOTAL RM`, `TOTAL: RM`
  3. `TOTAL AMOUNT`
  4. `TOTAL`, `AMOUNT`, `TOTAL DUE`, `AMOUNT DUE`, `BALANCE DUE`,
     `NETT TOTAL`, `NET TOTAL`
- Exclusion keywords (skip the whole line): `SUBTOTAL`, `SUB TOTAL`, `TAX`,
  `GST`, `SST`, `DISCOUNT`, `CHANGE`, `CASH TENDERED`.
- Amount is read from the matching line. If the matching line has no number,
  fall back to the last number on the next line.
- Grouping separators like `1,234.56` are allowed; strip commas before parsing.
- Prefer a token with a decimal point over a bare integer on the same line.
- Within a tier, if several matching lines yield amounts, use the last one
  (totals usually appear low on the receipt). Higher-priority tiers win over
  lower ones.
- If nothing matches -> null (empty cell).
