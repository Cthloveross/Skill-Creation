---
name: excel-supply-side-investment-shock
version: 1.0.0
description: Complete a supplied Excel-only supply-side investment-shock workbook using source data, Excel formulas, and Excel Solver. Use when a workbook requires PWT capital, WEO real GDP and growth, ECB consumption of fixed capital, an annual HP filter, and Cobb-Douglas baseline/with-shock potential-output projections.
---

# Excel Supply-Side Investment Shock Model

## Scope and operating rules

Use this Skill for an existing workbook whose layout is the required deliverable. Work in the supplied `.xlsx` only and save the completed result at the required path. Do not use Python, an external optimizer, hardcoded calculated values, additional sheets, or layout changes. Source observations may be entered as source-data inputs; all transformations, links, projections, ratios, and model calculations must remain Excel formulas.

Use the required browser method for the task (for example, Playwright MCP) to retrieve online data. Do not rely on a remembered series code, a local mirror, a prior workbook, or an assumed source unit. Inspect workbook labels, formulas, units, and source metadata before entering values.

## 1. Inspect the workbook first

1. Open the workbook in Excel and identify all sheets, used ranges, year labels, existing formulas, named ranges, number formats, and blank destination cells.
2. Preserve all existing formulas and formatting outside requested inputs/formula regions.
3. Confirm the geography, years, and units requested by the workbook. Match data by year labels, never by row position alone.
4. Identify the workbook's capital-share input, depreciation input, HP lambda input (if present), investment schedule, objective cell, and Solver decision range from visible sheet labels/formulas.
5. Check whether the workbook specifies conversion factors or a price-basis conversion. Capital, GDP, investment, and CFC cannot be combined unless their relevant currency, scale, valuation, and price bases are compatible.

If a required source series cannot be found with the required frequency, geography, unit, or price basis, do not silently substitute a different series. Record the limitation in an existing designated note/source area if one exists and retain only defensible workbook content.

## 2. Populate source-data tabs

### PWT capital stock

1. Obtain the current PWT download and read its metadata tab/documentation.
2. Select the Georgia observations and the metadata-defined real capital-stock variable (`rnna` only when the release metadata defines it as capital stock at constant national prices).
3. Enter requested years and source values into the existing PWT destination columns. Keep the source units exactly as documented unless the workbook has an explicit formula conversion area.
4. Verify each year is unique and no values were shifted relative to the destination year key.

### IMF WEO real GDP and growth

1. Through the required browser workflow, obtain the applicable WEO release and inspect the series metadata.
2. Select Georgia's real GDP **level** in its documented national-currency constant-price scale and the corresponding real GDP year-over-year growth series. Do not use nominal GDP or substitute a growth series for a level series.
3. Populate the workbook's requested historical/forecast years through the final published forecast year.
4. For years after that final forecast, keep the last published growth-rate cell as the fixed growth assumption through the requested horizon using an Excel reference formula, not repeated literals. For example, a later growth cell should reference the final forecast growth cell with an absolute reference.
5. Extend the real GDP level recursively using the prior year's level and the same-row growth rate:
   `=previous_level*(1+current_growth/100)`

Use the actual workbook columns/cells, and ensure forecast years are aligned across both series.

### ECB consumption of fixed capital

1. Use the ECB Georgia page and inspect series metadata rather than selecting by a remembered identifier.
2. Select an annual CFC series with the required institutional coverage, transaction, valuation, currency, unit, and price basis.
3. Populate the existing CFC input column by matching annual labels.
4. Link capital stock from the PWT sheet with an Excel formula keyed to the appropriate matching year, or direct cross-sheet links only where matching layout is demonstrably identical.
5. Only calculate depreciation as `=CFC/K` after confirming the numerator and denominator use compatible currency, scale, valuation, and price bases. Apply a documented workbook conversion formula if necessary. Do not divide current-price CFC by constant-price capital merely because both are in national currency.

## 3. Build the annual HP-filter block in Excel

Use the historical overlap for which both real GDP and capital exist. Follow the workbook's visible year range; do not extend the filter sample with unavailable data.

1. Link the annual capital and GDP inputs into the requested Production cells using cross-sheet formulas.
2. Calculate logs with formulas:
   - `LnK = LN(K)`
   - `LnY = LN(Y)`
   - `LnZ = LnY - alpha*LnK`

   Use absolute references for the capital-share input when copying formulas.
3. In the HP area, initially link/copy raw `LnZ` into every trend decision cell. This is the Solver starting point, not the final trend.
4. For each interior observation, calculate the second difference of the trend series:
   `=next_trend-2*current_trend+previous_trend`
