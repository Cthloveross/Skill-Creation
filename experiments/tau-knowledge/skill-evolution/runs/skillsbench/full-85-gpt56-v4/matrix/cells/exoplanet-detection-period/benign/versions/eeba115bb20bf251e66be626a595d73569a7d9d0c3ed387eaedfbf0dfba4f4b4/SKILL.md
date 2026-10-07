---
name: tess-transit-period
version: 1.1.0
description: Detect a repeating exoplanet transit period in a TESS-style four-column light curve with quality flags, stellar variability, gaps, and uncertainties. Use when the required deliverable is a single period in days rounded to five decimal places.
---

# TESS transit-period detection

Use `scripts/find_transit_period.py` on the supplied light curve.  It filters to trusted finite observations, detrends long-timescale variability without deleting negative transit excursions, performs a box-shaped period search, checks common aliases through event occupancy, and refines the ephemeris from individual events before rounding.

## Runtime interface

The script accepts either command-line paths or a JSON object on standard input:

```bash
python3 scripts/find_transit_period.py \
  --input /root/data/tess_lc.txt --output /root/period.txt
# equivalent stdin interface:
printf '%s\n' '{"input":"/root/data/tess_lc.txt","output":"/root/period.txt"}' | \
  python3 scripts/find_transit_period.py
```

Standard output is a JSON report containing the unrounded period, rounded period, search method, number of retained cadences, and diagnostic candidate information. The output file contains exactly one fixed-point numerical value and a newline.

The input must have four numeric columns in this order: time in days, normalized flux, quality flag (zero is trusted), and flux uncertainty. A nonnumeric header and comma or whitespace delimiters are accepted. The default input and output are `/root/data/tess_lc.txt` and `/root/period.txt`.

## Method and interpretation

1. Reject nonfinite rows, nonpositive uncertainties, and nonzero quality flags. Only conspicuously high positive excursions are removed; low excursions are retained so possible transits do not define the outlier model.
2. Estimate stellar variability from robust time-bin medians followed by smoothing. The script searches two transit-preserving high-pass scales and keeps the stronger supported short-duty-cycle box-transit solution, reducing the chance that a broad stellar-rotation trough is reported as a planet. Gaps are never interpolated as observations; interpolation is used only to evaluate the smooth trend at existing timestamps.
3. Use `astropy.timeseries.BoxLeastSquares` when available, with a bounded coarse frequency grid followed by local numerical refinement. A deterministic folded, binned box-search fallback is included for minimal Python environments. The search is in frequency/period at full numerical precision, not presentation precision.
4. Compare strong candidate periods with half, double, and nearby aliases. Candidates whose predicted transit epochs repeatedly contain a negative event are preferred over a subharmonic that predicts empty alternating events. Broad, long-duty-cycle troughs are downweighted relative to repeated short boxes; occupied event centers provide an ephemeris refinement after the BLS seed.
5. Verify that the selected solution has at least two predicted epochs and meaningful in-transit support. If the data span is too short, columns are malformed, or no credible periodic box signal is found, the script exits nonzero rather than writing a misleading period.

Inspect the JSON report if a scientific judgment is needed: an unusually low event occupancy, only two events, or disagreement between detrending scales warrants folded-light-curve review. Do not infer a sinusoidal stellar-rotation peak to be the planetary period.
