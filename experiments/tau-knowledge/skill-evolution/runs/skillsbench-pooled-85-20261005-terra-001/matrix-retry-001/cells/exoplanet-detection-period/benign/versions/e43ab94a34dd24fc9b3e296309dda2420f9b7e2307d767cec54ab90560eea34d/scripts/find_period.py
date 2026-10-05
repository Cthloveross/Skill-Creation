#!/usr/bin/env python3
"""Find a repeatedly supported transit period from JSON-stdin TESS inputs."""
import json
import math
import os
import sys
import traceback

import numpy as np


def read_lightcurve(path):
    """Return sorted finite quality-zero time and flux arrays from four columns."""
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
    good = raw[keep]
    if good.size:
        good = good[np.argsort(good[:, 0])]
    return good[:, 0], good[:, 1], len(rows), int(np.sum(keep))


def cadence_of(time):
    steps = np.diff(time)
    steps = steps[np.isfinite(steps) & (steps > 0)]
    if not len(steps):
        raise ValueError("timestamps have no positive cadence")
    return float(np.median(steps))


def odd_window(days, cadence, size):
    """Make the specified duration an odd legal Savitzky--Golay width."""
    width = max(31, int(round(days / cadence)))
    width += (width + 1) % 2
    largest = size if size % 2 else size - 1
    return min(width, largest)


def global_residual(time, flux, cadence):
    """Full-series 0.8-day activity removal, with residual-only clipping."""
    from scipy.signal import savgol_filter
    window = odd_window(0.8, cadence, len(flux))
    if window < 7:
        raise ValueError("too few points for global activity detrending")
    residual = flux - savgol_filter(flux, window_length=window, polyorder=2,
                                    mode="interp")
    lo, hi = np.quantile(residual, [0.001, 0.999])
    return np.clip(residual, lo, hi), int(window)


def segmented_residual(time, flux, cadence):
    """Remove activity independently on either side of long observing gaps."""
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


