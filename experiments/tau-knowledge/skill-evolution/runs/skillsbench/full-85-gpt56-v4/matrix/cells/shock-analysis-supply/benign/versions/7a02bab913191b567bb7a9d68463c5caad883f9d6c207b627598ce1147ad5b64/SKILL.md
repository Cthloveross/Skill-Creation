---
name: excel-supply-side-investment-shock
version: 1.1.0
description: Complete an existing Excel supply-side investment-shock workbook using PWT capital, IMF WEO real GDP and growth, ECB CFC, Excel formulas, and Excel Solver. Applies when the supplied workbook has source tabs and a production/HP-filter scenario model that must remain formula-driven.
---

# Excel Supply-Side Investment Shock Model

## Non-negotiable delivery rules

The supplied `.xlsx` is the deliverable. Use Excel (including its Solver) for calculations and retain formulas; do not use Python or an external optimizer to calculate or paste model outputs. Source observations are permitted literal inputs, but links, logs, ratios, extensions, production-function outputs, and shock results must be workbook formulas. Save the finished file at the requested path without changing sheets, layout, or formatting.

Use the browser/data-acquisition method mandated by the task. Inspect source metadata and the workbook labels before choosing a series. Do not infer a series code, unit, year range, row, or expected value from this Skill. Match observations by explicit year keys. If the source data require a currency, scale, or price-basis conversion, make that conversion transparently in an existing workbook formula/input area before combining series.

## End-to-end procedure

1. **Inspect first.** Identify actual sheet names, years, variable labels, source-input cells, the capital-share/depreciation assumptions, the investment schedule, the HP raw/trend/second-difference ranges, the objective cell, and the scenario table. Preserve existing styles and formulas. The provided formula plan is only a checked map for the public template; if labels or years differ, derive formula ranges from visible year keys.
2. **PWT.** Download the current PWT release from the prescribed source, read its metadata, select Georgia and the metadata-defined `rnna` real capital stock, and populate only the requested PWT source cells. Confirm the observation is in constant national prices and every year occurs once.
3. **WEO.** With the required browser workflow, obtain Georgia's real GDP *level* (constant-price national currency, documented scale) and real GDP year-over-year growth for all published years requested. Do not substitute nominal GDP or a growth series for level GDP. For post-forecast years, formulas must reference the final published growth cell and recursively extend the prior year's real GDP level.
4. **CFC and depreciation.** From the ECB Georgia page select the annual CFC series after reviewing its geography, sector, transaction, valuation, unit, currency, and price basis. Populate only source CFC values. Link capital from the PWT tab by matching year and calculate each rate as a formula `CFC/K` only after resolving any basis difference. Set the production depreciation assumption to an `AVERAGE` formula over the most recent eight valid annual rates.
5. **HP filter in Excel.** Link the historical capital/GDP overlap, calculate `LN(K)`, `LN(Y)`, and `LnZ=LnY-alpha*LnK`. Initialize the entire trend decision range from raw LnZ, calculate second differences for interior observations and residual checks, and make the objective include both squared fit deviations and `100*` squared second differences. Run Excel Solver: objective **Min**, changing the entire trend range, no invented constraints. Retain Solver's numeric trend solution; downstream cells must link to it.
6. **Scenario formulas.** Calculate K/Y only across the requested historical overlap. Use an Excel `AVERAGE` of the latest nine valid K/Y observations as the fixed anchor for extended capital. Link the solved historical trend, extend it with `TREND`, calculate baseline `EXP(trend)*K^alpha`, then calculate incremental shock capital recursively with depreciation and linked investment. Calculate with-shock output with the same trend and alpha, plus formula-driven uplift and growth columns.
7. **Recalculate and verify.** Recalculate with Excel or a compatible spreadsheet engine, reopen the file, and check that formula results are not stale. Verify no formula errors, WEO extension references the last forecast-growth cell, source links are year-aligned, Solver values occupy only its decision range, and `EXP(LnY-alpha*LnK)*K^alpha` reconstructs historical Y (rounding aside). Ensure the only difference between baseline and with-shock production functions is the capital path.

## Public-template formula map

For the public template with sheets `Production`, `Investment`, `CFC data`, `PWT`, and `WEO_Data`, follow [`references/workbook-formula-plan.md`](references/workbook-formula-plan.md). It specifies formula structure, formula ranges, Solver cells, and post-calculation checks, but deliberately contains no source observations or precomputed answers. It is a guide for entering formulas in Excel, not a substitute for metadata-led source selection or Solver.

## Failure handling

Do not silently fill unavailable source data with zeros, use nearby-year observations, divide noncomparable CFC and capital, or replace Solver values with an external HP calculation. A completed deliverable cannot contain missing source-input years. Resolve the source and its visible metadata through the task-required source workflow, then retain an auditable formula conversion if needed. If the source is genuinely unavailable, do not fabricate a value or substitute a different series; report the blocking issue rather than claiming completion.
