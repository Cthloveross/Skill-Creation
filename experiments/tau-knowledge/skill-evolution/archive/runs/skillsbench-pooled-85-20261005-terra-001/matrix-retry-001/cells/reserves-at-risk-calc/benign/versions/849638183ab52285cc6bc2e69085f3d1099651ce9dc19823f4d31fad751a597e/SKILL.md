---
name: reserves-at-risk-excel-workbook
version: 1.0.0
description: Complete a supplied commodity-reserves Excel template by importing current IMF monthly gold prices, calculating formula-driven gold-price volatility, reconciling 2025 gold reserve value and volume data, and producing country-level reserve-at-risk outputs. Use when the deliverable must remain an Excel workbook and calculations must be performed by Excel formulas.
---

# Commodity Reserves at Risk Excel Workbook

## Scope and non-negotiable rules

Use this Skill for the workbook task that requires a completed `.xlsx` file. The supplied workbook is the source of truth for its layout, labels, units, target cells, and any displayed risk definition. Inspect it before editing; do not assume row numbers beyond task-specified output areas or infer a source-table layout from another workbook.

- Preserve all existing sheets, names, styles, merged cells, formulas, and unrelated values.
- Use Excel formulas for calculations. Do not calculate returns, standard deviations, averages, conversions, exposures, lookups, or RaR externally and paste resulting constants.
- Imported source observations and country labels may be entered as source values; every derived result must be an Excel formula that links to workbook inputs.
- Do not invent a confidence multiplier, a quantile, a currency conversion, an annualization convention, or a country-name normalization not supported by visible task/workbook evidence.
- Save the final, recalculated workbook exactly to the requested output path.

The included `scripts/audit_workbook.py` is inspection-only. It does not calculate or modify a workbook and may be used before or after Excel editing to inventory labels, formulas, formats, and formula caches.

## Inputs and output

At runtime, identify the supplied template, normally at the public task's copied path. The completed result must be saved to the output path required by the task (for this task, `/root/output/rar_result.xlsx`).

Expected logical sheets, as specified by the task, are:

- `Gold price`: imported monthly US-dollar-per-troy-ounce gold series and return/volatility columns;
- `Value`: country-level gold reserve monetary values;
- `Volume`: country-level gold reserve physical quantities;
- `Total Reserves`: country-level all-reserves values;
- `Answer`: step 1, step 2, and step 3 output areas.

First inventory their actual headers, title rows, year headers, orientation, units, and existing formulas. For example:

```bash
python scripts/audit_workbook.py <<'JSON'
{"workbook":"/root/data/test-rar.xlsx","sheets":["Gold price","Value","Volume","Total Reserves","Answer"],"max_cells_per_sheet":3000}
JSON
```

This command only prints JSON metadata. It is not a substitute for opening and calculating the file in Excel.

## Procedure

### 1. Inspect and protect the template

1. Make a working copy of the supplied workbook and open that copy in Excel.
2. Locate the actual input region and headers in `Gold price`; confirm the task-designated calculation columns are C (monthly log return), D (3-month volatility), and E (12-month volatility). Identify the raw price and period columns from headers rather than assuming their letters.
3. Inspect `Answer` rows 3--6, 11--13, and 20--24. Read their labels, units, number formats, and any neighboring/sample formulas. The labels determine which of the calculated step-1 metrics each answer cell receives and whether results are displayed as values, ratios, or percentages.
4. On `Value`, `Volume`, and `Total Reserves`, find the country identifier range, the data matrix, and the unique 2025 header. A year can be stored as a number, date, or text; use the header that visibly represents 2025. Verify that each country/year lookup has exactly one match.
5. Record units visibly stated by each source table. In particular, determine whether monetary values are dollars, thousands, or millions of dollars and whether volumes are troy ounces, kilograms, or metric tonnes. Keep a small visible unit ledger while building formulas.

Do not overwrite source data sheets other than the requested `Gold price` population/calculation region.

### 2. Obtain and import the gold series

