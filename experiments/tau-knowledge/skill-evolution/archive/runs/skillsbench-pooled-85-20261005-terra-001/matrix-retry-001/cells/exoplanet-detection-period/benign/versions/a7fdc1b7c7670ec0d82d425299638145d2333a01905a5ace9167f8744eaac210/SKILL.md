---
name: tess-transit-period
version: 1.4.0
description: Identify a repeatedly observed transit period in an activity-dominated four-column TESS light curve using quality filtering, gap-aware detrending, and a count-weighted folded box search.
---

# TESS transit-period detection

Use this Skill for a table whose first four columns are **time (days), normalized flux, quality flag, and flux uncertainty**, with quality value `0` denoting trusted cadences. It produces a single orbital-period artifact for activity-dominated light curves containing short, transit-like brightness dips.

The method deliberately preserves time gaps, removes smooth activity independently within observing segments, and selects a period from a count-weighted box search only when its folded dip is supported by several distinct observed orbital epochs. A full-series phase-box search is retained as a diagnostic for aliases and detrending sensitivity, but it does not override repeated-event support with a one- or two-epoch feature.

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

Required fields:

- `input_path`: readable light-curve file.
- `output_path`: destination for the one-value period artifact.

Rows may be whitespace- or comma-separated. Nonnumeric header rows are ignored. `max_period: null` uses `min(15.0, baseline / 1.8)`, ensuring the searched interval can contain multiple orbital events. Trial counts must be at least 500.

For the supplied task:

```bash
printf '%s\n' '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' | python3 scripts/find_period.py
```

The script writes `output_path` and emits a JSON diagnostic object to stdout. The file, rather than stdout, is the deliverable.

## Method

1. Parse the first four numeric columns, retain rows with finite time, flux, and uncertainty and quality exactly zero, then sort chronologically. Flagged data, non-finite values, and malformed rows are excluded. No missing cadence is interpolated.
2. Find long gaps from the median positive cadence. In each contiguous segment, subtract a quadratic Savitzky--Golay trend with a roughly 0.7-day window. This targets stellar activity on longer scales while retaining short box-shaped events. Clip only the residual tails after detrending.
3. Fold every trial period into 240 phase bins. Scan circular boxes one through eight bins wide and compute an inside-versus-outside, robust-scatter-normalized, count-weighted depth statistic. A valid box needs at least eight in-transit and eight out-of-transit samples.
4. Select the strongest BLS trial after verifying that the selected box is supported by at least three separate orbital epochs, each containing two or more in-box points with below-median residual flux. If the nominal peak lacks this support, choose the strongest supported candidate among leading peaks; fail rather than treating an isolated excursion as a planet.
5. Separately calculate a full-series 180-bin phase-box diagnostic after 0.8-day detrending. Its peak and the selected candidate's score are reported so that disagreement can be recognized as an alias or detrending sensitivity rather than silently combined into a compromise period.
6. Round only the selected refined grid period for presentation and write exactly `NN.NNNNN\n` to `output_path`.

## Validation and failure handling

Successful JSON output includes the selected period, the count-weighted score, number of supported epochs, selected box location, full-series diagnostic score, both search peaks, cadence count, segment count, and search range. Validate that the artifact contains exactly one positive finite decimal with five digits after the decimal point and no explanatory text.

The program emits a JSON error and exits nonzero without replacing the output artifact if SciPy is unavailable; the file cannot be read; fewer than 100 trusted finite cadences remain; time has no positive cadence or baseline; bounds are invalid; or no positive, repeated-epoch box candidate exists. It uses no network or external actions.
