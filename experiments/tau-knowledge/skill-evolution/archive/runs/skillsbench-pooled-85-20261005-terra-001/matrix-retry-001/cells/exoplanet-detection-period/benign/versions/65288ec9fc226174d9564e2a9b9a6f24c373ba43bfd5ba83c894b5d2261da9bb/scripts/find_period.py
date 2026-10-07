#!/usr/bin/env python3
"""Robust transit-period search. JSON stdin -> JSON stdout; writes requested period file."""
import json
import math
import os
import sys
import traceback

import numpy as np


def read_lightcurve(path):
    """Read first four numeric fields from an ASCII comma/whitespace table."""
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.strip().replace(",", " ").split()
            if len(fields) < 4:
                continue
            try:
                rows.append([float(fields[i]) for i in range(4)])
            except ValueError:
                # This includes ordinary column-header lines.
                continue
    if not rows:
        raise ValueError("no numeric rows with four columns were found")
    a = np.asarray(rows, dtype=float)
    trusted = (
        np.isfinite(a[:, 0]) & np.isfinite(a[:, 1]) & np.isfinite(a[:, 3])
        & (a[:, 2] == 0) & (a[:, 3] > 0)
    )
    t, flux, dy = a[trusted, 0], a[trusted, 1], a[trusted, 3]
    order = np.argsort(t)
    return t[order], flux[order], dy[order], int(a.shape[0]), int(np.sum(trusted))


def rolling_nanmedian(values, half_window):
    """Small, deterministic centered rolling median for binned series."""
    n = len(values)
    out = np.empty(n, dtype=float)
    for i in range(n):
        lo = max(0, i - half_window)
        hi = min(n, i + half_window + 1)
        v = values[lo:hi]
        v = v[np.isfinite(v)]
        out[i] = np.median(v) if len(v) else np.nan
    return out


def robust_sigma(x):
    x = np.asarray(x)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return np.nan
    med = np.median(x)
    return 1.4826 * np.median(np.abs(x - med))


def segment_trend(t, flux, window_days):
    """Estimate a slowly changing multiplicative trend without spanning gaps."""
    dt = np.diff(t)
    positive_dt = dt[dt > 0]
    cadence = np.median(positive_dt) if len(positive_dt) else 0.02
    bin_width = max(0.005, min(0.05, 3.0 * cadence))
    gap = max(0.30, 8.0 * cadence)
    starts = np.r_[0, np.flatnonzero(dt > gap) + 1]
    ends = np.r_[starts[1:], len(t)]
    trend = np.empty_like(flux)

    for start, end in zip(starts, ends):
        ts, ys = t[start:end], flux[start:end]
        if len(ts) < 5:
            trend[start:end] = np.median(ys)
            continue
        origin = ts[0]
        bi = np.floor((ts - origin) / bin_width).astype(int)
        nb = int(bi.max()) + 1
        centers = origin + (np.arange(nb) + 0.5) * bin_width

        # First pass identifies gross positive excursions. It deliberately does
        # not label negative points as bad data in the eventual search series.
        med0 = np.median(ys)
        sig0 = robust_sigma(ys - med0)
        if not np.isfinite(sig0) or sig0 <= 0:
            sig0 = max(np.std(ys), 1e-8)
        usable = ys < med0 + 6.0 * sig0
        bmed = np.full(nb, np.nan)
        for k in range(nb):
            q = ys[(bi == k) & usable]
            if len(q):
                bmed[k] = np.median(q)
        if not np.any(np.isfinite(bmed)):
            trend[start:end] = med0
            continue
        half = max(1, int(round(window_days / bin_width / 2.0)))
        coarse = rolling_nanmedian(bmed, half)
        valid = np.isfinite(coarse)
        coarse = np.interp(centers, centers[valid], coarse[valid])
        preliminary = np.interp(ts, centers, coarse, left=coarse[0], right=coarse[-1])

        # Exclude provisional dips only for a second trend estimate. This keeps
        # a transit from pulling the baseline down, but preserves it later.
        residual = ys - preliminary
        sig = robust_sigma(residual)
        if not np.isfinite(sig) or sig <= 0:
            sig = sig0
        trend_usable = (residual > -4.0 * sig) & (residual < 6.0 * sig)
        bmed2 = np.full(nb, np.nan)
        for k in range(nb):
            q = ys[(bi == k) & trend_usable]
            if len(q):
                bmed2[k] = np.median(q)
        if np.any(np.isfinite(bmed2)):
            coarse2 = rolling_nanmedian(bmed2, half)
            valid = np.isfinite(coarse2)
            coarse2 = np.interp(centers, centers[valid], coarse2[valid])
            trend[start:end] = np.interp(ts, centers, coarse2, left=coarse2[0], right=coarse2[-1])
        else:
            trend[start:end] = preliminary
    return trend


