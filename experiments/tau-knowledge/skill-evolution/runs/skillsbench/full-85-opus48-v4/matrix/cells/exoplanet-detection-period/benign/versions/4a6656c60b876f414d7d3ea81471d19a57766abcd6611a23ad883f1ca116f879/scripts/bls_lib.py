"""Reusable helpers for transit-period detection.

Task-independent: all tunables are passed in; nothing about a specific
light curve is hardcoded. Only ``numpy`` is strictly required. ``scipy`` is
used for the median filter when available (pure-numpy fallback otherwise).
``astropy.timeseries.BoxLeastSquares`` is used for the box-least-squares search
when available; a pure-numpy BLS fallback runs otherwise.
"""
from __future__ import annotations
import numpy as np


def load_lightcurve(path):
    """Load a 4-column light curve, tolerating comments and ',' or whitespace.

    Returns (time, flux, qflag, err) as float arrays.
    """
    with open(path, "r") as fh:
        text = fh.read()
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
            continue
    if not rows:
        raise ValueError("No parseable 4-column rows found in %r" % path)
    arr = np.asarray(rows, dtype=float)
    t, f, q, e = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    return t, f, q, e


def filter_quality(t, f, q, e):
    """Keep good-quality (flag==0) finite rows with positive errors, time-sorted."""
    good = (np.rint(q) == 0)
    good &= np.isfinite(t) & np.isfinite(f) & np.isfinite(e)
    good &= (e > 0)
    t, f, e = t[good], f[good], e[good]
    order = np.argsort(t)
    return t[order], f[order], e[order]


