#!/usr/bin/env python3
"""Recover a repeated transit period from an activity-dominated light curve.

JSON is read from stdin and a JSON diagnostic is emitted on stdout.  The only
side effect on success is an atomically written one-number period artifact.
"""
import json
import os
import sys
import tempfile
import traceback

import numpy as np


def read_lightcurve(path):
    """Read a permissive whitespace/comma four-column numeric table."""
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.strip().replace(",", " ").split()
            if len(fields) < 4:
                continue
            try:
                rows.append(tuple(float(fields[i]) for i in range(4)))
            except ValueError:
                # This permits a header and other nonnumeric metadata lines.
                continue
    if not rows:
        raise ValueError("no numeric four-column rows were found")
    raw = np.asarray(rows, dtype=float)
    keep = ((raw[:, 2] == 0) & np.isfinite(raw[:, 0]) &
            np.isfinite(raw[:, 1]) & np.isfinite(raw[:, 3]))
    trusted = raw[keep]
    if not len(trusted):
        raise ValueError("no finite quality-zero cadences remain")
    trusted = trusted[np.argsort(trusted[:, 0])]
    return trusted[:, 0], trusted[:, 1], int(len(raw)), int(len(trusted))


def cadence_of(time):
    steps = np.diff(time)
    steps = steps[np.isfinite(steps) & (steps > 0)]
    if not len(steps):
        raise ValueError("timestamps have no positive cadence")
    return float(np.median(steps))


def odd_window(days, cadence, count):
    window = max(31, int(round(days / cadence)))
    if window % 2 == 0:
        window += 1
    largest = count if count % 2 else count - 1
    return min(window, largest)


def clip_residual(residual, low, high):
    lo, hi = np.quantile(residual, [low, high])
    return np.clip(residual, lo, hi)


def detrend_gap_aware(time, flux, cadence):
    """Detrend contiguous segments independently, never smoothing across gaps."""
    from scipy.signal import savgol_filter

    steps = np.diff(time)
    cuts = np.flatnonzero(steps > max(8.0 * cadence, 0.08)) + 1
    residual = np.empty_like(flux)
    starts = np.r_[0, cuts]
    stops = np.r_[cuts, len(time)]
    for start, stop in zip(starts, stops):
        values = flux[start:stop]
        window = odd_window(0.7, cadence, len(values))
        if window >= 7:
            trend = savgol_filter(values, window_length=window, polyorder=2,
                                  mode="interp")
            residual[start:stop] = values - trend
        else:
            residual[start:stop] = values - np.median(values)
    return clip_residual(residual, 0.002, 0.998), int(len(starts))


def detrend_continuous(flux, cadence):
    """Independent continuous trend diagnostic, retained separately from selection."""
    from scipy.signal import savgol_filter

    window = odd_window(0.8, cadence, len(flux))
    if window < 7:
        residual = flux - np.median(flux)
    else:
        residual = flux - savgol_filter(flux, window_length=window,
                                        polyorder=2, mode="interp")
    return clip_residual(residual, 0.001, 0.999)


def robust_scatter(values):
    return max(float(1.4826 * np.median(np.abs(values - np.median(values)))),
               1e-12)


def folded_bins(time, residual, period, bins):
    phase = ((time - time[0]) % period) / period
    index = np.minimum((phase * bins).astype(int), bins - 1)
    sums = np.bincount(index, weights=residual, minlength=bins).astype(float)
    counts = np.bincount(index, minlength=bins).astype(float)
    return sums, counts


def circular_box_sums(values, width):
    extended = np.r_[values, values[:width]]
    cumulative = np.r_[0.0, np.cumsum(extended)]
    return cumulative[width:width + len(values)] - cumulative[:len(values)]


def weighted_bls(time, residual, period, bins=240, return_location=False):
    """Count-weighted in-box versus out-of-box depth significance."""
    sums, counts = folded_bins(time, residual, period, bins)
    total_sum = float(sums.sum())
    total_count = float(counts.sum())
    sigma = robust_scatter(residual)
    best_score, best_start, best_width = -np.inf, 0, 0
    for width in range(1, 9):
        box_sums = circular_box_sums(sums, width)
        box_counts = circular_box_sums(counts, width)
        valid = (box_counts >= 8) & ((total_count - box_counts) >= 8)
        inside = np.divide(box_sums, box_counts, out=np.zeros(bins),
                           where=box_counts > 0)
        outside = np.divide(total_sum - box_sums, total_count - box_counts,
                            out=np.zeros(bins), where=(total_count - box_counts) > 0)
        score = ((outside - inside) *
                 np.sqrt(box_counts * (total_count - box_counts) / total_count) /
                 sigma)
        score[~valid] = -np.inf
        index = int(np.argmax(score))
        if score[index] > best_score:
            best_score = float(score[index])
            best_start, best_width = index, width
    if return_location:
        return best_score, best_start, best_width
    return best_score


def simple_box_score(time, residual, period, bins=180):
    """Unweighted box-depth diagnostic under independent continuous detrending."""
    sums, counts = folded_bins(time, residual, period, bins)
    deepest = np.inf
    for width in (2, 3, 4, 5):
        box_sums = circular_box_sums(sums, width)
        box_counts = circular_box_sums(counts, width)
        means = np.divide(box_sums, box_counts, out=np.full(bins, np.nan),
                          where=box_counts > 0)
        deepest = min(deepest, float(np.nanmin(means)))
    return float(-deepest / robust_scatter(residual))


