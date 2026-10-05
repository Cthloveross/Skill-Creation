---
name: tess-transit-period
summary: Detect, refine, and write the orbital period of a short-duration transiting signal in a four-column TESS light curve with strong stellar variability.
---

# TESS transit-period detection

Use this Skill for a TESS-style ASCII light curve with columns containing time
(days), normalized flux, quality flag, and flux uncertainty. It filters trusted
cadences, removes long-timescale variability, searches for repeated box-shaped
dimming, resolves common period aliases, and writes one five-decimal orbital
period in days.

## Method

1. Parse the first four numeric fields in every usable row. Retain finite rows
   with quality flag zero and positive finite uncertainty; sort by time without
   filling gaps.
2. Reject only extreme positive artifacts. Negative excursions are retained so
   that possible transits do not define the outlier rejection model.
3. Estimate stellar variability separately within continuous observing segments
   using short-bin medians followed by a substantially broader running median.
   Subtract this trend, preserving short transit-duration features.
4. Run a phase-binned box search over a uniform frequency grid and refine
   separated candidate peaks using dense local frequency scans on unbinned
   data. Candidate boxes must be supported by multiple observed cycles.
5. Compare harmonic candidates. In particular, fold each selected solution and
   test for a second comparably significant short dip near the opposite phase.
   If present, the stated period is a two-transit-cycle alias, so its half
   period is the orbital ephemeris. Repeat this check for nested factor-of-two
   aliases.
6. Round only after numerical search/refinement and write exactly one period
   with five digits after the decimal point.

The default search domain is 0.5 days through the smaller of 15 days and the
light-curve baseline divided by 2.2. The method is intended for a periodic,
short-duration transit signal; it is not a substitute for physical validation
of eclipsing binaries or instrumental false positives.

## Run

The script receives one JSON object on stdin and emits one JSON object on
stdout. On success it creates the requested artifact.

```bash
python scripts/detect_period.py <<'JSON'
{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}
JSON
```

Input fields:

- `input_path` (required string): source light-curve text file. Whitespace,
  comma, or semicolon field separators and nonnumeric header rows are allowed.
- `output_path` (required string): destination for the one-line period file.
- `min_period` and `max_period` (optional positive numbers): period bounds in
  days. The upper bound must permit at least two observed events.
- `trend_bin_days` (optional positive number, default `0.08`): robust trend
  bin width.
- `trend_window_days` (optional positive number, default `0.88`): activity
  smoothing scale, which should remain longer than the transit duration.

Successful stdout contains `period_days`, search diagnostics, and the number
of factor-of-two reductions applied. Failure stdout is `{"error":"..."}` and
the process exits nonzero. The output artifact itself contains only the final
period, for example `2.44535` followed by a newline.

## Validation

The script validates that the result is finite, positive, supported by at
least two observed transit cycles, and rendered as `^[0-9]+\.[0-9]{5}\n$`.
The executor should inspect JSON diagnostics if the search is marginal, but
must retain the generated `output_path` file rather than placing diagnostics in
that file.
