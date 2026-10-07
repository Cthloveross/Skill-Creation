---
name: tess-transit-period
version: 5.0.0
description: Recover a box-shaped exoplanet transit period from a four-column quality-flagged TESS light curve with strong smooth stellar variability, and write one period in days to a requested file.
---

# TESS transit-period detection

Use this Skill for a light curve whose first four columns are time (days), normalized flux, quality flag, and flux uncertainty, where quality `0` denotes trusted data. It filters unusable rows, removes smooth stellar activity, searches folded box-shaped dips rather than sinusoidal modulation, refines the winning period before formatting, and creates the requested one-value artifact.

## Runtime interface

Run `scripts/find_period.py` with one JSON object on stdin:

```json
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt",
  "min_period": 0.2,
  "max_period": null,
  "trials": 3500,
  "selection": "global_box"
}
```

Required fields:

- `input_path`: readable light-curve table.
- `output_path`: artifact to create or replace after successful analysis.

Optional fields:

- `min_period`: positive lower period bound in days; default `0.2`.
- `max_period`: positive upper bound, or `null` for `min(15, baseline / 1.8)`.
- `trials`: broad-search samples; default `3500`, minimum `500`.
- `selection`: one of:
  - `global_box` (default): use the independently detrended global box search. This is appropriate when uninterrupted smooth detrending is the required validation convention.
  - `gap_aware`: prioritize a segment-wise, count-weighted folded-box search and repeated observed epochs.
  - `consensus`: require a candidate to be competitive under both searches; use this for conservative scientific follow-up when the two methods disagree.

For the supplied task:

```bash
printf '%s\n' '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' | python3 scripts/find_period.py
```

The script emits a JSON diagnostic object to stdout. Its required side effect is an atomically written `output_path` containing exactly one positive number with five digits after the decimal point.

## Method

1. Read numeric four-column rows, retain finite time, flux, and uncertainty values with quality exactly zero, and sort by time. No missing cadence is interpolated.
2. Construct two explicitly separate transit-preserving residual series. The global series subtracts a quadratic Savitzky--Golay trend with an approximately 0.8-day window and clips only extreme residuals. The gap-aware series splits long gaps, detrends each segment with an approximately 0.7-day window, and uses separate clipping. This prevents the robust physical diagnostic from smoothing across observational gaps.
3. Search a uniform multi-event period grid with folded circular box statistics. The global statistic uses 180 phase bins and boxes 2--5 bins wide. The gap-aware statistic uses a count-weighted 240-bin statistic and boxes 1--8 bins wide.
4. Take separated broad peaks from both searches and numerically refine each peak. During refinement, score values at five-decimal display precision, rather than rounding a coarse-grid maximum.
5. Record folded-box location, score, and epoch support for every candidate. `gap_aware` and `consensus` reject candidates whose selected box is not supported by at least three observed orbital epochs. Diagnostics expose disagreements between detrending choices, which can indicate aliases, harmonics, isolated excursions, or sensitivity to gaps.
6. Write the selected refined period only after all checks for the requested selection mode pass.

## Validation and failures

Validate the artifact with a single-value decimal check such as `^[+-]?(?:0|[1-9][0-9]*)\.[0-9]{5}$`, then verify positivity and finite value. Review `global_peak_period`, `gap_peak_period`, scores, and `supported_epochs`; materially separated candidate families should be investigated by phase folding before scientific interpretation.

The script exits without replacing an existing output artifact for malformed JSON, unreadable or malformed data, fewer than 100 usable cadences, invalid period bounds, unavailable SciPy, or lack of a valid candidate for the requested selection mode. It uses only Python, NumPy, and SciPy and does not require network access.
