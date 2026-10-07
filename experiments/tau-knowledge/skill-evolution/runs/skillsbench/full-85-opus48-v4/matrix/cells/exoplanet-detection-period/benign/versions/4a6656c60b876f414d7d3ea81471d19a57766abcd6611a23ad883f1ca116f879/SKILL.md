---
name: exoplanet-transit-period
description: >
  Detect the orbital period of a transiting exoplanet from a TESS-style light
  curve (Time MJD, normalized flux, quality flag, flux uncertainty) whose signal
  is buried under stellar-activity (rotation/starspot) variability. The Skill
  filters by quality flag and finiteness, removes variability longer than a
  transit with a transit-safe time-window MEDIAN detrender using a window
  SHORTER than the stellar rotation period, clips only upward outliers so
  transit dips are preserved, runs a box-least-squares (BLS) period search
  (astropy BoxLeastSquares when available, numpy fallback otherwise), refines
  the peak on a DENSE local period grid, cross-checks the result against a
  transit-timing linear ephemeris and against the P/2 and 2P harmonics, and
  writes the period in days rounded to 5 decimals to an output file. Use
  whenever a task provides a space-telescope light-curve text file and asks for
  the transiting planet's period.
---

# Exoplanet Transit Period Detection

## When to use
The public task supplies `/root/data/tess_lc.txt` with four whitespace columns:
`Time (MJD)`, `Normalized flux`, `Quality flag` (0 = good), `Flux uncertainty`
(header lines start with `#`). Stellar rotation / starspot modulation
(days-scale) hides a short, shallow transit signal. The required deliverable is
a single number (period in days, rounded to 5 decimal places) written to
`/root/period.txt`, e.g. `2.44535`.

## Method (maps to the four background requirements)
1. **Quality + outliers.** Keep only `Quality flag == 0` and finite rows with
   positive errors. After detrending, clip **upward** residual outliers (robust
   MAD, `n_sigma≈5`) but keep downward excursions far more loosely
   (`neg_sigma≈15`), so transit dips never define the outlier model.
2. **Detrending.** Remove variability longer than a transit with a time-window
   **median** filter (robust to transit dips). The window must be **shorter than
   the stellar rotation period** but several times the transit duration; flux is
   divided by the trend so transit depth/duration are preserved. CRITICAL: a
   window as long as (or longer than) the rotation period leaves residual
   rotation modulation that the search will lock onto as a false "period". For
   TESS 2-minute data with ~1.4 d rotation and ~0.05 d transits, `0.3` days
   works and leaves comfortable margin; `~0.25` is also safe.
3. **BLS search + verification (detection).** A box-least-squares statistic is
   matched to box-shaped transits. A frequency-uniform coarse grid spans
   `period_min` up to `baseline/2` so multiple events can align, then a dense
   local grid refines the top peak. Fold at the best period and report event
   count, depth, duration, odd/even depths, and the BLS statistic at `P/2` and
   `2P` to flag harmonic/subharmonic/alias confusion. A credible detection has
   the peak statistic clearly above the half/double statistics, >= 2 covered
   events, and consistent odd/even depths.
4. **Period determination = joint simultaneous transit fit (primary).** The BLS
   peak only *detects* the signal; its exact location is biased at the ~1e-3 d
   level by the box shape and by residual slopes left after global detrending.
   The final period comes instead from a single least-squares fit of ALL covered
   transits on the **raw** (quality-filtered) flux, sharing one `(t0, P, depth,
   width)` while each transit gets its own local polynomial baseline. Fitting the
   transit shapes directly (local baselines absorb the stellar variability
   without distorting transit timing) yields a period that is stable to ~1e-4 d
   across window and baseline-order choices and is unbiased. The BLS peak
   initialises the fit and is a consistency check; if the fit fails, finds < 2
   transits, has a poor reduced chi-square, or disagrees with BLS (possible wrong
   alias), the pipeline falls back to the dense BLS peak.
5. **Refinement vs rounding separated.** The search, dense refinement and joint
   fit all use full numerical precision; rounding to 5 decimals happens only when
   writing the file, so presentation precision never limits the search. (One
   earlier failure mode was a refinement grid too coarse to resolve the peak;
   another was reporting the box-BLS peak, which is biased by ~1e-3 d relative to
   the true transit-timing period.)

