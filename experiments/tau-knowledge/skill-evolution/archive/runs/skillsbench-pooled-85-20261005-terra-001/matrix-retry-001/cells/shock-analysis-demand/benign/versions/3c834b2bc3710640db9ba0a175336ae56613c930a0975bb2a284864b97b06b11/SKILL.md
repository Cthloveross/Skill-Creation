---
name: excel-demand-side-investment-shock
summary: Populate and complete an Excel-only demand-side macroeconomic investment-shock workbook using IMF WEO data and an official supply-use table, while preserving formula-driven calculations and the existing workbook layout.
description: Use when a supplied Excel template requires official macroeconomic data, supply-use-table-based import-content estimation, a multi-year investment allocation, and comparable demand-side scenarios. The skill discovers labels and ranges in the supplied workbook at runtime rather than relying on an assumed layout. It requires access to the mandated official data sources and a spreadsheet application capable of recalculating formulas.
---

# Excel Demand-Side Investment-Shock Workbook

## Operating constraints

- Use the spreadsheet application only for workbook inspection, data import/copying, formula entry, calculation, and saving. Do not use Python, external optimization/calculation code, or hardcoded numeric results in cells that are supposed to calculate.
- Retain the template's sheets, names, layout, styles, existing formulas, and source data. Do not replace calculation formulas with values.
- The task brief is the authority for scenario assumptions (amount, start year, duration, exchange rate, multipliers, and alternative import-content assumption). Enter declared assumptions as clearly labelled inputs; all downstream results must reference those inputs.
- Use the required official sources. Before starting, confirm that the execution environment can access the IMF WEO database and the specified national statistical authority. If source access is unavailable, stop and report that the required official data cannot be obtained under the environment constraints; do not fabricate, substitute, or reuse unverified data.
- Save the completed artifact to the exact requested output filename and path.

## Required runtime inputs

Read the task brief and supplied workbook to establish:

1. target economy, source-release requirement, model start year, project duration, and total investment amount/currency;
2. specified exchange rate, baseline multiplier, alternative-scenario multiplier, and alternative import-content share;
3. required workbook output path;
4. required template sheets (normally identified by visible names such as `WEO_Data`, `SUT Calc`, and `NA`); and
5. the required supply-use release, table classification, and source sheets (for example, a published 38-by-38 supply/use pair when explicitly required).

Do not assume locations within a sheet merely because another workbook used them. The task may explicitly name an input cell; otherwise find cells from nearby labels and existing formulas.

## 1. Inspect the template before editing

1. Open the workbook in Excel and list all worksheets, hidden sheets/rows/columns, named ranges, table objects, used regions, formulas, labels, number formats, and merged areas.
2. On the macro-data sheet, identify rows by their visible series labels, units, economy metadata, and year headers. Establish which rows are imported source observations and which cells are intended to be formulas.
3. On the supply-use calculation sheet, identify the commodity/industry labels, headings for domestic supply/imports/total supply or equivalent measures, the cells intended to link source-table values, and the target import-content-share output.
4. On the national-accounts/scenario sheet, map the first scenario's input block, year header row, source-link columns, annual calculation rows, and output rows. Identify the table boundaries needed to duplicate it for two additional scenarios.
5. Check all existing formulas that reference these regions. Preserve their intended formula flow and use their labels and references to resolve ambiguous mappings.

If a requested label, year, source series, or output region is absent or ambiguous, do not guess based on cell coordinates. Escalate the missing-template issue.

## 2. Obtain and populate IMF WEO data

### Select and verify the data

1. From the required/current IMF WEO release, select the target economy using its displayed economy identifier and verify the country name and release/version.
2. Select the exact WEO series required by the template labels. At minimum distinguish:
   - real GDP level in a documented constant-price national-currency scale;
   - real GDP growth rate (percent change); and
   - GDP deflator level or GDP-deflator inflation/growth, according to the template.
3. Verify the definition, unit, scale, year coverage, and actual-versus-projection status in WEO metadata before copying values. Do not mix a nominal GDP series with a real GDP series.
4. Align data to workbook columns by explicit year headers. If headers are text or dates, use their calendar-year meaning rather than position.

### Populate WEO_Data

