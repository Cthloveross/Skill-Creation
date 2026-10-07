---
name: tess-transit-period
version: 4.0.0
description: Detect a repeated, box-shaped exoplanet transit period in a four-column, quality-flagged TESS light curve dominated by smooth stellar activity, then write one refined period in days.
---

# TESS transit-period detection

Use this Skill for a table whose first four columns are time in days, normalized flux, quality flag, and flux uncertainty, with quality `0` denoting trusted cadences. The Skill filters unusable cadences, detrends activity without bridging observational gaps, searches folded box-shaped dips, rejects candidates unsupported across multiple orbits, and writes the selected orbital period to the requested artifact.

## Runtime interface

Run `scripts/find_period.py` with one JSON object on standard input:

```json
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt",
  "min_period": 0.25,
  "max_period": null,
  "trials": 5000,
  "selection": "multi_epoch"
}
```

Required fields:

- `input_path`: readable light-curve path.
- `output_path`: period artifact path to create or replace only after success.

Optional fields:

- `min_period`: positive lower search bound in days; default `0.25`.
- `max_period`: positive upper bound, or `null` for `min(15, baseline / 1.8)`.
- `trials`: at least 500 uniformly spaced broad-search trials; default `5000`.
- `selection`: `multi_epoch` (default) prioritizes the gap-aware count-weighted search and requires repeated observed transit epochs. `global_box` is a diagnostic alternative that prioritizes a continuous-trend box statistic; it must still have repeated support.

For the supplied task, invoke:

```bash
printf '%s\n' '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' | python3 scripts/find_period.py
```

The script writes `output_path` and prints a JSON diagnostic object to stdout. Stdout is not part of the required artifact.

## Analysis method

1. Read numeric rows, retain only rows with quality exactly zero and finite time, flux, and uncertainty, then sort by time. Gaps remain gaps: neither timestamps nor fluxes are interpolated.
2. Split at large time gaps and subtract a quadratic Savitzky--Golay trend independently from each segment. The default approximately 0.7-day trend window removes smooth activity while preserving short transit-shaped dips. Residual clipping is applied only after detrending.
3. Search periods using a count-weighted folded-box statistic in 240 phase bins, scanning circular boxes one through eight bins wide. This is suited to transits rather than sinusoidal activity. A second, continuous 0.8-day detrending and unweighted 180-bin box score is calculated as an independent stability diagnostic.
4. Refine separated peaks from both searches. Each candidate is rescored at values that can actually be displayed to five decimal places. A valid selected candidate must have a positive box score and a negative in-transit median in at least three independently observed orbital epochs.
5. With `multi_epoch`, rank valid candidates by the gap-aware count-weighted statistic, then the independent box diagnostic and epoch support. This makes repeated, gap-aware events decisive and avoids choosing a lone activity excursion or a coarse-grid alias. Inspect diagnostics if the two detrending approaches prefer materially different candidate families.
6. Atomically write exactly one positive value formatted as `NN.NNNNN\n` after final refinement.

## Validation and failures

Check that `/root/period.txt` contains only one positive finite decimal value with exactly five fractional digits. The JSON result records the displayed period, both folded-box scores, folded box locations, supporting epoch count, broad-search peaks, accepted row counts, cadence, and number of gap-separated segments.

The script fails without replacing an existing output file on malformed JSON, unreadable input, fewer than 100 trusted finite cadences, invalid bounds, missing SciPy, or no repeatedly supported positive box candidate. It uses only Python, NumPy, and SciPy and does not require network access.