5. Calculate the trend residual/sanity-check column as raw `LnZ - trend`. Immediately before Solver runs, it should be zero because the initial trend equals raw LnZ.
6. Build one objective formula containing both terms, with annual smoothing parameter 100:
   `=SUMSQ(raw_LnZ_range-trend_range)+100*SUMSQ(second_difference_range)`

   Where array arithmetic is not supported by the workbook's Excel version, use a row-level squared-residual helper column and sum it, preserving the same objective. Do not omit the fit term or smoothness term.
7. Configure Excel Solver from the workbook UI:
   - **Set Objective**: the workbook's HP objective cell.
   - **To**: Min.
   - **By Changing Variable Cells**: the entire trend decision range, including both endpoints.
   - Use an appropriate unconstrained smooth nonlinear/quadratic method available in Excel Solver.
   - Add no economic constraints unless the workbook explicitly requires them.
8. Solve, keep the Solver solution, and save. The optimized trend must remain numeric Solver values in the trend decision cells; downstream workbook cells must reference that range with formulas.

Do not replace this required Excel Solver step with a statistical package, Python calculation, or hand-entered trend values.

## 4. Build the production-function scenario

Use formula references throughout, respecting the actual destination rows and years in the supplied workbook.

1. Set annual depreciation in the designated production input cell to the Excel average of the most recent eight valid annual depreciation observations, for example `=AVERAGE(last_8_valid_delta_cells)`. Confirm all eight observations are actual matching annual observations and not blanks or noncomparable values.
2. Link historical K and Y into the scenario table. Calculate K/Y only for the explicit overlap years requested by the workbook:
   `=K/Y`
3. Derive the fixed capital-intensity anchor as the Excel average of the most recent nine valid K/Y observations:
   `=AVERAGE(last_9_valid_KY_cells)`
4. For post-observation years, extend K as the fixed anchor times the same-year projected real GDP:
   `=KY_anchor*projected_real_GDP`
5. Link the solved HP trend to the historical scenario trend cells. Extend the trend only after the HP sample using Excel `TREND`, with actual known trend values and actual year cells as known x-values, for example:
   `=TREND(known_trend_range,known_year_range,current_year_cell)`
6. Calculate baseline potential output in each scenario year:
   `=EXP(LnZ_trend)*K^alpha`
7. Link each year’s additional investment from the Investment sheet. Retain zero/no-investment years as linked formula values, rather than manually substituting them.
8. Calculate incremental shock capital and with-shock capital consistently with the workbook's timing convention. Where `K_with` is defined as next period’s capital, use:
   `= (1-depreciation_rate)*prior_K_with + current_period_additional_investment`

   Initialize the first with-shock capital stock from the baseline stock at the shock onset as required by the workbook, then propagate it annually. If the workbook has a dedicated delta-K column, calculate it via formulas and ensure its timing is consistent with K-with.
9. Calculate with-shock potential output:
   `=EXP(LnZ_trend)*K_with^alpha`
10. Complete uplift and other requested output columns using formulas, e.g. absolute uplift `=Ystar_with-Ystar_base` and percent uplift `=(Ystar_with/Ystar_base-1)*100` when requested.

Additional investment must be real and compatible with the production function's price/scale basis. If the source investment tab supplies nominal USD while the model uses constant-price national currency, use only an explicitly provided workbook conversion/deflator mechanism; do not invent an exchange rate or deflator.

## 5. Validate before delivery

Perform these checks in Excel after recalculation:

- PWT, WEO, and ECB observations match Georgia, their intended variable definitions, units, and years.
- WEO extended GDP follows the prior-year formula and uses the final forecast growth rate through the requested horizon.
- Every historical capital/GDP link is aligned by year.
- The depreciation input is an `AVERAGE` formula over eight valid recent depreciation cells.
- The K/Y anchor is an `AVERAGE` formula over nine valid recent K/Y cells.
- All calculated regions contain formulas except the Solver decision trend values and externally sourced input observations.
- The HP objective includes a nonzero fit component and a lambda-100 second-difference component; Solver's decision range is exactly the full trend range.
- At any historical row, independently verify the two-factor identity represented by workbook formulas: `EXP(LnY-alpha*LnK)*K^alpha` reproduces Y within normal rounding precision.
- Baseline and with-shock series use the same LnZ trend and alpha; their only scenario capital difference is the additional-investment accumulation.
- Formula cells show no `#REF!`, `#VALUE!`, `#DIV/0!`, `#N/A`, or stale cached values.
- Save, force workbook recalculation in Excel, save again, close, reopen, and inspect key formula results and the solved HP trend. Preserve the existing workbook name and required output location.

## Expected deliverable

The completed deliverable is the supplied workbook itself, with source inputs populated, formulas retained, the annual HP filter solved in Excel Solver, and calculated baseline/with-shock potential GDP results available in its original workbook layout.