1. Open the current IMF commodity-price page named in the task and download its global commodity Excel database. Do not rely on a previously downloaded filename, an assumed workbook sheet, or an old copied value.
2. In the downloaded database, inspect the notes and headers. Select the monthly **gold price in US dollars per troy ounce**, not a gold index, another currency, an annual average, or a different metal.
3. Import/copy the source's monthly period and gold-price observations into the identified input columns of `Gold price`, in ascending chronological order. Preserve true Excel dates where possible. Retain the source's available history needed by the template; do not fabricate missing months or treat missing source values as zero.
4. Use the last chronologically valid numeric observation as “latest.” It is not necessarily the visually last formatted row in the template.

### 3. Put return and volatility formulas in `Gold price`

Use formulas in the designated C:D:E columns, adapting the raw-price column and first data row to the discovered template. Keep the return convention explicitly in percentage points as required by the task.

For an illustrative row `r` whose price is in `B`, use formulas equivalent to:

```excel
C[r] = IF(COUNT(B[r-1],B[r])=2,LN(B[r]/B[r-1])*100,"")
D[r] = IF(COUNT(C[r-2]:C[r])=3,STDEV.S(C[r-2]:C[r]),"")
E[r] = IF(COUNT(C[r-11]:C[r])=12,STDEV.S(C[r-11]:C[r]),"")
```

Fill them only through rows containing imported monthly prices. These formulas mean:

- C is the monthly log return, multiplied by 100;
- D is a trailing three-observation sample standard deviation of those percentage-point returns;
- E is a trailing twelve-observation sample standard deviation.

The `COUNT` guards prevent blank trailing template rows from generating errors. If the existing workbook demonstrates an equivalent established formula convention, preserve that convention rather than replacing it gratuitously.

In the four step-1 answer cells, insert formulas referencing the appropriate latest valid `Gold price` cells rather than hardcoded numbers. Based on the labels, these should cover the requested latest gold price, latest monthly log return if requested, latest 3-month volatility, latest 12-month volatility, and/or the requested 3-month annualized metric. The annualized three-month result must be linked to the stored latest 3-month volatility cell and be calculated as:

```excel
=<latest_3_month_volatility_cell>*SQRT(12)
```

Do not multiply by 100 again: D and E are already percentage-point volatility values because C was multiplied by 100.

### 4. Build the step-2 population and gold-price exposure

Populate the step-2 horizontal or vertical orientation exactly as established by the `Answer` sheet. The task identifies rows 11--13; do not switch its orientation or add a replacement table.

1. Build the ordered country list from every country with a genuine numeric 2025 gold reserve **value** in `Value`.
2. Add only countries with numeric 2025 `Volume` data that are not already represented in the `Value` 2025 population. Compare exact displayed identifiers unless the workbook itself supplies an evidenced country-ID mapping. Do not silently merge similarly spelled names.
3. Put country labels in the country row and gold reserve monetary values in the following value row. For countries from `Value`, use a formula linked to the 2025 source cell, preferably an exact two-key lookup rather than an assumed corresponding row. For example, with countries in `Value!$A$6:$A$200`, headers in `Value!$B$5:$Z$5`, and data matrix `Value!$B$6:$Z$200`:

```excel
=INDEX(Value!$B$6:$Z$200,MATCH(<answer_country_cell>,Value!$A$6:$A$200,0),MATCH(2025,Value!$B$5:$Z$5,0))
```

Use actual discovered ranges, and preserve numeric results as numeric values/formulas, not text.
4. For a volume-only country, create a formula that converts its 2025 physical quantity to the **same monetary unit as the `Value` sheet** using the arithmetic average of the January--September 2025 monthly gold prices. Build the Jan--Sep average with Excel from the imported period and price ranges. A date-based formula is preferred when the period cells are actual dates, for example:

```excel
=AVERAGEIFS(<price_range>,<date_range>,">="&DATE(2025,1,1),<date_range>,"<="&DATE(2025,9,30))
```

