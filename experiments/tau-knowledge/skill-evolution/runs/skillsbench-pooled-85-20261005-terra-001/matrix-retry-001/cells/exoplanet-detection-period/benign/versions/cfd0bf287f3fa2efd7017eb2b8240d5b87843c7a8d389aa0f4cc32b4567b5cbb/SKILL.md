---
name: tess-transit-period
version: 2.0.0
description: Recover a box-shaped exoplanet transit period from a four-column, activity-dominated TESS light curve using quality filtering, transit-preserving detrending, broad period search, and numerical refinement.
---

# TESS transit-period detection

Use this Skill when a light curve has columns **time in days, normalized flux, quality flag, and flux uncertainty**, and quality `0` identifies trusted cadences. The Skill writes one positive orbital period in days with exactly five decimal places.

## Runtime interface

Run `scripts/find_period.py` with a JSON object on standard input:

```json
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt",
  "min_period": 0.2,
  "max_period": null,
  "trials": 3500
}
```

`input_path` and `output_path` are required nonempty strings. `max_period: null` uses `min(15.0, baseline / 1.8)`, retaining periods for which multiple events can occur in the observed baseline. `trials` must be at least 500.

For the supplied task:

```bash
printf '%s\n' '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' | python3 scripts/find_period.py
```

The program writes the requested artifact and emits a JSON diagnostic object on stdout. The artifact, rather than stdout, is the task deliverable.

## Method

1. Parse numeric four-column rows, retain only finite rows with quality exactly zero, and sort by time. No missing cadence is interpolated.
2. Estimate the normal cadence from positive time differences. Remove activity using a quadratic Savitzky--Golay trend whose approximately 0.8-day window is longer than a short transit. Clip only the most extreme residual tails after detrending, so raw negative dips do not control input filtering.
3. For each trial period, fold the detrended data into 180 phase bins and scan circular boxes of two through five bins. The score is the negative mean in the deepest populated box in units of robust residual scatter.
4. Locate several separated broad-grid peaks and numerically refine each in a small local interval at finer than displayed precision. Select the strongest refined folded box, not merely a rounded grid point. A segment-aware, count-weighted BLS statistic and epoch support count are reported as diagnostics for aliases, gaps, and candidate follow-up.
5. Write only the selected refined period as `NN.NNNNN\n`. Rounding happens only after the numerical search.

The full-series folded-box search is the selection statistic because it measures the repeatable signal consistently across the supplied time series. The segment-aware diagnostics should be inspected when they disagree materially with the selected period: such disagreement can indicate a sampling alias, a detrending sensitivity, or insufficient observed events and merits manual phase-fold inspection rather than averaging periods.

## Output and failure handling

On success stdout is a JSON object containing `period_days`, `period_rounded`, the primary box score and location, broad and refined candidate information, cadence count, and segment-aware diagnostics. Confirm that the output file consists of exactly one positive finite decimal number with five digits after the decimal point.

The script emits `{"ok": false, ...}` and exits nonzero without replacing the output when the input is unreadable, fewer than 100 trusted cadences remain, timestamps or requested bounds are unusable, SciPy is unavailable, or no finite positive folded-box candidate exists. It requires only Python, NumPy, and SciPy and does not use network access.
