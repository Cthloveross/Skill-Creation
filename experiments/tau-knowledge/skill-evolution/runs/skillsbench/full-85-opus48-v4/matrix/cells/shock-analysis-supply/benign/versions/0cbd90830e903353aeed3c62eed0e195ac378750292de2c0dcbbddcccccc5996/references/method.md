# Formula & verification cheat-sheet

All cells below are **formulas** in the workbook unless marked DATA (downloaded)
or SOLVER (optimizer output). Addresses/ranges are placeholders — confirm the
real ones with inspect_workbook.py.

## Residual and HP filter
- `LnK = LN(K)`, `LnY = LN(Y)`.
- `LnZ = LnY - alpha*LnK`  (two-factor Solow residual).
- HP decision column starts = duplicate of LnZ (sanity: second-order diff and
  LnA-Trend read ~0 at this start).
- second-order diff at interior t: `(tau_{t+1}-tau_t)-(tau_t-tau_{t-1})`.
- objective (P5): `SUMSQ(LnZ - tau) + lambda*SUMSQ(second_order_diffs)`
  i.e. fit penalty + lambda*smoothness penalty, BOTH terms.
- lambda = 100 for annual data (6.25 is an alternative annual calibration;
  1600 is quarterly). Use what the instruction/workbook specifies.
- Decision column after solving = SOLVER values from hp_filter.py trend.
- Extend trend with Excel `TREND(known_tau, known_x, new_x)`.

## Depreciation
- `delta_t = CFC_t / K_t` only after CFC and K share currency+valuation+scale.
- Production delta (e.g. B3) = `AVERAGE(last 8 delta_t)` (use stated window).

## Capital extension & shock
- `K/Y` per year where both exist; anchor = `AVERAGE(last N K/Y)` (stated N).
- `K_proj = (K/Y)_anchor * Y_proj`.
- `Y_proj_{t+1} = Y_t*(1+g/100)` holding final WEO growth g constant.
- `K_with_{t+1} = (1-delta)*K_with_t + I_additional_t`; K_with starts at
  baseline K at shock onset; I in constant prices (deflate only if nominal).
- `Ystar_base = EXP(LnZ_trend)*K^alpha`.
- `Ystar_with  = EXP(LnZ_trend)*K_with^alpha`.
- `uplift = Ystar_with - Ystar_base`  (also % of baseline where asked).

## Verification identities (judge on units/identity, not on expected answers)
- Rowwise: `EXP(LnY - alpha*LnK)*K^alpha ~= Y` (floating point aside) ->
  detects bad scale conversions.
- Sanity column ~0 at the duplicated (pre-solve) trend.
- Objective at written trend <= objective at any starting trend (recompute with
  hp_filter.py and compare).
- WEO projection formulas begin only after the last observed year; observed
  values stay unchanged.
- Uplift non-negative and diminishing per extra unit of capital (alpha<1).
- No formula cell left blank / #REF! / #VALUE! / None after recalc.

## Data sources (confirm variable/series by metadata, not by a fixed code)
- PWT (rug.nl/ggdc): capital stock at constant national prices; read the PWT
  metadata sheet to pick the variable (background cites `rnna`).
- IMF WEO: real GDP level (national-currency scale) and real GDP growth rate;
  distinguish level vs growth and verify units.
- ECB SDW (Georgia): annual consumption of fixed capital; select by geography,
  frequency, sector, transaction, valuation, unit, currency — note its scale
  and price basis for the delta ratio.
