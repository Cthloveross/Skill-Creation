---
name: supply-side-shock-potential-gdp
description: >
  Build a fully formula-driven Excel workbook that estimates the potential-GDP
  uplift of a multi-year investment spending shock to a small open economy using
  a Cobb-Douglas production function. Covers data entry (PWT capital stock, IMF
  WEO real GDP level/growth, ECB consumption of fixed capital), a Solver-style
  HP filter of the two-factor Solow residual (LnZ), K/Y capital extension, and
  baseline vs. with-shock Y* and uplift. Use when a task hands you a template
  xlsx (e.g. test-supply.xlsx) with PWT / WEO_Data / CFC data / Production /
  Investment sheets and asks for an Excel-only, formula-preserving model.
---

# Supply-side investment-shock potential-GDP model

## What the task gives you and what you must produce

The host copies a template workbook into the workspace (read the manifest; the
opening also names it, e.g. `/root/test-supply.xlsx`). You must populate it and
leave it as the deliverable with **all computed cells driven by formulas** —
only genuinely exogenous data (downloaded observations) and the Solver output
column may be plain numbers. Do not hardcode any value that the instruction
says to "calculate", "link", or "extend".

Read the live instruction every run: the country, shock size, shock length,
start year, sheet names, column letters, and row ranges are **instance facts**.
Never reuse numbers, cell addresses, or series IDs from this document or from
any worked example — discover them from the actual workbook and the actual
downloaded data.

## Method (frozen background, condensed)

- **Production function**: `Y = exp(LnZ) * K^alpha`. Two-factor Solow residual
  `LnZ = ln(Y) - alpha*ln(K)` (bundles TFP and labor). `alpha` = capital's
  share — read it from the workbook, do not invent it.
- **HP filter** of `LnZ` to get the trend: minimize
  `sum((y_t - tau_t)^2) + lambda*sum((tau_{t+1}-tau_t)-(tau_t-tau_{t-1}))^2`.
  Annual data → `lambda = 100` (confirm against any value the workbook states).
  The exact minimizer is the solution of `(I + lambda*D'D) tau = y` where `D`
  is the `(T-2)xT` second-difference matrix; this equals the Solver optimum.
- **TREND extension**: extend `LnZ_trend` to the projection horizon with a
  least-squares line (Excel `TREND`).
- **Depreciation**: `delta_t = CFC_t / K_t`. CFC and K must share currency,
  price basis, and scale before dividing — see the unit trap below. Production
  `delta` = average of the most recent 8 years (use the window the instruction
  states, by formula).
- **Capital extension**: `K/Y` anchor = average of the most recent N years the
  instruction names (e.g. 9), then `K_proj = (K/Y)_anchor * Y_proj`.
- **WEO extension**: hold the final forecast-year growth rate constant;
  `Y_{t+1} = Y_t*(1+g/100)`.
- **Shock**: `K_with_{t+1} = (1-delta)*K_with_t + I_additional_t` (investment in
  constant prices, deflated if nominal; read the Investment sheet to see whether
  it is already real). `Y*_with = exp(LnZ_trend)*K_with^alpha`.
  **Uplift = Y*_with - Y*_base** (also as % of baseline where asked).

## Unit / scale trap (read carefully before computing delta)

PWT `rnna` is a constant-national-price capital stock in millions of 2017 US$;
ECB CFC for the economy is typically a current-price national-currency series,
possibly in a different scale. A ratio is only dimensionless when numerator and
denominator share currency, valuation (current vs constant), price base, and
scale. **Read each downloaded series' visible metadata** (unit, currency,
scale, valuation) and apply any conversion once, explicitly, in a labeled input
or formula before forming `CFC/K`. Validate by the rowwise identity
`EXP(LnY - alpha*LnK) * K^alpha ≈ Y` (floating point aside); a mismatch means a
scale conversion is wrong. Do not accept or reject on an expected delta value;
judge on units and the identity.

## Workflow for the executor

1. **Inspect the workbook first.** Run `scripts/inspect_workbook.py` to dump
   every non-empty cell (label text, formulas, cached values) per sheet. From
   the visible labels locate: PWT target columns, WEO rows for level and growth
   and the projection block, CFC columns C/D, Production `B3` (delta), the
   D/E/F input and LnK/LnY columns, the HP-filter block (LnZ column F, the
   LnZ_HP decision column L6:L27, the second-difference and sanity column, the
   objective cell P5), `alpha`, the production-function K/Y and Y* block
   (G36:G57 etc.), and the Investment linkage column I. Treat the ranges in the
   instruction as hints to confirm, not assume.
