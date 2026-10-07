#!/usr/bin/env python3
"""Robust TESS-like transit period finder.

CLI: find_transit_period.py --input LIGHTCURVE --output PERIOD_FILE
stdin alternative: {"input": "...", "output": "..."}
stdout: one JSON diagnostic object.  No third-party dependency is required;
Astropy is used opportunistically for its BoxLeastSquares implementation.
"""
import argparse
import json
import math
import os
import sys
import re
import numpy as np


def read_lightcurve(path):
    """Read first four numeric fields from every usable text line."""
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            # Headers are naturally ignored because they have fewer than 4 numbers.
            vals = re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", line)
            if len(vals) >= 4:
                try:
                    rows.append([float(x) for x in vals[:4]])
                except ValueError:
                    pass
    if len(rows) < 30:
        raise ValueError("light curve has fewer than 30 numeric four-column rows")
    a = np.asarray(rows, dtype=float)
    t, f, q, e = a.T
    keep = np.isfinite(t) & np.isfinite(f) & np.isfinite(q) & np.isfinite(e) & (e > 0) & (q == 0)
    t, f, e = t[keep], f[keep], e[keep]
    order = np.argsort(t)
    t, f, e = t[order], f[order], e[order]
    if len(t) < 30 or t[-1] <= t[0]:
        raise ValueError("too few usable, time-distinct quality-flag-zero observations")
    # Protect transit-like downward deviations: clip only extreme high excursions.
    med = np.median(f)
    mad = 1.4826 * np.median(np.abs(f - med))
    if np.isfinite(mad) and mad > 0:
        good = f < med + 10.0 * mad
        t, f, e = t[good], f[good], e[good]
    return t, f, e


def gaussian_smooth(y, sigma_bins):
    """Finite-aware Gaussian convolution; sigma is in regular time bins."""
    sigma_bins = max(float(sigma_bins), 1.0)
    half = max(2, int(math.ceil(4 * sigma_bins)))
    x = np.arange(-half, half + 1, dtype=float)
    k = np.exp(-0.5 * (x / sigma_bins) ** 2)
    k /= k.sum()
    valid = np.isfinite(y).astype(float)
    yy = np.where(np.isfinite(y), y, 0.0)
    num = np.convolve(yy, k, mode="same")
    den = np.convolve(valid, k, mode="same")
    return np.divide(num, den, out=np.full_like(num, np.nan), where=den > 1e-8)


def detrend(t, flux, smooth_days):
    """Robust trend from binned medians; missing bins remain missing observations."""
    span = t[-1] - t[0]
    # 0.02 d resolves ordinary transit durations while median binning rejects cadence noise.
    bw = min(0.05, max(0.005, span / 2000.0))
    nb = max(8, int(math.ceil(span / bw)) + 1)
    idx = np.clip(((t - t[0]) / bw).astype(int), 0, nb - 1)
    bins = np.full(nb, np.nan)
    for j in np.unique(idx):
        bins[j] = np.median(flux[idx == j])
    centers = t[0] + (np.arange(nb) + 0.5) * bw
    trend_bins = gaussian_smooth(bins, smooth_days / bw)
    usable = np.isfinite(trend_bins)
    if usable.sum() < 2:
        raise ValueError("cannot construct a detrending trend")
    trend = np.interp(t, centers[usable], trend_bins[usable],
                      left=trend_bins[usable][0], right=trend_bins[usable][-1])
    # Relative residual is appropriate for normalized flux and preserves depth scale.
    residual = flux / trend - 1.0
    residual -= np.median(residual)
    return residual


