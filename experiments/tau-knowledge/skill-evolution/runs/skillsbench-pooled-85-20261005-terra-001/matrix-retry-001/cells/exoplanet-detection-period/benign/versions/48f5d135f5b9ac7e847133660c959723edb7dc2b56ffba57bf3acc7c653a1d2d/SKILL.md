---
name: tess-transit-period
version: 1.1.0
description: Find a box-shaped exoplanet transit period in a TESS-style four-column light curve when stellar activity obscures the signal, and write one five-decimal period in days.
---

# TESS transit-period detection

Use this Skill for an ASCII light curve containing time, normalized flux, quality flag, and flux uncertainty columns, where quality flag `0` denotes trusted cadences. It filters invalid and flagged data, removes smooth stellar variability with a transit-scale-preserving Savitzky--Golay trend, then ranks periodic short box-shaped dips with a phase-binned box least-squares statistic.

## Runtime interface

Run `scripts/find_period.py` with one JSON object on standard input:

```json
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt",
  "min_period": 0.2,
  "max_period": null,
  "trend_window_days": 0.8,
  "trials": 3500
}
```

`input_path` and `output_path` are required strings. The input is whitespace- or comma-separated and must have at least four numeric columns in the documented order. Header lines are permitted. `max_period: null` searches up to `min(15 days, baseline / 1.8)`, ensuring coverage for multiple events. Other optional fields default to the displayed values.

For the provided task, invoke it as follows:

```bash
printf '%s\n' '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' | python3 scripts/find_period.py
```

## Method

1. Retain only finite time, flux, and uncertainty values with quality flag exactly zero, then time-sort the cadences. This handles non-finite rows, flags, and gaps without interpolating observations.
2. Estimate the activity trend with a quadratic Savitzky--Golay filter whose approximately 0.8-day window is substantially longer than ordinary transit durations. Subtract it from the flux. Clip only the most extreme 0.1% tails of the residual distribution, preserving the ordinary negative transit population while preventing isolated excursions from defining a peak.
3. Search evenly over the multi-event period range. At every trial period, fold the residuals into 180 bins and score the deepest circular contiguous phase window for several short box widths. This directly favors a repeating box-like dimming rather than sinusoidal activity.
4. Re-score the leading candidates at the exact five-decimal values that can be reported, select the strongest such value, and calculate scores at its half and double aliases for diagnostics. Rounding is therefore included in candidate validation rather than blindly applied after selection.
5. Write `output_path` containing only the selected positive period with exactly five digits after the decimal point and a newline.

The script emits a JSON diagnostic object on stdout. On success it includes `ok`, `period_days`, `period_rounded`, `box_score`, `grid_best_score`, candidate count, residual scatter, and valid cadence count. The stdout JSON is diagnostic only; the required deliverable is the output file.

## Validation and failure handling

A valid artifact matches `^[0-9]+\.[0-9]{5}$` after stripping whitespace and is within the searched range. A credible diagnostic has a positive box score and a selected score equal to or greater than the raw-grid best score after five-decimal candidate validation. Inspect `alias_scores` when distinguishing a candidate from half/double-period alternatives.

The script exits with JSON error output and does not write a result if SciPy is unavailable, too few trusted cadences remain, the time span cannot support the requested interval, or no finite positive box-dip score is found. It does not perform banking, network, or other external actions.
