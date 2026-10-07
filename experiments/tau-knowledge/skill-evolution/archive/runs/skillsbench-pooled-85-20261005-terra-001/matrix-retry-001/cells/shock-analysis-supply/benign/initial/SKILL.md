---
name: excel-supply-side-investment-shock
version: 1.0.0
description: Complete a supplied Excel production-function workbook for an investment shock by collecting documented annual source data, using Excel formulas and Excel Solver for the HP filter, and preserving the template's formula-driven model. Apply when the task requires PWT capital data, IMF WEO real GDP and growth data, ECB consumption of fixed capital, and an Excel-only potential-GDP scenario.
---

# Excel Supply-Side Investment-Shock Workbook

## Purpose and boundaries

Use this Skill to populate and calculate the supplied workbook in Excel. Browser use is limited to collecting the requested source data; all transformations, links, projections, model calculations, and HP optimization must be performed in Excel. Do not use Python, an external optimizer, hardcoded calculated results, or an external formula-calculation engine.

The source observations pasted into designated input cells are raw data, not calculated model outputs. All workbook-derived values must remain Excel formulas except the HP trend decision cells after Excel Solver has optimized them.

The final deliverable is the same workbook saved as the exact required output filename and location (for this task, `test-supply.xlsx`). Do not add sheets, replace formulas with values, alter unrelated formatting, or change the template structure.

## Inputs and required source checks

Before entering data, open the workbook in Excel and inspect the sheets named by the task, their headers, year labels, units, existing formulas, named ranges, and any notes. Confirm the destination cells actually correspond to the requested concepts before writing.

Collect only annual observations for the target economy and preserve the source-provided year keys.

### 1. Penn World Table (PWT)

1. Use the PWT site specified by the task and obtain the current downloadable PWT data and its metadata.
2. Read the metadata before selecting variables. Identify the target country by its country identifier/name and select the variable defined as real capital stock (`rnna` only if the downloaded metadata defines it that way).
3. Filter by the required annual years and paste year and capital-stock observations into the input columns of the `PWT` sheet indicated by its labels and the task.
4. Keep PWT values at their published precision. Do not substitute a country, series, year, or unit from memory.
5. Record source/series/unit information in an existing source-note area if the workbook provides one; otherwise preserve the workbook layout and retain the source evidence outside the model rather than inserting unrequested sheets.

### 2. IMF WEO real GDP and growth

Use Playwright MCP to navigate the IMF WEO database. In the current WEO release, locate the target economy and the two series by their visible definitions and units:

- real GDP level in the real, constant-price unit needed by the workbook; and
- real GDP annual percent change.

Do not select a nominal GDP series or infer a WEO indicator code without reading its current metadata. Capture observations from 2000 through the instructed final forecast year and paste them into the rows/columns labelled for the two series in `WEO_Data`.

For years beyond the final supplied WEO growth observation through the requested horizon, use Excel formulas that reference the final observed/projected WEO growth-rate cell. If growth is stored as a percent, the level extension is:

```excel
=prior_year_real_GDP*(1+final_WEO_growth_rate/100)
```

Copy this formula through the requested final year. If the sheet stores growth as a decimal instead, omit `/100`. Use the displayed unit and number format to determine the convention; do not guess.

Keep source WEO observations as pasted values and begin extension formulas only after the last WEO observation.

### 3. ECB consumption of fixed capital (CFC)

Use the ECB Georgia page specified by the task. Locate an annual CFC series by reading the series metadata, including geography, frequency, sector, transaction, valuation, currency, unit, and price basis. Populate the labelled raw-CFC input column in `CFC data` with annual observations aligned by year.

Link capital stock from `PWT` using an Excel lookup keyed by year, rather than assuming equal row positions. Calculate annual depreciation only after confirming CFC and capital are on compatible currency, valuation, price, and scale bases.

- If the source units differ only by a stated scale (for example, millions versus units), create one explicit Excel conversion formula before calculating the ratio.
- If price or currency bases differ, use a supplied, documented workbook conversion input/formula only where the workbook and source data support it.
- Do not directly divide a current-price CFC series by a constant-price capital series merely because both are monetary.
- If the supplied sources and workbook provide no defensible conversion, stop and flag the incompatibility rather than inventing a ratio.

