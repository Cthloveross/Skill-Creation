#!/usr/bin/env python3
"""End-to-end transit-period detection entrypoint.

Stdin: JSON (see SKILL.md). All keys optional; paths default to the task's
``/root/data/tess_lc.txt`` and ``/root/period.txt``.
Stdout: JSON report. Also writes the rounded period to the output file.

Pipeline:
  1. quality + finiteness filter;
  2. time-window **median** detrend (robust to transit dips, window shorter than
     stellar rotation but several transit durations long);
  3. upward-only sigma clip (transit dips preserved);
  4. BLS search (astropy BoxLeastSquares when available, numpy fallback) over a
     frequency-uniform coarse grid, then a DENSE local refinement so the grid
     step resolves the true peak;
  5. a transit-timing linear ephemeris (gold standard) that, when it agrees with
     the BLS peak, supersedes it for the final period;
  6. rounding to 5 decimals happens only at write time.

Self-check mode: ``python3 detect_period.py --self-check <period>`` prints the
5-decimal rendering used for the file and the format-regex result.
"""
from __future__ import annotations
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import numpy as np  # noqa: E402
import bls_lib as B  # noqa: E402


def render_period(value):
    """Round to 5 decimals and format exactly as required (e.g. '2.44535')."""
    return "{:.5f}".format(round(float(value), 5))


FORMAT_RE = re.compile(r"^-?\d+\.\d{5}$")


def run(cfg):
    input_path = cfg.get("input_path", "/root/data/tess_lc.txt")
    output_path = cfg.get("output_path", "/root/period.txt")

    t, f, q, e = B.load_lightcurve(input_path)
    t, f, e = B.filter_quality(t, f, q, e)

    warning = None
    if t.size < 10:
        warning = "Very few points survived quality filtering (%d)." % t.size

    window = float(cfg.get("detrend_window_days", 0.3))
    det, _trend = B.detrend(t, f, window)
    t2, det2, e2 = B.clip_upward_outliers(t, det, e)

    baseline = float(t2.max() - t2.min()) if t2.size else 0.0
    period_min = float(cfg.get("period_min", 0.5))
    period_max = cfg.get("period_max")
    if period_max is None:
        period_max = max(period_min * 2.0, baseline / 2.0)
    period_max = float(period_max)

    durations = cfg.get("durations", [0.03, 0.04, 0.05, 0.06, 0.08])
    n_freq_coarse = int(cfg.get("n_freq_coarse", 40000))
    n_grid_fine = int(cfg.get("n_grid_fine", 100000))

    # Coarse BLS over the whole range.
    P_coarse, stat_coarse, dur_c, t0_c = B.bls_search(
        t2, det2, e2, period_min, period_max, n_freq_coarse, durations)
    # Dense local refinement so the step resolves the true peak.
    P_fine, stat_fine, dur_f, t0_f = B.refine_period(
        t2, det2, e2, P_coarse, durations, n_grid=n_grid_fine)
    if stat_fine >= stat_coarse:
        best_P, best_stat, best_dur, best_t0 = P_fine, stat_fine, dur_f, t0_f
    else:
        best_P, best_stat, best_dur, best_t0 = P_coarse, stat_coarse, dur_c, t0_c

    # Harmonic/alias sanity: statistic at half and double the best period.
    def _stat_at(P):
        if P < period_min or P > period_max:
            return None
        _, s, _, _ = B.refine_period(t2, det2, e2, P, durations,
                                     n_grid=4000, frac=0.004)
        return float(s)

    stat_half = _stat_at(best_P / 2.0)
    stat_double = _stat_at(best_P * 2.0)

    diag = B.fold_diagnostics(t2, det2, e2, best_P)

    # PRIMARY period: a joint simultaneous transit fit on the RAW flux (shared
    # ephemeris + per-transit local baseline). This transit-timing period is
    # unbiased by box/detrend residual slopes that can shift a BLS peak by
    # ~1e-3 d, and it is highly stable across window/baseline choices. The BLS
    # peak is used only to initialise it and as a consistency check.
    final_P = best_P
    source = "bls_fine"
    fit = B.joint_transit_fit(t, f, e, best_P, best_t0, best_dur)
    ephem = None
    if fit is not None:
        consistent = (fit["n_transits"] >= 2 and
                      abs(fit["period"] - best_P) <= max(5.0 * fit["period_err"],
                                                         0.01 * best_P))
        ephem = {"period": fit["period"], "period_err": fit["period_err"],
                 "n_transits": fit["n_transits"], "red_chi2": fit["red_chi2"],
                 "consistent_with_bls": bool(consistent)}
        # Accept the transit-timing period when it is well constrained and
        # consistent with the BLS detection (same signal, not a wrong alias).
        if consistent and (not np.isfinite(fit["red_chi2"]) or fit["red_chi2"] < 5.0):
            final_P = fit["period"]
            source = "joint_transit_fit"

    rounded = render_period(final_P)
    with open(output_path, "w") as fh:
        fh.write(rounded + "\n")

    report = {
        "period_days": float(final_P),
        "period_rounded": rounded,
        "period_source": source,
        "bls_period": float(best_P),
        "ephemeris": ephem,
        "n_used": int(t2.size),
        "baseline_days": baseline,
        "period_min": period_min,
        "period_max": period_max,
        "best_stat": float(best_stat),
        "stat_half": stat_half,
        "stat_double": stat_double,
        "duration_days": best_dur,
        "transit_time": best_t0,
        "output_path": output_path,
    }
    report.update(diag)
    if warning:
        report["warning"] = warning
    report["format_ok"] = bool(FORMAT_RE.match(rounded))
    return report


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--self-check":
        val = float(sys.argv[2])
        rendered = render_period(val)
        print(json.dumps({"rendered": rendered,
                          "format_ok": bool(FORMAT_RE.match(rendered))}))
        return
    try:
        raw = sys.stdin.read().strip()
        cfg = json.loads(raw) if raw else {}
    except Exception as exc:
        print(json.dumps({"error": "bad stdin JSON: %s" % exc}))
        sys.exit(2)
    try:
        report = run(cfg)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