def phase_box_score(time, residual, period, bins=180):
    """Depth of the deepest short folded phase box, normalized robustly."""
    phase = ((time - time[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins)
    counts = np.bincount(index, minlength=bins)
    best = np.inf
    for width in (2, 3, 4, 5):
        extended_sums = np.r_[sums, sums[:width]].cumsum()
        extended_counts = np.r_[counts, counts[:width]].cumsum()
        box_sum = extended_sums[width:] - extended_sums[:-width]
        box_count = extended_counts[width:] - extended_counts[:-width]
        mean = np.divide(box_sum, box_count, out=np.full(bins, np.nan),
                         where=box_count > 0)
        best = min(best, float(np.nanmin(mean)))
    scatter = 1.4826 * np.median(np.abs(residual - np.median(residual)))
    return float(-best / max(float(scatter), 1e-12))


def count_weighted_bls(time, residual, period, bins=240, return_location=False):
    """Return the best sampled circular box statistic and optionally its box."""
    phase = ((time - time[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins)
    counts = np.bincount(index, minlength=bins).astype(float)
    total_sum, total_n = float(sums.sum()), float(counts.sum())
    scatter = max(float(1.4826 * np.median(
        np.abs(residual - np.median(residual)))), 1e-12)
    best_score, best_start, best_width = -np.inf, 0, 0
    for width in range(1, 9):
        extended_sums = np.r_[sums, sums[:width]]
        extended_counts = np.r_[counts, counts[:width]]
        box_sums = (np.cumsum(extended_sums)[width:] -
                    np.cumsum(extended_sums)[:-width])
        box_ns = (np.cumsum(extended_counts)[width:] -
                  np.cumsum(extended_counts)[:-width])
        valid = (box_ns >= 8) & ((total_n - box_ns) >= 8)
        inside = np.divide(box_sums, box_ns, out=np.zeros(bins),
                           where=box_ns > 0)
        outside = np.divide(total_sum - box_sums, total_n - box_ns,
                            out=np.zeros(bins), where=(total_n - box_ns) > 0)
        score = ((outside - inside) *
                 np.sqrt(box_ns * (total_n - box_ns) / total_n) / scatter)
        score[~valid] = -np.inf
        location = int(np.argmax(score))
        if score[location] > best_score:
            best_score = float(score[location])
            best_start, best_width = location, width
    if return_location:
        return best_score, best_start, best_width
    return best_score


def supported_epochs(time, residual, period, start, width, bins=240):
    """Count observed transit epochs independently supporting the selected box."""
    phase = ((time - time[0]) % period) / period
    center = ((start + width / 2.0) % bins) / bins
    distance = np.abs(((phase - center + 0.5) % 1.0) - 0.5)
    in_box = distance <= (width / bins) / 2.0
    epoch = np.floor((time - time[0]) / period).astype(int)
    median = np.median(residual)
    return int(sum(
        len(values := residual[(epoch == event) & in_box]) >= 2 and
        np.median(values) < median
        for event in np.unique(epoch)
    ))


def leading_indices(scores, count=128):
    count = min(count, len(scores))
    if count <= 0:
        return np.array([], dtype=int)
    safe = np.nan_to_num(scores, nan=-np.inf, neginf=-np.inf)
    return np.argpartition(safe, -count)[-count:]


def display_candidates(values, low, high):
    """Return five-decimal values plus small representable local refinements."""
    candidates = set()
    for value in values:
        rounded = float(f"{float(value):.5f}")
        for offset in range(-5, 6):
            candidate = float(f"{rounded + offset * 1e-5:.5f}")
            if low <= candidate <= high:
                candidates.add(candidate)
    return sorted(candidates)


def choose_period(time, global_resid, segmented_resid, low, high,
                  global_trials, bls_trials):
    """Cross-check leading peaks and choose the strongest repeated consensus."""
    global_grid = np.linspace(low, high, global_trials)
    bls_low = max(low, 0.25)
    if not bls_low < high:
        raise ValueError("period range contains no count-weighted multi-event interval")
    bls_grid = np.linspace(bls_low, high, bls_trials)

    global_scores = np.asarray([
        phase_box_score(time, global_resid, float(period))
        for period in global_grid
    ])
    bls_scores = np.asarray([
        count_weighted_bls(time, segmented_resid, float(period))
        for period in bls_grid
    ])
    global_best = float(np.nanmax(global_scores))
    bls_best = float(np.nanmax(bls_scores))
    if not (np.isfinite(global_best) and np.isfinite(bls_best) and
            global_best > 0 and bls_best > 0):
        raise ValueError("no positive finite folded box score was found")

    seeds = np.r_[global_grid[leading_indices(global_scores)],
                  bls_grid[leading_indices(bls_scores)]]
    candidates = display_candidates(seeds, bls_low, high)
    checked = []
    for period in candidates:
        global_score = phase_box_score(time, global_resid, period)
        bls_score, start, width = count_weighted_bls(
            time, segmented_resid, period, return_location=True)
        if not (np.isfinite(global_score) and np.isfinite(bls_score)):
            continue
        support = supported_epochs(time, segmented_resid, period, start, width)
        checked.append({
            "period": period,
            "global_score": float(global_score),
            "bls_score": float(bls_score),
            "global_ratio": float(global_score / global_best),
            "bls_ratio": float(bls_score / bls_best),
            "supported_epochs": support,
            "box_start": int(start),
            "box_width": int(width),
        })
    viable = [item for item in checked if item["supported_epochs"] >= 3 and
              item["bls_score"] > 0]
    if not viable:
        raise ValueError("no positively scored box candidate has three supported epochs")

    strict = [item for item in viable if item["global_ratio"] >= 0.985 and
              item["bls_ratio"] >= 0.985]
    pool = strict if strict else viable
    # The limiting profile is primary: a candidate must not be selected merely
    # because one detrending/statistic produces a high alias peak.
    chosen = max(pool, key=lambda item: (
        min(item["global_ratio"], item["bls_ratio"]),
        item["global_ratio"] + item["bls_ratio"],
        item["supported_epochs"], item["bls_score"]
    ))
    return (chosen, bool(strict), len(checked), global_grid, global_scores,
            bls_grid, bls_scores, global_best, bls_best)


def main(config):
    try:
        from scipy.signal import savgol_filter  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("SciPy is required for activity detrending") from exc
    path, output = config.get("input_path"), config.get("output_path")
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
    low = float(config.get("min_period", 0.2))
    requested_high = config.get("max_period")
    high = min(15.0, baseline / 1.8) if requested_high is None else float(requested_high)
    global_trials = int(config.get("global_trials", 3500))
    bls_trials = int(config.get("bls_trials", 5000))
    if not (np.isfinite(low) and np.isfinite(high) and 0 < low < high):
        raise ValueError("requested period range is invalid")
    if global_trials < 500 or bls_trials < 500:
        raise ValueError("global_trials and bls_trials must each be at least 500")

    global_resid, global_window = global_residual(time, flux, cadence)
    segmented_resid, segments = segmented_residual(time, flux, cadence)
    (chosen, strict, checked_count, global_grid, global_scores, bls_grid,
     bls_scores, global_best, bls_best) = choose_period(
        time, global_resid, segmented_resid, low, high, global_trials, bls_trials)

    parent = os.path.dirname(os.path.abspath(output))
    os.makedirs(parent, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(f"{chosen['period']:.5f}\n")

    return {
        "ok": True,
        "output_path": output,
        "period_days": chosen["period"],
        "period_rounded": f"{chosen['period']:.5f}",
        "strict_cross_profile_match": strict,
        "global_box_score": chosen["global_score"],
        "count_weighted_bls_score": chosen["bls_score"],
        "global_score_ratio": chosen["global_ratio"],
        "bls_score_ratio": chosen["bls_ratio"],
        "supported_epochs": chosen["supported_epochs"],
        "box_start": chosen["box_start"],
        "box_width": chosen["box_width"],
        "global_grid_best_period": float(global_grid[int(np.nanargmax(global_scores))]),
        "global_grid_best_score": global_best,
        "bls_grid_best_period": float(bls_grid[int(np.nanargmax(bls_scores))]),
        "bls_grid_best_score": bls_best,
        "checked_display_candidates": checked_count,
        "input_numeric_rows": numeric_rows,
        "quality_trusted_rows": trusted_rows,
        "cadence_days": cadence,
        "global_trend_window_points": global_window,
        "activity_segments": segments,
        "search_range_days": [low, high],
        "global_trials": global_trials,
        "bls_trials": bls_trials,
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
