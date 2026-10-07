---
name: reserves-at-risk-calc
description: >
  Build the "Reserves at Risk" (RaR) Excel workbook for a gold-reserve
  market-risk analysis. Use when a task supplies a template .xlsx with sheets
  such as "Gold price", "Answer", "Value", "Volume", and "Total Reserves" and
  asks to (1) download IMF primary-commodity gold prices and compute monthly log
  returns plus rolling volatilities, (2) assemble per-country 2025 gold-reserve
  values and a near-term valuation exposure, and (3) compute a quantile-based
  Reserves-at-Risk measure relative to total reserves. All derived numbers must
  be Excel formulas (recalculated with an independent engine), not Python
  literals. The Skill inspects the actual workbook at runtime and never hardcodes
  cell addresses, country lists, prices, or answer values.
---

# Reserves at Risk (RaR) workbook builder

## What the task requires (public contract)

The instruction has three steps and one output file
`/root/output/rar_result.xlsx`. The template is copied to `/root/data/test-rar.xlsx`
(confirm the real path from the task inputs at runtime).

- **STEP 1 — Gold price & volatility.** Download the IMF global commodity price
  Excel database (https://www.imf.org/en/research/commodity-prices), extract the
  **gold price in US$ per troy ounce**, and paste the monthly series into the
  `Gold price` sheet. In the sheet's columns **C / D / E** compute, as Excel
  formulas: **monthly log return** (ln(P_t/P_{t-1}), multiplied by 100 to show a
  percentage, per the HINT), the **3-month volatility**, and the **12-month
  volatility**. In the `Answer` sheet fill the **four blanks of STEP 1 (rows
  3-6)**: use the *latest* available data for the 3-month and 12-month
  volatility, and derive the **3-month annualized** figure from the 3-month
  volatility.
- **STEP 2 — 2025 reserve values & exposure.** In `Answer` STEP 2 area (rows
  **11-12**) list every country that has **2025 gold-reserve value** data in the
  `Value` sheet, with its value. Then add any country that appears in the
  `Volume` sheet with 2025 data **but is absent from `Value`**, converting its
  volume to a value by multiplying by a gold price equal to the **Jan–Sep 2025
  average** (used as a proxy for the 2025 annual price). Compute the **Gold price
  exposure** in row **13** (a near-term valuation swing).
- **STEP 3 — Reserves at Risk.** Replicate STEP 2's countries, reserve values,
  and the gold-price volatility into rows **20-22**. Use **INDEX+MATCH or
  XLOOKUP** to pull each country's **2025 total reserves** from the
  `Total Reserves` sheet into row **23**; drop any country lacking 2025 total
  reserves. Compute **RaR** in row **24** from the STEP 3 table.

Constraint: *computation must be done with Excel formulas*. Paste only the raw
gold series as values; everything derived (log returns, volatilities,
exposures, lookups, RaR) must be live formulas, then recalculated by a compatible
engine so cached values are present and error-free.

## Method and assumptions (frozen background)

- A reserve is a **stock**; production is a flow. A physical quantity (troy
  ounces / tonnes) and a monetary value are different dimensions — convert with a
  price on a **compatible unit, currency, and date**. Volume→value needs the
  gold price in the matching unit.
- **Log return** r_t = ln(P_t / P_{t-1}); the HINT asks to express it ×100 as a
  percentage. Keep that scale consistent downstream.
- **Rolling volatility** = sample standard deviation of the trailing window of
  monthly log returns (3 and 12 months). Volatility measures dispersion, not
  direction, and is in the same (percentage) units as the returns.
- **Annualization** of a monthly volatility uses √12 (monthly→annual). "3-month
  annualized" = 3-month monthly volatility × √12 unless a sheet label states
  another convention — verify the label before committing.
- **Quantile risk / RaR** multiplies an exposure (a value) by a volatility and a
  **confidence z-value** for the stated probability/horizon. z is a model
  parameter tied to a probability convention: read any z-cell / confidence label
  in the `Answer` sheet and respect its **stored precision** (an exact normal
  quantile, a table constant like 1.645/2.326, and a rounded display value are
  not interchangeable). Store the parameter once and reference it consistently;
  do not mix differently rounded copies.
- **Exposure labels differ**: gross gold value, value relative to total
  reserves, and a near-term valuation swing answer different questions. STEP 2's
  "gold price exposure" is a near-term swing; STEP 3's RaR is risk relative to
  the total-reserve base. Keep them distinct.
- **Missing ≠ zero.** A country without 2025 data must be excluded, not treated
  as zero. Keep provenance when normalizing country names across sheets; do not
  silently merge distinct entities.
- **Formula portability.** LibreOffice (the independent recalculation engine
  here) may not support `XLOOKUP`. **Prefer INDEX+MATCH** so the delivered file
  recalculates error-free in a compatible engine; verify formula text, cached
  values, and absence of errors.

## Tools in this Skill (`scripts/`)

Every script reads one JSON object from **stdin** and writes one JSON object to
**stdout**. Run with `python3 scripts/<name>.py <<'JSON' ... JSON`.

1. `inspect_workbook.py` — dump sheet names and a bounded grid of cell values
   **and** formulas so you can locate labels, blank cells, data ranges, and any
   pre-existing z/confidence inputs.
   - in: `{"path": "...xlsx", "max_rows": 60, "max_cols": 40, "sheets": [..]?}`
   - out: `{"sheets": {name: {"dims": [r,c], "cells": [[addr, value, formula], ...]}}}`
2. `fetch_imf_gold.py` — download the IMF monthly commodity file and extract the
   gold (US$/troy ounce) monthly series. Tries several official URLs; honors an
   explicit `urls` list and allows a pre-downloaded `file`.
   - in: `{"urls": [..]?, "file": "local.xlsx"?, "out_csv": "..."?}`
   - out: `{"source": url_or_file, "header": str, "unit": str,
            "series": [["2025M1", 2834.1], ...]}` (chronological)
   - If every source fails it returns `{"error": ..., "tried": [...]}`; then
     download manually via the task's internet access and pass `file`.
3. `write_cells.py` — apply a list of value/formula writes to a workbook and save
   (used to paste the gold series as values and to write all formulas). This is
   the mechanical writer; **derive every address and formula from runtime
   inspection**, not from this document.
   - in: `{"in_path": "...", "out_path": "...",
            "cells": [{"sheet": "Gold price", "cell": "B14", "value": 2834.1},
                      {"sheet": "Gold price", "cell": "C14", "formula": "=LN(B14/B13)*100"}, ...]}`
   - out: `{"written": n, "out_path": "..."}`
4. `recalc_libreoffice.py` — force a full recalculation with LibreOffice headless
   (creates a profile that sets ODF/OOXML recalc = Always) and rewrite the xlsx
   so cached values exist.
   - in: `{"path": "...xlsx", "out_dir": "..."?}`
   - out: `{"recalculated": "...xlsx", "stdout": "...", "returncode": 0}`
5. `verify_workbook.py` — reopen the recalculated file in value-reading mode and
   check that requested cells are numeric and error-free.
   - in: `{"path": "...xlsx", "checks": [{"sheet": "Answer", "cell": "B3"}, ...]}`
   - out: `{"ok": bool, "results": [{"sheet","cell","value","is_number","is_error"}, ...]}`

## End-to-end procedure for the executor

1. **Locate inputs.** Read the task inputs; confirm the template path
   (`/root/data/test-rar.xlsx`) and create `/root/output/`.
2. **Inspect the template.** Run `inspect_workbook.py` on the template. Record,
   for each sheet: where the `Gold price` dates/prices start and which cells in
   columns C/D/E are blank; the exact `Answer` cells for STEP 1 rows 3-6, STEP 2
   rows 11-13, STEP 3 rows 20-24; the row/label meaning of each STEP 2/STEP 3
   row; and whether a confidence/z or annualization-factor cell already exists.
   Read the actual labels — do not assume the orientation (rows vs columns) or
   that row N means a particular quantity; let the labels decide.
3. **Fetch gold prices.** Run `fetch_imf_gold.py`. Confirm the unit text contains
   "troy"/"ounce" and the series is monthly US$. If it fails, download the file
   with the shell (the task allows internet) and pass it via `file`.
4. **Populate `Gold price` as values + formulas.** With `write_cells.py`: paste
   the monthly dates and prices as **values** into the data columns; write column
   C as `=LN(P_t/P_{t-1})*100`, column D as the sample std-dev of the trailing
   3 monthly log returns, column E as the trailing-12 std-dev — using the
   workbook's own column letters and the first row that has a prior price. Fill
   C/D/E only where the template left them blank; preserve existing structure,
   styles, and other sheets.
5. **Answer STEP 1 (rows 3-6).** Write formulas that reference the *latest*
   populated 3-month and 12-month volatility cells and the latest monthly log
   return; compute the 3-month annualized value as `=<3m vol>*SQRT(12)` (confirm
   against any label). Prefer references over re-typed numbers so the chain stays
   formula-driven.
6. **Answer STEP 2 (rows 11-13).** From the `Value` sheet, list each country with
   2025 gold-reserve value; pull values with INDEX+MATCH referencing the
   country key and the 2025 column. For countries in `Volume` with 2025 data but
   absent from `Value`, append them and set value = volume × (Jan–Sep 2025
   average gold price), computing that average with `AVERAGE` over the Jan–Sep
   2025 cells in `Gold price`. Keep missing distinct from zero. Compute the gold
   price exposure in row 13 as the workbook's labelled near-term-swing formula
   (read the label to confirm which volatility/factor it uses).
7. **Answer STEP 3 (rows 20-24).** Copy STEP 2 countries, values, and the
   gold-price volatility into rows 20-22. In row 23 use **INDEX+MATCH** (portable
   across engines) to fetch each country's 2025 total reserves from
   `Total Reserves`; drop any country whose 2025 total reserve is missing. In row
   24 write the RaR formula implied by the labels (exposure × volatility × z,
   expressed per total-reserve base if the label says so), referencing a single
   stored z/confidence value at its documented precision.
8. **Save, recalculate, verify.** Save to `/root/output/rar_result.xlsx`, run
   `recalc_libreoffice.py` on it (overwrite the output with the recalculated
   copy), then `verify_workbook.py` on every STEP 1/2/3 answer cell you filled.
   Reject the artifact if any target cell is blank, non-numeric, or an error
   (`#NAME?`, `#REF!`, `#DIV/0!`, etc.); if `XLOOKUP` triggers `#NAME?`, rewrite
   those lookups as INDEX+MATCH and recalc again. Also re-inspect to confirm the
   source sheets (`Value`, `Volume`, `Total Reserves`) are unchanged and the
   layout is intact.

## Validation checklist (derive from the request, not hidden tests)

- Gold series: monthly, US$/troy ounce, chronological, pasted as values; the
  Jan–Sep 2025 cells exist and average cleanly.
- Columns C/D/E are formulas; C uses ×100 scaling; D/E use the correct trailing
  windows and the same percentage scale.
- STEP 1 rows 3-6 reference the *latest* volatilities; the annualized cell
  equals 3-month vol × √12 (or the labelled convention).
- STEP 2 includes exactly the `Value` 2025 countries plus `Volume`-only 2025
  countries converted at the Jan–Sep average; no missing-as-zero.
- STEP 3 lookups are INDEX+MATCH (portable), countries without 2025 total
  reserves are dropped, and RaR references one consistently-stored z value.
- Recalculated workbook opens with numeric, error-free target cells and the
  original layout and source sheets preserved.

## Failure handling

- IMF download blocked: retry with a browser-like User-Agent (already set in the
  fetch script), try the alternate URLs, or download via the shell and pass
  `file`. Never fabricate prices.
- Ambiguous labels (which volatility feeds exposure/RaR, z precision,
  annualization factor): resolve from the workbook's own labels and any
  pre-filled cells; state the assumption rather than guessing silently.
- Unsupported function on recalc: replace with the portable equivalent
  (INDEX+MATCH) and recalculate again before accepting the file.
