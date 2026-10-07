# DOTS formula reference

For bodyweight `bw` in kilograms and total `total` in kilograms:

`Dots = ROUND(total * 500 / denominator, 3)`

The denominator is a fourth-degree polynomial:

`a*bw^4 + b*bw^3 + c*bw^2 + d*bw + e`

Published coefficient sets used by this Skill:

| Category | a | b | c | d | e | bodyweight clamp |
|---|---:|---:|---:|---:|---:|---:|
| Men | -0.000001093 | 0.0007391293 | -0.1918759221 | 24.0900756 | -307.75076 | 40--210 kg |
| Women | -0.0000010706 | 0.0005158568 | -0.1126655495 | 13.6175032 | -57.96288 | 40--150 kg |

`TotalKg` is `ROUND(best squat + best bench + best deadlift, 3)`. The formula is only emitted as a usable numeric result when all three lifts are numeric. This avoids treating a missing lift as zero.
