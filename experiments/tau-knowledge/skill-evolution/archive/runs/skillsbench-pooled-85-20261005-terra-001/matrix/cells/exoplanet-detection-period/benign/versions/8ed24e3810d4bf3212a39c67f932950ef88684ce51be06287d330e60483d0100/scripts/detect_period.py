#!/usr/bin/env python3
import json
import math
import os
import re
import sys
import numpy as np


def fail(message):
    raise ValueError(message)


def scale(x):
    x = np.asarray(x, float)
    m = float(np.median(x))
    s = 1.4826 * float(np.median(np.abs(x - m)))
    if not np.isfinite(s) or s <= 0:
        s = float(np.std(x))
    if not np.isfinite(s) or s <= 0:
        s = 1e-12
    return s


def rows(path):
    result = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            fields = re.split(r'[\s,;]+', line.strip())
            if len(fields) < 4:
                continue
            try:
                result.append([float(v.replace('D', 'E').replace('d', 'e'))
                               for v in fields[:4]])
            except ValueError:
                pass
    if not result:
        fail('no parseable four-column numerical rows were found')
    return np.asarray(result, float)


def med_smooth(x, half):
    out = np.empty_like(x)
    for i in range(len(x)):
        out[i] = np.median(x[max(0, i-half):min(len(x), i+half+1)])
    return out


