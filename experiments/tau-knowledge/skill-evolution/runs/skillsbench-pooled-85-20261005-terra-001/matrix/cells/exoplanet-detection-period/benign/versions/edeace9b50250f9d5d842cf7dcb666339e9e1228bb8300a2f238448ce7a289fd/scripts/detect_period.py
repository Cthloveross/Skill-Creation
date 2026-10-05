#!/usr/bin/env python3
"""Robust box-transit search with local refinement and harmonic comparison.

Read one JSON object from stdin as documented in SKILL.md, write the requested
period artifact, and emit JSON diagnostics to stdout.
"""
import json
import math
import os
import re
import sys

import numpy as np


def fail(message):
    raise ValueError(message)


def robust_scale(values):
    values = np.asarray(values, dtype=float)
    med = float(np.median(values))
    scale = 1.4826 * float(np.median(np.abs(values - med)))
    if not np.isfinite(scale) or scale <= 0:
        scale = float(np.std(values))
    if not np.isfinite(scale) or scale <= 0:
        scale = max(abs(med) * 1e-10, 1e-12)
    return scale


def read_rows(path):
    """Read the first four numerical fields from non-header text rows."""
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = re.split(r"[\s,;]+", line)
            if len(fields) < 4:
                continue
            try:
                rows.append([float(x.replace("D", "E").replace("d", "e"))
                             for x in fields[:4]])
            except ValueError:
                # Textual headers are permitted.
                continue
    if not rows:
        fail("no parseable four-column numerical rows were found")
    return np.asarray(rows, dtype=float)


def running_median(values, half_width):
    """Centered, edge-truncated median smoothing for a binned series."""
    values = np.asarray(values, dtype=float)
    result = np.empty_like(values)
    for j in range(len(values)):
        result[j] = np.median(values[max(0, j - half_width):
                                     min(len(values), j + half_width + 1)])
    return result


def detrend_segments(time, flux, cadence, bin_days, window_days):
    """Subtract a gap-aware robust stellar-activity trend."""
    if bin_days <= 0 or window_days <= 0:
        fail("trend_bin_days and trend_window_days must both be positive")

    # Never interpolate a trend across a substantial observing gap.
    gap_limit = max(0.45, 15.0 * cadence)
    cuts = np.flatnonzero(np.diff(time) > gap_limit) + 1
    starts = np.r_[0, cuts]
    stops = np.r_[cuts, len(time)]
    trend = np.empty_like(flux)

    broad_bins = max(3, int(round(window_days / bin_days)))
    if broad_bins % 2 == 0:
        broad_bins += 1
    half_width = broad_bins // 2

    for lo, hi in zip(starts, stops):
        t = time[lo:hi]
        y = flux[lo:hi]
        if len(t) < 6 or t[-1] - t[0] < 2.0 * bin_days:
            trend[lo:hi] = np.median(y)
            continue
        ibin = np.floor((t - t[0]) / bin_days).astype(int)
        _, first = np.unique(ibin, return_index=True)
        ends = np.r_[first[1:], len(ibin)]
        centers = np.empty(len(first))
        medians = np.empty(len(first))
        for j, (a, b) in enumerate(zip(first, ends)):
            centers[j] = np.median(t[a:b])
            medians[j] = np.median(y[a:b])
        smooth = running_median(medians, half_width)
        trend[lo:hi] = np.interp(t, centers, smooth,
                                 left=smooth[0], right=smooth[-1])
    residual = flux - trend
    return residual - np.median(residual)


def bin_for_coarse_search(time, residual, weights, bin_days):
    """Compress close cadences for the broad scan without filling gaps."""
    ibin = np.floor((time - time[0]) / bin_days).astype(int)
    _, first = np.unique(ibin, return_index=True)
    ends = np.r_[first[1:], len(ibin)]
    bt = np.empty(len(first))
    br = np.empty(len(first))
    bw = np.empty(len(first))
    for j, (a, b) in enumerate(zip(first, ends)):
        w = weights[a:b]
        total_weight = float(np.sum(w))
        bt[j] = float(np.sum(time[a:b] * w) / total_weight)
        br[j] = float(np.sum(residual[a:b] * w) / total_weight)
        bw[j] = total_weight
    bw /= np.median(bw)
    return bt, br, np.clip(bw, 0.1, 10.0)


