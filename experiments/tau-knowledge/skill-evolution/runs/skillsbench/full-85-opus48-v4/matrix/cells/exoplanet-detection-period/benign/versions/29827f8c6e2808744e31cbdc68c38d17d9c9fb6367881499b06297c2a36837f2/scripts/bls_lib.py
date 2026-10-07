"""Reusable helpers for transit-period detection.

Task-independent: all tunables are passed in; nothing about a specific
light curve is hardcoded. Only `numpy` is strictly required; `scipy` is used
for the median filter when available, otherwise a pure-numpy fallback runs.
"""
from __future__ import annotations
import numpy as np


def load_lightcurve(path):
    """Load a 4-column light curve, tolerating comments and ',' or whitespace.

    Returns (time, flux, qflag, err) as float arrays.
    """
    with open(path, "r") as fh:
        text = fh.read()
    # Decide delimiter: prefer comma only if commas appear on data lines.
    data_lines = [ln for ln in text.splitlines()
                  if ln.strip() and not ln.lstrip().startswith("#")]
    delim = "," if any("," in ln for ln in data_lines[:50]) else None
    rows = []
    for ln in data_lines:
        parts = ln.replace(",", " ").split() if delim == "," else ln.split()
        if len(parts) < 4:
            continue
        try:
            rows.append([float(parts[0]), float(parts[1]),
                         float(parts[2]), float(parts[3])])
        except ValueError:
            # header or malformed line
            continue
    if not rows:
        raise ValueError("No parseable 4-column rows found in %r" % path)
    arr = np.asarray(rows, dtype=float)
    t, f, q, e = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    return t, f, q, e


def filter_quality(t, f, q, e):
    """Keep good-quality (flag==0) finite rows, sorted in time."""
    good = (np.rint(q) == 0)
    good &= np.isfinite(t) & np.isfinite(f) & np.isfinite(e)
    good &= (e > 0)
    t, f, e = t[good], f[good], e[good]
    order = np.argsort(t)
    return t[order], f[order], e[order]


