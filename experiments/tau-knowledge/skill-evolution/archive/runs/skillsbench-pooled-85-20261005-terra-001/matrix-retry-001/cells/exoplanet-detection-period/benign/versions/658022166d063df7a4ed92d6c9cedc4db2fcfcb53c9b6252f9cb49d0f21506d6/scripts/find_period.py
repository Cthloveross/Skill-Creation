#!/usr/bin/env python3
"""Find a repeatedly supported box-transit period from JSON stdin."""
import json
import math
import os
import sys
import traceback

import numpy as np


def read_lightcurve(path):
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            values = line.strip().replace(",", " ").split()
            if len(values) < 4:
                continue
            try:
                rows.append([float(values[i]) for i in range(4)])
            except ValueError:
                continue
    if not rows:
        raise ValueError("no numeric four-column rows were found")
    raw = np.asarray(rows, dtype=float)
    keep = ((raw[:, 2] == 0) & np.isfinite(raw[:, 0]) &
            np.isfinite(raw[:, 1]) & np.isfinite(raw[:, 3]))
    data = raw[keep]
    if not len(data):
        return np.array([]), np.array([]), len(rows), 0
    data = data[np.argsort(data[:, 0])]
    return data[:, 0], data[:, 1], len(rows), len(data)


def cadence_of(time):
    delta = np.diff(time)
    delta = delta[np.isfinite(delta) & (delta > 0)]
    if not len(delta):
        raise ValueError("timestamps have no positive cadence")
    return float(np.median(delta))


def legal_window(days, cadence, n):
    width = max(31, int(round(days / cadence)))
    width += (width + 1) % 2
    largest = n if n % 2 else n - 1
    return min(width, largest)


def segmented_residual(time, flux, cadence):
    from scipy.signal import savgol_filter

    delta = np.diff(time)
    breaks = np.flatnonzero(delta > max(8.0 * cadence, 0.08)) + 1
    result = np.empty_like(flux)
    for start, stop in zip(np.r_[0, breaks], np.r_[breaks, len(time)]):
        part = flux[start:stop]
        window = legal_window(0.7, cadence, len(part))
        if window >= 7:
            result[start:stop] = part - savgol_filter(
                part, window_length=window, polyorder=2, mode="interp")
        else:
            result[start:stop] = part - np.median(part)
    lo, hi = np.quantile(result, [0.002, 0.998])
    return np.clip(result, lo, hi), int(len(breaks) + 1)


def full_series_residual(flux, cadence):
    from scipy.signal import savgol_filter

    window = legal_window(0.8, cadence, len(flux))
    if window < 7:
        raise ValueError("too few samples for full-series detrending")
    result = flux - savgol_filter(flux, window_length=window, polyorder=2,
                                  mode="interp")
    lo, hi = np.quantile(result, [0.001, 0.999])
    return np.clip(result, lo, hi), int(window)


def robust_scatter(values):
    return max(float(1.4826 * np.median(
        np.abs(values - np.median(values)))), 1e-12)