def box_at_period(time, residual, period, noise, weights=None, bins=220):
    """Return negative-box S/N, phase-window start, and window width."""
    phase = np.mod((time - time[0]) / period, 1.0)
    index = np.minimum((phase * bins).astype(int), bins - 1)
    if weights is None:
        sums = np.bincount(index, weights=residual, minlength=bins)
        counts = np.bincount(index, minlength=bins).astype(float)
    else:
        sums = np.bincount(index, weights=residual * weights, minlength=bins)
        counts = np.bincount(index, weights=weights, minlength=bins)

    sums2 = np.r_[sums, sums]
    counts2 = np.r_[counts, counts]
    cumulative_sum = np.r_[0.0, np.cumsum(sums2)]
    cumulative_count = np.r_[0.0, np.cumsum(counts2)]
    best_score, best_start, best_width = -np.inf, 0, 1

    # Approximately 0.45--6.4 percent of an orbit: short-transit windows.
    for width in range(1, 15):
        total = cumulative_sum[width:width + bins] - cumulative_sum[:bins]
        n = cumulative_count[width:width + bins] - cumulative_count[:bins]
        valid = n >= 8.0
        if not np.any(valid):
            continue
        score = np.full(bins, -np.inf)
        score[valid] = -total[valid] / (noise * np.sqrt(n[valid]))
        j = int(np.argmax(score))
        if score[j] > best_score:
            best_score, best_start, best_width = float(score[j]), j, width
    return best_score, best_start, best_width


def separated_candidates(frequencies, scores, baseline, wanted=10):
    """Select distinct frequency maxima rather than samples of one peak."""
    selected = []
    separation = 2.0 / baseline
    for i in np.argsort(scores)[::-1]:
        if not np.isfinite(scores[i]):
            continue
        if all(abs(frequencies[i] - frequencies[j]) >= separation for j in selected):
            selected.append(int(i))
        if len(selected) >= wanted:
            break
    return selected


def local_refine(time, residual, noise, center_frequency, baseline, fmin, fmax):
    """Perform two nested dense scans around one frequency candidate."""
    lo = max(fmin, center_frequency - 2.5 / baseline)
    hi = min(fmax, center_frequency + 2.5 / baseline)
    if not np.isfinite(center_frequency) or hi <= lo:
        return None

    grid1 = np.linspace(lo, hi, 241)
    scores1 = np.empty(len(grid1))
    for j, frequency in enumerate(grid1):
        scores1[j] = box_at_period(time, residual, 1.0 / frequency, noise)[0]
    i1 = int(np.argmax(scores1))

    step = grid1[1] - grid1[0]
    lo2 = max(fmin, grid1[i1] - 4.0 * step)
    hi2 = min(fmax, grid1[i1] + 4.0 * step)
    grid2 = np.linspace(lo2, hi2, 401)
    scores2 = np.empty(len(grid2))
    geometry2 = []
    for j, frequency in enumerate(grid2):
        result = box_at_period(time, residual, 1.0 / frequency, noise)
        scores2[j] = result[0]
        geometry2.append(result[1:])
    i2 = int(np.argmax(scores2))
    return {
        "frequency": float(grid2[i2]),
        "period": float(1.0 / grid2[i2]),
        "score": float(scores2[i2]),
        "start": int(geometry2[i2][0]),
        "width": int(geometry2[i2][1]),
    }


def harmonic_refinements(time, residual, noise, primary, baseline, fmin, fmax):
    """Refine P/2 and 2P alternatives of the strongest primary solutions."""
    extra = []
    centers_seen = []
    # A small number controls runtime while still testing harmonics of several
    # independently separated broad-search peaks.
    for candidate in sorted(primary, key=lambda item: item["score"], reverse=True)[:4]:
        for factor in (0.5, 2.0):
            center = candidate["frequency"] * factor
            if center < fmin or center > fmax:
                continue
            if any(abs(center - old) < 1e-10 for old in centers_seen):
                continue
            centers_seen.append(center)
            refined = local_refine(time, residual, noise, center, baseline, fmin, fmax)
            if refined is not None and np.isfinite(refined["score"]):
                extra.append(refined)
    return extra


