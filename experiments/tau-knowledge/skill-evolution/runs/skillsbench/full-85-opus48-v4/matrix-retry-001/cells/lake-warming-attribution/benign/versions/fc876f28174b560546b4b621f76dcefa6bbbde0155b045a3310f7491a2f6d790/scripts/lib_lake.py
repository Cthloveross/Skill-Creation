"""Reusable helpers for lake warming trend + driver attribution.

No instance-specific values are hardcoded. All quantities are derived from the
supplied CSVs at runtime.
"""
import os
import math
import itertools
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Category keyword rules (task-independent). Order matters: first match wins.
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS = [
    ("Wind", ["wind", "gust"]),
    ("Flow", ["inflow", "outflow", "discharge", "flow", "runoff", "precip",
              "rain", "river", "stage", "level", "hydro", "stream", "evap"]),
    ("Human", ["land", "urban", "agri", "crop", "forest", "pop", "built",
               "impervious", "developed", "lulc", "land_use", "vegetation",
               "pasture", "settlement", "human"]),
    ("Heat", ["temp", "solar", "radiation", "shortwave", "longwave",
              "sunshine", "insolation", "cloud", "heat", "rad", "air",
              "irradiance"]),
]
KNOWN_CATEGORIES = ["Heat", "Flow", "Wind", "Human"]

TIME_HINTS = ["date", "time", "year", "month", "day", "datetime", "timestamp"]


def categorize(name, override=None):
    """Map a column name to Heat/Flow/Wind/Human (or 'Other' if unmatched)."""
    if override and name in override:
        return override[name]
    n = str(name).lower()
    for cat, kws in CATEGORY_KEYWORDS:
        if any(k in n for k in kws):
            return cat
    return "Other"


def _is_time_col(col):
    c = str(col).lower()
    return any(h in c for h in TIME_HINTS)


def add_year(df):
    """Return (df_with_year, parsed) where df has an integer 'year' column.

    Detects a date-like column or a year column. Aligns by the actual temporal
    key, never by row position.
    """
    cols = list(df.columns)
    lower = {str(c).lower(): c for c in cols}

    # 1. explicit date/datetime/timestamp column
    for key in ["date", "datetime", "timestamp", "time"]:
        if key in lower:
            s = pd.to_datetime(df[lower[key]], errors="coerce")
            if s.notna().any():
                out = df.copy()
                out["year"] = s.dt.year
                return out, True

    # 2. explicit year column
    for c in cols:
        if str(c).lower() == "year":
            yr = pd.to_numeric(df[c], errors="coerce")
            if yr.notna().any():
                out = df.copy()
                out["year"] = yr.astype("Int64").astype("float").astype("Int64")
                return out, True

    # 3. any column containing 'year'
    for c in cols:
        if "year" in str(c).lower():
            yr = pd.to_numeric(df[c], errors="coerce")
            if yr.notna().any():
                out = df.copy()
                out["year"] = yr.astype("Int64")
                return out, True

    # 4. try parsing the first column as a date
    first = cols[0]
    s = pd.to_datetime(df[first], errors="coerce")
    if s.notna().mean() > 0.5:
        out = df.copy()
        out["year"] = s.dt.year
        return out, True

    return df.copy(), False


def numeric_value_cols(df):
    """Numeric columns that are not the time key / 'year'."""
    out = []
    for c in df.columns:
        if str(c).lower() == "year":
            continue
        if _is_time_col(c):
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            out.append(c)
        else:
            coerced = pd.to_numeric(df[c], errors="coerce")
            if coerced.notna().mean() > 0.5:
                df[c] = coerced
                out.append(c)
    return out


def annual_frame(df):
    """Aggregate numeric value columns to annual means keyed by year."""
    dfy, ok = add_year(df)
    if not ok:
        return None, []
    vals = numeric_value_cols(dfy)
    if not vals:
        return None, []
    g = dfy.groupby("year")[vals].mean().reset_index()
    g = g.dropna(subset=["year"])
    g["year"] = g["year"].astype(int)
    return g, vals


def select_target(df, prefer_keyword="temp"):
    """Pick the target temperature series: a column (prefer name containing
    'temp'); if several, average them."""
    vals = numeric_value_cols(df)
    if not vals:
        return None
    temp_like = [c for c in vals if prefer_keyword in str(c).lower()]
    use = temp_like if temp_like else vals
    if len(use) == 1:
        return df[use[0]]
    return df[use].mean(axis=1)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def linear_trend(years, values):
    """OLS slope (per year) and two-sided p-value via scipy.linregress."""
    from scipy import stats
    years = np.asarray(years, dtype=float)
    values = np.asarray(values, dtype=float)
    mask = np.isfinite(years) & np.isfinite(values)
    years, values = years[mask], values[mask]
    if len(years) < 3:
        raise ValueError("Not enough annual observations for a trend (need >=3)")
    res = stats.linregress(years, values)
    return float(res.slope), float(res.pvalue), int(len(years))


def _ols_r2(X, y):
    n = len(y)
    yc = y - y.mean()
    sst = float((yc ** 2).sum())
    if sst <= 0:
        return 0.0
    if X.shape[1] == 0:
        return 0.0
    A = np.column_stack([np.ones(n), X])
    beta, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ beta
    sse = float((resid ** 2).sum())
    return 1.0 - sse / sst


def lmg_importance(X, y, max_exact=8, n_perm=3000, seed=0):
    """Partition model R^2 among predictors (LMG / Shapley averaging of
    incremental R^2 over orderings). Returns (contribs, full_r2).
    contribs sum (approximately) to full_r2."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    p = X.shape[1]
    full_r2 = _ols_r2(X, y)
    if p == 0:
        return np.array([]), 0.0
    if p == 1:
        return np.array([full_r2]), full_r2
    lmg = np.zeros(p)
    if p <= max_exact:
        idx = list(range(p))
        for i in idx:
            others = [j for j in idx if j != i]
            for s in range(0, len(others) + 1):
                w = 1.0 / (p * math.comb(p - 1, s))
                for S in itertools.combinations(others, s):
                    cols = list(S)
                    r_wo = _ols_r2(X[:, cols], y) if cols else 0.0
                    r_w = _ols_r2(X[:, cols + [i]], y)
                    lmg[i] += w * (r_w - r_wo)
    else:
        rng = np.random.default_rng(seed)
        for _ in range(n_perm):
            perm = rng.permutation(p)
            cum = []
            r_prev = 0.0
            for i in perm:
                r_new = _ols_r2(X[:, cum + [int(i)]], y)
                lmg[int(i)] += (r_new - r_prev)
                cum.append(int(i))
                r_prev = r_new
        lmg /= n_perm
    return lmg, full_r2


def contributions_percent(lmg):
    """Normalize LMG shares to percent summing to 100 (clip negatives to 0)."""
    v = np.clip(np.asarray(lmg, dtype=float), 0.0, None)
    total = v.sum()
    if total <= 0:
        return np.zeros_like(v)
    return v / total * 100.0
