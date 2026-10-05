#!/usr/bin/env python3
"""Quality-filtered, gap-aware folded-box transit-period finder.

stdin: JSON object documented in SKILL.md
stdout: JSON diagnostics
side effect on success: atomic five-decimal period file
"""
import json
import os
import sys
import tempfile
import traceback

import numpy as np


def read_lightcurve(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.strip().replace(",", " ").split()
            if len(fields) < 4:
                continue
            try:
                rows.append([float(x) for x in fields[:4]])
            except ValueError:
                continue
    if not rows:
        raise ValueError("input has no numeric four-column records")
    data = np.asarray(rows, float)
    good = ((data[:, 2] == 0) & np.isfinite(data[:, 0]) &
            np.isfinite(data[:, 1]) & np.isfinite(data[:, 3]))
    data = data[good]
    if not len(data):
        raise ValueError("no finite quality-zero cadences remain")
    data = data[np.argsort(data[:, 0])]
    return data[:, 0], data[:, 1], len(rows), len(data)


def cadence_of(time):
    delta = np.diff(time)
    delta = delta[np.isfinite(delta) & (delta > 0)]
    if not len(delta):
        raise ValueError("timestamps have no positive cadence")
    return float(np.median(delta))


def odd_window(days, cadence, n):
    width = max(31, int(round(days / cadence)))
    if width % 2 == 0:
        width += 1
    maximum = n if n % 2 else n - 1
    return min(width, maximum)


def clip_residual(residual, limits):
    lo, hi = np.quantile(residual, limits)
    return np.clip(residual, lo, hi)


def segment_residual(time, flux, cadence):
    from scipy.signal import savgol_filter
    cuts = np.flatnonzero(np.diff(time) > max(8 * cadence, 0.08)) + 1
    residual = np.empty_like(flux)
    for first, last in zip(np.r_[0, cuts], np.r_[cuts, len(time)]):
        y = flux[first:last]
        window = odd_window(.7, cadence, len(y))
        residual[first:last] = (y - savgol_filter(y, window, 2, mode="interp")
                                if window >= 7 else y - np.median(y))
    return clip_residual(residual, (.002, .998)), int(len(cuts) + 1)


def global_residual(flux, cadence):
    from scipy.signal import savgol_filter
    window = odd_window(.8, cadence, len(flux))
    residual = (flux - savgol_filter(flux, window, 2, mode="interp")
                if window >= 7 else flux - np.median(flux))
    return clip_residual(residual, (.001, .999))


def robust_scatter(values):
    return max(float(1.4826 * np.median(np.abs(values - np.median(values)))), 1e-12)


def folded_sums(time, residual, period, bins):
    phase = ((time - time[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins).astype(float)
    counts = np.bincount(index, minlength=bins).astype(float)
    return sums, counts


def shifted_circle_sums(values, width):
    """Circular width sums indexed consistently with the folded box location."""
    extended = np.r_[values, values[:width]]
    cumulative = np.cumsum(extended)
    return cumulative[width:] - cumulative[:-width]


def weighted_score(time, residual, period, location=False):
    bins = 240
    sums, counts = folded_sums(time, residual, period, bins)
    total_sum, total_n = float(sums.sum()), float(counts.sum())
    sigma = robust_scatter(residual)
    best, best_start, best_width = -np.inf, 0, 0
    for width in range(1, 9):
        box_sum = shifted_circle_sums(sums, width)
        box_n = shifted_circle_sums(counts, width)
        inside = np.divide(box_sum, box_n, out=np.zeros(bins), where=box_n > 0)
        outside = np.divide(total_sum - box_sum, total_n - box_n,
                            out=np.zeros(bins), where=(total_n - box_n) > 0)
        score = ((outside - inside) * np.sqrt(box_n * (total_n - box_n) / total_n)
                 / sigma)
        score[(box_n < 8) | ((total_n - box_n) < 8)] = -np.inf
        j = int(np.argmax(score))
        if score[j] > best:
            best, best_start, best_width = float(score[j]), j, width
    return (best, best_start, best_width) if location else best


def global_score(time, residual, period):
    bins = 180
    sums, counts = folded_sums(time, residual, period, bins)
    best = np.inf
    for width in (2, 3, 4, 5):
        box_sum = shifted_circle_sums(sums, width)
        box_n = shifted_circle_sums(counts, width)
        means = np.divide(box_sum, box_n, out=np.full(bins, np.nan), where=box_n > 0)
        best = min(best, float(np.nanmin(means)))
    return float(-best / robust_scatter(residual))


def support_count(time, residual, period, start, width):
    phase = ((time - time[0]) % period) / period
    center = ((start + width / 2) % 240) / 240
    distance = np.abs(((phase - center + .5) % 1.0) - .5)
    inside = distance <= width / 480
    epoch = np.floor((time - time[0]) / period).astype(int)
    median = np.median(residual)
    return int(sum(len(v := residual[(epoch == e) & inside]) >= 2 and np.median(v) < median
                   for e in np.unique(epoch)))


def peak_indices(scores, limit=6, separation=10):
    safe = np.nan_to_num(scores, nan=-np.inf, posinf=-np.inf, neginf=-np.inf)
    answer = []
    for index in np.argsort(safe)[::-1]:
        if not np.isfinite(safe[index]):
            continue
        if all(abs(int(index) - old) > separation for old in answer):
            answer.append(int(index))
        if len(answer) == limit:
            break
    return answer


def refine_periods(seed, step, low, high):
    first = int(np.ceil((max(low, seed - 2 * step)) * 100000))
    last = int(np.floor((min(high, seed + 2 * step)) * 100000))
    return np.arange(first, last + 1, dtype=float) / 100000.0


def atomic_write(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".period-", dir=directory, text=True)
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
        raise RuntimeError("SciPy is required for detrending") from exc
    input_path = config.get("input_path")
    output_path = config.get("output_path")
    if not isinstance(input_path, str) or not input_path:
        raise ValueError("input_path must be a nonempty string")
    if not isinstance(output_path, str) or not output_path:
        raise ValueError("output_path must be a nonempty string")
    selection = config.get("selection", "gap_aware")
    if selection not in {"gap_aware", "global_box", "consensus"}:
        raise ValueError("selection must be gap_aware, global_box, or consensus")

    time, flux, numeric_rows, trusted_rows = read_lightcurve(input_path)
    if len(time) < 100:
        raise ValueError("fewer than 100 trusted cadences remain")
    cadence = cadence_of(time)
    low = float(config.get("min_period", .25))
    supplied_high = config.get("max_period")
    high = (min(15.0, float((time[-1] - time[0]) / 1.8)) if supplied_high is None
            else float(supplied_high))
    trials = int(config.get("trials", 5000))
    if not (np.isfinite(low) and np.isfinite(high) and 0 < low < high):
        raise ValueError("period bounds must be finite, positive, and ordered")
    if trials < 500:
        raise ValueError("trials must be at least 500")

    gap, segments = segment_residual(time, flux, cadence)
    global_r = global_residual(flux, cadence)
    grid = np.linspace(low, high, trials)
    scores = np.asarray([weighted_score(time, gap, p) for p in grid])
    if not np.isfinite(scores).any():
        raise ValueError("no finite gap-aware box scores")
    step = float(grid[1] - grid[0])
    refined = np.unique(np.concatenate([refine_periods(float(grid[i]), step, low, high)
                                        for i in peak_indices(scores)]))
    records = []
    for period in refined:
        score, start, width = weighted_score(time, gap, period, location=True)
        records.append({"period": float(period), "gap_score": float(score),
                        "start": int(start), "width": int(width),
                        "support": support_count(time, gap, period, start, width),
                        "global_score": global_score(time, global_r, period)})
    repeated = [r for r in records if np.isfinite(r["gap_score"]) and r["gap_score"] > 0
                and r["support"] >= 3]
    if not repeated:
        raise ValueError("no refined box candidate has support in three observed epochs")
    gap_choice = max(repeated, key=lambda r: (r["gap_score"], r["support"], -r["period"]))
    global_choice = max(records, key=lambda r: (r["global_score"], r["gap_score"]))
    if selection == "global_box":
        chosen = global_choice
    elif selection == "consensus":
        if abs(gap_choice["period"] - global_choice["period"]) > 2 * step:
            raise ValueError("gap-aware and global box candidates disagree; no consensus artifact written")
        chosen = gap_choice
    else:
        chosen = gap_choice
    if selection != "global_box" and chosen["support"] < 3:
        raise ValueError("selected candidate lacks repeated observed epochs")

    rendered = f"{chosen['period']:.5f}"
    atomic_write(output_path, rendered + "\n")
    return {"ok": True, "output_path": output_path, "period_days": chosen["period"],
            "period_rounded": rendered, "selection": selection,
            "gap_weighted_score": chosen["gap_score"], "global_box_score": chosen["global_score"],
            "box_start_bin": chosen["start"], "box_width_bins": chosen["width"],
            "supported_epochs": chosen["support"], "gap_peak_period": float(grid[int(np.nanargmax(scores))]),
            "gap_peak_score": float(np.nanmax(scores)), "global_candidate_period": global_choice["period"],
            "global_candidate_score": global_choice["global_score"], "numeric_rows": numeric_rows,
            "trusted_rows": trusted_rows, "gap_segments": segments, "cadence_days": cadence,
            "search_range_days": [low, high], "trials": trials}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}, sort_keys=True))
        sys.exit(1)