def median_cadence(t):
    if t.size < 2:
        return 1.0 / 48.0
    dt = np.diff(t)
    dt = dt[dt > 0]
    return float(np.median(dt)) if dt.size else 1.0 / 48.0


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
        half = size // 2
        yp = np.pad(y, half, mode="reflect")
        out = np.empty_like(y)
        n = y.size
        step = max(1, 200000 // size)
        for start in range(0, n, step):
            stop = min(n, start + step)
            idx = np.arange(start, stop)[:, None] + np.arange(size)[None, :]
            out[start:stop] = np.median(yp[idx], axis=1)
        return out


def detrend(t, f, window_days):
    """Median-filter detrend; window in days -> samples via median cadence.

    Returns (flux_detrended, trend). A time-window **median** removes
    variability longer than a transit while transit dips survive, because the
    median is robust to short negative excursions. The window must be shorter
    than the stellar rotation period but several times the transit duration.
    """
    if t.size < 5:
        return f.copy(), np.ones_like(f)
    cad = median_cadence(t)
    size = max(3, int(round(window_days / cad)))
    trend = _median_filter_samples(f, size)
    trend = np.where(np.abs(trend) < 1e-12, np.nan, trend)
    det = f / trend
    det = np.where(np.isfinite(det), det, 1.0)
    return det, trend


def clip_upward_outliers(t, f, e, n_sigma=5.0, neg_sigma=15.0):
    """Robust clip: remove strong UPWARD outliers; keep transit dips.

    Only very extreme negative points (beyond ``neg_sigma``) are removed, so
    genuine transit dips are preserved and never define the outlier model.
    """
    med = np.median(f)
    mad = np.median(np.abs(f - med))
    sigma = 1.4826 * mad if mad > 0 else np.std(f)
    if sigma <= 0:
        return t, f, e
    keep = (f - med) <= n_sigma * sigma
    keep &= (f - med) >= -neg_sigma * sigma
    return t[keep], f[keep], e[keep]


# ---------------------------------------------------------------------------
# Box-least-squares search
# ---------------------------------------------------------------------------

def _have_astropy():
    try:
        from astropy.timeseries import BoxLeastSquares  # noqa: F401
        return True
    except Exception:
        return False


def _astropy_bls_power(t, f, e, periods, durations):
    from astropy.timeseries import BoxLeastSquares
    model = BoxLeastSquares(t, f, dy=e)
    pg = model.power(np.asarray(periods, dtype=float), list(durations))
    i = int(np.argmax(pg.power))
    return float(pg.period[i]), float(pg.power[i]), float(pg.duration[i]), \
        float(pg.transit_time[i])


def _numpy_bls_power(t, f, e, periods, durations, nbins=300):
    """Pure-numpy BLS fallback. Returns (best_period, best_sr, dur, t0)."""
    w = 1.0 / (e ** 2)
    w = w / w.sum()
    fm = f - np.sum(w * f)
    wf = w * fm
    nbins = int(nbins)
    best_sr = -np.inf
    best_P = float(periods[0])
    best_dur = float(durations[0])
    best_t0 = float(t[0])
    starts = np.arange(nbins)
    for P in periods:
        phase = (t % P) / P
        idx = np.floor(phase * nbins).astype(np.int64)
        np.clip(idx, 0, nbins - 1, out=idx)
        s = np.bincount(idx, weights=wf, minlength=nbins)
        r = np.bincount(idx, weights=w, minlength=nbins)
        cs = np.concatenate([[0.0], np.cumsum(np.concatenate([s, s]))])
        cr = np.concatenate([[0.0], np.cumsum(np.concatenate([r, r]))])
        for dur in durations:
            width = max(1, int(round((dur / P) * nbins)))
            if width >= nbins:
                continue
            S = cs[starts + width] - cs[starts]
            R = cr[starts + width] - cr[starts]
            denom = R * (1.0 - R)
            valid = denom > 1e-12
            if not np.any(valid):
                continue
            sr = (S[valid] ** 2) / denom[valid]
            k = int(np.argmax(sr))
            m = float(sr[valid][k])
            if m > best_sr:
                best_sr = m
                best_P = float(P)
                best_dur = float(dur)
                sidx = starts[valid][k]
                best_t0 = float(t.min() + ((sidx + width / 2.0) / nbins) * P)
    return best_P, best_sr, best_dur, best_t0


def bls_power(t, f, e, periods, durations):
    """Dispatch to astropy BLS when available else the numpy fallback.

    Returns (best_period, best_stat, best_duration, best_t0). The statistic is
    astropy's BLS "power" or the numpy SR; only comparisons within one search
    are meaningful.
    """
    if _have_astropy():
        return _astropy_bls_power(t, f, e, periods, durations)
    return _numpy_bls_power(t, f, e, periods, durations)


def bls_search(t, f, e, period_min, period_max, n_freq, durations):
    """Frequency-uniform coarse BLS search over [period_min, period_max]."""
    fmin = 1.0 / period_max
    fmax = 1.0 / period_min
    freqs = np.linspace(fmin, fmax, int(n_freq))
    periods = 1.0 / freqs
    P, stat, dur, t0 = bls_power(t, f, e, periods, durations)
    return P, stat, dur, t0


def refine_period(t, f, e, P0, durations, n_grid=100000, frac=0.004):
    """Dense LOCAL period grid around P0 at full numerical precision.

    The step must resolve the true peak: with ~N transits over a baseline B the
    peak width in period is ~ P0^2 / B, so n_grid is chosen large and frac small
    enough that the step << peak width. Rounding happens only at output time.
    """
    lo = P0 * (1.0 - frac)
    hi = P0 * (1.0 + frac)
    periods = np.linspace(lo, hi, int(n_grid))
    P, stat, dur, t0 = bls_power(t, f, e, periods, durations)
    return P, stat, dur, t0


def joint_transit_fit(t, f, e, P0, t0, dur, half=None, baseline_order=1):
    """Gold-standard period: a single simultaneous least-squares fit of ALL
    covered transits sharing one (t0, P, depth, width) with a per-transit local
    polynomial baseline, on the (raw) flux ``f``.

    Fitting a shared ephemeris to the transit shapes directly is unbiased by the
    box/detrend residual slopes that can shift a BLS peak by ~1e-3 d, and the
    per-transit local baseline absorbs the stellar variability without a global
    detrend distorting the transit timing. Returns a dict with the fitted period
    and its formal error, or None if scipy is unavailable or < 2 transits can be
    fit.

    Parameters mirror the BLS peak used only for initialisation: ``P0`` period,
    ``t0`` a transit time, ``dur`` transit duration (days).
    """
    try:
        from scipy.optimize import least_squares
    except Exception:
        return None
    dur = float(dur) if dur and dur > 0 else 0.05
    if half is None:
        half = max(0.15, 3.0 * dur)
    tmin, tmax = float(t.min()), float(t.max())
    # bring t0 near the data, then enumerate covered epochs with 2-sided coverage
    n_shift = round((0.5 * (tmin + tmax) - t0) / P0)
    t0 = t0 + n_shift * P0
    n_lo = int(np.floor((tmin - t0) / P0)) - 1
    n_hi = int(np.ceil((tmax - t0) / P0)) + 1
    segs = []
    for n in range(n_lo, n_hi + 1):
        tc = t0 + n * P0
        w = np.abs(t - tc) < half
        if w.sum() < 20:
            continue
        xs = t[w]
        # require samples on both sides so baseline+centre are constrained
        if np.sum(xs < tc - dur) < 5 or np.sum(xs > tc + dur) < 5:
            continue
        segs.append((n, t[w], f[w], e[w]))
    if len(segs) < 2:
        return None
    nb = int(baseline_order) + 1
    depth0 = max(1e-4, float(np.median(f) - np.min([s[2].min() for s in segs])))
    sig0 = max(dur / 2.355, 1e-3)

    def resid(p):
        t0_, P_, depth_, sig_ = p[:4]
        base = p[4:].reshape(len(segs), nb)
        r = []
        for i, (n, x, y, ee) in enumerate(segs):
            tc = t0_ + n * P_
            dx = x - tc
            bl = sum(base[i][k] * dx ** k for k in range(nb))
            m = bl - depth_ * np.exp(-0.5 * (dx / sig_) ** 2)
            r.append((y - m) / ee)
        return np.concatenate(r)

    p0 = [t0, P0, depth0, sig0] + ([float(np.median(f))] + [0.0] * (nb - 1)) * len(segs)
    try:
        sol = least_squares(resid, p0, method="lm", max_nfev=100000)
    except Exception:
        return None
    P = float(sol.x[1])
    try:
        J = sol.jac
        dof = max(1, len(sol.fun) - len(sol.x))
        chi2 = float(np.sum(sol.fun ** 2))
        cov = np.linalg.inv(J.T @ J) * (chi2 / dof)
        Perr = float(np.sqrt(np.diag(cov))[1])
        red_chi2 = chi2 / dof
    except Exception:
        Perr = float("nan")
        red_chi2 = float("nan")
    if not np.isfinite(P) or P <= 0:
        return None
    return {"period": P, "period_err": Perr, "n_transits": len(segs),
            "depth": float(sol.x[2]), "sigma": float(sol.x[3]),
            "red_chi2": red_chi2, "t0": float(sol.x[0])}


def fold_diagnostics(t, f, e, P):
    """Return event count, depth, duration estimate, odd/even depths."""
    baseline = t.max() - t.min()
    n_events = int(np.floor(baseline / P)) + 1 if P > 0 else 0
    phase = (t % P) / P
    nbins = 200
    idx = np.clip((phase * nbins).astype(int), 0, nbins - 1)
    w = 1.0 / e ** 2
    sumw = np.bincount(idx, weights=w, minlength=nbins)
    sumwf = np.bincount(idx, weights=w * f, minlength=nbins)
    binmean = np.where(sumw > 0, sumwf / np.maximum(sumw, 1e-30), np.nan)
    base = np.nanmedian(binmean)
    dip_bin = int(np.nanargmin(binmean))
    depth = float(base - binmean[dip_bin])
    duration = float(P / nbins)
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
