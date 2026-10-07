#!/usr/bin/env python3
"""Find a refined box-transit period from a quality-flagged light curve.

Input: JSON object on stdin described in SKILL.md.
Output: JSON diagnostics on stdout.  On success only, output_path is atomically
replaced with one five-decimal period followed by a newline.
"""
import json
import os
import sys
import tempfile
import traceback

import numpy as np


def read_table(path):
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as source:
        for line in source:
            words = line.strip().replace(",", " ").split()
            if len(words) < 4:
                continue
            try:
                rows.append([float(words[k]) for k in range(4)])
            except ValueError:
                # Allows comments, headers, and other non-numeric metadata.
                continue
    if not rows:
        raise ValueError("input contains no numeric four-column rows")
    raw = np.asarray(rows, dtype=float)
    good = ((raw[:, 2] == 0) & np.isfinite(raw[:, 0]) &
            np.isfinite(raw[:, 1]) & np.isfinite(raw[:, 3]))
    data = raw[good]
    if len(data) == 0:
        raise ValueError("no finite quality-zero rows remain")
    data = data[np.argsort(data[:, 0])]
    return data[:, 0], data[:, 1], int(len(raw)), int(len(data))


def cadence_days(time):
    steps = np.diff(time)
    steps = steps[np.isfinite(steps) & (steps > 0)]
    if len(steps) == 0:
        raise ValueError("timestamps have no positive spacing")
    return float(np.median(steps))


def odd_window(days, cadence, length):
    width = max(31, int(round(days / cadence)))
    if width % 2 == 0:
        width += 1
    largest_odd = length if length % 2 else length - 1
    return min(width, largest_odd)


def clipped(values, quantiles):
    lo, hi = np.quantile(values, quantiles)
    return np.clip(values, lo, hi)


def global_residual(flux, cadence):
    """Continuous 0.8-day detrending used by the global box-search track."""
    from scipy.signal import savgol_filter
    window = odd_window(0.8, cadence, len(flux))
    if window < 7:
        result = flux - np.median(flux)
    else:
        result = flux - savgol_filter(flux, window_length=window,
                                      polyorder=2, mode="interp")
    return clipped(result, (0.001, 0.999))


def gap_residual(time, flux, cadence):
    """Detrend each observing segment separately; never bridge large gaps."""
    from scipy.signal import savgol_filter
    cuts = np.flatnonzero(np.diff(time) > max(8.0 * cadence, 0.08)) + 1
    result = np.empty_like(flux)
    for first, last in zip(np.r_[0, cuts], np.r_[cuts, len(time)]):
        part = flux[first:last]
        window = odd_window(0.7, cadence, len(part))
        if window < 7:
            result[first:last] = part - np.median(part)
        else:
            result[first:last] = part - savgol_filter(part, window_length=window,
                                                       polyorder=2, mode="interp")
    return clipped(result, (0.002, 0.998)), int(len(cuts) + 1)


def scatter(values):
    mad = 1.4826 * np.median(np.abs(values - np.median(values)))
    return max(float(mad), 1e-12)