Then multiply that formula by the volume lookup and the evidenced physical-unit factor. Common factors are 1 for troy ounces, `32.1507466` for kilograms, and `32150.7466` for metric tonnes. Divide by 1,000 or 1,000,000 only when needed to express the output in the visible Value-sheet unit. Do not apply a factor merely because a result seems numerically large or small.
5. In row 13, calculate each country's gold-price exposure from the linked gold value and the gold volatility selected by the labels/task. With volatility stored in percentage points, the generic valuation-swing formula is:

```excel
=<gold_reserve_value_cell>*(<selected_volatility_cell>/100)
```

Use the label-supported latest volatility metric consistently for all countries. If the template visibly defines a different exposure formula, follow its definition. Do not add a normal-quantile multiplier unless an explicit input/label requires one.

Clear unused preformatted step-2 cells rather than allowing obsolete countries, values, or formulas to remain in the reported table.

### 5. Build the step-3 RaR table with lookup formulas

Step 3 is a filtered copy of step 2, not a second independently guessed country population.

1. Initially link each step-2 country, gold reserve value, and selected volatility into rows 20--22. Use direct formula links for values and volatility, not pasted results.
2. In row 23, retrieve 2025 total reserves using the task-required exact two-key lookup (`INDEX` + `MATCH` or `XLOOKUP`). Use the country in that step-3 column/row and the `Total Reserves` 2025 header. An `INDEX`/two-`MATCH` pattern is:

```excel
=INDEX(<total_reserves_data_matrix>,MATCH(<step3_country_cell>,<total_reserves_country_range>,0),MATCH(2025,<total_reserves_year_headers>,0))
```

Use absolute ranges appropriately so copied formulas continue to use the correct source table.
3. Before finalizing the table, remove/clear an entire step-3 entry for every country lacking a numeric 2025 total-reserves result. Do not leave an `#N/A`, a zero substituted for unavailable data, or a blank country inside the reported RaR range. Keep the remaining countries contiguous in the template's orientation.
4. In row 24, calculate RaR from the retained gold value, volatility, and total-reserves cells. Where RaR is labeled as a share of total reserves and volatility is percentage points, the formula is dimensionally:

```excel
=(<gold_value_cell>*(<volatility_cell>/100))/<total_reserves_cell>
```

Format it as a percentage only if the row/header format specifies a percentage. If the visible workbook instead explicitly defines RaR as a currency amount, retain the numerator and use that declared unit. Do not create a risk confidence scaling parameter that the task did not provide.

### 6. Recalculate, validate, and save

Recalculate in Excel (full calculation), save, close, and reopen the workbook. Formula-writing libraries alone are insufficient because they may not create updated formula caches.

Validate all of the following before delivery:

- `Gold price` contains the intended IMF monthly US$/troy-ounce series in chronological order; no fabricated zero replaces a missing quote.
- C has log-return formulas in percentage points; D uses a trailing 3-month `STDEV.S`; E uses a trailing 12-month `STDEV.S`.
- The latest step-1 values link to the latest actual monthly record, and the annualized 3-month measure is `3-month volatility * SQRT(12)`.
- The step-2 country set equals the union of numeric `Value` 2025 countries and genuinely additional numeric `Volume` 2025 countries.
- Jan--Sep 2025 gold price is an arithmetic average of the imported monthly observations and any physical conversion reconciles units explicitly.
- Step-3 entries are exactly the step-2 entries for which the `Total Reserves` 2025 lookup returns a numeric value.
- Every total-reserve formula is an exact country/year lookup, not a row-position assumption.
- Exposure and RaR use decimal volatility factors (`volatility/100`) when volatility is stored as percentage points.
- Target cells have no `#N/A`, `#VALUE!`, `#DIV/0!`, `#REF!`, stale blank cached formula result, or text masquerading as a number.
- Source sheets, workbook layout, and unrelated content remain unchanged.

Optionally run the inspection helper after saving to list formulas and cached values, then use Excel's reopened workbook as the authoritative recalculation check:

```bash
python scripts/audit_workbook.py <<'JSON'
{"workbook":"/root/output/rar_result.xlsx","sheets":["Gold price","Answer"],"max_cells_per_sheet":3000,"include_cached_values":true}
JSON
```

Deliver only the saved workbook at the requested path.