def phase_distance(phase):
    return (phase + 0.5) % 1.0 - 0.5


def transit_epoch_count(t, period, t0, duration):
    phase = ((t - t0) / period) % 1.0
    inside = np.abs(phase_distance(phase)) <= duration / (2.0 * period)
    if not np.any(inside):
        return 0, 0
    epochs = np.unique(np.rint((t[inside] - t0) / period).astype(int))
    return len(epochs), int(np.sum(inside))


def astropy_search(t, y, dy, lo, hi):
    from astropy.timeseries import BoxLeastSquares

    durations = np.array([0.010, 0.015, 0.020, 0.030, 0.045, 0.065,
                          0.090, 0.130, 0.180, 0.250], dtype=float)
    durations = durations[durations < 0.45 * lo]
    if len(durations) == 0:
        durations = np.array([0.1 * lo])
    bls = BoxLeastSquares(t, y, dy=dy)
    periods = bls.autoperiod(
        durations, minimum_period=lo, maximum_period=hi,
        minimum_n_transit=2, frequency_factor=0.7
    )
    if len(periods) == 0:
        raise ValueError("BLS generated no trial periods")
    result = bls.power(periods, durations, objective="likelihood")
    power = np.asarray(result.power)
    if not np.any(np.isfinite(power)):
        raise ValueError("BLS returned no finite powers")

    # Re-evaluate prominent peaks and explicitly test the common half/double
    # aliases. This is a comparison step, not a blind choice of a harmonic.
    npeak = min(24, len(power))
    idx = np.argpartition(np.nan_to_num(power, nan=-np.inf), -npeak)[-npeak:]
    candidates = []
    for p in np.asarray(periods)[idx]:
        for q in (p, p * 0.5, p * 2.0):
            if lo <= q <= hi:
                candidates.append(float(q))
    candidates = np.array(sorted(set(round(q, 11) for q in candidates)))
    checked = bls.power(candidates, durations, objective="likelihood")
    j = int(np.nanargmax(checked.power))
    p0 = float(candidates[j])

    # Numerical refinement is deliberately separate from final presentation
    # rounding. Use the automatically selected local grid scale.
    diffs = np.abs(np.diff(np.sort(np.asarray(periods))))
    step = float(np.median(diffs[diffs > 0])) if np.any(diffs > 0) else p0 * 1e-4
    half_width = max(3.0 * step, p0 * 2e-5)
    fine = np.linspace(max(lo, p0 - half_width), min(hi, p0 + half_width), 601)
    refined = bls.power(fine, durations, objective="likelihood")
    k = int(np.nanargmax(refined.power))
    period = float(fine[k])
    duration = float(np.asarray(refined.duration)[k])
    t0 = float(np.asarray(refined.transit_time)[k])
    depth = float(np.asarray(refined.depth)[k])
    epochs, in_points = transit_epoch_count(t, period, t0, duration)
    return period, duration, depth, epochs, in_points, "astropy_box_least_squares"