def trend_for_segment(t, y, bin_days, window_days):
    if len(t) < 6 or t[-1] - t[0] < 2 * bin_days:
        return np.full(len(t), np.median(y))
    b = np.floor((t-t[0]) / bin_days).astype(int)
    _, first = np.unique(b, return_index=True)
    last = np.r_[first[1:], len(b)]
    c = np.empty(len(first))
    m = np.empty(len(first))
    for i, (lo, hi) in enumerate(zip(first, last)):
        c[i], m[i] = np.median(t[lo:hi]), np.median(y[lo:hi])
    half = max(1, int(round(window_days / bin_days)) // 2)
    return np.interp(t, c, med_smooth(m, half), left=m[0], right=m[-1])


def detrend(t, y, cadence, bin_days, window_days):
    if bin_days <= 0 or window_days <= 0:
        fail('trend_bin_days and trend_window_days must be positive')
    cuts = np.flatnonzero(np.diff(t) > max(0.45, 15 * cadence)) + 1
    starts, stops = np.r_[0, cuts], np.r_[cuts, len(t)]
    tr = np.empty_like(y)
    for lo, hi in zip(starts, stops):
        tr[lo:hi] = trend_for_segment(t[lo:hi], y[lo:hi], bin_days, window_days)
    r = y - tr
    return r - np.median(r)


def compress(t, r, w, days):
    b = np.floor((t-t[0]) / days).astype(int)
    _, first = np.unique(b, return_index=True)
    last = np.r_[first[1:], len(b)]
    bt, br, bw = [], [], []
    for lo, hi in zip(first, last):
        q = w[lo:hi]
        z = float(q.sum())
        bt.append(float((t[lo:hi]*q).sum()/z))
        br.append(float((r[lo:hi]*q).sum()/z))
        bw.append(z)
    bw = np.asarray(bw)
    return np.asarray(bt), np.asarray(br), np.clip(bw/np.median(bw), .1, 10.)


def box(t, r, period, noise, weights=None, bins=220):
    phase = np.mod((t-t[0])/period, 1.)
    ind = np.minimum((phase*bins).astype(int), bins-1)
    if weights is None:
        sums = np.bincount(ind, weights=r, minlength=bins)
        counts = np.bincount(ind, minlength=bins).astype(float)
    else:
        sums = np.bincount(ind, weights=r*weights, minlength=bins)
        counts = np.bincount(ind, weights=weights, minlength=bins)
    ss, nn = np.r_[sums, sums], np.r_[counts, counts]
    cs, cn = np.r_[0., np.cumsum(ss)], np.r_[0., np.cumsum(nn)]
    best = (-np.inf, 0, 1)
    for width in range(1, 15):
        total = cs[width:width+bins] - cs[:bins]
        n = cn[width:width+bins] - cn[:bins]
        ok = n >= 8
        if np.any(ok):
            values = np.full(bins, -np.inf)
            values[ok] = -total[ok] / (noise*np.sqrt(n[ok]))
            j = int(np.argmax(values))
            if values[j] > best[0]:
                best = (float(values[j]), j, width)
    return best


def contrast_windows(t, r, noise, period, bins=320):
    phase = np.mod((t-t[0])/period, 1.)
    ind = np.minimum((phase*bins).astype(int), bins-1)
    sums = np.bincount(ind, weights=r, minlength=bins)
    counts = np.bincount(ind, minlength=bins).astype(float)
    total, nall = float(sums.sum()), float(counts.sum())
    cs = np.r_[0., np.cumsum(np.r_[sums, sums])]
    cn = np.r_[0., np.cumsum(np.r_[counts, counts])]
    best, widths = np.full(bins, -np.inf), np.zeros(bins, int)
    for width in range(2, 19):
        inside = cs[width:width+bins] - cs[:bins]
        n = cn[width:width+bins] - cn[:bins]
        outside = nall - n
        ok = (n >= 8) & (outside >= 20)
        val = np.full(bins, -np.inf)
        inn = inside[ok] / n[ok]
        out = (total-inside[ok]) / outside[ok]
        val[ok] = (out-inn) / (noise*np.sqrt(1/n[ok] + 1/outside[ok]))
        take = val > best
        best[take], widths[take] = val[take], width
    return best, widths


def is_two_cycle_alias(t, r, noise, period):
    scores, widths = contrast_windows(t, r, noise, period)
    primary = int(np.argmax(scores))
    first = float(scores[primary])
    width = int(widths[primary])
    if not np.isfinite(first) or width == 0:
        return False
    opposite = (primary + 160) % 320
    near = (opposite + np.arange(-max(3, width), max(3, width)+1)) % 320
    second = float(np.max(scores[near]))
    return second >= 4.0 and second >= .70 * first


def local(t, r, noise, center, baseline, fmin, fmax):
    lo, hi = max(fmin, center-2.5/baseline), min(fmax, center+2.5/baseline)
    if hi <= lo:
        return None
    grid = np.linspace(lo, hi, 241)
    scores = np.asarray([box(t, r, 1/f, noise)[0] for f in grid])
    mid = int(np.argmax(scores))
    step = grid[1]-grid[0]
    grid = np.linspace(max(fmin, grid[mid]-4*step), min(fmax, grid[mid]+4*step), 401)
    values = [box(t, r, 1/f, noise) for f in grid]
    k = int(np.argmax([v[0] for v in values]))
    return {'frequency': float(grid[k]), 'period': float(1/grid[k]),
            'score': float(values[k][0]), 'start': int(values[k][1]),
            'width': int(values[k][2])}


def detect(cfg):
    inp, out = cfg.get('input_path'), cfg.get('output_path')
    if not isinstance(inp, str) or not isinstance(out, str) or not inp or not out:
        fail('input_path and output_path are required strings')
    a = rows(inp)
    total = len(a)
    t, flux, quality, unc = a.T
    good = ((quality == 0) & np.isfinite(t) & np.isfinite(flux) &
            np.isfinite(unc) & (unc > 0))
    t, flux, unc = t[good], flux[good], unc[good]
    if len(t) < 50:
        fail('fewer than 50 finite quality-flag-zero cadences remain')
    order = np.argsort(t)
    t, flux, unc = t[order], flux[order], unc[order]
    med = float(np.median(flux))
    upper = scale(flux[flux >= med])
    keep = flux <= med + 8*upper
    t, flux, unc = t[keep], flux[keep], unc[keep]
    d = np.diff(t)
    d = d[d > 0]
    if len(t) < 50 or not len(d):
        fail('trusted data have insufficient distinct time coverage')
    cadence, baseline = float(np.median(d)), float(t[-1]-t[0])
    r = detrend(t, flux, cadence, float(cfg.get('trend_bin_days', .08)),
                float(cfg.get('trend_window_days', .88)))
    noise = scale(r)
    search_r = np.maximum(r, -12*noise)
    raww = 1/np.square(unc)
    w = np.clip(raww/np.median(raww), .1, 10.)
    bt, br, bw = compress(t, search_r, w, max(.003, 2*cadence))
    default_max = min(15., baseline/2.2)
    pmin = float(cfg.get('min_period', max(.5, 5*cadence)))
    pmax = float(cfg.get('max_period', default_max))
    if pmin <= 0 or pmax <= pmin or pmax > baseline/2 + 1e-12:
        fail('invalid period bounds')
    fmin, fmax = 1/pmax, 1/pmin
    nfreq = max(500, min(30000, int(math.ceil((fmax-fmin)*baseline*80))+1))
    freqs = np.linspace(fmin, fmax, nfreq)
    coarse = np.asarray([box(bt, br, 1/f, noise, bw)[0] for f in freqs])
    chosen = []
    for i in np.argsort(coarse)[::-1]:
        if all(abs(freqs[i]-freqs[j]) >= 2/baseline for j in chosen):
            chosen.append(int(i))
        if len(chosen) == 10:
            break
    candidates, centers = [], []
    for i in chosen:
        for factor in (1., .5, 2.):
            f = float(freqs[i]*factor)
            if fmin <= f <= fmax and all(abs(f-x) > 1e-9 for x in centers):
                centers.append(f)
                item = local(t, search_r, noise, f, baseline, fmin, fmax)
                if item is not None:
                    candidates.append(item)
    if not candidates:
        fail('the box search returned no finite candidates')
    best = max(candidates, key=lambda x: x['score'])
    if best['score'] < 5:
        fail('no significant repeated negative box-shaped signal was found')
    period = best['period']
    reductions = 0
    while period/2 >= pmin and reductions < 3 and is_two_cycle_alias(t, search_r, noise, period):
        period /= 2
        reductions += 1
    final_score, start, width = box(t, search_r, period, noise)
    if final_score < 5:
        fail('resolved orbital period has no significant box-shaped dimming')
    phase = np.mod((t-t[0])/period, 1.)
    lo, hi = start/220., (start+width)/220.
    inside = ((phase >= lo) & (phase < hi)) if hi <= 1 else ((phase >= lo) | (phase < hi-1))
    cycles = np.floor((t[inside]-t[0])/period).astype(int)
    ncycles = len(np.unique(cycles))
    if ncycles < 2:
        fail('selected box does not occupy at least two distinct orbital cycles')
    rendered = f'{period:.5f}\n'
    if not re.fullmatch(r'[0-9]+\.[0-9]{5}\n', rendered) or float(rendered) <= 0:
        fail('internal period formatting validation failed')
    parent = os.path.dirname(os.path.abspath(out))
    os.makedirs(parent, exist_ok=True)
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(rendered)
    return {'period_days': period, 'box_score': final_score,
            'n_transit_cycles': int(ncycles), 'factor_two_reductions': reductions,
            'total_rows': int(total), 'trusted_rows': int(len(t)),
            'coarse_binned_rows': int(len(bt)), 'baseline_days': baseline,
            'candidates_examined': len(candidates), 'output_path': out}


def main():
    try:
        cfg = json.load(sys.stdin)
        if not isinstance(cfg, dict):
            fail('stdin JSON must be an object')
        print(json.dumps(detect(cfg), sort_keys=True, allow_nan=False))
    except Exception as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(2)


if __name__ == '__main__':
    main()