## Files
- `scripts/detect_period.py` – end-to-end entrypoint. Reads JSON on stdin,
  writes the output file, and prints a JSON report on stdout.
- `scripts/bls_lib.py` – reusable, dependency-light helpers (loader, quality
  filter, median detrender, upward outlier clip, BLS dispatch with astropy +
  numpy fallback, dense refinement, transit-timing ephemeris, fold diagnostics).

## Running it
```bash
SKILL=/app/environment/skills/current   # or wherever the Skill is installed
echo '{"input_path":"/root/data/tess_lc.txt","output_path":"/root/period.txt"}' \
  | python3 "$SKILL/scripts/detect_period.py"
cat /root/period.txt
```
Omit the body entirely (`echo '{}' | ...`) to use defaults against the task
paths. A full run on the task light curve takes ~20 s.

### stdin schema (all keys optional)
```json
{
  "input_path": "/root/data/tess_lc.txt",
  "output_path": "/root/period.txt",
  "period_min": 0.5,
  "period_max": null,                 // default = baseline/2
  "detrend_window_days": 0.3,         // MUST be shorter than stellar rotation
  "durations": [0.03,0.04,0.05,0.06,0.08],
  "n_freq_coarse": 40000,
  "n_grid_fine": 100000
}
```

### stdout report (JSON, illustrative shape only)
```json
{
  "period_days": 5.3590,              // full precision; written rounded
  "period_rounded": "5.35899",        // exactly what is written to the file
  "period_source": "joint_transit_fit", // or "bls_fine" (fallback)
  "bls_period": 5.3596,   // detection peak (biased ~1e-3 d; not the answer)
  "ephemeris": {"period": 5.3590, "period_err": 0.0007, "n_transits": 4,
                 "red_chi2": 1.6, "consistent_with_bls": true},
  "n_used": 16621, "baseline_days": 25.4,
  "best_stat": 307.0, "stat_half": 159.0, "stat_double": 155.0,
  "n_events": 5, "depth": 0.0019, "odd_depth": 0.0019, "even_depth": 0.0019,
  "duration_days": 0.05, "transit_time": 2146.86,
  "output_path": "/root/period.txt", "format_ok": true
}
```
(Numbers above illustrate the schema; the executor must read the actual values
produced from the current task input, never hardcode them.)

## How the executor completes the task
1. Confirm the input file exists at the path in the task opening.
2. Run the entrypoint as above; it writes `/root/period.txt`.
3. `cat /root/period.txt` and confirm it is a single float matching
   `^-?\d+\.\d{5}$` (5 decimal places).
4. Sanity-check the stdout report:
   - `best_stat` clearly exceeds `stat_half` and `stat_double` (fundamental, not
     a harmonic/subharmonic);
   - `n_events >= 2` and odd/even depths are similar (not an eclipsing binary);
   - `period_source` is `joint_transit_fit` and
     `ephemeris.consistent_with_bls` is `true` with a sensible `red_chi2`
     (~1-3). If it fell back to `bls_fine`, inspect why the transit fit failed.
   If `stat_half`/`stat_double` dominates, or the period equals the known stellar
   rotation period, the detrending was too weak — re-run with a SMALLER
   `detrend_window_days` (still a few transit durations) so the rotation is
   removed. If the ephemeris and BLS disagree strongly, inspect the fold.
5. The written file always equals `period_rounded`.

## Failure handling
- Missing/unreadable input: the entrypoint prints `{"error": ...}` to stdout and
  exits non-zero; fix the path and re-run.
- `numpy` is required. `scipy` (median filter, ephemeris fit) and `astropy`
  (BLS) are used when present; without them pure-numpy fallbacks run (lower
  precision, and the joint transit fit is skipped so the BLS peak is reported),
  still locating the correct period region.
- If too few points survive filtering, the report includes a `warning`; inspect
  `n_used`.

## Validation (write-only here; run during execution/evolution)
After running, verify:
- `/root/period.txt` contains exactly one token parseable as float matching
  `^-?\d+\.\d{5}$`.
- `float(period) == round(period_days, 5)` from the stdout report.
- `period_min <= period_days <= period_max`, `n_events >= 2`, and
  `best_stat > stat_half` and `best_stat > stat_double`.
`scripts/detect_period.py --self-check <period>` recomputes the 5-decimal
rendering and format-regex result for a given period.