def fallback_bls(t, y, minp, maxp):
    """Folded binned box search, used only when Astropy is unavailable."""
    # Frequency spacing follows the shortest searched box duration over the baseline.
    span = t[-1] - t[0]
    fmin, fmax = 1.0 / maxp, 1.0 / minp
    nfreq = int(np.clip(math.ceil((fmax - fmin) * span / 0.012), 2500, 16000))
    freqs = np.linspace(fmin, fmax, nfreq)
    nbins = 240
    widths = (2, 3, 4, 6, 8, 12, 16, 22)
    best = []
    for fr in freqs:
        phase = (t * fr) % 1.0
        bi = np.minimum((phase * nbins).astype(int), nbins - 1)
        count = np.bincount(bi, minlength=nbins).astype(float)
        sums = np.bincount(bi, weights=y, minlength=nbins)
        # Duplicate arrays to allow boxes across phase zero.
        cc = np.r_[count, count]
        ss = np.r_[sums, sums]
        cs_c = np.r_[0.0, np.cumsum(cc)]
        cs_s = np.r_[0.0, np.cumsum(ss)]
        total_n, total_s = count.sum(), sums.sum()
        local_best = (-np.inf, None, None)
        for w in widths:
            n = cs_c[w:w + nbins] - cs_c[:nbins]
            s = cs_s[w:w + nbins] - cs_s[:nbins]
            outn = total_n - n
            outs = total_s - s
            inn = np.divide(s, n, out=np.zeros_like(s), where=n > 0)
            out = np.divide(outs, outn, out=np.zeros_like(outs), where=outn > 0)
            # Negative in-box mean relative to out-of-box mean is transit evidence.
            score = (out - inn) * np.sqrt(np.maximum(n, 0))
            j = int(np.argmax(score))
            if score[j] > local_best[0]:
                local_best = (float(score[j]), j, w)
        score, j, w = local_best
        best.append((score, 1.0 / fr, (j + 0.5 * w) / nbins, w / nbins / fr))
    best.sort(reverse=True)
    return best[:40], "folded_binned_fallback"


def astropy_bls(t, y, dy, minp, maxp):
    from astropy.timeseries import BoxLeastSquares
    # Guard against underestimated formal errors dominating a few cadences.
    robust = 1.4826 * np.median(np.abs(y - np.median(y)))
    use_dy = np.maximum(dy, max(robust * 0.15, np.percentile(dy, 10)))
    model = BoxLeastSquares(t, y, dy=use_dy)
    durations = np.geomspace(0.015, min(0.45, maxp * 0.12), 14)
    result = model.autopower(durations, minimum_period=minp, maximum_period=maxp,
                             frequency_factor=1.0, objective="snr")
    order = np.argsort(result.power)[::-1]
    candidates = []
    for j in order[:80]:
        candidates.append((float(result.power[j]), float(result.period[j]),
                           float((result.transit_time[j] / result.period[j]) % 1.0),
                           float(result.duration[j])))
    return candidates, "astropy_boxleastsquares"


def occupancy_and_centers(t, y, period, phase, duration):
    """Assess whether each predicted orbit contains a negative event and time it."""
    # phase convention: epoch modulo P. Choose nearby epoch range over observed time.
    epoch0 = phase * period
    k0 = int(math.floor((t[0] - epoch0) / period)) - 1
    k1 = int(math.ceil((t[-1] - epoch0) / period)) + 1
    centers, strengths, expected = [], [], 0
    half = max(duration * 0.65, 0.01)
    baseline_noise = 1.4826 * np.median(np.abs(y - np.median(y))) + 1e-12
    for k in range(k0, k1 + 1):
        c = epoch0 + k * period
        if c - half < t[0] or c + half > t[-1]:
            continue
        expected += 1
        use = np.abs(t - c) <= half
        if use.sum() < 3:
            continue
        yy, tt = y[use], t[use]
        local = np.median(yy)
        deficit = np.maximum(local - yy, 0.0)
        # A weighted centroid is a sub-cadence timing refinement for genuine dips.
        if deficit.sum() > 0:
            tc = float(np.sum(tt * deficit) / deficit.sum())
        else:
            tc = c
        strength = max(0.0, -float(np.percentile(yy, 25))) / baseline_noise
        if strength > 0.35:
            centers.append((k, tc))
            strengths.append(strength)
    occ = len(centers) / max(expected, 1)
    return occ, centers, strengths, expected


