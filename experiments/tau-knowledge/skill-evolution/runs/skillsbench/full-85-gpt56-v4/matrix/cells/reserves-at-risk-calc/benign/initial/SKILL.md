---
name: reserves-at-risk-workbook
version: 1.0.0
description: Populate and calculate an IMF gold-price and country-reserve-at-risk Excel workbook while preserving formulas, using workbook-discovered labels and Excel formulas for all calculations. Use for tasks requesting monthly gold-price returns/volatility, reserve-value completion, INDEX/MATCH reserve lookups, and a saved .xlsx deliverable.
---

# Reserves-at-risk workbook workflow

Use this Skill when the supplied workbook contains sheets analogous to **Gold price**, **Value**, **Volume**, **Total Reserves**, and **Answer** and requests commodity-price risk calculations.

## Principles

- Inspect the actual workbook before selecting rows, columns, units, years, or formulas. Sheet labels, existing formulas, number formats, and units are authoritative.
- Do not hard-code countries, source row positions, downloaded values, or an expected answer. The script reads these from the runtime workbook/source file.
- Put all arithmetic in worksheet formulas. Python only copies source observations, identifies eligible records, writes formulas, and validates structure.
- Gold volume may only be converted after confirming the volume unit, value scale/currency, and the required troy-ounce conversion. Do not guess whether values are dollars, millions, or billions.
- Preserve existing sheets, styles, merged cells, formula cells outside requested output areas, and workbook layout.

## Runtime inputs

1. Download the IMF global commodity-price Excel database from the public IMF commodity-prices page. Save the downloaded `.xlsx` locally.
2. Inspect the template workbook and IMF workbook. Run:

```bash
python /app/environment/skills/current/scripts/xlsx_rar.py inspect \
  --workbook /root/data/test-rar.xlsx --json-out /root/rar-inspection.json
python /app/environment/skills/current/scripts/xlsx_rar.py candidates \
  --imf-xlsx /root/imf-commodity-prices.xlsx --json-out /root/imf-candidates.json
```

`inspect` emits sheet dimensions, nonempty cells, formulas, and number formats. `candidates` emits likely gold rows and their date/value observations. Confirm the candidate is the monthly **Gold, US dollars per troy ounce** series rather than a different currency, fixing, average, or unit.

3. Create a JSON configuration using `references/config-schema.md`. Coordinates must be established from the inspected workbook, not presumed from this Skill. In particular, verify:
   - price table columns and first data row;
   - Answer cells/rows requested by the task;
   - country and 2025-data table structures and units in Value, Volume, and Total Reserves;
   - the intended risk convention shown by labels or existing workbook formulas (periodic vs annualized volatility, confidence multiplier, and whether RaR is an amount or ratio).

4. Build the output:

```bash
python /app/environment/skills/current/scripts/xlsx_rar.py build \
  --workbook /root/data/test-rar.xlsx \
  --imf-xlsx /root/imf-commodity-prices.xlsx \
  --config /root/rar-config.json \
  --output /root/output/rar_result.xlsx
```

The build command writes the selected raw monthly prices and writes Excel formulas for log returns, rolling standard deviations, annualization, Jan--Sep 2025 price averaging, value lookup/conversion, exposure, total-reserve lookup, and RaR. It uses `INDEX(MATCH())` for country/2025 table formulas.

5. Recalculate the *delivered file* with Excel if available. A compatible headless spreadsheet engine may be used solely to recalculate formulas, for example:

```bash
mkdir -p /root/recalc
libreoffice --headless --convert-to xlsx --outdir /root/recalc /root/output/rar_result.xlsx
cp /root/recalc/rar_result.xlsx /root/output/rar_result.xlsx
```

Then validate:

```bash
python /app/environment/skills/current/scripts/xlsx_rar.py validate \
  --workbook /root/output/rar_result.xlsx --config /root/rar-config.json
```

`validate` checks requested cells/ranges are populated, expected formulas remain formulas, price dates are ordered and monthly, Step 3 countries are a subset of Step 2 countries, and no configured output cell has an Excel error. It reports formula-cache limitations when the workbook has not been recalculated.

## Formula conventions

The default formula definitions are:

- monthly log return: `LN(current_price/previous_price)*100`;
- rolling volatility: `STDEV.S` of the requested monthly-return window;
- annualized three-month volatility: periodic three-month volatility times `SQRT(12)` unless the workbook explicitly calls for another convention;
- 2025 annual proxy price: average of available January--September 2025 monthly prices;
- country lookup: `INDEX(data_range,MATCH(country,country_range,0))`;
- volume conversion: source volume × configured ounces-per-source-unit × Jan--Sep price ÷ configured value-scale divisor.

The exposure and RaR templates are deliberately configuration fields because templates vary in whether they are values, shares of total reserves, and/or confidence-adjusted loss estimates. Derive them from the workbook's labels and stated convention; do not silently impose a model.

## Failure handling

Stop rather than manufacture data if the IMF source does not contain a uniquely identifiable monthly gold USD/troy-ounce series, a country appears more than once, a 2025 header is ambiguous, required units are absent, or source data are nonnumeric/missing. A country with no 2025 Total Reserves observation must be excluded from Step 3, as requested. Missing is not zero.
