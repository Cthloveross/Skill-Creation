---
name: tess-transit-period
version: 1.5.0
description: Recover a repeated, box-shaped exoplanet transit period from an activity-dominated four-column TESS light curve using quality filtering, gap-aware detrending, and a refined count-weighted BLS search.
---

# TESS transit-period detection

Use this Skill for a table whose first four columns are **time in days, normalized flux, quality flag, and flux uncertainty**, where quality `0` marks trusted observations. It writes one orbital period in days, displayed to exactly five decimal places.

The primary selection method is deliberately gap-aware and requires repeated observed transit epochs. This avoids promoting a deep event introduced or emphasized by smoothing across TESS observing gaps. A separate full-series box search is reported as an alias/detrending-sensitivity diagnostic; disagreement is evidence to inspect rather than a reason to silently average unrelated candidate periods.

## Runtime interface

Run `scripts/find_period.py` with one JSON object on standard input:

```json
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt",
  "min_period": 0.25,
  "max_period": null,
  "bls_trials": 5000,
  "global_trials": 3500
}
```

`input_path` and `output_path` are required nonempty strings. Input rows may be whitespace- or comma-separated; nonnumeric header rows are ignored. With `max_period: null`, the upper bound is `min(15.0, baseline / 1.8)`, which retains a multi-event search range. Both trial counts must be at least 500.

For the supplied task:

```bash
printf '%s\n' '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' | python3 scripts/find_period.py
```

The script writes the artifact and emits a JSON diagnostic object to stdout. The artifact, not stdout, is the requested deliverable.

## Method

1. Retain only rows having quality exactly zero and finite time, flux, and uncertainty. Sort by time; do not interpolate gaps.
2. Split at long cadence gaps and remove a local quadratic Savitzky--Golay trend in every segment. The approximately 0.7-day trend scale targets slower activity while retaining short transit-shaped dips. Clip only extreme *residual* tails.
3. Search trial periods by folding into 240 bins and scanning circular boxes one through eight bins wide. The statistic is the robust-scatter-normalized inside/outside depth with its sampling-count weight.
4. Refine leading broad-grid peaks directly at five-decimal presentation precision. Accept a candidate only when its deepest folded box is supported by at least three distinct orbital epochs, each with two or more below-median in-box samples. Select the highest-scoring supported candidate.
5. Independently calculate a 180-bin full-series diagnostic after a 0.8-day trend removal. Compare its peak, the selected candidate's diagnostic score, transit support, and competing aliases when interpreting the result. It is intentionally reported separately because smoothing across gaps can favor a sparsely observed long-period excursion.
6. Write only `NN.NNNNN\n` after period refinement.

## Validation and failure handling

A successful stdout object includes the selected period, refined BLS score and box location, number of supported epochs, broad-search peak, full-series diagnostic peak, cadence count, and segment count. Confirm that the output file contains exactly one positive finite decimal value with five digits following the decimal point and no explanatory text.

The program emits JSON with `ok: false`, exits nonzero, and does not replace the output artifact if the file is unreadable, too few trusted samples remain, timestamps are unusable, bounds are invalid, SciPy is absent, or no positive candidate has repeated-epoch support. It uses no network or external service.
