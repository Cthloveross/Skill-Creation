#!/usr/bin/env python3
"""Find a repeated, box-shaped transit period in an activity-dominated light curve."""
import json
import os
import sys
import tempfile
import traceback

import numpy as np


def read_lightcurve(path):
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
    data = raw[keep]
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


def odd_window(days, cadence, size):
    width = max(31, int(round(days / cadence)))
    if width % 2 == 0:
        width += 1
    largest = size if size % 2 else size - 1
    return min(width, largest)


def detrend_gaps(time, flux, cadence):
    """Detrend each contiguous observing segment without bridging gaps."""
    from scipy.signal import savgol_filter
    steps = np.diff(time)
    breaks = np.flatnonzero(steps > max(8.0 * cadence, 0.08)) + 1
    residual = np.empty_like(flux)
    for first, last in zip(np.r_[0, breaks], np.r_[breaks, len(time)]):
        values = flux[first:last]
        window = odd_window(0.7, cadence, len(values))
        if window >= 7:
            trend = savgol_filter(values, window_length=window, polyorder=2,
                                  mode="interp")
            residual[first:last] = values - trend
        else:
            residual[first:last] = values - np.median(values)
    lo, hi = np.quantile(residual, [0.002, 0.998])
    return np.clip(residual, lo, hi), int(len(breaks) + 1)


def detrend_full_diagnostic(flux, cadence):
    """A separate continuous-trend diagnostic, not the selection statistic."""
    from scipy.signal import savgol_filter
    window = odd_window(0.8, cadence, len(flux))
    if window < 7:
        return flux - np.median(flux)
    residual = flux - savgol_filter(flux, window, 2, mode="interp")
    lo, hi = np.quantile(residual, [0.001, 0.999])
    return np.clip(residual, lo, hi)


def robust_scatter(values):
    return max(float(1.4826 * np.median(np.abs(values - np.median(values)))),
               1e-12)