def refine_period(period, phase, duration, t, y):
    occ, centers, strengths, expected = occupancy_and_centers(t, y, period, phase, duration)
    if len(centers) >= 3:
        kk = np.asarray([x[0] for x in centers], dtype=float)
        cc = np.asarray([x[1] for x in centers], dtype=float)
        ww = np.asarray(strengths, dtype=float)
        # Iteratively discard timing outliers before a weighted ephemeris fit.
        keep = np.ones(len(kk), dtype=bool)
        for _ in range(2):
            coef = np.polyfit(kk[keep], cc[keep], 1, w=ww[keep])
            resid = cc - np.polyval(coef, kk)
            scale = 1.4826 * np.median(np.abs(resid[keep] - np.median(resid[keep])))
            if scale > 0:
                keep = np.abs(resid) < max(4 * scale, duration * 0.35)
        if keep.sum() >= 3 and coef[0] > 0:
            period = float(coef[0])
    return period, occ, len(centers), expected


def solve(t, flux, err):
    span = t[-1] - t[0]
    minp = max(0.15, 2.0 * np.median(np.diff(t)))
    # Two transits are the minimum evidence; do not search unsupported periods.
    maxp = min(30.0, span / 1.7)
    if maxp <= minp * 1.05:
        raise ValueError("time baseline is insufficient to support a repeated transit search")
    all_solutions = []
    for smooth in (0.7, 1.8):
        y = detrend(t, flux, smooth)
        try:
            candidates, method = astropy_bls(t, y, err, minp, maxp)
        except (ImportError, ModuleNotFoundError):
            candidates, method = fallback_bls(t, y, minp, maxp)
        # Deduplicate numerically close BLS grid points, then explicitly inspect aliases.
        raw = candidates[:24]
        augmented = list(raw)
        for score, p, ph, dur in raw[:10]:
            for fac in (0.5, 2.0):
                pp = p * fac
                if minp <= pp <= maxp:
                    augmented.append((score * 0.90, pp, (ph / fac) % 1.0, dur * fac))
        seen = []
        for score, p, ph, dur in augmented:
            if any(abs(p - z[1]) / p < 2e-4 for z in seen):
                continue
            rp, occ, nev, expected = refine_period(p, ph, dur, t, y)
            # Repeated occupied epochs distinguish a fundamental from a subharmonic.
            merit = score * (0.25 + 0.75 * occ) * math.sqrt(max(nev, 1) / max(expected, 1))
            seen.append((merit, rp, occ, nev, expected, score, smooth, method))
        all_solutions.extend(seen)
    viable = [x for x in all_solutions if x[3] >= 2 and x[2] >= 0.45 and np.isfinite(x[1])]
    if not viable:
        raise ValueError("no credible box-shaped candidate with at least two supported events")
    viable.sort(key=lambda x: x[0], reverse=True)
    best = viable[0]
    # A refinement cannot turn a candidate into an unsupported period.
    if not (minp <= best[1] <= maxp):
        raise ValueError("refined period lies outside the supported search range")
    return best, viable[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/root/data/tess_lc.txt")
    ap.add_argument("--output", default="/root/period.txt")
    args = ap.parse_args()
    if not sys.stdin.isatty():
        try:
            supplied = json.load(sys.stdin)
            args.input = supplied.get("input", args.input)
            args.output = supplied.get("output", args.output)
        except (json.JSONDecodeError, ValueError):
            pass
    t, f, e = read_lightcurve(args.input)
    best, ranked = solve(t, f, e)
    merit, period, occ, nev, expected, rawscore, smooth, method = best
    rounded = f"{period:.5f}"
    outdir = os.path.dirname(os.path.abspath(args.output))
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as g:
        g.write(rounded + "\n")
    report = {
        "period_days_unrounded": period,
        "period_days_rounded": rounded,
        "output": args.output,
        "retained_cadences": int(len(t)),
        "baseline_days": float(t[-1] - t[0]),
        "search_method": method,
        "detrend_smoothing_days": smooth,
        "event_occupancy": occ,
        "supported_events": nev,
        "expected_full_events": expected,
        "top_candidates_days": [float(x[1]) for x in ranked],
    }
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(2)
