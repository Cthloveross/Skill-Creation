---
name: demand-side-investment-shock-excel
description: >-
  Build a formula-driven, demand-side macroeconomic scenario in an existing
  Excel workbook that estimates the GDP impact of a multi-year investment
  spending shock on a small open economy. Use when the task supplies a workbook
  (e.g. test_demand.xlsx) with WEO_Data / SUT Calc / NA style sheets and asks
  you to populate IMF WEO data, copy a national Supply-and-Use table, derive an
  import-content share, allocate a fixed investment over several years with a
  bell-shaped profile, apply a demand multiplier, and replicate the table into
  alternative scenarios. The workbook's own labels, coordinates and years are
  the only source of truth; this Skill discovers them at runtime and never
  hardcodes answers.
---

# Demand-side investment spending shock (Excel, formula-driven)

## When to use

The public task gives you a workbook and asks you to turn an investment/spending
shock into an auditable macro scenario *inside Excel formulas only* (no Python
numbers written into cells that must be calculated). You collect data from the
IMF WEO database and the national statistics office, populate the supplied
sheets, and build baseline plus alternative scenarios that differ only in a
single declared assumption.

The current instance (read `/bundle/public_inputs.json` for exact wording) is
Georgia, 6.5 billion USD invested over 8 years starting 2026, Lari/USD = 2.746,
demand multiplier 0.8, bell-shaped allocation, with Scenario 2 (multiplier = 1)
and Scenario 3 (import content share = 0.5). **Read these numbers from the live
task, not from this document** — they can change between instances.

## Core method (frozen background)

Separate real levels, the deflator and growth rates and compound them:

```
real_gdp[t]    = real_gdp[t-1]    * (1 + real_growth[t])
deflator[t]    = deflator[t-1]    * (1 + inflation[t])
nominal_gdp[t] = real_gdp[t] * deflator[t]
```

Convert project spending into domestic demand and then into a GDP increment:

```
domestic_impulse[t] = allocated_spending[t] * (1 - import_content_share)
gdp_increment[t]    = allocated_spending[t] * (1 - import_content_share) * multiplier[t]
```

Import content for a single-industry project comes from the Supply-and-Use /
input-output table (imported intermediate inputs for that industry's commodity
composition), **not** an economy-wide imports ratio. Allocate a multi-period
project with a documented profile whose shares sum to one; a symmetric
bell-shaped profile models ramp-up, peak and ramp-down. Alternative scenarios
must differ only in one declared assumption so every change is traceable.

## Mandatory first step: discover the workbook

Never assume sheet names, row numbers or columns. Run the inspector first:

```
echo '{"path":"/root/test_demand.xlsx"}' | python3 scripts/inspect_workbook.py
```

It returns every non-empty cell per sheet with its formula, literal value and
cached value. Use it to locate, from labels (not coordinates copied from here):

- in `WEO_Data`: the rows for *real GDP growth (constant prices, % change)* and
  the *GDP deflator*, which columns are years, and the last observed/forecast
  year;
- in `SUT Calc`: the destination blocks for columns C–E (links to the Supply /
  Use sheets), columns C–H (the computation) and the import-content-share cell
  (`C46` in the current instance);
- in `NA`: which columns link to `WEO_Data` (columns C and J currently), the
  assumption input cells (`D30:D33` currently) and the projection table body;
- the blank region below the first table where Scenarios 2 and 3 go.

## Data acquisition (internet is allowed at runtime)

1. **IMF WEO** for the target economy: download the current release and read the
   real GDP growth (percent change, constant prices) and the GDP deflator
   series. Verify the country, units and which years are historical vs
   projected before writing. Populate the observed/forecast WEO values into the
   matching `WEO_Data` cells.
2. **National statistics office Supply-and-Use table** (Geostat for Georgia):
   download the latest workbook, then copy its SUPPLY and USE sheets into the
   target workbook **keeping their original sheet names** with:

   ```
   echo '{"source":"/root/sut_source.xlsx","target":"/root/test_demand.xlsx",
          "sheets":[{"src_name":"Supply"},{"src_name":"Use"}]}' \
     | python3 scripts/copy_sheets.py
   ```

   (Replace the real source path and the actual sheet names you see; if the
   source sheets contain formulas, recalc the source first so cached values
   copy.)

Do not invent values if a source is unreachable — report the failure explicitly
rather than fabricating data.

## Writing the model as formulas

Write **formula strings** (and only declared assumption literals) with the
helper, so every calculated cell stays an Excel formula:

```
echo '{"path":"/root/test_demand.xlsx","writes":[
  {"sheet":"NA","coord":"D30","value":2.746},
  {"sheet":"NA","coord":"D31","value":0.8},
  {"sheet":"NA","coord":"C5","formula":"=WEO_Data!D7"}
]}' | python3 scripts/write_cells.py
```