The annual rate formula is conceptually:

```excel
=compatible_CFC / compatible_capital_stock
```

Use the actual labelled CFC and capital columns when writing the formula. Fill it only where both values are numeric and the year matches uniquely.

## Formula construction in the workbook

Use formulas that point to labelled source values and use absolute references for fixed assumptions. Use two-key/year lookups where the workbook includes multiple series. Do not use a hardcoded row alignment when an explicit year field is available.

### Depreciation assumption

In `Production`, calculate the requested annual depreciation assumption in `B3` as an Excel average of the depreciation-rate cells corresponding to the most recent eight valid annual observations. The selection must be based on the year labels and complete numeric source observations, not an assumed block of rows. Preserve full precision; use formatting, not `ROUND`, unless the workbook explicitly requires rounding.

### Historical production-function inputs and residual

In the `Production` historical block:

1. Link capital and real GDP to the designated ranges (including `D6:D27` and `E6:E27` when those are the labelled input ranges in the supplied template).
2. Use `LN` formulas for the linked positive capital and GDP values.
3. Calculate the two-factor residual with the capital-share input referenced absolutely:

```excel
=LnY - capital_share * LnK
```

This residual is the workbook's composite productivity/labor term, not necessarily pure TFP.

4. Validate that all linked values are positive before applying `LN` and that all year links resolve to exactly one source observation.
5. Where the workbook has a reconstruction check, or in a designated existing check cell, verify the identity:

```excel
=EXP(LnY-capital_share*LnK)*capital_stock^capital_share
```

It should reproduce the corresponding real GDP apart from floating-point precision. A failure indicates a bad link, unit conversion, or formula reference.

## HP filter using Excel Solver

The annual HP trend must be produced by Excel Solver, not a Python function, an external optimizer, or manually smoothed values.

1. Locate the HP filter panel by labels. Link the calculated residual (`LnZ`) into its indicated input column (the task identifies column F for this template).
2. Initialize the trend decision range (`L6:L27` in this template) by copying the residual values into it as initial numeric values. Do not leave formulas in Solver-changing cells, because Solver must be able to alter them.
3. Fill the displayed second-difference formula only for interior observations. For an interior trend value \(T_t\), use the equivalent Excel relationship:

```excel
=next_trend - 2*current_trend + prior_trend
```

