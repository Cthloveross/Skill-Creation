---
name: tess-transit-period
summary: Find a repeated box-shaped transit period in a four-column TESS light curve, suppressing stellar activity and numerically refining the selected period before writing a five-decimal-day artifact.
---

# TESS transit-period detection

Use this Skill when a TESS-style ASCII light curve has columns for time,
normalized flux, quality flag, and flux uncertainty, and the required artifact
is one orbital period in days.

The detector is intended for short, repeated flux decreases hidden by slower
stellar variability. It does not rely on a sinusoidal periodogram.

## Method

1. Parse numeric rows, retain finite quality-flag-zero records with positive,
   finite uncertainties, sort by time, and retain temporal gaps as gaps.
2. Reject only implausibly high flux outliers. Low flux values are retained so
   transits cannot be discarded as outliers. Extremely deep negative residuals
   are capped only for the search statistic, not removed from the light curve.
3. Detrend each continuous observing segment with short time-bin medians and a
   broader running median. This robustly follows activity on scales longer than
   a transit while limiting the influence of a small number of transit cadences
   on the baseline.
4. Perform a phase-binned box least-squares-style search over a uniform
   frequency grid and several short box durations. Candidate peaks are separated
   in frequency so that nearby samples of one peak do not consume the candidate
   list.
5. Refine every leading candidate with two increasingly dense local frequency
   grids using the original detrended cadences and an unweighted robust box
   statistic. The final reported candidate is therefore a local numerical peak,
   rather than a coarse-grid trial or a flux-centroid estimate.
6. Write only the refined period, rounded at the final step to exactly five
   digits after the decimal point.

The default search interval is 0.5 days through the smaller of 15 days and the
baseline divided by 2.2, so the search requires repeated events. Supply bounds
when scientifically justified. Inspect the returned score, number of occupied
transit cycles, and folded data before accepting a marginal result; compare
harmonics or aliases when they are plausible.

## Run

The executable receives one JSON object on standard input, emits one JSON
object on standard output, and writes the requested artifact.

```bash
python scripts/detect_period.py <<'JSON'
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt"
}
JSON
```

Input fields:

- `input_path` (required string): text file whose first four numeric columns
  are time in days, normalized flux, quality flag, and flux uncertainty.
  Headers, comments, commas, tabs, and whitespace are accepted.
- `output_path` (required string): destination for the one-line result.
- `min_period` and `max_period` (optional positive numbers): period bounds in
  days. The maximum must allow at least two expected events.
- `trend_window_days` (optional positive number, default `0.88`): broad
  median-filter scale for activity removal.
- `trend_bin_days` (optional positive number, default `0.08`): bin scale used
  to construct the robust trend. It should remain shorter than the activity
  scale and not so broad that it smears a short transit.

Successful stdout contains `period_days`, `coarse_period_days`, `box_score`,
`n_transit_cycles`, row-count diagnostics, and the output path. Failures emit
`{"error": "..."}` and exit nonzero.

## Output validation

The artifact is validated internally against `^[0-9]+\.[0-9]{5}\n$` and must
parse as a finite positive period. The executor should also ensure that the
reported box score is significant and that multiple distinct cycles occupy the
selected folded transit window. If no significant repeated box-shaped candidate
is found, revise scientifically justified search or detrending settings rather
than writing an unsupported value.
