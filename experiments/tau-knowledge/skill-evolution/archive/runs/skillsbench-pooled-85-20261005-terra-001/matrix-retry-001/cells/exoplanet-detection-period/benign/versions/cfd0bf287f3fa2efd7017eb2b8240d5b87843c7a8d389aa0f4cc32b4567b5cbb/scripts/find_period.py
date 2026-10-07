#!/usr/bin/env python3
"""Activity-detrend a TESS light curve and refine its strongest folded box dip."""
import json
import math
import os
import sys
import tempfile
import traceback

import numpy as np


def read_lightcurve(path):
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            words = line.strip().replace(",", " ").split()
            if len(words) < 4:
                continue
            try:
                rows.append(tuple(float(words[k]) for k in range(4)))
            except ValueError:
                continue
    if not rows:
        raise ValueError("no numeric four-column rows were found")
    raw = np.asarray(rows, dtype=float)
    good = ((raw[:, 2] == 0) & np.isfinite(raw[:, 0]) &
            np.isfinite(raw[:, 1]) & np.isfinite(raw[:, 3]))
    data = raw[good]
    if not len(data):
        raise ValueError("no finite quality-zero cadences remain")
    data = data[np.argsort(data[:, 0])]
    return data[:, 0], data[:, 1], len(rows), len(data)


def cadence_of(time):
    steps = np.diff(time)
    steps = steps[np.isfinite(steps) & (steps > 0)]
    if not len(steps):
        raise ValueError("timestamps have no positive cadence")
    return float(np.median(steps))


def odd_window(days, cadence, n):
    window = max(31, int(round(days / cadence)))
    window += (window + 1) % 2
    largest = n if n % 2 else n - 1
    return min(window, largest)


def detrend_full(flux, cadence):
    from scipy.signal import savgol_filter
    window = odd_window(0.8, cadence, len(flux))
    if window < 7:
        raise ValueError("too few samples for detrending")
    residual = flux - savgol_filter(flux, window_length=window,
                                    polyorder=2, mode="interp")
    lo, hi = np.quantile(residual, [0.001, 0.999])
    return np.clip(residual, lo, hi), window


def detrend_segments(time, flux, cadence):
    """Gap-aware diagnostic detrending; it is not used to alter primary selection."""
    from scipy.signal import savgol_filter
    breaks = np.flatnonzero(np.diff(time) > max(8.0 * cadence, 0.08)) + 1
    residual = np.empty_like(flux)
    for start, stop in zip(np.r_[0, breaks], np.r_[breaks, len(time)]):
        part = flux[start:stop]
        window = odd_window(0.7, cadence, len(part))
        if window >= 7:
            residual[start:stop] = part - savgol_filter(
                part, window_length=window, polyorder=2, mode="interp")
        else:
            residual[start:stop] = part - np.median(part)
    lo, hi = np.quantile(residual, [0.002, 0.998])
    return np.clip(residual, lo, hi), int(len(breaks) + 1)


def robust_scatter(values):
    return max(float(1.4826 * np.median(
        np.abs(values - np.median(values)))), 1e-12)


