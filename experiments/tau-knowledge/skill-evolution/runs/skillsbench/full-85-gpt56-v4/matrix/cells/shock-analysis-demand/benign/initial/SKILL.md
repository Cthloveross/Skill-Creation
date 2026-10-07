---
name: demand-side-investment-shock-workbook
version: 1.0.0
description: Complete an Excel-only demand-side macroeconomic investment-shock workbook using IMF WEO data and a national supply-use table. Use when a supplied template must retain formulas, source sheets, and scenario calculations rather than producing a separate analysis.
---

# Demand-Side Investment Shock Workbook

## Scope and operating rule

Use this Skill for an Excel workbook that projects GDP effects of an investment project in a small open economy. Perform data entry, linking, calculations, scenario construction, and recalculation **in Excel or a compatible spreadsheet application only**. Do not use Python, external calculation scripts, or hardcoded calculated outputs. All model calculations must remain visible Excel formulas in the delivered workbook.

The task-specific workbook, requested country, projection years, project duration, investment amount, exchange rate, and scenario assumptions are supplied in the task request. Treat workbook labels and source metadata as authoritative; discover the actual layout before editing.

## Required inputs

1. The supplied `.xlsx` template, opened as an editable workbook.
2. The current IMF World Economic Outlook release, using its metadata to identify Georgia and the required real-GDP, real-GDP-growth, nominal-GDP, and GDP-deflator series requested by the template.
3. The latest available Georgia national supply-and-use publication from Geostat containing the requested 38-by-38 Supply and Use tables.

Keep downloaded source data separate from the delivered workbook unless the template specifically provides a source-data area. The final artifact is the original workbook filename in its required output location.

## Workbook-first inspection

Before entering data:

1. Open the template and inventory all worksheet names, used ranges, visible labels, dates/years, existing formulas, merged cells, number formats, named ranges, tables, and blank output regions.
2. Identify the rows on `WEO_Data` from row labels and units, not from a presumed row number. Identify year columns from the header values.
3. Inspect `SUT Calc` to determine what each of columns C:H represents and which source-table labels it expects. Preserve its existing calculation design where present.
4. Inspect `NA` to identify the first scenario block, its assumption cells, year row/column, calculation rows, and the exact location where the two additional scenario blocks must be created.
5. Preserve all supplied observations and pre-existing formulas unless replacement is explicitly necessary to finish an incomplete template. Never overwrite a source value with a projection.

If an expected sheet or labelled destination is absent, do not invent a layout. Record the obstruction in an obvious note cell only if a note area exists, otherwise preserve the workbook and report the unsupported requirement to the task executor.

## Step 1 — WEO data and projections

### Obtain and verify WEO series

Download/export the current WEO dataset from the IMF source. Before copying values, verify from its metadata:

- economy is Georgia (not a similarly named geography);
- indicator definitions and units match the labels in `WEO_Data`;
- annual years are aligned by explicit year headers;
- actual versus forecast coverage is understood;
- level-series scale is retained exactly or converted transparently with a labelled conversion input/formula if the template requires a different scale.

Populate only the designated historical/forecast source cells on `WEO_Data` with WEO values. Enter values as source observations, not as fabricated formulas. Do not replace a valid supplied observation.

### Extend the real GDP growth path

Locate the 2027 real GDP growth-rate cell using year headers. For every projection year after 2027 through the requested horizon, enter a formula referring to the 2027 rate with an absolute reference, for example:

```excel
=$<2027_growth_column>$<real_growth_row>
```

Use the actual discovered cell reference. Do not type a copied percentage into each future cell. Keep percentage units consistent with the template: if WEO growth is stored as percentage points, divide by 100 only where a level-growth formula requires a decimal.

### Project real GDP levels

Where the template requires real GDP to be extended, preserve observed values through the last WEO observation and begin formulas only afterward. Use compounding, not addition:

