# Formula reference (portable, engine-safe)

All derived cells are Excel formulas. Replace the bracketed column letters and
row numbers with the ones you discover by inspecting the target workbook at
runtime; nothing below is a fixed layout.

## STEP 1 — Gold price sheet

Let prices sit in column B starting at the first data row R0 (so B[R0] is the
first month). For a row r > R0:

- Monthly log return (×100 percentage, per the HINT):
  `=LN(B{r}/B{r-1})*100`
- 3-month rolling volatility (sample std-dev of the trailing 3 monthly log
  returns in column C):
  `=STDEV(C{r-2}:C{r})`
- 12-month rolling volatility:
  `=STDEV(C{r-11}:C{r})`

Use the workbook's actual columns if returns are not in C. `STDEV` is the sample
standard deviation (n-1) and recalculates in LibreOffice; `STDEV.S` is
equivalent if preferred.

### Answer STEP 1 (rows 3-6)
Reference the *latest* populated cells, e.g. for the last data row RL:
- latest monthly log return: `='Gold price'!C{RL}`
- latest 3-month volatility:  `='Gold price'!D{RL}`
- latest 12-month volatility: `='Gold price'!E{RL}`
- 3-month annualized: `=<3-month vol cell>*SQRT(12)`
Confirm, from the Answer labels, which of the four blanks is which before
writing; the annualization factor is √12 unless a label states otherwise.

## STEP 2 — values and exposure

- Jan–Sep 2025 average gold price (proxy for 2025 annual):
  `=AVERAGE('Gold price'!B{jan2025}:B{sep2025})`
- Value for a country present in the `Value` sheet (two-key lookup by country
  and the 2025 column):
  `=INDEX('Value'!<value range>, MATCH(<country cell>, 'Value'!<country range>, 0),
          MATCH(2025, 'Value'!<year header range>, 0))`
- Value for a `Volume`-only country (convert volume to value):
  `=<2025 volume cell or lookup> * <Jan-Sep avg price cell>`
- Gold price exposure (row 13): follow the Answer label; it is a near-term
  valuation swing on the gold value, so it typically multiplies the value by a
  volatility (and any horizon factor) the label names.

## STEP 3 — Reserves at Risk

- Pull 2025 total reserves with a portable two-key lookup (prefer INDEX+MATCH;
  avoid XLOOKUP for LibreOffice recalc):
  `=INDEX('Total Reserves'!<value range>,
          MATCH(<country cell>, 'Total Reserves'!<country range>, 0),
          MATCH(2025, 'Total Reserves'!<year header range>, 0))`
  If the match may be absent, guard with
  `=IFERROR(INDEX(...MATCH(...)...), "")` and drop empty-result countries.
- RaR (row 24): quantile risk = exposure × volatility × z. Store z (the
  confidence multiplier) in one cell at its documented precision and reference
  it. If RaR is expressed relative to the total-reserve base, divide by the row
  23 total-reserves cell. Read the Answer labels to confirm whether RaR is a
  level or a ratio and which volatility feeds it.

## Portability note
LibreOffice headless (used for recalculation) may raise `#NAME?` on `XLOOKUP`.
If verification reports that error, rewrite the lookup as INDEX+MATCH and
recalculate again. Keep units consistent (percentage vs decimal volatility;
currency and scale of values and reserves) across every formula.
