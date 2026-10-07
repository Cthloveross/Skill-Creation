#!/usr/bin/env python3
"""Detect a repeated box-like transit period from JSON-stdin TESS inputs."""
import json
import math
import os
import sys
import traceback

import numpy as np


def read_lightcurve(path):
    """Read first four numeric columns and retain finite quality-zero rows."""
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.strip().replace(",", " ").split()
            if len(fields) < 4:
                continue
            try:
                rows.append([float(fields[i]) for i in range(4)])
            except ValueError:
                continue
    if not rows:
        raise ValueError("no numeric four-column rows were found")
    raw = np.asarray(rows, dtype=float)
    keep = ((raw[:, 2] == 0) & np.isfinite(raw[:, 0]) &
            np.isfinite(raw[:, 1]) & np.isfinite(raw[:, 3]))
    good = raw[keep]
    if len(good):
        good = good[np.argsort(good[:, 0])]
    return good[:, 0], good[:, 1], len(rows), int(np.sum(keep))


def median_cadence(time):
    steps = np.diff(time)
    steps = steps[np.isfinite(steps) & (steps > 0)]
    if not len(steps):
        raise ValueError("timestamps have no positive cadence")
    return float(np.median(steps))


def odd_window(days, cadence, length):
    """Return an odd, legal Savitzky--Golay window length."""
    width = max(31, int(round(days / cadence)))
    width += (width + 1) % 2
    largest = length if length % 2 else length - 1
    return min(width, largest)


def segmented_residual(time, flux, cadence):
    """Detrend each observing segment without bridging temporal gaps."""
    from scipy.signal import savgol_filter

    steps = np.diff(time)
    breaks = np.flatnonzero(steps > max(8.0 * cadence, 0.08)) + 1
    residual = np.empty_like(flux)
    starts = np.r_[0, breaks]
    stops = np.r_[breaks, len(time)]
    for start, stop in zip(starts, stops):
        segment = flux[start:stop]
        window = odd_window(0.7, cadence, len(segment))
        if window >= 7:
            residual[start:stop] = segment - savgol_filter(
                segment, window_length=window, polyorder=2, mode="interp")
        else:
            residual[start:stop] = segment - np.median(segment)
    lo, hi = np.quantile(residual, [0.002, 0.998])
    return np.clip(residual, lo, hi), int(len(starts))


def global_residual(flux, cadence):
    """Full-series activity residual used only as an alias diagnostic."""
    from scipy.signal import savgol_filter

    window = odd_window(0.8, cadence, len(flux))
    if window < 7:
        raise ValueError("too few points for global activity detrending")
    residual = flux - savgol_filter(flux, window_length=window, polyorder=2,
                                    mode="interp")
    lo, hi = np.quantile(residual, [0.001, 0.999])
    return np.clip(residual, lo, hi), int(window)