def box_score(time, residual, period, bins=180, return_location=False):
    """Robust-scatter normalized depth of the deepest circular folded box."""
    phase = ((time - time[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins)
    counts = np.bincount(index, minlength=bins)
    best, best_start, best_width = np.inf, 0, 0
    for width in (2, 3, 4, 5):
        extended_sums = np.r_[sums, sums[:width]].cumsum()
        extended_counts = np.r_[counts, counts[:width]].cumsum()
        box_sums = extended_sums[width:] - extended_sums[:-width]
        box_counts = extended_counts[width:] - extended_counts[:-width]
        means = np.divide(box_sums, box_counts,
                          out=np.full(bins, np.nan), where=box_counts > 0)
        at = int(np.nanargmin(means))
        if means[at] < best:
            best, best_start, best_width = float(means[at]), at, width
    score = -best / robust_scatter(residual)
    if return_location:
        return float(score), best_start, best_width
    return float(score)


def weighted_bls(time, residual, period, bins=240):
    """Gap-aware count-weighted folded-box diagnostic."""
    phase = ((time - time[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins)
    counts = np.bincount(index, minlength=bins).astype(float)
    total_sum, total_n = float(sums.sum()), float(counts.sum())
    sigma = robust_scatter(residual)
    best, location = -np.inf, (0, 0)
    for width in range(1, 9):
        es = np.r_[sums, sums[:width]].cumsum()
        ec = np.r_[counts, counts[:width]].cumsum()
        box_sums = es[width:] - es[:-width]
        box_n = ec[width:] - ec[:-width]
        valid = (box_n >= 8) & ((total_n - box_n) >= 8)
        inside = np.divide(box_sums, box_n, out=np.zeros(bins), where=box_n > 0)
        outside = np.divide(total_sum - box_sums, total_n - box_n,
                            out=np.zeros(bins), where=(total_n - box_n) > 0)
        scores = ((outside - inside) *
                  np.sqrt(box_n * (total_n - box_n) / total_n) / sigma)
        scores[~valid] = -np.inf
        at = int(np.argmax(scores))
        if scores[at] > best:
            best, location = float(scores[at]), (at, width)
    return best, location[0], location[1]


def epoch_support(time, residual, period, start, width, bins=240):
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
    return int(count)


def peak_indices(scores, limit=8):
    safe = np.nan_to_num(scores, nan=-np.inf, neginf=-np.inf)
    local = np.flatnonzero((safe[1:-1] >= safe[:-2]) &
                           (safe[1:-1] >= safe[2:])) + 1
    local = np.r_[0, local, len(safe) - 1]
    ranked = local[np.argsort(safe[local])[::-1]]
    selected = []
    # Do not refine many adjacent samples belonging to the same broad peak.
    for index in ranked:
        if all(abs(int(index) - prior) > 4 for prior in selected):
            selected.append(int(index))
        if len(selected) == limit:
            break
    return selected


def refine_candidates(time, residual, grid, scores, low, high):
    step = float(grid[1] - grid[0])
    candidates = set()
    for index in peak_indices(scores):
        center = float(grid[index])
        # Fine samples are denser than output precision, avoiding grid rounding.
        fine = np.linspace(max(low, center - 1.5 * step),
                           min(high, center + 1.5 * step), 801)
        fine_scores = np.asarray([box_score(time, residual, float(p)) for p in fine])
        best = float(fine[int(np.nanargmax(fine_scores))])
        candidates.add(best)
        candidates.add(float(fine[0]))
        candidates.add(float(fine[-1]))
    evaluated = []
    for period in sorted(candidates):
        score, start, width = box_score(time, residual, period,
                                        return_location=True)
        if np.isfinite(score):
            evaluated.append({"period": period, "score": score,
                              "start": int(start), "width": int(width)})
    if not evaluated:
        raise ValueError("no finite folded-box candidate was found")
    return max(evaluated, key=lambda item: (item["score"], -item["period"])), evaluated


def atomic_write(path, text):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".period-", dir=parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


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

    low = float(config.get("min_period", 0.2))
    requested_high = config.get("max_period")
    high = (min(15.0, baseline / 1.8) if requested_high is None
            else float(requested_high))
    trials = int(config.get("trials", 3500))
    if not (np.isfinite(low) and np.isfinite(high) and 0 < low < high):
        raise ValueError("requested period range is invalid")
    if trials < 500:
        raise ValueError("trials must be at least 500")

    residual, trend_window = detrend_full(flux, cadence)
    grid = np.linspace(low, high, trials)
    scores = np.asarray([box_score(time, residual, float(period)) for period in grid])
    if not np.isfinite(scores).any() or float(np.nanmax(scores)) <= 0:
        raise ValueError("no positive finite folded-box candidate was found")
    selected, refined = refine_candidates(time, residual, grid, scores, low, high)

    segmented, segments = detrend_segments(time, flux, cadence)
    weighted_score, weighted_start, weighted_width = weighted_bls(
        time, segmented, selected["period"])
    support = epoch_support(time, segmented, selected["period"], weighted_start,
                            weighted_width)
    broad = int(np.nanargmax(scores))

    atomic_write(output_path, f"{selected['period']:.5f}\n")
    return {
        "ok": True,
        "output_path": output_path,
        "period_days": selected["period"],
        "period_rounded": f"{selected['period']:.5f}",
        "box_score": selected["score"],
        "box_start": selected["start"],
        "box_width": selected["width"],
        "broad_peak_period": float(grid[broad]),
        "broad_peak_score": float(scores[broad]),
        "refined_candidates": len(refined),
        "gap_aware_weighted_bls_score": weighted_score,
        "gap_aware_box_start": weighted_start,
        "gap_aware_box_width": weighted_width,
        "gap_aware_supported_epochs": support,
        "input_numeric_rows": numeric_rows,
        "quality_trusted_rows": trusted_rows,
        "cadence_days": cadence,
        "activity_trend_window_points": trend_window,
        "gap_aware_segments": segments,
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
