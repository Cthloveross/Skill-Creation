# DOTS coefficient reference

The DOTS (Dynamic Objective Team Scoring) coefficient normalizes a lifter's
total by bodyweight:

```
Dots = 500 / (A + B*x + C*x^2 + D*x^3 + E*x^4) * TotalKg
```

where `TotalKg = Best3SquatKg + Best3BenchKg + Best3DeadliftKg` and `x` is the
bodyweight in kilograms, clamped to the published domain for the lifter's sex.

## Coefficients (A, B, C, D, E)

Men:
```
A = -307.75076
B =  24.0900756
C =  -0.1918759221
D =   0.0007391293
E =  -0.000001093
```

Women:
```
A =  -57.96288
B =   13.6175032
C =   -0.1126655495
D =    0.0005158568
E =   -0.0000010706
```

## Bodyweight clamp (input domain)

```
Men:   x = min(max(bodyweight, 40), 210)
Women: x = min(max(bodyweight, 40), 150)
```

Sex handling (OpenPowerlifting dispatch): `"M"` and `"Mx"` use the men's
equation; `"F"` uses the women's equation. Any other value defaults to the
women's equation. These coefficients and the clamp ranges are taken from the
authoritative OpenPowerlifting implementation (crates/coefficients/src/dots.rs),
which is the correct reference for `openipf`-sourced data.

## Notes

- Preserve the published coefficient order and the boundary (clamp) rules.
- Keep full precision during the computation and round only the final `Dots`
  value to the requested number of decimal places (default 3).
- `TotalKg` is written as an exact Excel sum; blank lift cells behave as 0 in
  Excel addition, matching the source rows.
- openpyxl writes formulas but does not compute them; recalculate with a
  spreadsheet engine (LibreOffice headless, always-recalc) before a value
  reader opens the file.