def fallback_search(t, y, dy, lo, hi):
    """Dependency-free approximate BLS for environments without Astropy."""
    # Retain temporal coverage while capping work for very dense cadence data.
    max_points = 18000
    if len(t) > max_points:
        take = np.linspace(0, len(t) - 1, max_points).astype(int)
        t, y = t[take], y[take]
    baseline = t[-1] - t[0]
    fmin, fmax = 1.0 / hi, 1.0 / lo
    nfreq = int(min(12000, max(3500, math.ceil((fmax - fmin) * baseline * 85))))
    freqs = np.linspace(fmin, fmax, nfreq)
    bins = 256
    widths = (2, 3, 4, 6, 8, 12, 16, 22)
    best = (-np.inf, None, None, None)
    centered = y - np.median(y)
    for freq in freqs:
        phase = ((t - t[0]) * freq) % 1.0
        ib = np.minimum((phase * bins).astype(int), bins - 1)
        sums = np.bincount(ib, weights=centered, minlength=bins)
        counts = np.bincount(ib, minlength=bins).astype(float)
        ss = np.r_[sums, sums]
        cc = np.r_[counts, counts]
        for width in widths:
            win_sum = np.convolve(ss, np.ones(width), mode="valid")[:bins]
            win_count = np.convolve(cc, np.ones(width), mode="valid")[:bins]
            valid = win_count >= 5
            if not np.any(valid):
                continue
            means = np.full(bins, np.inf)
            means[valid] = win_sum[valid] / win_count[valid]
            b = int(np.argmin(means))
            depth = -means[b]
            score = depth * math.sqrt(win_count[b])
            if depth > 0 and score > best[0]:
                best = (score, 1.0 / freq, width, b)
    if best[1] is None:
        raise ValueError("fallback BLS found no transit-like box")
    _, period, width, b = best
    duration = period * width / bins
    t0 = t[0] + ((b + width / 2.0) / bins) * period
    phase = ((t - t0) / period) % 1.0
    inside = np.abs(phase_distance(phase)) <= duration / (2.0 * period)
    depth = -float(np.median(y[inside])) if np.any(inside) else 0.0
    epochs, in_points = transit_epoch_count(t, period, t0, duration)
    return period, duration, depth, epochs, in_points, "numpy_phase_binned_bls"


def main(config):
    path = config.get("input_path")
    output = config.get("output_path")
    if not isinstance(path, str) or not path:
        raise ValueError("input_path must be a nonempty string")
    if not isinstance(output, str) or not output:
        raise ValueError("output_path must be a nonempty string")
    t, flux, dy, rows, trusted = read_lightcurve(path)
    if len(t) < 30:
        raise ValueError("fewer than 30 trusted finite cadences remain")
    baseline = float(t[-1] - t[0])
    if not np.isfinite(baseline) or baseline <= 0:
        raise ValueError("time baseline is not positive")
    lo = float(config.get("min_period", 0.3))
    configured_hi = config.get("max_period", None)
    hi = min(20.0, baseline / 2.0) if configured_hi is None else float(configured_hi)
    if lo <= 0 or hi <= lo:
        raise ValueError("requested period interval is unsupported by the time baseline")
    window = float(config.get("trend_window_days", 1.5))
    if window <= 0:
        raise ValueError("trend_window_days must be positive")

    trend = segment_trend(t, flux, window)
    valid = np.isfinite(trend) & (trend > 0)
    t, flux, dy, trend = t[valid], flux[valid], dy[valid], trend[valid]
    y = flux / trend - 1.0
    dy = dy / trend
    # Remove only conspicuous positive artifacts from BLS. Negative values are
    # retained so a real transit cannot be filtered as an outlier.
    sig = robust_sigma(y)
    if not np.isfinite(sig) or sig <= 0:
        sig = max(float(np.std(y)), 1e-8)
    keep = np.isfinite(y) & np.isfinite(dy) & (dy > 0) & (y < 8.0 * sig)
    t, y, dy = t[keep], y[keep], dy[keep]
    if len(t) < 30:
        raise ValueError("too few cadences remain after robust artifact filtering")
    t = t - t[0]

    try:
        period, duration, depth, epochs, in_points, backend = astropy_search(t, y, dy, lo, hi)
    except ImportError:
        period, duration, depth, epochs, in_points, backend = fallback_search(t, y, dy, lo, hi)
    if not np.isfinite(period) or not (lo <= period <= hi):
        raise ValueError("period search did not return a finite in-range period")
    if not np.isfinite(depth) or depth <= 0:
        raise ValueError("best box does not have a positive transit depth")
    if epochs < 2:
        raise ValueError("candidate is not supported by at least two sampled transit epochs")

    parent = os.path.dirname(os.path.abspath(output))
    os.makedirs(parent, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(f"{period:.5f}\n")
    return {
        "ok": True,
        "period_days": period,
        "period_rounded": f"{period:.5f}",
        "duration_days": duration,
        "depth_relative_flux": depth,
        "transit_epochs": epochs,
        "in_transit_points": in_points,
        "input_numeric_rows": rows,
        "quality_trusted_rows": trusted,
        "search_rows": int(len(t)),
        "backend": backend,
        "output_path": output,
    }


if __name__ == "__main__":
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError("JSON stdin must contain an object")
        print(json.dumps(main(config), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}, sort_keys=True))
        sys.exit(1)
