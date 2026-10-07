---
name: reserves-at-risk-workbook
description: Build an Excel reserves-at-risk deliverable from an IMF commodity-price workbook and an IMF-style reserve workbook. Use when the task requires gold monthly prices, log-return volatility, country reserve values, exposure, and INDEX/MATCH total-reserve lookup formulas in an existing .xlsx workbook.
---

# Reserves-at-risk workbook

This Skill produces the requested workbook while retaining its sheets and layout. It dynamically discovers period labels, source columns, answer labels, and 2025 country data. It does **not** hard-code countries, values, data coordinates, or an IMF database version.

## Inputs and output

- Template workbook: the task-supplied `.xlsx` file.
- IMF commodity database: an `.xlsx` download containing a monthly gold series explicitly labelled **US dollars per troy ounce**.
- Output: the requested completed `.xlsx` path.

The executable uses command-line paths and emits a JSON execution report on stdout. It uses only `openpyxl` plus the Python standard library. Source price observations are copied as numeric inputs; every requested calculation is written as an Excel formula.

## Run

Download the public IMF database, then build and recalculate the final workbook:

```bash
mkdir -p /root/output /root/recalc
python3 /app/environment/skills/current/scripts/download_imf.py \
  --output /root/imf-commodity-prices.xlsx
python3 /app/environment/skills/current/scripts/xlsx_rar.py build \
  --workbook /root/data/test-rar.xlsx \
  --imf-xlsx /root/imf-commodity-prices.xlsx \
  --output /root/output/rar_result.xlsx
libreoffice --headless --convert-to xlsx --outdir /root/recalc \
  /root/output/rar_result.xlsx
cp /root/recalc/rar_result.xlsx /root/output/rar_result.xlsx
python3 /app/environment/skills/current/scripts/xlsx_rar.py validate \
  --workbook /root/output/rar_result.xlsx
```

`download` starts at the public IMF commodity-prices page and follows a database link. If that page changes, pass the directly downloaded public Excel URL using `--url`; inspect the downloaded file before building:

```bash
python3 /app/environment/skills/current/scripts/xlsx_rar.py inspect \
  --workbook /root/imf-commodity-prices.xlsx
```

## What `build` verifies and writes

1. It finds all monthly labels in column A of **Gold price**, and finds an explicit USD/troy-ounce gold series (and an explicit PM series when the template requests PM) in the supplied source. It refuses a missing month or an ambiguous/non-explicit series.
2. It writes raw price observations and Excel formulas for `LN(current/previous)*100`, trailing three-return `STDEV.S`, and trailing twelve-return `STDEV.S`. The latest Step 1 cells receive `NORM.S.INV(0.95)`, latest three-month volatility, its `SQRT(12)` annualization, and latest twelve-month volatility, respectively.
3. It discovers the 2025 row and country descriptors in **Value** and **Volume**. It lists every numeric USD-million gold value observation. It appends volume-only countries with numeric 2025 troy-ounce data, converting them using the January--September average price and the source descriptor's thousands/millions troy-ounce scale.
4. Step 2 exposure formulas use gold value × 95%-one-sided z score × annualized three-month volatility.
5. Step 3 links each qualifying Step 2 country/value/exposure by formulas. It retains only countries with a numeric USD total-reserve observation in **Total Reserves**, retrieves total reserves with `INDEX`/`MATCH`, and calculates `exposure / total reserves * 100`.

The workbook calculation flags are set to force recalculation. Recalculation with LibreOffice (or Excel) is still necessary to populate formula caches. If LibreOffice rewrites formula names for its locale, open the delivered file once in Excel or use the locale-compatible spreadsheet engine required by the task.

## Failure handling

Do not substitute a different gold fixing, currency, price unit, date frequency, or a missing reserve observation. A nonnumeric source marker is missing, not zero. The builder stops with JSON error output when required workbook labels, monthly source observations, source units, or a unique 2025 row cannot be established. This makes a changed IMF export or incompatible template observable instead of silently producing a plausible but invalid result.
