---
name: tess-transit-period
version: 1.3.0
description: Filter a four-column TESS light curve, remove smooth stellar activity, and identify a repeated box-shaped transit period while comparing global and gap-aware detrending diagnostics.
---

# TESS transit-period detection

Use this Skill for a light curve whose first four columns are **time, normalized flux, quality flag, flux uncertainty**, where quality `0` denotes a trusted cadence. It is intended for activity-dominated photometry containing short transit-like dips.

The Skill retains finite quality-zero observations, preserves gaps rather than interpolating them, detrends smooth variability on a substantially longer timescale than a transit, and searches folded light curves using both a simple phase-box diagnostic and a count-weighted box statistic. The second statistic and epoch check prevent an isolated poorly sampled dip from being treated as a planet candidate.

## Runtime interface

Run `scripts/find_period.py` with one JSON object on standard input:

```json
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt",
  "min_period": 0.2,
  "max_period": null,
  "global_trials": 3500,
  "bls_trials": 5000
}
```

`input_path` and `output_path` are required nonempty strings. Numeric input rows may be whitespace- or comma-separated; nonnumeric header rows are ignored. With `max_period: null`, the upper bound is `min(15.0, baseline / 1.8)` days. `global_trials` and `bls_trials` must both be at least 500.

For the supplied task, execute:

```bash
printf '%s\n' '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' | python3 scripts/find_period.py
```

The program writes the requested artifact and emits one JSON diagnostic object on stdout. The artifact, not stdout, is the required deliverable.

## Detection procedure

1. Parse the documented four columns, retain only finite rows with quality exactly zero, and sort by time. Invalid rows and flagged cadences are excluded; temporal gaps remain gaps.
2. Construct two residual light curves with quadratic Savitzky--Golay activity trends:
   - a 0.8-day full-series trend, and
   - a 0.7-day trend independently in each contiguous observing segment.

   Residual tails are conservatively clipped only after trend subtraction. The two residual constructions expose candidates that are sensitive to long gaps or a particular activity model.
3. Search the full multi-event range with two complementary folded phase-box profiles. The global profile scans short boxes in 180 phase bins. The count-weighted BLS profile scans 1--8-bin boxes in 240 phase bins, requires at least eight in-box observations, and measures inside-versus-outside depth with robust scatter normalization.
4. Re-evaluate five-decimal candidates from the leading peaks of both profiles, including nearby representable values. For every candidate, calculate both profile ratios and count distinct orbital epochs having at least two in-box measurements with below-median residual flux.
5. Prefer candidates that are within 1.5% of the maximum in **both** independent profiles and have at least three supported epochs. If no candidate meets all strict criteria, select the highest reproducible consensus score among three-or-more-epoch candidates and report that the strict intersection was unavailable. This fallback is explicit because aliased peaks or a single phase-bin outlier can make otherwise incompatible periodograms disagree.
6. Write exactly one positive decimal period, formatted as `NN.NNNNN\n`, to `output_path`.

## Validation and failure handling

The JSON result includes the selected period, both box scores and ratios, support count, profile peak periods, search range, cadence count, and whether the strict cross-profile criterion was met. A valid output file contains no commentary or extra values.

The script returns a JSON error and exits nonzero without writing a new artifact if SciPy is unavailable, fewer than 100 trusted finite cadences remain, timestamps cannot define a positive cadence/baseline, bounds are invalid, or no positively scored multi-epoch candidate is found. It uses no network or external action.
