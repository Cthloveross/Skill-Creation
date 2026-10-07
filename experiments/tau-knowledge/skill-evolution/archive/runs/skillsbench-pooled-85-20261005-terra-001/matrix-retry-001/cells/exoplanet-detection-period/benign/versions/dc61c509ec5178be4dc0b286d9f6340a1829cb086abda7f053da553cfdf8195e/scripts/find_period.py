#!/usr/bin/env python3
"""JSON-stdin TESS box-transit search that writes a five-decimal period artifact."""
import json
import math
import os
import sys
import traceback

import numpy as np


def read_lightcurve(path):
    """Read the first four documented numeric columns, tolerating headers."""
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
        raise ValueError("no numeric lightcurve rows with four columns were found")
    raw = np.asarray(rows, dtype=float)
    keep = ((raw[:, 2] == 0) & np.isfinite(raw[:, 0]) &
            np.isfinite(raw[:, 1]) & np.isfinite(raw[:, 3]))
    data = raw[keep]
    if data.size:
        data = data[np.argsort(data[:, 0])]
    return data[:, 0], data[:, 1], len(rows), int(np.sum(keep))


def cadence_of(time):
    steps = np.diff(time)
    steps = steps[steps > 0]
    if not len(steps):
        raise ValueError("timestamps have no positive cadence")
    return float(np.median(steps))


def odd_window(days, cadence, n):
    window = max(31, int(round(days / cadence)))
    window += (window + 1) % 2
    largest = n if n % 2 else n - 1
    return min(window, largest)


def global_residual(time, flux, cadence):
    """Global 0.8-day smooth trend and conservative tail clipping."""
    from scipy.signal import savgol_filter
    window = odd_window(0.8, cadence, len(flux))
    if window < 7:
        raise ValueError("too few points for global activity detrending")
    residual = flux - savgol_filter(flux, window_length=window, polyorder=2,
                                    mode="interp")
    lo, hi = np.quantile(residual, [0.001, 0.999])
    return np.clip(residual, lo, hi), int(window)


def segmented_residual(time, flux, cadence):
    """Detrend each observing segment so gaps do not bleed into the trend."""
    from scipy.signal import savgol_filter
    steps = np.diff(time)
    breaks = np.flatnonzero(steps > max(8.0 * cadence, 0.08)) + 1
    residual = np.empty_like(flux)
    for start, stop in zip(np.r_[0, breaks], np.r_[breaks, len(time)]):
        segment = flux[start:stop]
        window = odd_window(0.7, cadence, len(segment))
        if window >= 7:
            residual[start:stop] = segment - savgol_filter(
                segment, window_length=window, polyorder=2, mode="interp")
        else:
            residual[start:stop] = segment - np.median(segment)
    lo, hi = np.quantile(residual, [0.002, 0.998])
    return np.clip(residual, lo, hi), int(len(breaks) + 1)


def bls_score(time, residual, period, bins=240, return_location=False):
    """Count-weighted deepest circular phase box, including its location."""
    phase = ((time - time[0]) % period) / period
    idx = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(idx, weights=residual, minlength=bins)
    counts = np.bincount(idx, minlength=bins).astype(float)
    total_sum = float(sums.sum())
    total_n = float(counts.sum())
    scatter = max(float(1.4826 * np.median(
        np.abs(residual - np.median(residual)))), 1e-12)
    best_score, best_start, best_width = -np.inf, 0, 0
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
                 np.sqrt(box_n * (total_n - box_n) / total_n) / scatter)
        score[~valid] = -np.inf
        where = int(np.argmax(score))
        if score[where] > best_score:
            best_score, best_start, best_width = float(score[where]), where, width
    if return_location:
        return best_score, best_start, best_width
    return best_score


def supported_epochs(time, residual, period, start, width, bins=240):
    """Count independently observed below-median orbital transit epochs."""
    phase = ((time - time[0]) % period) / period
    center = ((start + width / 2.0) % bins) / bins
    distance = np.abs(((phase - center + 0.5) % 1.0) - 0.5)
    in_box = distance <= (width / bins) / 2.0
    epoch = np.floor((time - time[0]) / period).astype(int)
    median = np.median(residual)
    count = 0
    for event in np.unique(epoch):
        values = residual[(epoch == event) & in_box]
        if len(values) >= 2 and np.median(values) < median:
            count += 1
    return int(count)


def top_indices(values, n):
    n = min(int(n), len(values))
    if n <= 0:
        return np.array([], dtype=int)
    return np.argpartition(np.nan_to_num(values, nan=-np.inf), -n)[-n:]


