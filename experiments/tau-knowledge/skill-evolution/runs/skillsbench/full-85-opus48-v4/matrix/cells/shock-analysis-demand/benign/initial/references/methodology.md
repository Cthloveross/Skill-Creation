# Demand-side shock methodology (reference)

This reference restates the frozen background so the executor can map it to the
live workbook. It contains no instance answers, coordinates, or data values.

## Accounting identities

- Real GDP level: `real_gdp[t] = real_gdp[t-1] * (1 + real_growth[t])`.
- GDP deflator: `deflator[t] = deflator[t-1] * (1 + inflation[t])`.
- Nominal GDP: `nominal_gdp[t] = real_gdp[t] * deflator[t]`.
- Keep decimal vs percentage explicit; compound growth rates period by period.
- When extending an official series, keep observed values as sources and start
  projection formulas only after the last observed period. Record the boundary.

## WEO extension conventions

- Hold the final-forecast-year real GDP growth constant to the horizon (the
  instance holds the 2027 rate through 2043) via a formula referencing the
  anchor cell.
- Extend the GDP deflator with a fixed anchor equal to the average deflator
  growth over the most recent 4 observed years, then compound forward.

## From spending to GDP increment

- First-round domestic impulse removes imported content:
  `domestic_impulse = project_spending * (1 - import_content_share)`.
- Contemporaneous increment with a multiplier:
  `gdp_increment[t] = allocated_spending[t] * (1 - import_content_share) * multiplier[t]`.
- Import content for a single-industry project is estimated from the Supply-and-
  Use / input-output table using that industry's commodity composition, not an
  economy-wide imports ratio. Identify rows/columns from labels and metadata.
- Nominal project spending is converted to local currency with the given
  exchange rate; deflate to real terms using the GDP deflator before combining
  with real quantities, keeping units dimensionally consistent.

## Allocation profile

- Shares across the project years must sum to one.
- A symmetric bell profile (ramp-up, peak, ramp-down) is a valid explicit
  modelling choice; declare its parameters. One auditable formula-based option
  is a discretised normal density `NORM.DIST(i, mu, sigma, FALSE)` with
  `mu=(n+1)/2`, a stated `sigma`, normalised by the sum of densities.

## Scenario discipline

- Alternative scenarios differ only in a single declared assumption so each
  change is auditable (e.g. multiplier = 1; import content share = 0.5). All
  other logic references the same baseline formulas.

## Workbook construction and validation

1. Inventory sheets, headers, existing formulas; locate regions from labels.
2. Preserve source-table sheet names when linking formulas to them.
3. Write assumptions as inputs and projected values as formulas.
4. Keep units and absolute/relative references consistent.
5. Recalculate with a compatible spreadsheet engine; cached values go stale.
6. Reopen and inspect for formula errors and broken references.

Minimum checks: shares sum to one; observed source values unchanged; projection
formulas start after the last observation; import content in a meaningful range
and traceable; scenario deltas reconcile to their assumptions; real/nominal
conversions dimensionally consistent; no spreadsheet error values.

Public methodological background: OECD Supply and Use Tables describe supply
origins, imports, intermediate consumption and final demand without prescribing
any workbook layout.
