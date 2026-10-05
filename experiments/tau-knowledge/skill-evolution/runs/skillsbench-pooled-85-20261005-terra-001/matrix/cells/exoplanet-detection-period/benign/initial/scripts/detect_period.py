#!/usr/bin/env python3
"""Quality-filter, detrend, and BLS-search a four-column transit light curve.

JSON stdin schema is documented in SKILL.md.  The only intended filesystem side
 effect is writing the explicitly requested output_path.
"""
import json
import math
import os
import re
import sys

import numpy as np


def fail(message):
    raise ValueError(message)


def read_four_columns(path):
    """Read the first four numeric fields of data rows, ignoring textual headers."""
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = re.split(r"[\s,;]+", stripped)
            if len(fields) < 4:
                continue
            try:
                vals = [float(x.replace("D", "E").replace("d", "e"))
                        for x in fields[:4]]
            except ValueError:
                # This is normally a header line.
                continue
            rows.append(vals)
    if not rows:
        fail("no four-column numerical data rows were found")
    return np.asarray(rows, dtype=float)


def robust_scale(x):
    x = np.asarray(x, dtype=float)
    med = np.median(x)
    scale = 1.4826 * np.median(np.abs(x - med))
    if not np.isfinite(scale) or scale <= 0:
        scale = np.std(x)
    if not np.isfinite(scale) or scale <= 0:
        scale = max(abs(med) * 1e-8, 1e-10)
    return float(scale)


def smooth_edge(values, width):
    """Edge-padded moving average; width is made odd for centered smoothing."""
    values = np.asarray(values, dtype=float)
    if len(values) < 3 or width <= 1:
        return values.copy()
    width = int(min(width, len(values)))
    if width % 2 == 0:
        width -= 1
    if width <= 1:
        return values.copy()
    half = width // 2
    padded = np.pad(values, (half, half), mode="edge")
    return np.convolve(padded, np.ones(width) / width, mode="valid")


def detrend_segments(t, flux, cadence, window_days):
    """Return additive residuals after a gap-aware broad local trend estimate."""
    if window_days <= 0:
        fail("trend_window_days must be positive")
    # Bins much shorter than the smoothing scale retain transit information.
    bin_days = max(0.003, 3.0 * cadence)
    # A gap must not be bridged by the interpolation used to build a trend.
    gap_limit = max(0.30, 20.0 * cadence)
    breaks = np.flatnonzero(np.diff(t) > gap_limit) + 1
    starts = np.r_[0, breaks]
    ends = np.r_[breaks, len(t)]
    trend = np.empty_like(flux)

    for lo, hi in zip(starts, ends):
        ts, fs = t[lo:hi], flux[lo:hi]
        if len(ts) < 5 or ts[-1] - ts[0] < 2.0 * bin_days:
            trend[lo:hi] = np.median(fs)
            continue
        key = np.floor((ts - ts[0]) / bin_days).astype(int)
        keys, first = np.unique(key, return_index=True)
        med = np.empty(len(keys), dtype=float)
        center = np.empty(len(keys), dtype=float)
        # np.unique gives sorted keys, so adjacent first indices delimit groups.
        stops = np.r_[first[1:], len(key)]
        for j, (a, b) in enumerate(zip(first, stops)):
            med[j] = np.median(fs[a:b])
            center[j] = np.median(ts[a:b])
        # The wide smoother is intentionally much longer than a transit. A
        # median first makes isolated instrumental spikes have little leverage.
        width = max(3, int(round(window_days / bin_days)))
        broad = smooth_edge(med, width)
        trend[lo:hi] = np.interp(ts, center, broad, left=broad[0], right=broad[-1])
    return flux - trend


def bin_for_search(t, residual, weights, bin_days):
    """Compress nearby cadences while retaining weighted mean residuals."""
    key = np.floor((t - t[0]) / bin_days).astype(int)
    keys, first = np.unique(key, return_index=True)
    stops = np.r_[first[1:], len(key)]
    bt = np.empty(len(keys))
    br = np.empty(len(keys))
    bw = np.empty(len(keys))
    for j, (a, b) in enumerate(zip(first, stops)):
        ww = weights[a:b]
        sw = np.sum(ww)
        bt[j] = np.sum(t[a:b] * ww) / sw
        br[j] = np.sum(residual[a:b] * ww) / sw
        bw[j] = sw
    # Preserve relative precision but avoid a few underestimated uncertainties
    # dominating every trial box.
    bw /= np.median(bw)
    bw = np.clip(bw, 0.1, 10.0)
    return bt, br, bw


