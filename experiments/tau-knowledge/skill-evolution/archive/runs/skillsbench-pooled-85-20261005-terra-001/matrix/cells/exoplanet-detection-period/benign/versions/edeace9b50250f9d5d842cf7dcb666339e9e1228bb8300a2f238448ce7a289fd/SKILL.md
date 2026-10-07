---
name: tess-transit-period
summary: Detect and refine a repeated box-shaped transit period in a four-column TESS light curve while removing slower stellar activity and explicitly comparing period harmonics.
---

# TESS transit-period detection

Use this Skill for a TESS-style ASCII light curve whose first four columns are
time in days, normalized flux, quality flag, and flux uncertainty. It writes a
single orbital period in days, rounded to exactly five decimal places.

## Method

1. Parse numeric rows; retain only finite records having quality flag zero and
   a positive finite flux uncertainty. Sort retained cadences without filling
   time gaps.
2. Reject only highly positive flux artifacts. Preserve negative deviations so
   a transit cannot be removed as an outlier.
3. Detrend each continuous observing segment using time-bin medians followed by
   a broader running median. This suppresses stellar variability on timescales
   longer than a short transit while reducing the influence of transit cadences
   on the baseline.
4. Search a uniform frequency grid with a phase-binned, negative box statistic
   over several short transit durations. Refine separated broad candidates with
   two dense local frequency scans using unbinned cadences.
5. Explicitly refine the `P/2` and `2P` possibilities of the strongest local
   candidates before choosing the highest-scoring coherent box signal. This
   prevents retaining a period-doubling harmonic merely because the initial
   broad candidate list missed its fundamental.
6. Check that the selected phase box occupies multiple orbital cycles, then
   write only the final refined period with five digits after the decimal.

The default search interval is from 0.5 days through the smaller of 15 days
and the baseline divided by 2.2. A transit candidate should have a significant
box score, multiple observed events, sensible duration, and folded-light-curve
support. If a candidate is marginal, inspect nearby aliases and revise only
scientifically justified detrending or search bounds.

## Run

The script accepts one JSON object on stdin and emits one JSON object on
stdout. It creates the requested output artifact on success.

```bash
python scripts/detect_period.py <<'JSON'
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt"
}
JSON
```

Input fields:

- `input_path` (required string): input text file. Headers, comments, commas,
  tabs, and whitespace are accepted; the first four numeric fields are used.
- `output_path` (required string): destination for the one-line period file.
- `min_period`, `max_period` (optional positive numbers): search bounds in
  days. `max_period` must permit at least two observed events.
- `trend_window_days` (optional positive number, default `0.88`): broad robust
  trend scale.
- `trend_bin_days` (optional positive number, default `0.08`): binning scale
  used to estimate the activity trend.

Successful stdout includes `period_days`, `box_score`, transit-cycle count,
row diagnostics, and the number of harmonic candidates examined. Failures emit
`{"error":"..."}` and exit nonzero.

## Validation

The script internally validates that the artifact matches
`^[0-9]+\.[0-9]{5}\n$`, parses as a finite positive value, and corresponds to a
significant repeated box-shaped signal. The executor should retain the created
artifact rather than copying diagnostic stdout into it.