```excel
=<prior_year_real_GDP_cell>*(1+<current_year_growth_rate_cell>/100)
```

Omit `/100` only if the workbook stores the growth rate as a decimal. Formula references must be year-aligned.

### Extend the GDP deflator

Identify the GDP deflator row and its annual growth-rate row, or calculate deflator growth from adjacent deflator levels only if the workbook structure calls for it:

```excel
=<current_deflator>/<previous_deflator>-1
```

Calculate the fixed anchor as the arithmetic average of the **four most recent applicable annual deflator growth rates**, using a formula such as:

```excel
=AVERAGE(<four_contiguous_recent_growth_cells>)
```

The four cells must be selected from actual year headers and must not include blanks, a projected value accidentally treated as historical, or a mismatched series. Use an absolute reference to that anchor for every forward deflator projection:

```excel
=<prior_year_deflator_cell>*(1+$<anchor_cell>$)
```

If the growth-rate row is in percentage points rather than decimals, use `/$100` logic consistent with the workbook's formatting. Do not hardcode the average or the projected deflator values.

Fill all remaining intended columns on `WEO_Data` with formulas that reconcile the workbook's identified real, nominal, deflator, and growth series. A standard identity is nominal GDP = real GDP × deflator, subject to the workbook's stated deflator base/scale. Use explicit scale conversion factors in formula inputs when required.

## Step 1 — Supply and use tables and import content

### Import source sheets

From the latest Geostat supply-and-use-table publication, obtain the requested 38-by-38 tables. Confirm publication date, table dimension, title, valuation/unit, and whether imported and domestic supply are separately identified.

Copy the source worksheets into the target workbook, keeping the requested original sheet names exactly (normally `SUPPLY` and `USE`). Copy the complete relevant tables, headers, labels, units, footnotes needed for interpretation, and values. Do not rename source sheets, flatten their formulas, or substitute an economy-wide import share.

If source sheet names already exist in the template, update their contents only after confirming they are intended source placeholders; preserve formula references that depend on their names.

### Link `SUT Calc`

Use Excel cell links from `SUT Calc` columns C:E to the copied `SUPPLY` and `USE` sheets. Do not manually retype source-table values. Match rows/columns by commodity and industry labels, not by copied coordinates from another workbook.

Determine the table’s import-content calculation using the labels and source metadata. For a project represented by a particular industry/commodity composition, import content should reflect imported supply used in that relevant composition rather than total economy imports. A common transparent structure is:

```text
import content for component = imported supply for component / total supply for component
weighted project import content = SUMPRODUCT(component weights, component import shares)
```

Use the template's stated definitions where they differ. Complete `SUT Calc` columns C:H with formulas, preserving input links and intermediate calculations. Ensure cell `C46` contains the final estimated import-content share as an Excel formula linked to the preceding calculation chain, not a pasted result.

Use `IFERROR` only to handle genuinely unavailable denominators, preferably returning blank rather than zero. Do not conceal a broken source link with `IFERROR`.

## Step 2 — Base scenario on `NA`

### Links and assumptions

Link the requested `NA` column C and column J rows to their aligned `WEO_Data` values with direct formulas. Match source and destination years explicitly. Do not paste duplicate WEO values.

