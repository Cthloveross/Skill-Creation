#!/usr/bin/env python3
"""Transit period search: JSON stdin -> JSON diagnostics and a period artifact."""
import json
import math
import os
import sys
import traceback

import numpy as np


def read_lightcurve(path):
    """Read documented numeric columns while tolerating headers and delimiters."""
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.strip().replace(",", " ").split()
            if len(fields) < 4:
                continue
            try:
                rows.append([float(fields[k]) for k in range(4)])
            except ValueError:
                continue
    if not rows:
        raise ValueError("no numeric rows with at least four columns were found")
    data = np.asarray(rows, dtype=float)
    good = ((data[:, 2] == 0) & np.isfinite(data[:, 0]) &
            np.isfinite(data[:, 1]) & np.isfinite(data[:, 3]))
    data = data[good]
    if len(data):
        data = data[np.argsort(data[:, 0])]
    return data[:, 0], data[:, 1], int(len(rows)), int(np.sum(good))


def detrended_residual(t, flux, window_days):
    """Remove smooth activity without rejecting ordinary negative transits."""
    try:
        from scipy.signal import savgol_filter
    except ImportError as exc:
        raise RuntimeError("SciPy is required for transit-preserving detrending") from exc
    steps = np.diff(t)
    steps = steps[steps > 0]
    if len(steps) == 0:
        raise ValueError("timestamps do not have positive cadence")
    cadence = float(np.median(steps))
    window = max(31, int(round(window_days / cadence)))
    # Savitzky--Golay requires odd length and cannot exceed the series length.
    window += (window + 1) % 2
    largest_odd = len(t) - 1 + (len(t) % 2)
    window = min(window, largest_odd)
    if window < 5:
        raise ValueError("too few cadences for smooth activity detrending")
    trend = savgol_filter(flux, window_length=window, polyorder=2, mode="interp")
    residual = flux - trend
    # Extreme isolated artifacts should not establish a box-search maximum.
    lo, hi = np.quantile(residual, [0.001, 0.999])
    return np.clip(residual, lo, hi), cadence, window


def box_score(t, residual, period, bins=180):
    """Largest phase-folded short negative box signal, in robust-sigma units."""
    phase = ((t - t[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins)
    counts = np.bincount(index, minlength=bins)
    best = np.inf
    for width in (2, 3, 4, 5):
        # Duplicate the leading bins so windows crossing phase zero are included.
        ext_sum = np.r_[sums, sums[:width]].cumsum()
        ext_count = np.r_[counts, counts[:width]].cumsum()
        win_sum = ext_sum[width:] - ext_sum[:-width]
        win_count = ext_count[width:] - ext_count[:-width]
        means = np.divide(win_sum, win_count, out=np.full(bins, np.nan),
                          where=win_count > 0)
        candidate = np.nanmin(means)
        if candidate < best:
            best = candidate
    scatter = 1.4826 * np.median(np.abs(residual - np.median(residual)))
    return float(-best / max(float(scatter), 1e-12))


def choose_period(t, residual, lo, hi, trials):
    """Search box periods, then validate the actually displayable precision."""
    grid = np.linspace(lo, hi, trials)
    grid_scores = np.asarray([box_score(t, residual, float(p)) for p in grid])
    if not np.any(np.isfinite(grid_scores)):
        raise ValueError("box search returned no finite scores")
    raw_best = float(np.nanmax(grid_scores))
    if not np.isfinite(raw_best) or raw_best <= 0:
        raise ValueError("no positive repeating box-like dimming was found")

    # A formatting change can move phase-bin boundaries. Re-evaluate the most
    # promising trial periods as exact five-decimal values before choosing one.
    nlead = min(48, len(grid))
    lead = np.argpartition(np.nan_to_num(grid_scores, nan=-np.inf), -nlead)[-nlead:]
    displayed = sorted({float(f"{grid[i]:.5f}") for i in lead
                        if lo <= float(f"{grid[i]:.5f}") <= hi})
    if not displayed:
        raise ValueError("no five-decimal candidate lies in requested range")
    display_scores = np.asarray([box_score(t, residual, p) for p in displayed])
    winner = int(np.nanargmax(display_scores))
    period = float(displayed[winner])
    score = float(display_scores[winner])
    if not np.isfinite(score) or score <= 0:
        raise ValueError("displayable candidates have no positive box score")
    return period, score, raw_best, grid, grid_scores


def main(config):
    path = config.get("input_path")
    output = config.get("output_path")
    if not isinstance(path, str) or not path:
        raise ValueError("input_path must be a nonempty string")
    if not isinstance(output, str) or not output:
        raise ValueError("output_path must be a nonempty string")

    t, flux, numeric_rows, trusted_rows = read_lightcurve(path)
    if len(t) < 100:
        raise ValueError("fewer than 100 finite quality-zero cadences remain")
    baseline = float(t[-1] - t[0])
    if not np.isfinite(baseline) or baseline <= 0:
        raise ValueError("time baseline is not positive")

    lo = float(config.get("min_period", 0.2))
    configured_hi = config.get("max_period", None)
    hi = min(15.0, baseline / 1.8) if configured_hi is None else float(configured_hi)
    if not (np.isfinite(lo) and np.isfinite(hi) and 0 < lo < hi):
        raise ValueError("requested period interval is invalid for this baseline")
    window_days = float(config.get("trend_window_days", 0.8))
    if not np.isfinite(window_days) or window_days <= 0:
        raise ValueError("trend_window_days must be positive")
    trials = int(config.get("trials", 3500))
    if trials < 100:
        raise ValueError("trials must be at least 100")

    residual, cadence, window = detrended_residual(t, flux, window_days)
    period, score, raw_best, grid, grid_scores = choose_period(t, residual, lo, hi, trials)
    aliases = {}
    for label, candidate in (("half", period / 2.0), ("double", period * 2.0)):
        if lo <= candidate <= hi:
            aliases[label] = box_score(t, residual, candidate)

    parent = os.path.dirname(os.path.abspath(output))
    os.makedirs(parent, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(f"{period:.5f}\n")

    scatter = 1.4826 * np.median(np.abs(residual - np.median(residual)))
    return {
        "ok": True,
        "output_path": output,
        "period_days": period,
        "period_rounded": f"{period:.5f}",
        "box_score": score,
        "grid_best_score": raw_best,
        "grid_best_period": float(grid[int(np.nanargmax(grid_scores))]),
        "alias_scores": aliases,
        "input_numeric_rows": numeric_rows,
        "quality_trusted_rows": trusted_rows,
        "cadence_days": cadence,
        "trend_window_points": int(window),
        "residual_robust_scatter": float(scatter),
        "search_range_days": [lo, hi],
        "trials": trials,
    }


if __name__ == "__main__":
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError("JSON stdin must contain an object")
        print(json.dumps(main(config), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc),
                          "traceback": traceback.format_exc()}, sort_keys=True))
        sys.exit(1)