def bls_score(time, residual, period, bins=240, return_location=False):
    """Count-weighted depth significance of the best circular folded box."""
    phase = ((time - time[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins)
    counts = np.bincount(index, minlength=bins).astype(float)
    total_sum = float(sums.sum())
    total_count = float(counts.sum())
    sigma = robust_scatter(residual)
    best_score, best_start, best_width = -np.inf, 0, 0
    for width in range(1, 9):
        extended_sums = np.r_[sums, sums[:width]]
        extended_counts = np.r_[counts, counts[:width]]
        box_sums = np.cumsum(extended_sums)[width:] - np.cumsum(extended_sums)[:-width]
        box_counts = (np.cumsum(extended_counts)[width:] -
                      np.cumsum(extended_counts)[:-width])
        valid = (box_counts >= 8) & ((total_count - box_counts) >= 8)
        inside = np.divide(box_sums, box_counts, out=np.zeros(bins),
                           where=box_counts > 0)
        outside = np.divide(total_sum - box_sums, total_count - box_counts,
                            out=np.zeros(bins), where=(total_count - box_counts) > 0)
        score = ((outside - inside) *
                 np.sqrt(box_counts * (total_count - box_counts) / total_count) /
                 sigma)
        score[~valid] = -np.inf
        at = int(np.argmax(score))
        if score[at] > best_score:
            best_score, best_start, best_width = float(score[at]), at, width
    if return_location:
        return best_score, best_start, best_width
    return best_score


def epoch_support(time, residual, period, start, width, bins=240):
    phase = ((time - time[0]) % period) / period
    center = ((start + width / 2.0) % bins) / bins
    distance = np.abs(((phase - center + 0.5) % 1.0) - 0.5)
    in_box = distance <= width / (2.0 * bins)
    epochs = np.floor((time - time[0]) / period).astype(int)
    baseline = np.median(residual)
    supported = 0
    for epoch in np.unique(epochs):
        values = residual[(epochs == epoch) & in_box]
        if len(values) >= 2 and np.median(values) < baseline:
            supported += 1
    return int(supported)


def full_box_score(time, residual, period, bins=180):
    """Simple unweighted folded-box depth retained as a diagnostic."""
    phase = ((time - time[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins)
    counts = np.bincount(index, minlength=bins)
    best = np.inf
    for width in (2, 3, 4, 5):
        ss = np.r_[sums, sums[:width]].cumsum()
        cc = np.r_[counts, counts[:width]].cumsum()
        means = np.divide(ss[width:] - ss[:-width], cc[width:] - cc[:-width],
                          out=np.full(bins, np.nan),
                          where=(cc[width:] - cc[:-width]) > 0)
        best = min(best, float(np.nanmin(means)))
    return float(-best / robust_scatter(residual))


def separated_peak_indices(scores, limit=8):
    safe = np.nan_to_num(scores, nan=-np.inf, neginf=-np.inf)
    ranked = np.argsort(safe)[::-1]
    chosen = []
    for index in ranked:
        if not np.isfinite(safe[index]):
            continue
        if all(abs(int(index) - old) > 4 for old in chosen):
            chosen.append(int(index))
        if len(chosen) >= limit:
            break
    return chosen


def score_with_support(time, residual, period):
    score, start, width = bls_score(time, residual, period, return_location=True)
    support = epoch_support(time, residual, period, start, width)
    return {"period": float(period), "score": float(score), "start": int(start),
            "width": int(width), "support": int(support)}


def refine_displayed_period(time, residual, center, coarse_step, low, high):
    """Refine a peak and select according to the value actually written to disk."""
    fine = np.linspace(max(low, center - 2.0 * coarse_step),
                       min(high, center + 2.0 * coarse_step), 1201)
    fine_scores = np.asarray([bls_score(time, residual, float(p)) for p in fine])
    best_raw = float(fine[int(np.nanargmax(fine_scores))])

    # Search rounded values explicitly; phase bins make the optimum discontinuous.
    displayed = set()
    for value in np.linspace(best_raw - 0.002, best_raw + 0.002, 401):
        rounded = float(f"{value:.5f}")
        if low <= rounded <= high:
            displayed.add(rounded)
    candidates = [score_with_support(time, residual, value)
                  for value in sorted(displayed)]
    repeated = [item for item in candidates if item["support"] >= 3]
    pool = repeated if repeated else candidates
    if not pool:
        raise ValueError("no displayed refinement candidate is in the search range")
    return max(pool, key=lambda item: (item["score"], item["support"], -item["period"]))


def atomic_write(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".period-", dir=directory, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
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

    low = float(config.get("min_period", 0.25))
    maximum = config.get("max_period")
    high = min(15.0, baseline / 1.8) if maximum is None else float(maximum)
    trials = int(config.get("trials", 3500))
    if not (np.isfinite(low) and np.isfinite(high) and 0 < low < high):
        raise ValueError("requested period range is invalid")
    if trials < 500:
        raise ValueError("trials must be at least 500")

    residual, segments = detrend_gaps(time, flux, cadence)
    grid = np.linspace(low, high, trials)
    scores = np.asarray([bls_score(time, residual, float(period)) for period in grid])
    if not np.isfinite(scores).any() or float(np.nanmax(scores)) <= 0:
        raise ValueError("no positive finite folded-box candidate was found")

    # Evaluate separated high peaks first. Repeated epoch support resolves aliases.
    broad_candidates = [score_with_support(time, residual, grid[index])
                        for index in separated_peak_indices(scores)]
    repeated = [item for item in broad_candidates if item["support"] >= 3]
    initial = max(repeated if repeated else broad_candidates,
                  key=lambda item: (item["score"], item["support"], -item["period"]))
    refined = refine_displayed_period(time, residual, initial["period"],
                                      float(grid[1] - grid[0]), low, high)
    if not np.isfinite(refined["score"]) or refined["score"] <= 0:
        raise ValueError("refined period does not have a positive box score")
    if refined["support"] < 3:
        raise ValueError("no candidate has a folded dip supported in three epochs")

    diagnostic_residual = detrend_full_diagnostic(flux, cadence)
    diagnostic_score = full_box_score(time, diagnostic_residual, refined["period"])
    rendered = f"{refined['period']:.5f}"
    atomic_write(output_path, rendered + "\n")
    return {
        "ok": True,
        "output_path": output_path,
        "period_days": refined["period"],
        "period_rounded": rendered,
        "bls_score": refined["score"],
        "box_start": refined["start"],
        "box_width": refined["width"],
        "supported_epochs": refined["support"],
        "broad_peak_period": float(grid[int(np.nanargmax(scores))]),
        "broad_peak_score": float(np.nanmax(scores)),
        "full_series_box_score_diagnostic": diagnostic_score,
        "input_numeric_rows": numeric_rows,
        "quality_trusted_rows": trusted_rows,
        "cadence_days": cadence,
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