Enter the task-specified assumptions in the labelled cells `D30:D33` (or retain the workbook's exact labels if their order identifies them):

- USD/Lari exchange rate: `2.746`;
- demand multiplier: `0.8` for the first/base scenario;
- project allocation: bell-shaped over the stated project duration;
- the remaining required project/import/deflator assumption as labelled by the template.

Use numeric input cells for assumptions and formulas elsewhere that reference those cells absolutely. Do not embed 2.746, 0.8, project value, or import share repeatedly inside calculation formulas.

### Bell-shaped allocation

Create the stated number of annual allocation cells as editable formula-driven weights, with a ramp-up, central peak, and ramp-down. The allocation must be non-negative and sum exactly to one. If the template supplies a preferred shape, use it. Otherwise use a symmetric, documented bell-shaped profile created in worksheet formulas (for example, weights based on a normal-density expression centered at the middle project year and divided by the sum of all raw weights).

A robust formula approach is:

1. create raw bell weights for the project years using a formula based on the year’s position relative to the midpoint;
2. normalize each annual raw weight by `SUM(<all_project_raw_weight_cells>)`;
3. set years outside the project window to zero or blank as the template convention requires;
4. add a visible check `=SUM(<allocation_cells>)`, which must equal 1.

Reference the start year and duration through assumption cells or labelled year headers when those inputs exist. Do not use manually entered annual spending results.

### Core annual formulas

Build the remaining rows using formulas and the workbook’s discovered headers. The expected accounting flow is:

```text
project spending in USD
→ project spending in Lari = USD spending × exchange rate
→ nominal annual allocation = total Lari project value × annual allocation share
→ real investment = nominal annual allocation adjusted by GDP deflator
→ domestic impulse = allocated spending × (1 − import content share)
→ GDP increment = domestic impulse × demand multiplier
→ with-shock GDP = baseline GDP + GDP increment
```

Use the GDP deflator as the investment deflator as requested. Apply it consistently using its visible base. For example, a deflator indexed at 100 generally requires division by `(deflator/100)`, whereas an index stored as 1.00 requires division by `deflator`. Put conversion logic in formulas, not manually transformed values.

Maintain nominal and real units separately. Compare/add only like-for-like values. If the output effect is defined in real GDP, deflate spending before deriving the real effect and add it to real baseline GDP. If the template separately presents nominal effect, derive it consistently using the deflator rather than mixing units.

## Step 3 — Scenario 2 and Scenario 3

Replicate the full first scenario table structure below the first block, including labels, years, formulas, number formats, allocation checks, and output rows. Preserve source links and do not paste static calculated values.

For each copied block, formulas must reference that block’s own assumption cells while continuing to link common WEO and SUT source data:

- **Scenario 2:** set only the demand multiplier assumption to `1`.
- **Scenario 3:** set only the import-content-share assumption to `0.5`.

All other scenario inputs must equal the base scenario or link to common source assumptions. Scenario 2 must not alter import content, and Scenario 3 must not alter the multiplier. This isolation makes the resulting deltas auditable.

## Recalculation and validation

Before delivery, recalculate the workbook in Excel or a compatible spreadsheet engine, save it, reopen it in value-reading mode, and inspect key outputs. Verify all of the following:

1. WEO rows align by year and use the intended Georgia series and units.
2. Existing observed data are unchanged; projections begin only after the final observed/required boundary.
3. Post-2027 real GDP growth cells refer to the 2027 growth cell; projected GDP levels compound correctly.
4. The deflator anchor is an `AVERAGE` formula over four correct recent growth observations; projected deflators compound from the prior level.
5. `SUPPLY` and `USE` sheets are present under their required unchanged names and `SUT Calc` C:E use links to them.
6. `SUT Calc!C46` is a valid formula, import content is a share (normally between 0 and 1), and the formula chain contains no broken reference.
7. `NA` C and J values link to `WEO_Data`; `D30:D33` contain the stated base assumptions in the labels’ intended positions.
8. Every bell allocation is non-negative and sums to 1; spending occurs only over the stated project window.
9. Scenario 2 differs only by multiplier and Scenario 3 only by import-content assumption.
10. Formula cells show no `#REF!`, `#VALUE!`, `#DIV/0!`, `#NAME?`, or stale/missing cached results.
11. Key identities reconcile after rounding: annual allocation sums to total project spending; domestic impulse equals spending times one minus import content; GDP increment equals domestic impulse times multiplier; with-shock GDP equals baseline plus increment in matching units.

Save the completed, recalculated workbook under the required filename (`test_demand.xlsx` when that is the supplied task filename).