def detect(config):
    input_path = config.get("input_path")
    output_path = config.get("output_path")
    if not isinstance(input_path, str) or not input_path:
        fail("input_path is required")
    if not isinstance(output_path, str) or not output_path:
        fail("output_path is required")

    data = read_rows(input_path)
    total_rows = int(len(data))
    time, flux, quality, uncertainty = data.T
    trusted = ((quality == 0) & np.isfinite(time) & np.isfinite(flux) &
               np.isfinite(uncertainty) & (uncertainty > 0))
    time, flux, uncertainty = time[trusted], flux[trusted], uncertainty[trusted]
    if len(time) < 50:
        fail("fewer than 50 finite quality-flag-zero cadences remain")
    order = np.argsort(time)
    time, flux, uncertainty = time[order], flux[order], uncertainty[order]

    # Preserve potential transit dips; reject only implausibly high artifacts.
    median_flux = float(np.median(flux))
    upper_scale = robust_scale(flux[flux >= median_flux])
    keep = flux <= median_flux + 8.0 * upper_scale
    time, flux, uncertainty = time[keep], flux[keep], uncertainty[keep]
    if len(time) < 50 or time[-1] <= time[0]:
        fail("trusted data have insufficient distinct time coverage")
    delta = np.diff(time)
    positive_delta = delta[delta > 0]
    if len(positive_delta) == 0:
        fail("time values are not distinct")
    cadence = float(np.median(positive_delta))
    baseline = float(time[-1] - time[0])

    bin_days = float(config.get("trend_bin_days", 0.08))
    window_days = float(config.get("trend_window_days", 0.88))
    residual = detrend_segments(time, flux, cadence, bin_days, window_days)
    noise = robust_scale(residual)
    # Cap only the statistic input, so one pathological negative point cannot
    # dominate while the original filtered light curve remains intact.
    search_residual = np.maximum(residual, -12.0 * noise)

    raw_weight = 1.0 / np.square(uncertainty)
    raw_weight /= np.median(raw_weight)
    weights = np.clip(raw_weight, 0.1, 10.0)
    coarse_bin_days = max(0.003, 2.0 * cadence)
    bt, br, bw = bin_for_coarse_search(time, search_residual, weights, coarse_bin_days)

    default_min = max(0.5, 5.0 * cadence)
    default_max = min(15.0, baseline / 2.2)
    min_period = float(config.get("min_period", default_min))
    max_period = float(config.get("max_period", default_max))
    if min_period <= 0 or max_period <= min_period:
        fail("period bounds must be positive and max_period must exceed min_period")
    if max_period > baseline / 2.0 + 1e-12:
        fail("max_period must allow at least two observed events")

    fmin, fmax = 1.0 / max_period, 1.0 / min_period
    nfreq = int(math.ceil((fmax - fmin) * baseline * 80.0)) + 1
    nfreq = max(500, min(nfreq, 30000))
    frequencies = np.linspace(fmin, fmax, nfreq)
    coarse_scores = np.empty(nfreq)
    for j, frequency in enumerate(frequencies):
        coarse_scores[j] = box_at_period(bt, br, 1.0 / frequency, noise,
                                          weights=bw)[0]

    candidates = separated_candidates(frequencies, coarse_scores, baseline)
    if not candidates:
        fail("the broad box search returned no finite candidates")

    primary = []
    for index in candidates:
        refined = local_refine(time, search_residual, noise,
                               float(frequencies[index]), baseline, fmin, fmax)
        if refined is not None and np.isfinite(refined["score"]):
            primary.append(refined)
    if not primary:
        fail("local transit-period refinement returned no finite candidates")

    # An initial BLS list can contain 2P even when P was not retained as a
    # broad local maximum. Refine both integer-neighbour possibilities before
    # selecting the statistically strongest folded transit.
    harmonics = harmonic_refinements(time, search_residual, noise, primary,
                                     baseline, fmin, fmax)
    refinements = primary + harmonics
    best = max(refinements, key=lambda item: item["score"])
    if best["score"] < 5.0:
        fail("no significant repeated negative box-shaped signal was found")

    period = best["period"]
    phase = np.mod((time - time[0]) / period, 1.0)
    lo = best["start"] / 220.0
    hi = (best["start"] + best["width"]) / 220.0
    if hi <= 1.0:
        in_box = (phase >= lo) & (phase < hi)
    else:
        in_box = (phase >= lo) | (phase < hi - 1.0)
    cycles = np.floor((time[in_box] - time[0]) / period).astype(int)
    n_cycles = int(len(np.unique(cycles)))
    if n_cycles < 2:
        fail("the selected box does not occupy at least two distinct orbital cycles")

    rendered = f"{period:.5f}\n"
    if not re.fullmatch(r"[0-9]+\.[0-9]{5}\n", rendered):
        fail("internal fixed-five-decimal formatting validation failed")
    rounded = float(rendered)
    if not np.isfinite(rounded) or rounded <= 0:
        fail("rounded period is not finite and positive")

    parent = os.path.dirname(os.path.abspath(output_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)

    coarse_index = candidates[0]
    return {
        "period_days": period,
        "coarse_period_days": float(1.0 / frequencies[coarse_index]),
        "box_score": best["score"],
        "n_transit_cycles": n_cycles,
        "total_rows": total_rows,
        "trusted_rows": int(len(time)),
        "coarse_binned_rows": int(len(bt)),
        "baseline_days": baseline,
        "trend_bin_days": bin_days,
        "trend_window_days": window_days,
        "primary_candidates_examined": len(primary),
        "harmonic_candidates_examined": len(harmonics),
        "output_path": output_path,
    }


def main():
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            fail("stdin JSON must be an object")
        print(json.dumps(detect(config), sort_keys=True, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
