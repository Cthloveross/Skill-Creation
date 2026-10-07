---
name: demand-side-investment-shock-workbook
description: >-
  Populate and extend a supplied Excel workbook that estimates a multi-year
  investment/spending shock to a small open economy using the demand-side
  (macro accounting) framework. Use when a task gives an .xlsx template with
  sheets such as WEO_Data, a supply-and-use calculation sheet, and a national
  accounts (NA) sheet, and asks you to fill IMF WEO data, derive an import
  content share from a supply-and-use table, build a bell-shaped multi-year
  allocation, apply a demand multiplier, and replicate the table for alternate
  scenarios -- keeping every computed cell as an Excel FORMULA (no hardcoded
  results). The Skill discovers the workbook's real sheet/cell layout at
  runtime; it does not carry any instance's coordinates or answer values.
---

# Demand-side investment-shock workbook

## When to use

Use this Skill for an Excel-only demand-side shock task: a template workbook is
supplied, you collect public macro data (IMF WEO, a national statistics office
supply-and-use table), write source observations as values and all projected /
derived cells as Excel formulas, and build several scenarios that differ only in
declared assumptions. The current task's own instruction text is normative
(investment amount, horizon, exchange rate, multiplier, scenario changes,
output filename). This Skill supplies the method and reusable tooling, not the
numbers.

## Hard constraints (read first)

- **Excel only / formulas only.** Every cell that must be *calculated* has to
  contain an Excel formula, not a literal result. Only genuine source
  observations (raw WEO numbers, raw SUT table numbers) and declared
  assumptions (exchange rate, multiplier, import share override, bell
  parameters) may be literals. The helper `scripts/write_cells.py` writes
  formulas as strings beginning with `=`; use it so computation stays in the
  spreadsheet engine, never precomputed in Python.
- **Do not hardcode coordinates from this document.** Discover the actual
  sheet names, label positions, year headers, and destination ranges with
  `scripts/inspect_workbook.py` before writing anything.
- **Preserve the template.** Keep original sheet names (including copied
  source-table sheets), existing layout, styles, and existing formula flow.
  Only fill the regions the task names.
- **Output goes to the task's named workbook** (e.g. `test_demand.xlsx` in the
  workdir). The final file must contain the formulas *and* fresh cached values
  (recalculated), with no spreadsheet errors.

## Workflow

### 0. Inspect the supplied workbook
```
echo '{"path":"/root/test_demand.xlsx"}' | python3 scripts/inspect_workbook.py
```
This prints every sheet, its dimensions, defined names, and all non-empty cells
(coordinate + formula/value). Read it to build a label→coordinate map for:
- the WEO data sheet (which rows hold real GDP, real GDP growth, GDP deflator,
  nominal GDP; which columns are which years; where the last *observed* year
  ends);
- the supply-and-use calculation sheet (what columns C–H and cell C46 mean from
  their row labels, and which source cells feed them);
- the national-accounts sheet (where to link WEO data, where assumptions go
  such as D30–D33, and the shape of the main results table to be replicated).

Do the mapping from **labels**, not from the examples in this file.

### 1. IMF WEO data (sheet named by the task, e.g. WEO_Data)
1. Identify from the sheet's row labels which WEO series are required (typical
   candidates: real GDP level in national currency, real GDP growth %, GDP
   deflator index, nominal GDP). Confirm the country identifier (e.g. Georgia),
   variable definitions, units, and year coverage before writing — see
   `references/methodology.md`.
2. Internet is allowed: fetch the matching series from the current IMF WEO
   release. Enter each *observed* year as a literal value in its labelled
   cell/row. Record where observed data ends.
3. **Projection formulas (start only after the last observed year):**
   - Real GDP: hold the task-specified growth year constant to the horizon.
     `=prev_real_cell*(1+ $growth_cell/100)` where `$growth_cell` is the
     referenced growth rate (as a percent). (Task here: hold the 2027 real GDP
     growth rate unchanged through 2043.)
   - GDP deflator: anchor its growth to the average of the recent 4 observed
     year-over-year deflator growth rates, then compound:
     `=prev_deflator_cell*(1+ $anchor_cell)` where `$anchor_cell =
     AVERAGE(last 4 observed deflator YoY growths)`.
   - Nominal GDP: derive from real GDP and the deflator consistently with the
     workbook's base-year convention. Verify the scale with an observed year:
     for an index with base 100, `nominal ≈ real*deflator/100`. Pick the scale
     that reproduces an observed nominal value, then use the same formula for
     all years.