2. **Collect data at runtime** (internet is allowed; use the browser/Playwright
   MCP as the instruction directs): PWT capital stock (read the PWT metadata
   sheet to pick the right variable), IMF WEO real GDP level and real GDP growth
   for the stated year span, ECB annual CFC for the economy. Record source,
   variable definition, year coverage, unit/scale for each before writing.
3. **Write cells** with `scripts/apply_cells.py` (or openpyxl directly):
   downloaded observations as values; everything the instruction says to link,
   calculate, or extend as **formulas** (cell references across sheets, `LN`,
   `AVERAGE` over the stated window, `TREND`, `(1+g/100)` chains, Cobb-Douglas
   `EXP(...)*...^alpha`, `K_with` recursion, uplift). Keep the template layout.
4. **HP filter.** Set column F = `LnZ` by formula, duplicate it into the
   decision column as the Solver starting point, write the second-order
   difference and `LnA-Trend` sanity formulas (these read 0 when the trend
   equals the raw series — confirm this before optimizing), and the objective
   formula in P5 (fit penalty + lambda * smoothness penalty, both terms).
   Then compute the optimal trend with `scripts/hp_filter.py` (closed-form equal
   to Solver's minimum) and write those numbers into the decision range
   (L6:L27). The decision column is legitimately numeric because it is Solver
   output; every other HP cell stays a formula. Use `lambda` for annual data
   (100 unless the workbook states otherwise). If a working spreadsheet Solver
   is available you may run it instead, but the closed form reaches the same
   objective minimum.
5. **Recalculate and verify** with `scripts/recalc_verify.py`, which recalcs via
   LibreOffice (install `libreoffice-calc` if `soffice` is missing — internet
   is allowed) and reads cached values for cells you pass in `check_cells`.
   Confirm: no formula cell is blank/`#REF!`/`#VALUE!`/None; the sanity column
   is ~0 at the starting (duplicated) trend; the objective is minimized at the
   written trend (recompute with `hp_filter.py` and compare); the rowwise
   `EXP(LnY-alpha*LnK)*K^alpha ≈ Y` identity holds; delta uses the right window;
   K/Y anchor uses the stated window; WEO projection starts after the last
   observed year and compounds the held growth; uplift = with - base and is
   non-negative and diminishing (alpha<1).
6. **Save** back to the deliverable path. The recalculated cached values must be
   present so an independent reader sees numbers, not stale formulas.

## Failure handling

- Missing/renamed sheet, column, or label → re-inspect and map by label text;
  report if a required region genuinely does not exist rather than guessing.
- A data source unreachable or a series ambiguous → record which source failed
  and do not fabricate values; leave the dependent formulas in place so the
  model completes once the value is supplied.
- LibreOffice unavailable and uninstallable → still write all formulas; note
  that cached values could not be refreshed, and verify the arithmetic you can
  reproduce in Python against the written inputs.
- Investment series already real vs nominal → decide from its visible labels;
  only deflate if nominal, and record the deflator source.

## Scripts (stdin JSON → stdout JSON)

- `inspect_workbook.py` — in `{"path":...,"max_cells_per_sheet":2000?}`; out
  `{"sheets":[{"title","dims","cells":[{"cell","value"|"formula"+"cached"}]}]}`.
- `hp_filter.py` — in `{"series":[...],"lambda":100}`; out
  `{"trend":[...],"second_diffs":[...],"objective":...,"lambda":...}`. The
  trend is the exact HP minimizer; write it into the decision range.
- `apply_cells.py` — in `{"path":...,"out":...?,"cells":[{"sheet","cell",
  "formula"|"value"}]}`; out `{"written":n,"out":path}`. Writes formulas/values,
  preserving other cells.
- `recalc_verify.py` — in `{"path":...,"check_cells":[{"sheet","cell"}]}`; out
  `{"recalc":path|null,"checks":[{"sheet","cell","value"}],"errors":[...]}`.
  Recalcs with LibreOffice headless and returns post-recalc values.

See `references/method.md` for the formula cheat-sheet and verification identities.