def bls_at_period(t, r, wgt, period, origin, noise, nbin=240):
    """Weighted phase-binned BLS-style score and its best box geometry."""
    phase = np.mod((t - origin) / period, 1.0)
    ibin = np.minimum((phase * nbin).astype(int), nbin - 1)
    sums = np.bincount(ibin, weights=r * wgt, minlength=nbin)
    counts = np.bincount(ibin, weights=wgt, minlength=nbin)
    ss = np.r_[0.0, np.cumsum(np.r_[sums, sums])]
    cc = np.r_[0.0, np.cumsum(np.r_[counts, counts])]

    # Fractional durations from approximately 0.5% through 12% of an orbit.
    widths = np.unique(np.maximum(1, np.round(
        np.array([0.004, 0.006, 0.008, 0.011, 0.015, 0.020, 0.028,
                  0.038, 0.052, 0.070, 0.095, 0.120]) * nbin).astype(int)))
    best_score, best_start, best_width = -np.inf, 0, int(widths[0])
    starts = np.arange(nbin)
    for width in widths:
        inside_sum = ss[starts + width] - ss[starts]
        inside_count = cc[starts + width] - cc[starts]
        # Positive residual denotes a flux dip.  Scaling by sqrt(weight) gives
        # a useful detection statistic while the robust noise prevents a raw
        # flux scale from changing period ranking.
        score = inside_sum / np.sqrt(np.maximum(inside_count, 1e-30) * noise * noise)
        j = int(np.argmax(score))
        if score[j] > best_score:
            best_score = float(score[j])
            best_start, best_width = j, int(width)
    return best_score, best_start, best_width


def choose_candidates(frequencies, scores, baseline, count=16):
    """Choose separated frequency peaks, not many samples of one BLS maximum."""
    order = np.argsort(scores)[::-1]
    chosen = []
    separation = 1.5 / baseline
    for idx in order:
        if not np.isfinite(scores[idx]):
            continue
        f = frequencies[idx]
        if all(abs(f - frequencies[j]) >= separation for j in chosen):
            chosen.append(int(idx))
        if len(chosen) >= count:
            break
    return chosen


def event_refine(t, residual, weights, period, start, width, nbin, origin, noise):
    """Fit times of repeatedly detected events to refine the numerical period."""
    phase_center = (start + 0.5 * width) / float(nbin)
    epoch = origin + phase_center * period
    half_duration = max(period * width / float(nbin) * 0.75, 1e-8)
    cycle = np.rint((t - epoch) / period).astype(int)
    centers, numbers, strengths = [], [], []

    for k in np.unique(cycle):
        dt = t - (epoch + k * period)
        use = np.abs(dt) <= half_duration
        if np.count_nonzero(use) < 2:
            continue
        ww = weights[use]
        mean_depth = np.sum(residual[use] * ww) / np.sum(ww)
        # A weak event may be a missed transit; do not give its noise centroid
        # equal leverage in the ephemeris regression.
        significance = mean_depth * math.sqrt(np.sum(ww)) / noise
        if not np.isfinite(significance) or significance < 0.7:
            continue
        deficit = np.maximum(residual[use], 0.0) * ww
        if np.sum(deficit) <= 0:
            continue
        centers.append(epoch + k * period + np.sum(dt[use] * deficit) / np.sum(deficit))
        numbers.append(int(k))
        strengths.append(max(float(significance), 0.1))

    if len(centers) < 2:
        return period, len(centers)
    x = np.asarray(numbers, dtype=float)
    y = np.asarray(centers, dtype=float)
    sw = np.asarray(strengths, dtype=float)
    fit = np.polyfit(x, y, 1, w=sw)
    pfit = float(fit[0])
    # Remove grossly inconsistent event centers once, then refit. This protects
    # against an activity minimum accidentally admitted as a weak event.
    err = y - np.polyval(fit, x)
    keep = np.abs(err) <= max(3.0 * robust_scale(err), 0.25 * half_duration)
    if np.count_nonzero(keep) >= 2:
        pfit = float(np.polyfit(x[keep], y[keep], 1, w=sw[keep])[0])
    if not np.isfinite(pfit) or pfit <= 0 or abs(pfit / period - 1.0) > 0.08:
        return period, int(np.count_nonzero(keep))
    return pfit, int(np.count_nonzero(keep))


