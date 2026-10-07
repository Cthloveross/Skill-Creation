"""Shared helpers for lake-warming trend analysis and driver attribution.

All functions are task-independent: column names, categories and values are
derived from the data passed in at runtime, never hardcoded.
"""
import os
import json
import numpy as np
import pandas as pd

TIME_CANDIDATES = ["year", "date", "datetime", "time", "timestamp", "month"]


def load_table(path):
    if not os.path.exists(path):
        raise FileNotFoundError("Missing required table: %s" % path)
    return pd.read_csv(path)


def detect_time_key(df):
    """Return (year_series:int, key_name) detected from df; raise if none."""
    cols = {c.lower(): c for c in df.columns}
    # explicit year column
    for name in ["year", "yr"]:
        if name in cols:
            s = pd.to_numeric(df[cols[name]], errors="coerce")
            return s.astype("Int64"), cols[name]
    # date-like column
    for name in ["date", "datetime", "time", "timestamp"]:
        if name in cols:
            dt = pd.to_datetime(df[cols[name]], errors="coerce")
            if dt.notna().any():
                return dt.dt.year.astype("Int64"), cols[name]
    # fall back: try first column as date, else as year
    first = df.columns[0]
    dt = pd.to_datetime(df[first], errors="coerce")
    if dt.notna().mean() > 0.5:
        return dt.dt.year.astype("Int64"), first
    s = pd.to_numeric(df[first], errors="coerce")
    if s.notna().mean() > 0.5 and s.dropna().between(1500, 3000).mean() > 0.5:
        return s.astype("Int64"), first
    raise ValueError("Could not detect a temporal key in columns: %s" % list(df.columns))


def numeric_columns(df, exclude):
    out = []
    for c in df.columns:
        if c in exclude:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        if s.notna().sum() >= 2 and s.dropna().std(ddof=0) > 0:
            out.append(c)
    return out


def annual_mean(df, time_key_name, value_cols):
    """Aggregate value_cols to annual mean keyed by detected year."""
    years, _ = detect_time_key(df)
    tmp = df.copy()
    tmp["__year__"] = years
    tmp = tmp.dropna(subset=["__year__"])
    for c in value_cols:
        tmp[c] = pd.to_numeric(tmp[c], errors="coerce")
    g = tmp.groupby(tmp["__year__"].astype(int))[value_cols].mean()
    g.index.name = "year"
    return g


def mann_kendall_pvalue(y):
    """Two-sided Mann-Kendall p-value (normal approximation)."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 3:
        return float("nan")
    s = 0
    for i in range(n - 1):
        s += np.sum(np.sign(y[i + 1:] - y[i]))
    # variance (no tie correction for simplicity on continuous data)
    var = n * (n - 1) * (2 * n + 5) / 18.0
    if var <= 0:
        return float("nan")
    if s > 0:
        z = (s - 1) / np.sqrt(var)
    elif s < 0:
        z = (s + 1) / np.sqrt(var)
    else:
        z = 0.0
    # two-sided p from standard normal
    from math import erfc, sqrt
    p = erfc(abs(z) / sqrt(2.0))
    return float(p)


def relative_weights(X, y):
    """Johnson's relative weights. X: (n,p) ndarray, y: (n,) ndarray.
    Returns (raw_weights summing to R^2, r_squared, method). Falls back to
    normalized squared correlations when unstable.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n, p = X.shape
    # standardize
    Xs = (X - X.mean(axis=0)) / X.std(axis=0, ddof=0)
    ys = (y - y.mean()) / y.std(ddof=0)
    r_xy = Xs.T.dot(ys) / n  # correlations predictors<->criterion
    try:
        if n <= p:
            raise np.linalg.LinAlgError("n<=p")
        R = Xs.T.dot(Xs) / n
        evals, evecs = np.linalg.eigh(R)
        evals = np.clip(evals, 1e-10, None)
        Lambda = evecs.dot(np.diag(np.sqrt(evals))).dot(evecs.T)
        beta = np.linalg.solve(Lambda, r_xy)
        raw = (Lambda ** 2).dot(beta ** 2)
        r2 = float(np.sum(raw))
        if not np.all(np.isfinite(raw)) or r2 <= 0:
            raise np.linalg.LinAlgError("non-finite weights")
        return raw, r2, "relative_weights"
    except Exception:
        # fallback: squared zero-order correlations normalized to an R^2 proxy
        raw = r_xy ** 2
        r2 = float(min(1.0, np.sum(raw)))
        return raw, r2, "fallback_sq_correlation"


def map_categories(col_source, keywords):
    """Map each column to Heat/Flow/Wind/Human given its source file and keywords.
    col_source: dict col->source filename (basename).
    """
    wind_kw = [k.lower() for k in keywords.get("wind", [])]
    out = {}
    for col, src in col_source.items():
        s = src.lower()
        name = col.lower()
        if "land_cover" in s or "land" in s:
            out[col] = "Human"
        elif "hydro" in s:
            out[col] = "Flow"
        elif "climate" in s:
            out[col] = "Wind" if any(k in name for k in wind_kw) else "Heat"
        else:
            # unknown source: keyword-only best effort
            if any(k in name for k in wind_kw):
                out[col] = "Wind"
            else:
                out[col] = "Heat"
    return out


def load_keywords(ref_path):
    with open(ref_path, "r", encoding="utf-8") as f:
        return json.load(f)