4. Fill the displayed raw-residual-minus-trend check. Before solving, it must be zero in every applicable row because the initial trend equals the residual; this is the required linkage sanity check (including the task's column-N check where applicable).
5. In the existing objective cell `P5`, retain/build one Excel formula containing both terms:

```excel
=SUMSQ(residual_range-trend_range) + lambda_cell*SUMSQ(second_difference_range)
```

Use the workbook's lambda assumption cell and set it to the annual-data convention of 100 if the template does not already provide the required annual smoothing input. The residual/trend ranges must have identical historical years, and the second-difference range must include only interior years.
6. Enable the Excel Solver add-in if necessary. In Solver configure:
   - **Set Objective:** `$P$5`
   - **To:** `Min`
   - **By Changing Variable Cells:** `$L$6:$L$27`
   - **Method:** GRG Nonlinear
   - **Constraints:** none unless an existing workbook instruction explicitly supplies one.
7. Solve and keep the Solver solution in the worksheet. Confirm Solver reports a solution and that `P5` is finite. The post-solve residual-minus-trend cells will generally no longer be zero; the zero condition applies only to the initialization check.

Do not replace the Solver result with a trend generated by `TREND`, a moving average, or copied residual values.

## Baseline capital and potential GDP projection

Use the year labels in the production forecast table and the stated model windows. Maintain the exact timing convention already implied by the workbook's historical and forecast columns.

1. Calculate historical `K/Y` only over the requested common period (2002–2023 for this task):

```excel
=capital_stock / real_GDP
```

2. Calculate the fixed capital-intensity anchor as the Excel average of the most recent nine complete `K/Y` observations in that requested range. Reference this anchor absolutely in later formulas.
3. For forecast years where capital is not observed, extend baseline capital with an Excel formula:

```excel
=fixed_K_to_Y_anchor * same_year_real_GDP
```

Use observed capital where available; do not overwrite it with the extension.
4. Link the solved HP trend into the historical/overlap trend cells, including the requested `G36:G57` range when that is the template's trend destination.
5. Extend the trend only for future years with the Excel `TREND` function, using known solved HP-trend values and their corresponding actual year cells as `known_y` and `known_x`. Use the destination year as `new_x`, for example conceptually:

```excel
=TREND(known_HP_trend_range, known_year_range, destination_year)
```

Do not use row numbers as the x-axis and do not overwrite linked solved historical trend values. Extend only through the horizon requested by the template/instruction.
6. Calculate baseline potential GDP row by row:

```excel
=EXP(LnZ_trend) * baseline_capital ^ capital_share
```

The capital-share reference must be absolute and the levels must be in a consistent real scale.

## Investment shock scenario

Treat the supplied `Investment` sheet as the source of the scenario's annual additional-investment path. Link, do not manually retype, its annual inputs into the production scenario table (including the instructed investment column).

Before using the values, inspect their labels and units. Investment entering the production function must be real and in the same scale as capital. If the sheet provides nominal spending plus a deflator, exchange-rate conversion, or scale factor, reference those cells in the Excel formula. If it declares an amount already real and compatible, link it directly. Never silently treat USD/current-price values as compatible with a real capital series.

Calculate the shock's incremental capital in the timeline convention used by the table. With investment recognized in the same year, the standard recurrence is:

```excel
=current_year_additional_investment + (1 - depreciation_rate) * prior_year_delta_K
```

Initialize the pre-shock delta capital at zero. If the workbook labels investment as end-of-year/carry-forward, use the equivalent next-year placement consistently for both capital and output; do not mix conventions.

Then calculate:

```excel
K_with = K_baseline + delta_K
Ystar_with = EXP(LnZ_trend) * K_with ^ capital_share
uplift = Ystar_with - Ystar_base
uplift_percent = 100 * uplift / Ystar_base
growth = 100 * (current_level / prior_level - 1)
growth_difference = growth_with - growth_base
```

Use formulas for every applicable forecast row. The additional investment should affect only the instructed eight-year shock period; after that period, investment should follow the supplied scenario path (normally zero) while the accumulated capital effect depreciates according to the formula.

## Final validation and delivery

Before saving, use Excel recalculation (for example, Calculate Now / full recalculation) and check the following:

- PWT, WEO, and ECB observations align to their displayed year keys and target economy.
- WEO extension begins after the final supplied WEO year, holds the final supplied growth rate fixed, and is formula-driven to the requested horizon.
- CFC, capital, GDP, and investment units have documented compatible real/nominal, currency, valuation, and scale treatment.
- `B3` averages exactly the latest eight usable depreciation observations.
- The HP objective includes both fit and smoothness terms, uses annual lambda 100, and has been minimized by Excel Solver over the stated trend range.
- Historical `K/Y` uses only 2002–2023; the anchor uses the latest nine valid observations in that range; observed capital is not overwritten.
- `TREND` uses actual years and solved HP trend cells, not an unrelated range.
- Baseline and shock potential GDP formulas use the same trend and capital-share assumption.
- The shock capital recurrence, output uplift, percentage uplift, and growth comparisons reconcile row by row.
- No formula errors (`#REF!`, `#VALUE!`, `#DIV/0!`, `#N/A`, or `#NUM!`) remain in required cells.
- Formula cells remain formulas, links point to the intended source sheets, Solver cells contain its retained solution, and unrelated workbook sheets/layout remain unchanged.

Save the recalculated workbook to the exact required output path as `test-supply.xlsx`. Reopen it in Excel once and confirm that the formulas and displayed results persist after saving.

## Explicit failure handling

Do not fabricate missing source observations, source-series mappings, currency/price conversions, or Solver results. If a requested year is absent, a source match is non-unique, a value is nonnumeric, units cannot be reconciled, a linked value is nonpositive for a log, or Solver does not converge, preserve the workbook and report the specific unresolved source/formula/optimization issue rather than inserting an unsupported number.