def choose_period(time, residual_a, residual_b, low, high, trials):
    """Choose a five-decimal, repeated-event candidate robust to detrending."""
    grid = np.linspace(low, high, trials)
    scores_a = np.asarray([bls_score(time, residual_a, float(p)) for p in grid])
    scores_b = np.asarray([bls_score(time, residual_b, float(p)) for p in grid])
    best_a = float(np.nanmax(scores_a))
    best_b = float(np.nanmax(scores_b))
    if not (np.isfinite(best_a) and np.isfinite(best_b) and best_a > 0 and best_b > 0):
        raise ValueError("no positive finite box-transit score was found")

    # The reporting precision itself can change phase-bin assignments. Evaluate
    # displayable values from broad leading sets of both independent searches.
    leading = np.unique(np.r_[top_indices(scores_a, 256), top_indices(scores_b, 256)])
    candidates = sorted({float(f"{grid[i]:.5f}") for i in leading
                         if low <= float(f"{grid[i]:.5f}") <= high})
    checked = []
    for period in candidates:
        score_a = float(bls_score(time, residual_a, period))
        score_b, start, width = bls_score(time, residual_b, period,
                                          return_location=True)
        support = supported_epochs(time, residual_b, period, start, width)
        if np.isfinite(score_a) and np.isfinite(score_b):
            checked.append({"period": period, "global_score": score_a,
                            "segmented_score": float(score_b),
                            "supported_epochs": support,
                            "box_start": int(start), "box_width": int(width),
                            "global_ratio": score_a / best_a,
                            "segmented_ratio": float(score_b) / best_b})
    if not checked:
        raise ValueError("no displayable finite period candidates were found")

    qualified = [c for c in checked if c["supported_epochs"] >= 3 and
                 c["global_ratio"] >= 0.985 and c["segmented_ratio"] >= 0.985]
    if not qualified:
        # Retain the same physical safeguards if the two smoothing choices do
        # not produce an exact threshold tie at five-decimal precision.
        qualified = [c for c in checked if c["supported_epochs"] >= 3]
    if not qualified:
        raise ValueError("no box candidate is supported in at least three epochs")

    # Maximize the weaker detrending score first, then total support and score.
    chosen = max(qualified, key=lambda c: (
        min(c["global_ratio"], c["segmented_ratio"]),
        c["supported_epochs"],
        c["global_ratio"] + c["segmented_ratio"]))
    return chosen, grid, scores_a, scores_b, best_a, best_b, len(checked)


def main(config):
    try:
        from scipy.signal import savgol_filter  # noqa: F401; dependency check
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
    cadence = cadence_of(time)
    baseline = float(time[-1] - time[0])
    if not np.isfinite(baseline) or baseline <= 0:
        raise ValueError("time baseline is not positive")
    low = float(config.get("min_period", 0.25))
    requested_high = config.get("max_period")
    high = min(15.0, baseline / 1.8) if requested_high is None else float(requested_high)
    trials = int(config.get("trials", 5000))
    if not (np.isfinite(low) and np.isfinite(high) and 0 < low < high):
        raise ValueError("requested period range is invalid")
    if trials < 500:
        raise ValueError("trials must be at least 500")

    residual_a, global_window = global_residual(time, flux, cadence)
    residual_b, segment_count = segmented_residual(time, flux, cadence)
    chosen, grid, scores_a, scores_b, best_a, best_b, checked_count = choose_period(
        time, residual_a, residual_b, low, high, trials)

    parent = os.path.dirname(os.path.abspath(output))
    os.makedirs(parent, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(f"{chosen['period']:.5f}\n")

    return {
        "ok": True,
        "output_path": output,
        "period_days": chosen["period"],
        "period_rounded": f"{chosen['period']:.5f}",
        "global_box_score": chosen["global_score"],
        "segmented_box_score": chosen["segmented_score"],
        "global_score_ratio": chosen["global_ratio"],
        "segmented_score_ratio": chosen["segmented_ratio"],
        "supported_epochs": chosen["supported_epochs"],
        "global_grid_best_period": float(grid[int(np.nanargmax(scores_a))]),
        "segmented_grid_best_period": float(grid[int(np.nanargmax(scores_b))]),
        "global_grid_best_score": best_a,
        "segmented_grid_best_score": best_b,
        "checked_display_candidates": checked_count,
        "input_numeric_rows": numeric_rows,
        "quality_trusted_rows": trusted_rows,
        "cadence_days": cadence,
        "global_trend_window_points": global_window,
        "activity_segments": segment_count,
        "search_range_days": [low, high],
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
