# Formula plan for the supplied supply-shock template

This is a formula-entry plan, not a source of observations. It applies only after the executor has inspected the visible labels and confirmed that they match the template described below. Type the formulas in Excel, fill them down, run Solver, and save the original workbook as `test-supply.xlsx`.

## Source tabs

* Enter PWT `rnna` as source inputs in `PWT!C2:C35`, beside the existing years in column B (1990--2023).
* Enter WEO real GDP level and real GDP growth as source inputs in `WEO_Data!C8:D35` for 2000--2027. Keep the WEO level in the documented **billions of constant-price lari**; the source-tab headers already state that scale. For 2028--2043, use `=$D$35` in column D and `=C(previous row)*(1+D(current row)/100)` in column C.
* Enter annual ECB CFC observations in `CFC data!C2:C29`, adjacent to the existing 1996--2023 time-period keys. Enter a formula link (not copied value) from `CFC data!D2` to the matching PWT capital observation, then fill through 2023. In this template years line up after PWT row 2, so the direct matching links are valid from 1996: `=PWT!C8` in D2 through `=PWT!C35` in D29. Read the ECB unit and PWT scale before making the rate. If ECB reports domestic-currency **units** and PWT rnna is in **millions**, set E2 to `=C2/1000000/D2`; if both inputs are already in millions, use `=C2/D2`. Fill the selected, unit-ledgered formula down.

The executor must verify source metadata and make the source observations comparable before using the ratio. The CFC conversion factor belongs in the depreciation formula (or another visible existing conversion/input cell), so the raw ECB observation remains an auditable source input; never convert a calculated output into a literal.
## Production filter block

The existing labels identify the following rows and columns. Formula text is written in Excel A1 notation; enter the first formula then use Excel Fill Down.

* `Production!B3`: `=AVERAGE('CFC data'!E22:E29)` (the latest eight annual rates: 2016--2023).
* `D6`: `=PWT!C14`, through `D27`: `=PWT!C35`.
* `E6`: `='WEO_Data'!C10`, through `E27`: `='WEO_Data'!C31`.
* `F6`: `=LN(D6)`; `G6`: `=LN(E6)`; `H6`: `=G6-$B$2*F6`; fill each through row 27.
* `K6`: `=H6`; fill through `K27` (raw residual in HP area).
* Initialize `L6:L27` by copying the **values** currently calculated in `K6:K27`. These are the Solver decision cells and remain numeric values after Solver, rather than formulas.
* In the interior second-difference range, enter `=L7-2*L6+L5` only where all three trend cells are inside the decision range. With the visible template this means `M7 = L8-2*L7+L6`, filled through `M26`.
* `N6`: `=K6-L6`, filled through `N27`. It is zero at initialization.
* `P5`: `=SUMXMY2(K6:K27,L6:L27)+100*SUMSQ(M7:M26)`. This is algebraically the required fit plus lambda-100 smoothness objective without relying on legacy array entry.

In Excel Solver set objective `Production!P5` to **Min**, changing `Production!L6:L27`, with no constraints. Use GRG Nonlinear (or the available unconstrained nonlinear quadratic method), retain the solution, and save. Do not replace these decision-cell values with an external HP-filter calculation.

## Scenario table

The scenario table starts at row 36 with 2002 and ends at row 75 with 2041. The existing headings are: D `K/Y`, E `K`, F `Y`, G `LnZ trend`, H `Ystar_base`, I `Investment`, J `ΔK`, K `K_With`, L `Ystar_with`, M `Uplift`, N `Projected GDP`, O `Projected GDP Growth`, and P `Baseline GDP Growth`.

1. Put `=E36/F36` in D36 and fill only through D57 (2002--2023). The requested nine-year anchor is `=AVERAGE(D49:D57)` (2015--2023); place this formula in an existing designated anchor/input cell or use it directly in extension formulas. Do not use a one-year anchor.
2. Link historical capital and GDP: `E36 = PWT!C14` through `E57 = PWT!C35`; `F36 = 'WEO_Data'!C10` through `F57 = 'WEO_Data'!C31`. For every row 58--75, use `=AVERAGE($D$49:$D$57)*F58` in column E, and `='WEO_Data'!C32` through `='WEO_Data'!C49` in column F. (If the same labels occur in a shifted template, derive the equivalent ranges by year rather than using these coordinates.)
3. `G36 = L6` through `G57 = L27`. In `G58`, use `=TREND($G$36:$G$57,$C$36:$C$57,C58)` and fill through G75. `H36 = EXP(G36)*E36^$B$2`, filled down through H75.
4. Link investment by year. Where the year grids are aligned, `I36 = IFERROR(INDEX(Investment!$B$2:$B$9,MATCH($C36,Investment!$A$2:$A$9,0)),0)` and fill down. This is a formula even in no-investment years.
5. In `J36`, enter `=0` and fill down through the row before the shock. At all rows use the recursive formula after the preceding row exists: `= (1-$B$3)*J(previous row)+I(current row)`. Thus the 2026 row is `=(1-$B$3)*J59+I60`. `K36 = E36+J36`; fill down. This makes the incremental-capital timing explicit and avoids applying depreciation to the entire K/Y-extended baseline.
6. `L36 = EXP(G36)*K36^$B$2`; `M36 = L36-H36`; `N36 = F36`; `O36 = 'WEO_Data'!D10`; and `P37 = (H37/H36-1)*100`. Fill the appropriate formulas down through 2041. Set first-row baseline growth to blank or `=NA()` only if the template requires it.

After Excel recalculation, check no calculated cell has `#REF!`, `#VALUE!`, or `#DIV/0!`; check the 2028+ WEO growth cells reference the 2027 rate; and confirm `EXP(G36)*E36^$B$2` equals H36. Keep all formulas and the solved L6:L27 values in the delivered `.xlsx`.

## Unit ledger before Solver

Record the visible source unit/scale beside the source selection while entering it. The PWT source tab retains `rnna` as supplied; WEO's `Scale: Billions` applies to its real-GDP inputs; the ECB CFC API may report domestic-currency **units**. A production residual can absorb a fixed K/Y scale difference when it is used consistently, but the depreciation ratio cannot: its CFC numerator and PWT-capital denominator must first be in the same currency, price basis, and scale. In particular, do not place raw domestic-currency units over a capital input expressed in millions. Preserve this conversion as an Excel formula and verify the resulting recent depreciation rates are dimensionless, not a result of a million-fold scale mismatch.

## Source-entry audit before formula fill

Before entering any formulas, use the workbook's own year column to make a three-item audit for every source tab: (1) Georgia/geography is the selected observation, (2) the selected descriptor is exactly the requested measure (`rnna`; real GDP level; real GDP growth; annual CFC), and (3) all required year keys resolve once. For WEO, verify that the real GDP level is a national-currency **level** and the growth series is **percent change**, not a nominal level or a price index. For the last published forecast year, retain that source growth observation as an input; every later growth cell must be a formula referring to it. Do not enter 2028--2043 as copied source values.

For every imported source number, preserve the displayed precision supplied by the source. Source values are inputs, not calculated answer cells; do not round them merely to make downstream output look plausible. Formulas and Solver values are the only permitted calculated content in the model areas.