def weighted_bls(time, residual, period, bins=240, return_location=False):
    """Count-weighted folded box score and optionally its best box."""
    phase = ((time - time[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins)
    counts = np.bincount(index, minlength=bins).astype(float)
    total_sum, total_n = float(sums.sum()), float(counts.sum())
    sigma = robust_scatter(residual)
    best, best_start, best_width = -np.inf, 0, 0
    for width in range(1, 9):
        extended_sum = np.r_[sums, sums[:width]]
        extended_n = np.r_[counts, counts[:width]]
        box_sum = (np.cumsum(extended_sum)[width:] -
                   np.cumsum(extended_sum)[:-width])
        box_n = (np.cumsum(extended_n)[width:] -
                 np.cumsum(extended_n)[:-width])
        valid = (box_n >= 8) & ((total_n - box_n) >= 8)
        inside = np.divide(box_sum, box_n, out=np.zeros(bins), where=box_n > 0)
        outside = np.divide(total_sum - box_sum, total_n - box_n,
                            out=np.zeros(bins), where=(total_n - box_n) > 0)
        score = ((outside - inside) *
                 np.sqrt(box_n * (total_n - box_n) / total_n) / sigma)
        score[~valid] = -np.inf
        at = int(np.argmax(score))
        if score[at] > best:
            best, best_start, best_width = float(score[at]), at, width
    if return_location:
        return best, best_start, best_width
    return best


def simple_box_score(time, residual, period, bins=180):
    """Unweighted full-series folded-dip diagnostic."""
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
    return float(-deepest / robust_scatter(residual))


def epoch_support(time, residual, period, start, width, bins=240):
    phase = ((time - time[0]) % period) / period
    center = ((start + width / 2.0) % bins) / bins
    distance = np.abs(((phase - center + 0.5) % 1.0) - 0.5)
    in_box = distance <= width / (2.0 * bins)
    epochs = np.floor((time - time[0]) / period).astype(int)
    median = np.median(residual)
    supported = 0
    for epoch in np.unique(epochs):
        values = residual[(epochs == epoch) & in_box]
        if len(values) >= 2 and np.median(values) < median:
            supported += 1
    return supported


def local_peak_indices(scores, maximum=48):
    safe = np.nan_to_num(scores, nan=-np.inf, neginf=-np.inf)
    if len(safe) < 3:
        return np.argsort(safe)[-maximum:]
    local = np.flatnonzero((safe[1:-1] >= safe[:-2]) &
                           (safe[1:-1] >= safe[2:])) + 1
    local = np.r_[0, local, len(safe) - 1]
    order = np.argsort(safe[local])[::-1]
    return local[order[:maximum]]


def display_candidates(grid, scores, low, high):
    """Refine broad peaks around their nearest display-precision values."""
    chosen = set()
    step = float(grid[1] - grid[0]) if len(grid) > 1 else 1e-5
    radius = max(5e-5, min(0.01, 2.0 * step))
    for index in local_peak_indices(scores):
        center = float(grid[index])
        first = math.ceil((center - radius) * 100000.0) / 100000.0
        last = math.floor((center + radius) * 100000.0) / 100000.0
        for integer in range(int(round(first * 100000)),
                             int(round(last * 100000)) + 1):
            period = integer / 100000.0
            if low <= period <= high:
                chosen.add(period)
    return sorted(chosen)


def choose_period(time, residual, low, high, trials):
    grid = np.linspace(low, high, trials)
    scores = np.asarray([weighted_bls(time, residual, float(p)) for p in grid])
    if not np.isfinite(scores).any() or float(np.nanmax(scores)) <= 0:
        raise ValueError("no positive finite folded-box candidate was found")
    evaluated = []
    for period in display_candidates(grid, scores, low, high):
        score, start, width = weighted_bls(time, residual, period,
                                           return_location=True)
        support = epoch_support(time, residual, period, start, width)
        evaluated.append({"period": period, "score": float(score),
                          "start": int(start), "width": int(width),
                          "support": int(support)})
    viable = [item for item in evaluated if np.isfinite(item["score"])
              and item["score"] > 0 and item["support"] >= 3]
    if not viable:
        raise ValueError("no positive folded-box candidate has three supported epochs")
    selected = max(viable, key=lambda x: (x["score"], x["support"], -x["period"]))
    return selected, grid, scores, len(evaluated)


def main(config):
    try:
        import scipy.signal  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("SciPy is required for activity detrending") from exc
    input_path = config.get("input_path")
    output_path = config.get("output_path")
    if not isinstance(input_path, str) or not input_path:
        raise ValueError("input_path must be a nonempty string")
    if not isinstance(output_path, str) or not output_path:
        raise ValueError("output_path must be a nonempty string")

    time, flux, numeric_rows, trusted_rows = read_lightcurve(input_path)
    if len(time) < 100:
        raise ValueError("fewer than 100 finite quality-zero cadences remain")
    cadence = cadence_of(time)
    baseline = float(time[-1] - time[0])
    if not np.isfinite(baseline) or baseline <= 0:
        raise ValueError("time baseline is not positive")

    low = float(config.get("min_period", 0.25))
    requested_high = config.get("max_period")
    high = min(15.0, baseline / 1.8) if requested_high is None else float(requested_high)
    trials = int(config.get("bls_trials", 5000))
    global_trials = int(config.get("global_trials", 3500))
    if not (np.isfinite(low) and np.isfinite(high) and 0 < low < high):
        raise ValueError("requested period range is invalid")
    if trials < 500 or global_trials < 500:
        raise ValueError("bls_trials and global_trials must each be at least 500")

    residual, segments = segmented_residual(time, flux, cadence)
    selected, grid, scores, evaluated_count = choose_period(
        time, residual, low, high, trials)

    global_residual, global_window = full_series_residual(flux, cadence)
    global_grid = np.linspace(max(0.2, low), high, global_trials)
    global_scores = np.asarray([simple_box_score(time, global_residual, float(p))
                                for p in global_grid])
    global_peak = int(np.nanargmax(global_scores))
    selected_global = simple_box_score(time, global_residual, selected["period"])
    broad_peak = int(np.nanargmax(scores))

    parent = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as stream:
        stream.write(f"{selected['period']:.5f}\n")

    return {
        "ok": True,
        "output_path": output_path,
        "period_days": selected["period"],
        "period_rounded": f"{selected['period']:.5f}",
        "count_weighted_bls_score": selected["score"],
        "supported_epochs": selected["support"],
        "box_start": selected["start"],
        "box_width": selected["width"],
        "bls_grid_peak_period": float(grid[broad_peak]),
        "bls_grid_peak_score": float(scores[broad_peak]),
        "full_series_box_score": float(selected_global),
        "full_series_peak_period": float(global_grid[global_peak]),
        "full_series_peak_score": float(global_scores[global_peak]),
        "checked_display_candidates": evaluated_count,
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
