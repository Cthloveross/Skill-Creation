---
name: tess-transit-period
version: 6.0.0
description: Detect a repeatedly supported box-shaped transit period in a quality-flagged four-column TESS light curve with smooth stellar variability and write the refined period as one five-decimal value.
---

# TESS transit-period detection

Use this Skill for a table whose first four columns are time in days, normalized flux, quality flag, and flux uncertainty. Quality value `0` is treated as trusted. The Skill is designed for light curves where stellar rotation or other smooth activity obscures short transit dips.

## Runtime interface

Run `scripts/find_period.py` with one JSON object on stdin:

```json
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt",
  "min_period": 0.25,
  "max_period": null,
  "trials": 5000,
  "selection": "gap_aware"
}
```

`input_path` and `output_path` are required nonempty strings. Optional settings are:

- `min_period`: positive lower bound in days; defaults to `0.25`.
- `max_period`: positive upper bound, or `null` for `min(15, baseline / 1.8)`.
- `trials`: number of broad period samples; defaults to `5000`, minimum `500`.
- `selection`: `gap_aware` (default), `global_box`, or `consensus`.

For the supplied task, execute:

```bash
printf '%s\n' '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' | python3 scripts/find_period.py
```

The script emits a JSON diagnostic object on stdout. On success it atomically creates or replaces `output_path` with only a positive decimal period in days, displayed to exactly five digits after the decimal point and followed by a newline.

## Method

1. Read numeric four-column records, retain finite time, flux, and uncertainty rows having quality exactly zero, and sort them by time. Gaps are never interpolated.
2. Identify major observing gaps from the cadence. Detrend every uninterrupted segment separately with a roughly 0.7-day quadratic Savitzky--Golay window. This removes smooth activity without fitting across gaps. Extreme residuals are clipped only after detrending.
3. Fold each trial period and score short circular boxes using a count-weighted in-box versus out-of-box depth statistic. Search box widths from one through eight of 240 phase bins. This statistic is matched to transit dips, unlike a sinusoidal periodogram.
4. Search the complete multi-event range, refine the strongest broad candidates at the final five-decimal display precision, and retain the best refined box score. The selected transit window must have negative residual samples in at least three separately observed orbital epochs.
5. Also calculate a continuous 0.8-day global detrending diagnostic and its folded-box score. `gap_aware` prioritizes the gap-preserving, repeated-event solution. `global_box` is available only when a continuous detrending convention is explicitly required. `consensus` refuses to write an artifact unless the two diagnostics select compatible candidates.

The diagnostics include selected score and period, global and gap-aware broad peaks, selected box location, and observed-epoch support. Inspect disagreement between diagnostics as a possible alias, harmonic, or detrending-sensitive candidate rather than silently treating a single event as a planet.

## Validation and failures

A valid artifact matches `^[+-]?(?:0|[1-9][0-9]*)\.[0-9]{5}$` after stripping its trailing newline, is finite, and is positive. A selected candidate is additionally required to be in the requested multi-event range and have at least three supported observed epochs for `gap_aware` or `consensus` selection.

The script exits without replacing an existing output for malformed JSON, unreadable input, insufficient trusted data, invalid period bounds, unavailable SciPy, or no repeatedly supported candidate. It uses only Python, NumPy, and SciPy and does not require network access.