def box_score(time, residual, period, bins=180):
    """Return deepest short phase-box mean divided by robust scatter."""
    phase = ((time - time[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins)
    counts = np.bincount(index, minlength=bins)
    deepest = np.inf
    for width in (2, 3, 4, 5):
        es = np.r_[sums, sums[:width]].cumsum()
        ec = np.r_[counts, counts[:width]].cumsum()
        box_sum = es[width:] - es[:-width]
        box_n = ec[width:] - ec[:-width]
        mean = np.divide(box_sum, box_n, out=np.full(bins, np.nan),
                         where=box_n > 0)
        deepest = min(deepest, float(np.nanmin(mean)))
    scatter = 1.4826 * np.median(np.abs(residual - np.median(residual)))
    return float(-deepest / max(float(scatter), 1e-12))


def count_weighted_bls(time, residual, period, bins=240, return_location=False):
    """Scan circular phase boxes and return the strongest sampled dip score."""
    phase = ((time - time[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins)
    counts = np.bincount(index, minlength=bins).astype(float)
    total_sum, total_n = float(sums.sum()), float(counts.sum())
    scatter = max(float(1.4826 * np.median(
        np.abs(residual - np.median(residual)))), 1e-12)
    best, best_start, best_width = -np.inf, 0, 0
    for width in range(1, 9):
        es = np.r_[sums, sums[:width]]
        ec = np.r_[counts, counts[:width]]
        box_sums = np.cumsum(es)[width:] - np.cumsum(es)[:-width]
        box_ns = np.cumsum(ec)[width:] - np.cumsum(ec)[:-width]
        valid = (box_ns >= 8) & ((total_n - box_ns) >= 8)
        inside = np.divide(box_sums, box_ns, out=np.zeros(bins),
                           where=box_ns > 0)
        outside = np.divide(total_sum - box_sums, total_n - box_ns,
                            out=np.zeros(bins), where=(total_n - box_ns) > 0)
        scores = ((outside - inside) *
                  np.sqrt(box_ns * (total_n - box_ns) / total_n) / scatter)
        scores[~valid] = -np.inf
        start = int(np.argmax(scores))
        if scores[start] > best:
            best, best_start, best_width = float(scores[start]), start, width
    if return_location:
        return best, best_start, best_width
    return best


def supported_epochs(time, residual, period, start, width, bins=240):
    """Count independent observed orbits supporting the chosen folded box."""
    phase = ((time - time[0]) % period) / period
    center = ((start + width / 2.0) % bins) / bins
    distance = np.abs(((phase - center + 0.5) % 1.0) - 0.5)
    in_box = distance <= width / (2.0 * bins)
    epochs = np.floor((time - time[0]) / period).astype(int)
    median = np.median(residual)
    count = 0
    for epoch in np.unique(epochs):
        values = residual[(epochs == epoch) & in_box]
        if len(values) >= 2 and np.median(values) < median:
            count += 1
    return count


def leading_indices(scores, n=160):
    """Indices of high finite scores, avoiding a full sort."""
    n = min(n, len(scores))
    safe = np.nan_to_num(scores, nan=-np.inf, neginf=-np.inf)
    return np.argpartition(safe, -n)[-n:]


def period_candidates(grid, score, low, high):
    """Generate display-precision candidates around leading grid maxima."""
    candidates = set()
    for value in grid[leading_indices(score)]:
        rounded = float(f"{float(value):.5f}")
        for offset in range(-5, 6):
            candidate = float(f"{rounded + offset * 1e-5:.5f}")
            if low <= candidate <= high:
                candidates.add(candidate)
    return sorted(candidates)


def choose_period(time, residual, low, high, trials):
    """Choose highest BLS period with at least three independently seen events."""
    grid = np.linspace(low, high, trials)
    grid_scores = np.asarray([
        count_weighted_bls(time, residual, float(period)) for period in grid
    ])
    if not np.isfinite(grid_scores).any() or np.nanmax(grid_scores) <= 0:
        raise ValueError("no positive finite count-weighted box score was found")

    # Re-score nearby five-decimal values. This separates presentation rounding
    # from the broad period search and retains the exact displayed candidate.
    checked = []
    for period in period_candidates(grid, grid_scores, low, high):
        score, start, width = count_weighted_bls(
            time, residual, period, return_location=True)
        support = supported_epochs(time, residual, period, start, width)
        checked.append({"period": period, "score": float(score),
                        "start": int(start), "width": int(width),
                        "support": int(support)})
    viable = [item for item in checked
              if np.isfinite(item["score"]) and item["score"] > 0 and
              item["support"] >= 3]
    if not viable:
        raise ValueError("no positive box candidate is supported in three epochs")
    # Repeated-event evidence is the primary selection criterion. Score is
    # first; support breaks close aliases deterministically.
    chosen = max(viable, key=lambda item: (item["score"], item["support"],
                                           -item["period"]))
    peak_index = int(np.nanargmax(grid_scores))
    return chosen, grid, grid_scores, peak_index, len(checked)


def main(config):
    try:
        import scipy.signal  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("SciPy is required for activity detrending") from exc

    path = config.get("input_path")
    output = config.get("output_path")
    if not isinstance(path, str) or not path:
        raise ValueError("input_path must be a nonempty string")
    if not isinstance(output, str) or not output:
        raise ValueError("output_path must be a nonempty string")

    time, flux, numeric_rows, trusted_rows = read_lightcurve(path)
    if len(time) < 100:
        raise ValueError("fewer than 100 finite quality-zero cadences remain")
    cadence = median_cadence(time)
    baseline = float(time[-1] - time[0])
    if not np.isfinite(baseline) or baseline <= 0:
        raise ValueError("time baseline is not positive")

    low = float(config.get("min_period", 0.25))
    requested_high = config.get("max_period")
    high = (min(15.0, baseline / 1.8) if requested_high is None
            else float(requested_high))
    trials = int(config.get("bls_trials", 5000))
    global_trials = int(config.get("global_trials", 3500))
    if not (np.isfinite(low) and np.isfinite(high) and 0 < low < high):
        raise ValueError("requested period range is invalid")
    if trials < 500 or global_trials < 500:
        raise ValueError("bls_trials and global_trials must each be at least 500")

    residual, segments = segmented_residual(time, flux, cadence)
    chosen, bls_grid, bls_scores, bls_peak, checked_count = choose_period(
        time, residual, low, high, trials)

    # An independent full-series diagnostic is intentionally not used to turn a
    # high but sparsely supported activity/alias feature into the final period.
    diagnostic_residual, global_window = global_residual(flux, cadence)
    diagnostic_grid = np.linspace(max(0.2, low), high, global_trials)
    diagnostic_scores = np.asarray([
        box_score(time, diagnostic_residual, float(period))
        for period in diagnostic_grid
    ])
    diagnostic_peak = int(np.nanargmax(diagnostic_scores))
    chosen_global_score = box_score(time, diagnostic_residual,
                                    chosen["period"])

    parent = os.path.dirname(os.path.abspath(output))
    os.makedirs(parent, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(f"{chosen['period']:.5f}\n")

    return {
        "ok": True,
        "output_path": output,
        "period_days": chosen["period"],
        "period_rounded": f"{chosen['period']:.5f}",
        "count_weighted_bls_score": chosen["score"],
        "supported_epochs": chosen["support"],
        "box_start": chosen["start"],
        "box_width": chosen["width"],
        "bls_grid_peak_period": float(bls_grid[bls_peak]),
        "bls_grid_peak_score": float(bls_scores[bls_peak]),
        "full_series_box_score": float(chosen_global_score),
        "full_series_peak_period": float(diagnostic_grid[diagnostic_peak]),
        "full_series_peak_score": float(diagnostic_scores[diagnostic_peak]),
        "checked_display_candidates": checked_count,
        "input_numeric_rows": numeric_rows,
        "quality_trusted_rows": trusted_rows,
        "cadence_days": cadence,
        "activity_segments": segments,
        "global_trend_window_points": global_window,
        "search_range_days": [low, high],
        "bls_trials": trials,
        "global_trials": global_trials,
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