Use `"value"` only for genuine assumption inputs (exchange rate, multiplier,
import-share override, horizon). Use `"formula"` for everything that must be
calculated. Guidance for each block (map to the coordinates you discovered):

### WEO_Data
- Observed/forecast cells: the actual WEO numbers (these are source data).
- Real GDP growth after the last forecast year up to the horizon: a formula
  referencing the chosen anchor year's growth cell (the instance holds the 2027
  rate constant through 2043), e.g. `=$F$7`.
- GDP deflator extension: first compute the average deflator growth over the
  most recent 4 observed years with a formula (e.g.
  `=AVERAGE(... /... -1 over 4 periods)` or an `AVERAGE` of year-on-year ratios),
  then extend `deflator[t] = deflator[t-1]*(1+avg)` as a formula referencing the
  anchor cell. Keep the observed deflator values unchanged; projection formulas
  start only after the last observation.
- Any remaining columns (nominal/real levels) follow the identities above.

### SUT Calc
- Columns C–E: `=Supply!...` / `=Use!...` links to the copied sheets (two-key
  lookup by label if orders differ).
- Columns C–H: the intermediate computation that isolates the relevant
  industry's imported intermediate inputs versus its total inputs/supply.
- Import-content-share cell (`C46`): a formula equal to imported inputs divided
  by total inputs for that industry, giving a share in a plausible 0–1 range.

### NA (baseline table)
- Link columns C and J from `WEO_Data` by formula.
- Assumption inputs: exchange rate, demand multiplier, and the import-content
  share (reference `SUT Calc!C46` rather than retyping it).
- Total investment and horizon: from the task (6.5e9 USD, 8 years from 2026).
- **Bell-shaped allocation**: build per-year weights with a formula and
  normalise so they sum to one. A defensible explicit choice is a discretised
  normal density: for year index i in 1..n, `weight_i = NORM.DIST(i, mu, sigma,
  FALSE)` with `mu=(n+1)/2` and a stated `sigma` (e.g. n/4), and
  `share_i = weight_i / SUM(weights)`. Document mu and sigma as inputs.
- Allocated spending[t] (Lari) `= total_USD * exchange_rate * share_t`.
- Deflate with the GDP deflator (hint in the task): real spending[t] =
  nominal spending[t] / (deflator_index[t]/deflator_base) using the same
  deflator rows you populated.
- GDP increment[t] `= allocated_spending[t] * (1 - import_content_share) *
  multiplier`, consistent with the sheet's level definitions, plus any uplift /
  share-of-GDP columns the table requests.

### Scenarios 2 and 3
Replicate the baseline table structure in the blank region below it. Each
scenario must reference the baseline's data and formulas and change exactly one
assumption: Scenario 2 sets the demand multiplier input to 1; Scenario 3 sets
the import-content-share input to 0.5. Point every other cell at the same WEO /
allocation logic so deltas reconcile only to the changed assumption.

## Recalculate and verify (do not trust cached values)

openpyxl writes formula strings but does not evaluate them. Recalculate with
LibreOffice headless, which rewrites cached values on load:

```
echo '{"path":"/root/test_demand.xlsx"}' | python3 scripts/recalc_workbook.py
```

Then validate. Supply the coordinates you discovered:

```
echo '{"path":"/root/test_demand.xlsx",
       "sum_checks":[{"sheet":"NA","range":"<allocation share range>","expected":1.0,"tol":1e-6}],
       "formula_cells":[{"sheet":"SUT Calc","coord":"C46"},
                         {"sheet":"NA","coord":"<a gdp increment cell>"}]}' \
  | python3 scripts/validate_demand.py
```

Confirm:
- allocation shares sum to one;
- observed WEO source values are unchanged and projection formulas start after
  the last observation;
- the import-content share is a formula in a meaningful 0–1 range and traceable
  to the SUT;
- calculated cells are formulas, not literals (`is_formula` true);
- `error_count` is 0 (no `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#N/A`);
- Scenario 2 differs from baseline only through the multiplier, Scenario 3 only
  through the import share (re-inspect their formulas to confirm).

If validation fails, fix the specific formula or link and re-run recalc +
validate; do not paper over a broken formula with a hardcoded number.

## Output

The deliverable is the saved, recalculated `test_demand.xlsx` at the task's
output path, with all required formulas intact across WEO_Data, the copied
Supply/Use sheets, SUT Calc, NA and the two additional scenario tables.

## Failure handling
- Missing LibreOffice: `recalc_workbook.py` reports `soffice not found`; install
  or locate it, because Excel-cached values would otherwise be stale.
- Unreachable data source: stop and report; never fabricate WEO or SUT numbers.
- Unexpected layout: re-run `inspect_workbook.py`; always drive coordinates from
  the live workbook.
