---
name: exoplanet-transit-period
description: >
  Detect the orbital period of a transiting exoplanet from a TESS-style light
  curve (Time MJD, normalized flux, quality flag, flux uncertainty) that is
  dominated by stellar-activity variability. The Skill filters by quality flag,
  removes variability longer than a transit with a transit-safe (median)
  detrender, clips only upward outliers so transit dips are preserved, runs a
  box-least-squares (BLS) period search, refines the best period numerically,
  and writes the period in days rounded to 5 decimals to an output file.
  Use whenever a task provides a space-telescope light-curve text file and asks
  for the transiting planet's period.
---

# Exoplanet Transit Period Detection

## When to use
The public task supplies `/root/data/tess_lc.txt` with four whitespace columns:
`Time (MJD)`, `Normalized flux`, `Quality flag` (0 = good), `Flux uncertainty`.
Stellar rotation / starspot modulation (days-scale) hides a short transit
signal. The required deliverable is a single number (period in days, rounded to
5 decimal places) written to `/root/period.txt`, e.g. `2.44535`.

## Method (maps to the four background requirements)
1. **Quality + outliers.** Keep only `Quality flag == 0` and finite rows. After
   detrending, clip **upward** residual outliers aggressively (robust MAD) but
   keep downward excursions, so transit dips never define the outlier model.
2. **Detrending.** Remove variability longer than a transit with a time-window
   **median** filter (robust to transit dips) whose window is several times a
   transit duration but shorter than the rotation period. Flux is divided by the
   trend so transit depth/duration are preserved.
3. **BLS search + verification.** A box-least-squares statistic is matched to
   box-shaped transits. The grid spans short periods up to about half the
   baseline so that multiple events can align. The code folds at the best period
   and reports event count, depth, duration, and odd/even depths as diagnostics,
   and reports the SR at P/2 and 2P to flag harmonic/alias confusion.
4. **Refinement vs rounding separated.** The search uses full numerical
   precision; a fine local grid refines the peak; rounding to 5 decimals happens
   only when writing the file, so presentation precision never limits the search.

## Files
- `scripts/detect_period.py` – end-to-end entrypoint. Reads JSON on stdin,
  writes the output file, and prints a JSON report on stdout.
- `scripts/bls_lib.py` – reusable, dependency-light helpers (loader, detrender,
  outlier clip, pure-numpy BLS, refinement). Imported by the entrypoint.

## Running it
```bash
SKILL=/app/environment/skills/current
echo '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' \
  | python3 "$SKILL/scripts/detect_period.py"
cat /root/period.txt
```

### stdin schema (all optional except paths default to the task paths)
```json
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt",
  "period_min": 0.5,            // days; default 0.5
  "period_max": null,           // days; default = baseline/2
  "detrend_window_days": 0.3,   // median-filter window
  "n_freq_coarse": 12000,
  "n_freq_fine": 3000,
  "nbins": 200
}
```
All keys are optional; omit the body entirely (`echo '{}' | ...`) to use defaults
against the task paths.

### stdout report (JSON)
```json
{
  "period_days": 2.4453471,       // full precision
  "period_rounded": "2.44535",    // exactly what is written to the file
  "n_used": 17890,                // points surviving filtering
  "baseline_days": 27.3,
  "best_sr": 0.0123,
  "n_events": 11,                 // transits covered in the baseline
  "depth": 0.0021,
  "duration_days": 0.12,
  "sr_half": 0.004, "sr_double": 0.006, // for alias/harmonic sanity
  "output_path": "/root/period.txt"
}
```

## How the executor completes the task
1. Confirm the input file exists at the path given in the task opening.
2. Run the entrypoint as above; it writes `/root/period.txt`.
3. `cat /root/period.txt` and confirm it is a single float with 5 decimals.
4. Sanity-check the stdout report: `n_events >= 2` (period supported by multiple
   events) and `best_sr` clearly above `sr_half`/`sr_double`. If `sr_half` or
   `sr_double` dominates, the reported peak may be a harmonic/subharmonic — in
   that case re-run with an adjusted `period_min`/`period_max` to bracket the
   favoured value, or set the period to the value with the strongest folded,
   multi-event signal. The written file always equals `period_rounded`.

## Failure handling
- Missing/unreadable input: the entrypoint prints `{"error": ...}` to stdout and
  exits non-zero; fix the path and re-run.
- If `scipy` is unavailable the detrender falls back to a pure-numpy sliding
  median, so no extra install is required. `numpy` is required.
- If after filtering fewer than a handful of points remain, the report includes
  a warning and the search still runs on whatever survives; inspect `n_used`.

## Validation (write-only here; run during evolution/execution)
After running, verify:
- `/root/period.txt` contains exactly one token parseable as float and matches
  `^\d+\.\d{5}$` (5 decimal places).
- `float(period) == round(period_days, 5)` from the stdout report.
- `period_min <= period_days <= period_max` and `n_events >= 2`.
A ready-made check is embedded in `scripts/detect_period.py` under
`--self-check` which recomputes rounding and format from a given period.
