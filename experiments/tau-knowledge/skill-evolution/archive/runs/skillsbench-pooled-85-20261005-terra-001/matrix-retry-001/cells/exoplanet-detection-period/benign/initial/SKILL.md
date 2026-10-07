---
name: tess-transit-period
version: 1.0.0
description: Detect a periodic box-shaped transit in a TESS-style light curve with time, normalized flux, quality flag, and flux-uncertainty columns. Use when stellar variability obscures a transit and the required deliverable is a single orbital period in days.
---

# TESS transit-period detection

This Skill filters trusted cadences, removes long-timescale stellar variability without using negative transit-like points to define the trend, and searches the detrended light curve with a box least-squares (BLS) statistic. It prefers `astropy.timeseries.BoxLeastSquares` when available and has a NumPy phase-binned BLS fallback.

## Input

`scripts/find_period.py` reads one JSON object from standard input:

```json
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt",
  "min_period": 0.3,
  "max_period": null,
  "trend_window_days": 1.5
}
```

Required fields are `input_path` and `output_path`. The input must contain at least four whitespace- or comma-separated numeric columns in this order: time in days, normalized flux, quality flag (`0` is trusted), and flux uncertainty. Header and nonnumeric lines are ignored. Optional search and detrending settings have the defaults shown above; `max_period: null` means the shorter of 20 days and half of the valid time span.

## Procedure

1. Run the script with the supplied light-curve path and the required result path, for example:

   ```bash
   printf '%s\n' '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' | python3 scripts/find_period.py
   ```

2. The script retains only finite positive-time observations with finite flux, finite positive uncertainty, and quality flag zero. It separates large gaps before detrending, estimates a local robust median trend in each segment, and masks positive spikes plus provisional negative transit excursions only while estimating the trend. Negative excursions remain in the transit-search data.
3. It divides by the trend, searches a range of transit durations using BLS, checks high-ranking period peaks together with their half/double aliases, and numerically refines the winning period on a dense local grid before formatting it.
4. The script writes `output_path` itself. Its contents are exactly one fixed-point numerical value with five digits after the decimal point and a trailing newline. Standard output is a JSON diagnostic record; it is not the requested artifact.

## Validation and failure handling

A successful JSON response has `"ok": true`, a finite `period_days`, at least two sampled transit epochs, and a positive fitted transit depth. Confirm that the output file contains only a value matching `^-?[0-9]+\\.[0-9]{5}$` after stripping whitespace. The diagnostic fields report retained cadence count, number of observed transit epochs, fitted duration, depth, and search backend.

The script terminates with a JSON error and does not create a period file when fewer than 30 trusted finite points remain, the baseline cannot support the requested period interval, or no positive-depth BLS candidate can be obtained. If the science target has a known period range or a transit duration longer than the default detrending assumption, provide appropriate `min_period`, `max_period`, and `trend_window_days` values rather than treating an unconstrained search result as validated.