def epoch_support(time, residual, period, start, width, bins=240):
    """Count observed orbits containing at least two negative in-box samples."""
    phase = ((time - time[0]) % period) / period
    center = ((start + width / 2.0) % bins) / bins
    distance = np.abs(((phase - center + 0.5) % 1.0) - 0.5)
    in_box = distance <= width / (2.0 * bins)
    epoch = np.floor((time - time[0]) / period).astype(int)
    baseline = float(np.median(residual))
    supported = 0
    for number in np.unique(epoch):
        values = residual[(epoch == number) & in_box]
        if len(values) >= 2 and float(np.median(values)) < baseline:
            supported += 1
    return int(supported)


def separated_indices(scores, limit=5, separation=4):
    safe = np.nan_to_num(scores, nan=-np.inf, posinf=-np.inf, neginf=-np.inf)
    selected = []
    for index in np.argsort(safe)[::-1]:
        if not np.isfinite(safe[index]):
            continue
        if all(abs(int(index) - prior) > separation for prior in selected):
            selected.append(int(index))
        if len(selected) == limit:
            break
    return selected


def score_candidate(time, gap_residual, continuous_residual, period):
    weighted, start, width = weighted_bls(time, gap_residual, period,
                                          return_location=True)
    return {
        "period": float(period),
        "weighted_score": float(weighted),
        "simple_score": float(simple_box_score(time, continuous_residual, period)),
        "box_start": int(start),
        "box_width": int(width),
        "supported_epochs": epoch_support(time, gap_residual, period, start, width),
    }


def displayed_neighborhood(center, step, low, high):
    """Return five-decimal values around a refined peak, without presentation loss."""
    candidates = set()
    for value in np.linspace(center - 1.5 * step, center + 1.5 * step, 601):
        rounded = float(f"{value:.5f}")
        if low <= rounded <= high:
            candidates.add(rounded)
    return sorted(candidates)


def refine_seed(time, gap_residual, continuous_residual, seed, coarse_step, low, high):
    fine = np.linspace(max(low, seed - 2.0 * coarse_step),
                       min(high, seed + 2.0 * coarse_step), 1001)
    scores = np.asarray([weighted_bls(time, gap_residual, float(period))
                         for period in fine])
    if not np.isfinite(scores).any():
        return []
    center = float(fine[int(np.nanargmax(scores))])
    return [score_candidate(time, gap_residual, continuous_residual, period)
            for period in displayed_neighborhood(center, coarse_step, low, high)]


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
    requested_high = config.get("max_period")
    high = min(15.0, baseline / 1.8) if requested_high is None else float(requested_high)
    trials = int(config.get("trials", 5000))
    selection = config.get("selection", "multi_epoch")
    if not (np.isfinite(low) and np.isfinite(high) and 0 < low < high):
        raise ValueError("requested period range is invalid")
    if trials < 500:
        raise ValueError("trials must be at least 500")
    if selection not in {"multi_epoch", "global_box"}:
        raise ValueError("selection must be 'multi_epoch' or 'global_box'")

    gap_residual, segments = detrend_gap_aware(time, flux, cadence)
    continuous_residual = detrend_continuous(flux, cadence)
    grid = np.linspace(low, high, trials)
    weighted_grid = np.asarray([weighted_bls(time, gap_residual, float(period))
                                for period in grid])
    simple_grid = np.asarray([simple_box_score(time, continuous_residual, float(period))
                              for period in grid])
    if not np.isfinite(weighted_grid).any() or np.nanmax(weighted_grid) <= 0:
        raise ValueError("no positive finite folded-box candidate was found")

    seeds = set(separated_indices(weighted_grid))
    seeds.update(separated_indices(simple_grid))
    candidates = []
    coarse_step = float(grid[1] - grid[0])
    for index in sorted(seeds):
        candidates.extend(refine_seed(time, gap_residual, continuous_residual,
                                      float(grid[index]), coarse_step, low, high))
    # A period can appear from both statistics; retain its strongest complete record.
    by_period = {}
    for item in candidates:
        old = by_period.get(item["period"])
        if old is None or (item["weighted_score"], item["simple_score"]) > (old["weighted_score"], old["simple_score"]):
            by_period[item["period"]] = item
    repeated = [item for item in by_period.values()
                if np.isfinite(item["weighted_score"]) and item["weighted_score"] > 0
                and item["supported_epochs"] >= 3]
    if not repeated:
        raise ValueError("no candidate has a positive folded dip supported in three epochs")

    if selection == "multi_epoch":
        chosen = max(repeated, key=lambda item: (item["weighted_score"],
                                                  item["simple_score"],
                                                  item["supported_epochs"],
                                                  -item["period"]))
    else:
        chosen = max(repeated, key=lambda item: (item["simple_score"],
                                                  item["weighted_score"],
                                                  item["supported_epochs"],
                                                  -item["period"]))

    rendered = f"{chosen['period']:.5f}"
    atomic_write(output_path, rendered + "\n")
    return {
        "ok": True,
        "output_path": output_path,
        "period_days": chosen["period"],
        "period_rounded": rendered,
        "selection": selection,
        "weighted_bls_score": chosen["weighted_score"],
        "continuous_box_score": chosen["simple_score"],
        "box_start": chosen["box_start"],
        "box_width": chosen["box_width"],
        "supported_epochs": chosen["supported_epochs"],
        "weighted_broad_peak_period": float(grid[int(np.nanargmax(weighted_grid))]),
        "weighted_broad_peak_score": float(np.nanmax(weighted_grid)),
        "continuous_broad_peak_period": float(grid[int(np.nanargmax(simple_grid))]),
        "continuous_broad_peak_score": float(np.nanmax(simple_grid)),
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