def _median_filter_samples(y, size):
    size = int(size)
    if size < 3:
        size = 3
    if size % 2 == 0:
        size += 1
    try:
        from scipy.ndimage import median_filter
        return median_filter(y, size=size, mode="reflect")
    except Exception:
        # Pure-numpy sliding median via reflected padding.
        half = size // 2
        yp = np.pad(y, half, mode="reflect")
        out = np.empty_like(y)
        # chunked to limit memory
        n = y.size
        step = max(1, 200000 // size)
        for start in range(0, n, step):
            stop = min(n, start + step)
            idx = np.arange(start, stop)[:, None] + np.arange(size)[None, :]
            out[start:stop] = np.median(yp[idx], axis=1)
        return out


def detrend(t, f, window_days):
    """Median-filter detrend. Window given in days -> samples via median cadence.

    Returns (flux_detrended, trend). Transit dips survive because the median is
    robust to short negative excursions.
    """
    if t.size < 5:
        return f.copy(), np.ones_like(f)
    dt = np.diff(t)
    cad = np.median(dt[dt > 0]) if np.any(dt > 0) else 1.0 / 48.0
    size = max(3, int(round(window_days / cad)))
    trend = _median_filter_samples(f, size)
    trend = np.where(np.abs(trend) < 1e-12, np.nan, trend)
    det = f / trend
    det = np.where(np.isfinite(det), det, 1.0)
    return det, trend


def clip_upward_outliers(t, f, e, n_sigma=4.0, neg_sigma=12.0):
    """Robust clip: remove strong UPWARD outliers; keep transit dips.

    Only very extreme negative points (likely cosmic/instrument) beyond
    `neg_sigma` are removed, so genuine transits are preserved.
    """
    med = np.median(f)
    mad = np.median(np.abs(f - med))
    sigma = 1.4826 * mad if mad > 0 else np.std(f)
    if sigma <= 0:
        return t, f, e
    keep = (f - med) <= n_sigma * sigma
    keep &= (f - med) >= -neg_sigma * sigma
    return t[keep], f[keep], e[keep]


def _bls_over_periods(t, f, e, periods, nbins, min_dur_frac, max_dur_frac):
    """Pure-numpy BLS. Returns arrays (sr_best, period) best over durations.

    Statistic SR = S^2 / (R*(1-R)) with weighted, mean-subtracted flux.
    """
    w = 1.0 / (e ** 2)
    w = w / w.sum()
    fm = f - np.sum(w * f)
    wf = w * fm
    nbins = int(nbins)
    min_bins = max(1, int(round(min_dur_frac * nbins)))
    max_bins = max(min_bins, int(round(max_dur_frac * nbins)))
    widths = np.arange(min_bins, max_bins + 1)
    best_sr = -np.inf
    best_P = float(periods[0])
    starts = np.arange(nbins)
    for P in periods:
        phase = (t % P) / P
        idx = np.floor(phase * nbins).astype(np.int64)
        np.clip(idx, 0, nbins - 1, out=idx)
        s = np.bincount(idx, weights=wf, minlength=nbins)
        r = np.bincount(idx, weights=w, minlength=nbins)
        s2 = np.concatenate([s, s])
        r2 = np.concatenate([r, r])
        cs = np.concatenate([[0.0], np.cumsum(s2)])
        cr = np.concatenate([[0.0], np.cumsum(r2)])
        local_best = 0.0
        for width in widths:
            S = cs[starts + width] - cs[starts]
            R = cr[starts + width] - cr[starts]
            denom = R * (1.0 - R)
            valid = denom > 1e-12
            if not np.any(valid):
                continue
            sr = (S[valid] ** 2) / denom[valid]
            m = sr.max()
            if m > local_best:
                local_best = m
        if local_best > best_sr:
            best_sr = local_best
            best_P = float(P)
    return best_sr, best_P


def bls_search(t, f, e, period_min, period_max, n_freq, nbins,
               min_dur_frac=0.005, max_dur_frac=0.12):
    """Frequency-uniform BLS search. Returns (best_period, best_sr)."""
    fmin = 1.0 / period_max
    fmax = 1.0 / period_min
    freqs = np.linspace(fmin, fmax, int(n_freq))
    periods = 1.0 / freqs
    sr, P = _bls_over_periods(t, f, e, periods, nbins, min_dur_frac, max_dur_frac)
    return P, sr


def refine_period(t, f, e, P0, n_freq, nbins, frac=0.02,
                  min_dur_frac=0.005, max_dur_frac=0.12):
    """Fine local search around P0 (+/- frac) at full numerical precision."""
    lo = P0 * (1.0 - frac)
    hi = P0 * (1.0 + frac)
    periods = np.linspace(lo, hi, int(n_freq))
    sr, P = _bls_over_periods(t, f, e, periods, nbins, min_dur_frac, max_dur_frac)
    return P, sr


def fold_diagnostics(t, f, e, P):
    """Return event count, depth, duration estimate, odd/even depths."""
    baseline = t.max() - t.min()
    n_events = int(np.floor(baseline / P)) + 1 if P > 0 else 0
    phase = (t % P) / P
    # find the box bin with the deepest weighted mean
    nbins = 200
    idx = np.clip((phase * nbins).astype(int), 0, nbins - 1)
    w = 1.0 / e ** 2
    sumw = np.bincount(idx, weights=w, minlength=nbins)
    sumwf = np.bincount(idx, weights=w * f, minlength=nbins)
    binmean = np.where(sumw > 0, sumwf / np.maximum(sumw, 1e-30), np.nan)
    base = np.nanmedian(binmean)
    dip_bin = np.nanargmin(binmean)
    depth = float(base - binmean[dip_bin])
    duration = float(P / nbins)
    # odd/even depths (cycle parity)
    cycle = np.floor(t / P).astype(int)
    in_dip = idx == dip_bin
    odd = in_dip & (cycle % 2 == 1)
    even = in_dip & (cycle % 2 == 0)
    def _depth(mask):
        if np.any(mask):
            return float(base - np.average(f[mask], weights=w[mask]))
        return float("nan")
    return {
        "n_events": n_events,
        "depth": depth,
        "duration_days": duration,
        "odd_depth": _depth(odd),
        "even_depth": _depth(even),
    }
