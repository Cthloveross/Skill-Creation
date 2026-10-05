---
name: tess-transit-period
summary: Detect a periodic box-shaped transit in a TESS light curve with quality flags, uncertainty-aware detrending, and a BLS-style period search. Use when the required deliverable is a single orbital period in days.
---

# TESS transit-period detection

Use this Skill for a four-column light curve containing time, normalized flux,
quality flag, and flux uncertainty. It produces the requested period artifact
without relying on a sinusoidal periodogram, which is poorly matched to transit
signals.

## Method

1. Read numerical rows, sort them by time, and retain only finite records with
   quality flag zero and a positive finite flux uncertainty.
2. Reject only extreme *upward* flux excursions. Negative excursions are not
   used to define a rejection threshold: they can be real transits. Non-finite
   values and bad-quality cadences are removed, while temporal gaps are retained
   as gaps rather than interpolated observations.
3. Estimate the slowly varying stellar baseline separately on continuous data
   segments. The estimate uses short time-bin medians followed by a broad
   smoothing window, then subtracts the baseline. This is intended for activity
   that is longer than a transit; it deliberately does not fit a periodic
   sinusoid.
4. Search a dense frequency grid with a weighted, phase-binned box least
   squares (BLS-style) statistic across plausible transit durations. The search
   requires the strongest repeated negative (flux-decrease) box signal.
5. Use the best folded box to estimate centers of individual events and fit an
   event-number versus time relation. This numerically refines the period after
   the broad grid search. The script reports diagnostics so the executor can
   inspect whether multiple events supported the result.
6. Validate and write exactly one fixed-point number with five decimal places.

The default period range is derived from the data baseline and cadence. It
requires at least two expected events and searches periods down to about 0.1
or 0.15 days, subject to cadence. If domain knowledge supplies a narrower
range, pass `min_period` and/or `max_period` to avoid known aliases.

## Run

The script receives one JSON object on stdin and emits a JSON result on stdout.
It also writes the artifact specified by `output_path`.

```bash
python scripts/detect_period.py <<'JSON'
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt"
}
JSON
```

Input schema:

- `input_path` (string, required): text file with the first four numerical
  columns interpreted as time [days], normalized flux, quality flag, and flux
  uncertainty. Header and comment lines are allowed; commas, tabs, and spaces
  are accepted.
- `output_path` (string, required): destination for the one-line period file.
- `min_period` / `max_period` (positive numbers, optional): search bounds in
  days. They must permit at least two events in the observed baseline.
- `trend_window_days` (positive number, optional; default `0.75`): smoothing
  scale for stellar activity. It should be safely longer than the expected
  transit duration.

Successful stdout schema includes `period_days`, `raw_period_days`,
`bls_score`, `n_events_used`, and row-count diagnostics. `period_days` is the
unrounded numerical refinement; the artifact is rounded only at final output.

## Validation and failure handling

The script fails clearly if there are too few trusted cadences, no meaningful
time baseline, invalid search bounds, or no finite positive BLS candidate. On
success it verifies that the created artifact matches
`^[0-9]+\.[0-9]{5}\n$` and that its parsed value is positive and finite.

Before treating a result as scientifically credible, inspect the reported event
count and score, fold the detrended light curve at `period_days`, and compare
nearby harmonic, subharmonic, and sampling-alias candidates if they are
plausible. A result based on only two events or a trend window comparable to a
transit duration should be regarded as less secure.