def detect(config):
    input_path = config.get("input_path")
    output_path = config.get("output_path")
    if not isinstance(input_path, str) or not input_path:
        fail("input_path is required")
    if not isinstance(output_path, str) or not output_path:
        fail("output_path is required")

    arr = read_four_columns(input_path)
    total_rows = len(arr)
    time, flux, quality, uncertainty = arr.T
    trusted = ((quality == 0) & np.isfinite(time) & np.isfinite(flux) &
               np.isfinite(uncertainty) & (uncertainty > 0))
    time, flux, uncertainty = time[trusted], flux[trusted], uncertainty[trusted]
    if len(time) < 30:
        fail("fewer than 30 finite quality-flag-zero cadences remain")
    order = np.argsort(time)
    time, flux, uncertainty = time[order], flux[order], uncertainty[order]

    # Reject only implausibly high values. Low values are deliberately retained
    # because transit-shaped negative flux excursions are the desired signal.
    med, scale = np.median(flux), robust_scale(flux)
    high_ok = flux <= med + 8.0 * scale
    time, flux, uncertainty = time[high_ok], flux[high_ok], uncertainty[high_ok]
    if len(time) < 30 or time[-1] <= time[0]:
        fail("trusted data have insufficient distinct time coverage")
    dt = np.diff(time)
    positive_dt = dt[dt > 0]
    if len(positive_dt) == 0:
        fail("time values are not distinct")
    cadence = float(np.median(positive_dt))
    baseline = float(time[-1] - time[0])

    trend_window = float(config.get("trend_window_days", 0.75))
    residual = detrend_segments(time, flux, cadence, trend_window)
    # Precision weighting is clipped to avoid pathological reported errors.
    weights = 1.0 / (uncertainty * uncertainty)
    weights /= np.median(weights)
    weights = np.clip(weights, 0.1, 10.0)
    noise = robust_scale(residual)
    # Cap only the search influence of fantastically isolated low points. They
    # are retained in the data and repeated normal-depth transits remain favored.
    search_residual = np.minimum(residual, 20.0 * noise)
    bt, br, bw = bin_for_search(time, search_residual, weights, max(0.003, 2.0 * cadence))

    min_period = float(config.get("min_period", max(0.10, 5.0 * cadence)))
    default_max = min(0.48 * baseline, 30.0)
    max_period = float(config.get("max_period", default_max))
    if min_period <= 0 or max_period <= min_period:
        fail("period bounds must be positive and max_period must exceed min_period")
    if max_period > 0.5 * baseline + 1e-12:
        fail("max_period must allow at least two observed events (<= half baseline)")

    fmin, fmax = 1.0 / max_period, 1.0 / min_period
    # Frequency spacing gives phase drift around 1/60 cycle across the baseline.
    nfreq = int(math.ceil((fmax - fmin) * baseline * 60.0)) + 1
    nfreq = max(400, min(nfreq, 22000))
    freq = np.linspace(fmin, fmax, nfreq)
    scores = np.empty(nfreq)
    geometry = []
    origin = float(time[0])
    for i, f in enumerate(freq):
        score, start, width = bls_at_period(bt, br, bw, 1.0 / f, origin, noise)
        scores[i] = score
        geometry.append((start, width))
    candidate_indices = choose_candidates(freq, scores, baseline)
    if not candidate_indices:
        fail("BLS search returned no finite candidate")
    best_i = candidate_indices[0]
    raw_period = float(1.0 / freq[best_i])
    start, width = geometry[best_i]
    refined_period, event_count = event_refine(
        time, residual, weights, raw_period, start, width, 240, origin, noise)
    if not np.isfinite(refined_period) or refined_period <= 0:
        fail("period refinement did not produce a positive finite period")

    rendered = f"{refined_period:.5f}\n"
    if not re.fullmatch(r"[0-9]+\.[0-9]{5}\n", rendered):
        fail("internal output formatting validation failed")
    parsed = float(rendered)
    if not np.isfinite(parsed) or parsed <= 0:
        fail("rounded period is not a positive finite value")
    parent = os.path.dirname(os.path.abspath(output_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)

    return {
        "period_days": refined_period,
        "raw_period_days": raw_period,
        "bls_score": float(scores[best_i]),
        "n_events_used": event_count,
        "total_rows": int(total_rows),
        "trusted_rows": int(len(time)),
        "search_binned_rows": int(len(bt)),
        "baseline_days": baseline,
        "trend_window_days": trend_window,
        "output_path": output_path,
    }


def main():
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            fail("stdin JSON must be an object")
        result = detect(config)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