1. Place WEO source observations only in the rows and year columns whose labels match each selected series. Preserve source observations as values with the documented source/release, and do not overwrite existing unrelated observations.
2. If required by the template, retain real GDP level and real-GDP-growth source rows separately. The level should be real/constant-price and use a consistent scale.
3. For years beyond the final WEO growth forecast through the requested horizon, enter formulas that carry forward the final forecast real-GDP growth rate. Each extended real-GDP level must compound from the preceding year's level:

   `current real GDP = prior real GDP * (1 + current real GDP growth / 100)`

   Use the final WEO forecast growth as an absolute reference or an equivalent named reference, so every post-forecast growth cell remains linked to the last WEO forecast. Do not type a copied calculated level.
4. Find the most recent four valid annual GDP-deflator-growth observations identified by the sheet/source labels. Exclude blanks, nonnumeric markers, and years not intended as the anchor. Calculate their arithmetic average in an input/anchor cell with an Excel formula such as `AVERAGE` over the verified four cells.
5. Extend GDP deflator growth beyond the available source horizon with formulas referencing that average anchor. Extend the deflator level through compounding:

   `current deflator = prior deflator * (1 + current deflator growth / 100)`

   If the sheet has only deflator levels, calculate annual growth from adjacent levels using formulas before calculating the four-year average. Follow the scale indicated in labels (index versus percent) and do not treat a percent as a decimal.
6. Where nominal GDP is required, calculate it from compatible real GDP and deflator measures using the workbook's unit convention. If the deflator is an index with base 100, apply the corresponding `/100` conversion; if it is already a ratio, do not divide again. Make the conversion visible in a formula or labelled assumption.

Add or retain a concise source note in an existing source/notes area if the template provides one: WEO release, series definition, download date, unit, and the observed/projected boundary.

## 3. Import the official supply and use tables and calculate import content

1. Download/open the latest qualifying supply-use-table release from the national statistical authority specified by the task. Verify the economy, table year, classification/version, dimensions, units, valuation, and whether it contains the mandated supply and use sheets.
2. Copy the complete required source worksheets into the target workbook using Excel's sheet-copy command. Keep their original sheet names unchanged, including any classification/dimension text. Do not recreate a partial source table by pasting selected values.
3. On `SUT Calc` (or the label-equivalent calculation sheet), fill its source-link columns using Excel formulas that reference the copied source sheets. Use label-based matches or references to the verified source cells; do not paste manually transcribed calculation values.
4. Determine the project-relevant commodity or construction/investment composition from the workbook's labels and the SUT classification. Estimate import content from the relevant commodity-level supply data, not from a whole-economy imports-to-GDP ratio.
5. For each included commodity, calculate an import share using the definition supported by the source headings, ordinarily imports divided by total supply or total available supply. Use formula guards only where the template permits them; a zero or missing denominator is a data-quality issue, not a reason to silently assign zero.
6. Complete columns C:H or their label-equivalent intended calculation fields with formulas linking source data, calculating shares, applying any documented project weights, and forming totals. Ensure the project weights cover the intended composition and sum to 100% (or 1, as labelled).
7. Calculate the designated import-content-share cell (for example, `C46` when the task explicitly specifies it) as a formula-driven weighted import share:

   `SUMPRODUCT(project composition weights, commodity import shares) / SUM(project composition weights)`

   Adjust the formula only for the workbook's displayed units. Keep the output as a proportion if downstream demand formulas subtract it from 1; do not convert it to a percent unless all dependent formulas expect percentages.
8. Validate that each source link points to the copied SUT sheets, weights and import shares are aligned by commodity labels, the denominator is positive, and the result lies in the meaningful range from 0 to 1 (or 0% to 100% if explicitly formatted as a percent).

## 4. Complete the baseline scenario in NA

### Source links and assumptions

1. Link the instructed NA source columns (such as columns C and J if explicitly named in the task) to the appropriate `WEO_Data` year/series cells. Use formulas, not duplicated values. Use year-keyed matching when rows/columns are not already directly aligned.
2. Populate the specified assumption cells (for example, the explicitly named D30:D33 block) with the task's declared inputs. Enter the exchange rate, project value, duration/start timing, import-content share link, and multiplier in the cells indicated by their labels. The baseline import-content assumption must link to the calculated SUT result rather than be retyped.
3. Use the task-provided exchange rate exactly as a labelled input. Convert USD project cost to local currency with a formula referencing both the USD amount and exchange-rate input.
4. Use the task-provided baseline demand multiplier exactly as a labelled input. Do not invent a supply-side capital-stock effect: this workbook is a demand-side analysis.

### Allocation and calculations