### 2. Supply-and-use table → import content share
1. Obtain the latest supply-and-use table from the national statistics office
   (Geostat for Georgia). Copy the required SUPPLY and USE sheets into the
   workbook **keeping their original sheet names** (openpyxl: load both
   workbooks, copy cell values/formulas into new sheets of the target with the
   same titles; or append via a spreadsheet engine). Verify they are not
   renamed.
2. On the SUT calculation sheet, link columns C–E to the relevant SUPPLY/USE
   cells with formulas (e.g. `='USE'!<cell>`), and build the derived columns
   (C–H per the task) as formulas.
3. Compute the import content share in the designated cell (C46 here) as a
   formula. The share is imported inputs relative to total inputs for the
   project's industry/commodity composition, e.g.
   `=imports_sum/(imports_sum+domestic_sum)` or `=imports/total_supply`,
   matching the sheet's row semantics. Confirm the result lies in a sensible
   range (0–1) and that its derivation is traceable to the linked SUT cells.

### 3. National-accounts table (sheet named by the task, e.g. NA)
1. Link columns C and J (and any other linking columns the labels indicate)
   from the WEO sheet with formulas.
2. Fill the assumption cells (D30–D33 here) as declared inputs/formulas:
   - exchange rate = the task's fixed Lari/USD value (2.746 here);
   - demand multiplier = the task's small-open-economy value (0.8 here);
   - import content share = reference to the SUT share cell (link, don't
     retype);
   - allocation profile = bell-shaped (see below).
3. **Investment to domestic demand (formulas):**
   - Total investment in national currency = USD amount × exchange rate
     (watch workbook units — millions vs billions of Lari; verify via
     inspection).
   - **Bell-shaped allocation over the horizon** (8 years from 2026 here) whose
     shares sum to one, built with formulas so nothing is hardcoded. A clean
     formula profile: per period index `i`, weight
     `=EXP(-((i-mu)^2)/(2*sigma^2))` with `mu` = midpoint of the horizon and
     `sigma` a declared input; share `=weight_i/SUM(weight_range)`. By
     construction the shares sum to 1. Document `mu`/`sigma` as explicit
     modelling choices.
   - Allocated spending per year = total investment × share.
   - Deflate the (nominal) allocated investment with the GDP deflator (task
     hint) to real terms: `=allocated/(deflator/base)`.
   - First-round domestic impulse / GDP increment per year:
     `gdp_increment = allocated_real * (1 - import_content_share) *
     multiplier`, applied contemporaneously. Add to the baseline path and
     report uplift in level and as % of baseline GDP as the table requires.

### 4. Scenarios (replicate the table below the first)
Copy the first table's structure into the regions below it and change **only**
the one declared assumption per scenario, keeping all other formulas identical
and still formula-driven:
- Scenario 2: demand multiplier = 1.
- Scenario 3: import content share = 0.5.
Each scenario's deltas must reconcile to its spending, import, timing, and
multiplier assumptions.

### 5. Recalculate and validate
1. Write cells:
```
echo '{"path":"/root/test_demand.xlsx","out":"/root/test_demand.xlsx","cells":[...]}' | python3 scripts/write_cells.py
```
   Each cell is `{"sheet":"NA","cell":"D30","formula":"=..."}` (computed) or
   `{"sheet":"WEO_Data","cell":"E5","value":123.4}` (raw observation /
   declared constant only).
2. Recalculate with the spreadsheet engine so formulas carry fresh cached
   values (openpyxl does not evaluate formulas):
```
echo '{"path":"/root/test_demand.xlsx","outdir":"/tmp/recalc"}' | python3 scripts/recalc.py
```
   Then copy the recalculated file back over the deliverable (it keeps formulas
   plus cached values). Confirm `ok=true`.
3. Validate:
```
echo '{"path":"/root/test_demand.xlsx","share_ranges":[{"sheet":"NA","range":"<bell share range>","expected":1.0}],"probes":[...]}' | python3 scripts/validate_workbook.py
```
   Confirm: bell shares sum to 1; required cells hold formulas (not literals);
   no cells contain `#REF!/#DIV/0!/#VALUE!/#NAME?/#N/A/#NUM!`; observed source
   values unchanged; projection formulas begin after the last observation;
   import share in (0,1); scenario deltas respond to their changed assumption.

## Failure handling
- If internet or a source series is unavailable, stop and report which series
  could not be fetched rather than inventing numbers.
- If `libreoffice`/`soffice` is absent, `recalc.py` reports it; try the
  available engine or document that cached values could not be refreshed.
- If inspection cannot resolve a required label uniquely, report the ambiguity;
  never guess a coordinate.
- Treat a missing/duplicate lookup match or any spreadsheet error value as a
  validation failure to fix, not to ignore.

See `references/methodology.md` for the full accounting identities, unit checks,
and the bell-profile derivation.
