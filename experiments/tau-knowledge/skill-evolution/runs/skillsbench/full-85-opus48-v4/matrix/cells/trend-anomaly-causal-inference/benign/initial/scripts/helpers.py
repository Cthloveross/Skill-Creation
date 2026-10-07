"""Reusable helpers for the trend-anomaly / DiD pipeline.

All functions are task-independent: they operate on whatever columns/values the
current cleaned data provides. No instance-specific constants live here.
"""
import re
import math
import numpy as np
import pandas as pd

try:
    from scipy import stats as _sps  # type: ignore
    _HAVE_SCIPY = True
except Exception:  # pragma: no cover
    _HAVE_SCIPY = False


def find_col(df, *keywords):
    """Return the first column whose lowercased name contains all keywords."""
    low = {c: c.lower() for c in df.columns}
    for c in df.columns:
        name = low[c]
        if all(k.lower() in name for k in keywords):
            return c
    return None


def to_numeric_money(series):
    s = series.astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
    s = s.replace({"": np.nan, "-": np.nan, ".": np.nan})
    return pd.to_numeric(s, errors="coerce")


def normalize_text(series):
    s = series.astype(str).str.strip()
    s = s.str.replace(r"\s+", " ", regex=True)
    s = s.replace({"": np.nan, "nan": np.nan, "NaN": np.nan, "NA": np.nan,
                   "N/A": np.nan, "None": np.nan, "null": np.nan})
    return s


def t_sf_twosided(tval, dof):
    """Two-sided p-value for a t statistic."""
    if not np.isfinite(tval) or dof <= 0:
        return 1.0
    if _HAVE_SCIPY:
        return float(2.0 * _sps.t.sf(abs(tval), dof))
    # normal approximation
    z = abs(tval)
    p = math.erfc(z / math.sqrt(2.0))
    return float(min(1.0, max(0.0, p)))


def ols_fit(X, y):
    """OLS via pseudo-inverse. Returns (beta, pvals). Robust to singular X."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n, k = X.shape
    XtX = X.T @ X
    XtX_pinv = np.linalg.pinv(XtX)
    beta = XtX_pinv @ (X.T @ y)
    resid = y - X @ beta
    rank = np.linalg.matrix_rank(X)
    dof = max(n - rank, 1)
    sigma2 = float(resid @ resid) / dof
    cov = sigma2 * XtX_pinv
    se = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    pvals = np.ones(k)
    for i in range(k):
        if se[i] > 0 and np.isfinite(beta[i]):
            tval = beta[i] / se[i]
            pvals[i] = t_sf_twosided(tval, dof)
    return beta, pvals


def build_calendar_features(dates):
    """Design matrix: intercept, scaled time trend, dow dummies, month dummies."""
    dates = pd.DatetimeIndex(dates)
    t = (dates - dates.min()).days.astype(float)
    if t.max() > 0:
        t = t / t.max()
    dow = pd.get_dummies(dates.dayofweek, prefix="dow")
    # drop one level each to avoid perfect collinearity with intercept
    if dow.shape[1] > 1:
        dow = dow.iloc[:, 1:]
    month = pd.get_dummies(dates.month, prefix="m")
    if month.shape[1] > 1:
        month = month.iloc[:, 1:]
    X = np.column_stack([
        np.ones(len(dates)),
        t,
        dow.to_numpy(dtype=float) if dow.shape[1] else np.empty((len(dates), 0)),
        month.to_numpy(dtype=float) if month.shape[1] else np.empty((len(dates), 0)),
    ])
    return X


def category_anomaly_index(daily_spend, split_date, treat_start, treat_end,
                           min_pre_nonzero=5):
    """Compute a bounded [-100,100] anomaly index for one category.

    daily_spend: pd.Series indexed by daily DatetimeIndex (missing days filled 0).
    split_date : first treatment day (training uses dates strictly before it).
    Returns dict with index + diagnostics, or None if insufficient history.
    """
    s = daily_spend.sort_index()
    dates = s.index
    pre_mask = dates < split_date
    march_mask = (dates >= treat_start) & (dates <= treat_end)
    if pre_mask.sum() < 10 or march_mask.sum() == 0:
        return None
    pre_nonzero = int((s[pre_mask] > 0).sum())
    X = build_calendar_features(dates)
    y = s.to_numpy(dtype=float)
    Xpre, ypre = X[pre_mask.values if hasattr(pre_mask, 'values') else pre_mask], y[pre_mask]
    try:
        beta, _ = ols_fit(Xpre, ypre)
        pred = X @ beta
    except Exception:
        pred = np.full(len(y), np.nanmean(ypre))
    resid_pre = ypre - pred[pre_mask]
    sigma = float(np.std(resid_pre, ddof=1)) if len(resid_pre) > 1 else 0.0
    march_resid_mean = float(np.mean(y[march_mask] - pred[march_mask]))
    if sigma > 0:
        z = march_resid_mean / sigma
        idx = 100.0 * math.tanh(z)
    else:
        idx = 100.0 if march_resid_mean > 0 else (-100.0 if march_resid_mean < 0 else 0.0)
    idx = float(max(-100.0, min(100.0, idx)))
    return {
        "index": round(idx, 2),
        "pre_nonzero": pre_nonzero,
        "qualifies": pre_nonzero >= min_pre_nonzero,
    }


def univariate_did(df, feature_col, outcome_col="Total_Spend", period_col="Period"):
    """Univariate DiD: outcome ~ 1 + Period + Feature + Period*Feature.

    Returns (did_estimate, p_value) for the interaction, or None if invalid.
    """
    sub = df[[outcome_col, period_col, feature_col]].dropna()
    if sub.shape[0] < 8:
        return None
    P = sub[period_col].to_numpy(dtype=float)
    F = sub[feature_col].to_numpy(dtype=float)
    if np.std(P) == 0 or np.std(F) == 0:
        return None
    y = sub[outcome_col].to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(y)), P, F, P * F])
    beta, pvals = ols_fit(X, y)
    did = beta[3]
    if not np.isfinite(did):
        return None
    return float(did), float(pvals[3])


def multivariate_heterogeneous_did(df, feature_cols, outcome_col="Has_Purchase",
                                   period_col="Period"):
    """Multivariate heterogeneous DiD (linear probability model).

    outcome ~ 1 + Period + sum(Feature_i) + sum(Period*Feature_i).
    Returns dict feature -> (did_estimate, p_value) for finite interactions.
    """
    cols = [c for c in feature_cols if c in df.columns]
    sub = df[[outcome_col, period_col] + cols].dropna()
    if sub.shape[0] < max(10, 2 + 2 * 1):
        return {}
    P = sub[period_col].to_numpy(dtype=float)
    if np.std(P) == 0:
        return {}
    # keep features with within-subset variance
    use = [c for c in cols if np.std(sub[c].to_numpy(dtype=float)) > 0]
    if not use:
        return {}
    Fmat = sub[use].to_numpy(dtype=float)
    inter = Fmat * P[:, None]
    X = np.column_stack([np.ones(len(P)), P, Fmat, inter])
    y = sub[outcome_col].to_numpy(dtype=float)
    beta, pvals = ols_fit(X, y)
    base = 2 + len(use)  # start index of interaction block
    out = {}
    for i, c in enumerate(use):
        did = beta[base + i]
        if np.isfinite(did):
            out[c] = (float(did), float(pvals[base + i]))
    return out