1. Allocate the total project spending over the specified consecutive project years using a clearly visible bell-shaped profile in the allocation row. The yearly allocation cells must be formulas/inputs that sum to exactly 100% (or 1). Set all years outside the specified project window to zero through formulas where the table covers them.
2. The profile must rise during ramp-up, have a central peak or plateau, and decline during ramp-down. Use a symmetric, formula-based profile where the template does not prescribe exact annual shares. Ensure the allocation duration exactly equals the task's project duration and the total annual nominal spending reconciles to the total project value in local currency.
3. Use GDP deflator values linked from `WEO_Data` as the investment deflator. Calculate real project investment as nominal allocated local-currency spending divided by the appropriate deflator scale. If the index base is 100, divide by `deflator/100`; if the sheet uses an index normalized to 1, divide directly by the index. Maintain a visible, consistent price basis.
4. Calculate the first-round domestic real-demand impulse using formulas:

   `real allocated investment * (1 - import content share)`

5. Calculate the total real GDP increment using formulas:

   `domestic real-demand impulse * demand multiplier`

   The multiplier is contemporaneous unless the template explicitly provides a lag structure. Do not double count the project amount in baseline GDP.
6. Calculate with-shock real GDP as baseline real GDP plus the real GDP increment. Calculate the nominal counterpart only through the appropriately aligned GDP deflator if the table calls for nominal GDP.
7. Fill the rest of the annual table by copying formulas with deliberate absolute/mixed references: absolute references for shared assumptions, relative references for the current year, and direct/lookup links for annual WEO series. Keep formulas throughout the calculation area.

## 5. Build scenarios 2 and 3

1. Copy/replicate the full first scenario table, including year headings, row labels, number formats, and formula architecture, into the two required table regions below it. Do not alter scenario 1 after copying.
2. Scenario 2 must differ from scenario 1 only in the demand multiplier. Link all common inputs to the same source assumptions/series, but set its multiplier input to the task-specified alternative multiplier.
3. Scenario 3 must differ from scenario 1 only in import content. Link all common inputs to the same source assumptions/series, but set its import-content input to the task-specified alternative import-content share.
4. Confirm that scenario formulas reference each scenario's own multiplier/import-content input while source GDP, deflator, project cost, exchange rate, allocation profile, dates, and baseline series remain consistently linked.

## 6. Recalculate and validate before delivery

Use Excel's full recalculation, then inspect the workbook after saving and reopening.

Required checks:

- WEO rows match the selected economy, series definitions, units, and explicit year keys.
- WEO sourced observations have not been overwritten; formulas begin only after the applicable last source observation.
- Extended real GDP compounds the final WEO growth rate annually, and extended deflator growth references the calculated four-year average anchor.
- The copied source SUT sheets are complete and retain their original names.
- All `SUT Calc` source data fields are links to the copied sheets; project weights sum to one/100%; calculated import content is traceable and in range.
- The project allocation has the required number of active years, is bell-shaped, sums to one/100%, and annual project amounts sum to the converted total investment.
- Investment deflation uses the GDP deflator in the correct index scale, and all monetary series combined in an equation use compatible price bases and currency units.
- For every scenario and year, `GDP increment = real spending * (1 - import share) * multiplier`; with-shock GDP equals baseline GDP plus that increment.
- Scenario 2 changes only the stated multiplier relative to scenario 1; scenario 3 changes only the stated import-content assumption relative to scenario 1.
- No target cell contains `#REF!`, `#VALUE!`, `#DIV/0!`, stale formula results, text masquerading as a number, or a pasted value where a formula is required.
- Formulas, source sheets, original formatting, and unrelated workbook content remain intact.

Save the final recalculated workbook under the required output filename (for the supplied task, `test_demand.xlsx`).

## Observable failure handling

- **No network/source access:** report the prerequisite failure and do not create invented source data.
- **Source release lacks the required SUT tabs/classification:** report the mismatch; do not use an economy-wide proxy without explicit authorization.
- **Ambiguous template mapping or absent labels:** preserve the workbook and request clarification rather than assume coordinates.
- **Missing/duplicate year or commodity match:** resolve via source metadata and labels; if it cannot be resolved uniquely, stop that calculation rather than link an arbitrary row.
- **Unit, base-year, currency, or deflator-scale incompatibility:** document the issue and correct only through an explicit, auditable conversion supported by labels/metadata.
- **Formula recalculation unavailable:** formulas may be entered, but do not claim calculated validation; use a compatible spreadsheet engine before final delivery when cached values are required.
