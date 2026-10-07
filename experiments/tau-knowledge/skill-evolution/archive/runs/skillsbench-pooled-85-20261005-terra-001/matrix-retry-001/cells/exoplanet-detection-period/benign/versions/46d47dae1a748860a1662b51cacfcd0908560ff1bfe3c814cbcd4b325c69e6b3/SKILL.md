---
name: tess-transit-period
version: 3.0.0
description: Recover a repeated box-shaped exoplanet transit period from a quality-flagged, activity-dominated four-column TESS light curve and write the refined period in days.
---

# TESS transit-period detection

Use this Skill for a light curve whose first four columns are time in days, normalized flux, quality flag, and flux uncertainty, where quality `0` marks trusted cadences. It filters trusted finite rows, removes smooth stellar activity without interpolating gaps, searches for repeated box-like dips, and writes one orbital period rounded to five decimal places.

## Runtime interface

Run `scripts/find_period.py` with one JSON object on standard input:

```json
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt",
  "min_period": 0.25,
  "max_period": null,
  "trials": 3500
}
```

`input_path` and `output_path` are required nonempty strings. `max_period: null` sets the upper bound to `min(15.0, baseline / 1.8)`, retaining a multi-event search range. `trials` must be at least 500.

For the supplied task, run:

```bash
printf '%s\n' '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' | python3 scripts/find_period.py
```

The program writes the deliverable to `output_path` and emits a JSON diagnostic object on stdout. Stdout is not the task artifact.

## Method

1. Read numeric rows, retain only finite observations with quality exactly zero, and sort by timestamp. Gaps are retained as gaps; no flux or timestamp is interpolated.
2. Split the series at large cadence gaps. In every segment, subtract a quadratic Savitzky--Golay trend with an approximately 0.7-day window. This targets stellar activity on longer time scales while retaining short transit-like events. Residuals are clipped only after detrending at the 0.2% and 99.8% quantiles, so negative transits do not determine raw-data rejection.
3. Fold each trial period into 240 bins and scan circular boxes one through eight bins wide. The count-weighted score is the in-box versus out-of-box depth normalized by robust scatter. Empty or poorly populated boxes are rejected.
4. Prefer the strongest candidate whose folded box has negative residuals in at least three independently observed orbital epochs. Refine the selected peak well below presentation precision, then explicitly rescore nearby five-decimal values. This avoids selecting a coarse-grid point, a single excursion, or an alias that loses support after rounding.
5. Write exactly `NN.NNNNN\n` to the requested output path only after a valid candidate has been selected.

The JSON result includes the unrounded and displayed periods, BLS location and score, number of supporting epochs, input counts, detrending segment count, and a separate full-series box-score diagnostic. Inspect competing peaks and phase folds manually if no candidate has repeated support or if diagnostics disagree substantially.

## Validation and failures

Confirm that the output file contains one positive finite decimal value and exactly five digits after the decimal point. A credible selected fold must have a positive box score and at least three supported epochs.

On malformed JSON, unreadable input, fewer than 100 trusted cadences, unusable timestamps or bounds, missing SciPy, or absence of a finite positive candidate, the script writes `{"ok": false, ...}` to stdout, exits nonzero, and does not replace an existing output file. The script uses Python, NumPy, and SciPy only and does not use the network.
