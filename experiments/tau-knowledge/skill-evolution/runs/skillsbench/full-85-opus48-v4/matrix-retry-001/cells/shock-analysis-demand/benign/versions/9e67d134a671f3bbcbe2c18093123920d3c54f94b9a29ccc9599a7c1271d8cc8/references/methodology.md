# Demand-side investment-shock methodology (reusable)

General macro-accounting method. All values, coordinates, and series codes come
from the runtime workbook and the current task instruction, never from this
file.

## 1. Real / deflator / nominal

Track real GDP and the GDP deflator separately; nominal GDP is their product on
a consistent base.

```
real_gdp[t]  = real_gdp[t-1]  * (1 + real_growth[t])
deflator[t]  = deflator[t-1]  * (1 + inflation[t])
nominal_gdp  = real_gdp * deflator        # scaled to the index base
```

- Keep every observed value as a source literal; begin projection formulas only
  after the final observed period, and record that boundary.
- Decimal vs percent: a WEO growth rate stated in percent enters a compounding
  formula as `(1 + g/100)`.
- Projection rules for this task family:
  - real GDP: hold the task-specified growth-year rate constant to the horizon;
  - deflator: compound at an anchor = AVERAGE of the recent 4 observed
    deflator year-over-year growth rates;
  - nominal: use the base-year convention that reproduces an observed nominal
    value (for a base-100 index, `nominal = real*deflator/100`). Determine the
    scale from an observed year identity, then apply uniformly.

## 2. IMF WEO verification

Before writing, confirm from the sheet labels and the WEO release metadata: the
country/economy identifier, each variable's definition and unit, the national-
currency scale, and which years are historical vs projected. Distinguish a real
output level from a real growth rate; verify units before combining series.
Beyond the last WEO forecast year the standard convention is a constant growth
rate.

## 3. Import content share from a supply-and-use table

For a project concentrated in one industry, estimate import content from the
commodity composition of that industry in the supply-and-use (or input-output)
table, not an economy-wide imports ratio. Identify rows/columns from labels and
metadata.

```
import_content_share = imported_inputs / (imported_inputs + domestic_inputs)
```
(or imports / total supply, matching the sheet's row semantics). It must lie in
(0,1) and be traceable to the linked SUT cells. Copy the SUPPLY and USE source
sheets into the workbook with their original names; link, do not retype.

## 4. Spending -> domestic demand

```
total_investment_LC = usd_amount * exchange_rate      # watch workbook units
allocated[t]        = total_investment_LC * share[t]  # shares sum to 1
allocated_real[t]   = allocated[t] / (deflator[t]/base)
gdp_increment[t]    = allocated_real[t] * (1 - import_content_share) * multiplier[t]
```

Apply the multiplier contemporaneously (or via a declared lag). Avoid double
counting any project spending already in the baseline.

### Bell-shaped allocation (shares sum to one, formula-driven)

For horizon length N and period index i = 1..N:
```
weight_i = EXP(-((i - mu)^2) / (2 * sigma^2))      # mu = (N+1)/2 midpoint
share_i  = weight_i / SUM(weight_1..weight_N)       # sums to 1 by construction
```
`mu` and `sigma` are explicit modelling inputs. Keep them as workbook cells so
shares stay computed, not hardcoded. This produces ramp-up, peak, ramp-down.

## 5. Scenarios

Replicate the first table's structure; change ONLY the one declared assumption
per scenario (e.g. multiplier = 1; import content share = 0.5). All other
formulas identical. Scenario deltas must reconcile to their spending, import,
timing, and multiplier assumptions, so each change is auditable.

## 6. Validation checklist

- allocation shares sum to one;
- observed source values unchanged; projection formulas start after the last
  observation;
- import content share in a meaningful range with a traceable derivation;
- nominal/real/deflator conversions dimensionally consistent (scale confirmed
  on an observed year);
- required computed cells contain formulas, not literals;
- no `#REF!/#DIV/0!/#VALUE!/#NAME?/#N/A/#NUM!`;
- workbook recalculated so cached values match the formulas, original layout
  and source sheet names preserved.

## 7. Workbook integrity

Formula-writing libraries do not evaluate formulas. After writing, recalculate
with a spreadsheet engine (LibreOffice), reopen in cached-value mode, and reject
the artifact if required formula values are missing/stale or any identity
fails. This is an integrity check, not a reason to replace formulas with
hardcoded outputs.

Public background: OECD Supply and Use Tables describe supply origins, imports,
intermediate consumption, and final demand without prescribing any workbook
layout.
