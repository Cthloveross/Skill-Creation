---
name: tess-transit-period
version: 1.2.0
description: Detect a repeatedly supported box-shaped transit period in a four-column TESS light curve with flagged cadences and strong stellar variability, then write one period in days to five decimal places.
---

# TESS transit-period detection

Use this Skill for a light curve with columns **time, normalized flux, quality flag, flux uncertainty**, where quality flag `0` means a trusted cadence. It filters invalid or flagged observations, removes smooth activity without interpolating gaps, and searches for a short, repeatedly observed box-shaped dimming.

## Runtime interface

Run `scripts/find_period.py` with one JSON object on standard input:

```json
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt",
  "min_period": 0.25,
  "max_period": null,
  "trials": 5000
}
```

`input_path` and `output_path` are required nonempty strings. The input may be whitespace- or comma-separated and may contain header lines; each numeric row must provide the documented first four columns. With `max_period: null`, the upper search bound is `min(15, baseline / 1.8)` days. The default interval begins at 0.25 days to focus on periodically repeatable multi-event candidates.

For the supplied task:

```bash
printf '%s\n' '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' | python3 scripts/find_period.py
```

The script emits a JSON diagnostic object on stdout and writes the required artifact itself. Its stdout is diagnostic; the deliverable is `output_path`.

## Method

1. Read numeric rows, retain only finite time, flux, and uncertainty values with quality exactly zero, and sort by time. Gaps are retained as gaps rather than filled.
2. Form two transit-preserving residual series using quadratic Savitzky--Golay trends. One uses a 0.8-day global window; the other uses a 0.7-day window independently within contiguous observing segments, so a long data gap cannot influence the local trend. Extreme residual tails are clipped only after detrending.
3. Fold each residual series at 5,000 trial periods. At every period, evaluate circular phase boxes of 1--8 bins and use a count-weighted inside-versus-outside depth statistic. This favors coherent transit dips with enough observed cadences over a single low-count excursion.
4. Re-evaluate displayable five-decimal candidates from the leading periods of both detrendings. A selected candidate must have a folded box dip supported by at least three observed orbital epochs, each with at least two in-box measurements and a below-median residual.
5. Prefer a repeatedly supported candidate that is within 1.5% of the best score under **both** detrending variants. This guards against choosing a peak caused by a particular smoothing or gap treatment. Among qualifying candidates, choose the strongest balanced score. The period is evaluated at its final five-decimal value before it is written.
6. Write exactly `NN.NNNNN\n` to `output_path`.

## Validation and failure handling

A valid artifact is one positive finite decimal value with exactly five digits after the decimal point. Successful diagnostics include the selected period, scores and normalized score ratios for both residual constructions, supported-epoch count, search bounds, and cadence count.

The script returns JSON error output and exits nonzero without creating a result when SciPy is unavailable, fewer than 100 trusted finite cadences remain, the time range is invalid, or no finite positively scored candidate is found. It makes no network, banking, or other external action.
