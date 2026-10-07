#!/usr/bin/env python3
"""End-to-end transit-period detection entrypoint.

Stdin: JSON (see SKILL.md). All keys optional; paths default to the task's
`/root/data/tess_lc.txt` and `/root/period.txt`.
Stdout: JSON report. Also writes the rounded period to the output file.

Self-check mode: `python3 detect_period.py --self-check <period>` prints the
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

    nbins = int(cfg.get("nbins", 200))
    n_freq_coarse = int(cfg.get("n_freq_coarse", 12000))
    n_freq_fine = int(cfg.get("n_freq_fine", 3000))

    # Coarse BLS over the full range (full precision kept internally).
    P_coarse, sr_coarse = B.bls_search(
        t2, det2, e2, period_min, period_max, n_freq_coarse, nbins)
    # Fine refinement around the coarse peak.
    P_fine, sr_fine = B.refine_period(
        t2, det2, e2, P_coarse, n_freq_fine, nbins)
    best_P, best_sr = (P_fine, sr_fine) if sr_fine >= sr_coarse else (P_coarse, sr_coarse)

    # Harmonic/alias sanity: SR at half and double the best period.
    def _sr_at(P):
        if P < period_min or P > period_max:
            return None
        _, s = B.refine_period(t2, det2, e2, P, max(500, n_freq_fine // 3),
                               nbins, frac=0.01)
        return float(s)

    sr_half = _sr_at(best_P / 2.0)
    sr_double = _sr_at(best_P * 2.0)

    diag = B.fold_diagnostics(t2, det2, e2, best_P)

    rounded = render_period(best_P)
    with open(output_path, "w") as fh:
        fh.write(rounded + "\n")

    report = {
        "period_days": float(best_P),
        "period_rounded": rounded,
        "n_used": int(t2.size),
        "baseline_days": baseline,
        "period_min": period_min,
        "period_max": period_max,
        "best_sr": float(best_sr),
        "sr_half": sr_half,
        "sr_double": sr_double,
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
    except Exception as exc:  # malformed stdin
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