def binned(time, residual, period, bins):
    phase = ((time - time[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins).astype(float)
    counts = np.bincount(index, minlength=bins).astype(float)
    return sums, counts


def circle_sums(values, width):
    extended = np.r_[values, values[:width]]
    cumulative = np.r_[0.0, np.cumsum(extended)]
    return cumulative[width:width + len(values)] - cumulative[:len(values)]


def global_box_score(time, residual, period, return_location=False):
    """Unweighted 180-bin folded-box depth statistic for global detrending."""
    bins = 180
    sums, counts = binned(time, residual, period, bins)
    best, start, width_out = np.inf, 0, 0
    for width in (2, 3, 4, 5):
        box_sum = circle_sums(sums, width)
        box_count = circle_sums(counts, width)
        means = np.divide(box_sum, box_count, out=np.full(bins, np.nan),
                          where=box_count > 0)
        here = int(np.nanargmin(means))
        if means[here] < best:
            best, start, width_out = float(means[here]), here, width
    value = float(-best / scatter(residual))
    return (value, start, width_out) if return_location else value


def weighted_box_score(time, residual, period, return_location=False):
    """Gap-aware count-weighted in-box/out-of-box depth significance."""
    bins = 240
    sums, counts = binned(time, residual, period, bins)
    total_sum, total_count = float(sums.sum()), float(counts.sum())
    scale = scatter(residual)
    best, start_out, width_out = -np.inf, 0, 0
    for width in range(1, 9):
        box_sum = circle_sums(sums, width)
        box_count = circle_sums(counts, width)
        inside = np.divide(box_sum, box_count, out=np.zeros(bins),
                           where=box_count > 0)
        outside = np.divide(total_sum - box_sum, total_count - box_count,
                            out=np.zeros(bins), where=(total_count - box_count) > 0)
        score = ((outside - inside) *
                 np.sqrt(box_count * (total_count - box_count) / total_count) /
                 scale)
        score[(box_count < 8) | ((total_count - box_count) < 8)] = -np.inf
        at = int(np.argmax(score))
        if score[at] > best:
            best, start_out, width_out = float(score[at]), at, width
    return (best, start_out, width_out) if return_location else best


def support_count(time, residual, period, start, width, bins=240):
    phase = ((time - time[0]) % period) / period
    center = ((start + width / 2.0) % bins) / bins
    distance = np.abs(((phase - center + 0.5) % 1.0) - 0.5)
    in_box = distance <= width / (2.0 * bins)
    orbit = np.floor((time - time[0]) / period).astype(int)
    median = float(np.median(residual))
    return int(sum(len(values := residual[(orbit == epoch) & in_box]) >= 2 and
                   float(np.median(values)) < median
                   for epoch in np.unique(orbit)))


def separated_peak_indices(scores, maximum=6, separation=4):
    safe = np.nan_to_num(scores, nan=-np.inf, posinf=-np.inf, neginf=-np.inf)
    answer = []
    for index in np.argsort(safe)[::-1]:
        if not np.isfinite(safe[index]):
            continue
        if all(abs(int(index) - old) > separation for old in answer):
            answer.append(int(index))
        if len(answer) >= maximum:
            break
    return answer


def displayed_values(center, half_width, low, high):
    # Search at output precision so final formatting never changes the winner.
    values = set()
    for value in np.linspace(center - half_width, center + half_width, 1201):
        rounded = float(f"{value:.5f}")
        if low <= rounded <= high:
            values.add(rounded)
    return sorted(values)


def evaluate(time, global_r, gap_r, period):
    global_score, global_start, global_width = global_box_score(
        time, global_r, period, return_location=True)
    weighted, gap_start, gap_width = weighted_box_score(
        time, gap_r, period, return_location=True)
    return {
        "period": float(period),
        "global_score": float(global_score),
        "global_start": int(global_start),
        "global_width": int(global_width),
        "weighted_score": float(weighted),
        "gap_start": int(gap_start),
        "gap_width": int(gap_width),
        "supported_epochs": support_count(time, gap_r, period, gap_start, gap_width),
    }


def refine_seed(time, global_r, gap_r, seed, broad_step, low, high):
    fine = np.linspace(max(low, seed - 2.0 * broad_step),
                       min(high, seed + 2.0 * broad_step), 1201)
    # Refine with both objectives so neither candidate family is lost.
    gs = np.asarray([global_box_score(time, global_r, p) for p in fine])
    ws = np.asarray([weighted_box_score(time, gap_r, p) for p in fine])
    centers = []
    if np.isfinite(gs).any():
        centers.append(float(fine[int(np.nanargmax(gs))]))
    if np.isfinite(ws).any():
        centers.append(float(fine[int(np.nanargmax(ws))]))
    records = []
    for center in centers:
        for period in displayed_values(center, broad_step, low, high):
            records.append(evaluate(time, global_r, gap_r, period))
    return records


def atomic_write(path, contents):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".period-", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(contents)
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
        raise RuntimeError("SciPy is required for Savitzky-Golay detrending") from exc
    if not isinstance(config.get("input_path"), str) or not config["input_path"]:
        raise ValueError("input_path must be a nonempty string")
    if not isinstance(config.get("output_path"), str) or not config["output_path"]:
        raise ValueError("output_path must be a nonempty string")

    time, flux, numeric_rows, trusted_rows = read_table(config["input_path"])
    if len(time) < 100:
        raise ValueError("fewer than 100 finite quality-zero cadences remain")
    cadence = cadence_days(time)
    baseline = float(time[-1] - time[0])
    low = float(config.get("min_period", 0.2))
    supplied_high = config.get("max_period")
    high = min(15.0, baseline / 1.8) if supplied_high is None else float(supplied_high)
    trials = int(config.get("trials", 3500))
    selection = config.get("selection", "global_box")
    if not (np.isfinite(low) and np.isfinite(high) and 0 < low < high):
        raise ValueError("period bounds must be finite positive values with min < max")
    if trials < 500:
        raise ValueError("trials must be at least 500")
    if selection not in {"global_box", "gap_aware", "consensus"}:
        raise ValueError("selection must be global_box, gap_aware, or consensus")

    global_r = global_residual(flux, cadence)
    gap_r, segments = gap_residual(time, flux, cadence)
    grid = np.linspace(low, high, trials)
    global_grid = np.asarray([global_box_score(time, global_r, p) for p in grid])
    weighted_grid = np.asarray([weighted_box_score(time, gap_r, p) for p in grid])
    if not np.isfinite(global_grid).any() or not np.isfinite(weighted_grid).any():
        raise ValueError("no finite folded-box scores were produced")

    seed_indices = set(separated_peak_indices(global_grid))
    seed_indices.update(separated_peak_indices(weighted_grid))
    step = float(grid[1] - grid[0])
    records = []
    for index in sorted(seed_indices):
        records.extend(refine_seed(time, global_r, gap_r, float(grid[index]),
                                   step, low, high))
    unique = {}
    for record in records:
        old = unique.get(record["period"])
        if old is None or (record["global_score"], record["weighted_score"]) > (old["global_score"], old["weighted_score"]):
            unique[record["period"]] = record
    candidates = list(unique.values())
    if not candidates:
        raise ValueError("period refinement produced no displayable candidates")

    if selection == "global_box":
        valid = [x for x in candidates if np.isfinite(x["global_score"]) and x["global_score"] > 0]
        key = lambda x: (x["global_score"], x["weighted_score"], x["supported_epochs"], -x["period"])
    elif selection == "gap_aware":
        valid = [x for x in candidates if np.isfinite(x["weighted_score"]) and x["weighted_score"] > 0 and x["supported_epochs"] >= 3]
        key = lambda x: (x["weighted_score"], x["global_score"], x["supported_epochs"], -x["period"])
    else:
        best_global = max(x["global_score"] for x in candidates)
        best_weighted = max(x["weighted_score"] for x in candidates)
        valid = [x for x in candidates if x["supported_epochs"] >= 3 and x["global_score"] >= 0.90 * best_global and x["weighted_score"] >= 0.90 * best_weighted]
        key = lambda x: (min(x["global_score"] / best_global, x["weighted_score"] / best_weighted), x["supported_epochs"], -x["period"])
    if not valid:
        raise ValueError("no candidate satisfies the requested selection criteria")
    chosen = max(valid, key=key)
    rendered = f"{chosen['period']:.5f}"
    atomic_write(config["output_path"], rendered + "\n")
    return {
        "ok": True,
        "output_path": config["output_path"],
        "period_days": chosen["period"],
        "period_rounded": rendered,
        "selection": selection,
        "global_box_score": chosen["global_score"],
        "gap_weighted_score": chosen["weighted_score"],
        "supported_epochs": chosen["supported_epochs"],
        "global_peak_period": float(grid[int(np.nanargmax(global_grid))]),
        "global_peak_score": float(np.nanmax(global_grid)),
        "gap_peak_period": float(grid[int(np.nanargmax(weighted_grid))]),
        "gap_peak_score": float(np.nanmax(weighted_grid)),
        "numeric_rows": numeric_rows,
        "trusted_rows": trusted_rows,
        "cadence_days": cadence,
        "gap_segments": segments,
        "search_range_days": [low, high],
        "trials": trials,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc),
                          "traceback": traceback.format_exc()}, sort_keys=True))
        sys.exit(1)
