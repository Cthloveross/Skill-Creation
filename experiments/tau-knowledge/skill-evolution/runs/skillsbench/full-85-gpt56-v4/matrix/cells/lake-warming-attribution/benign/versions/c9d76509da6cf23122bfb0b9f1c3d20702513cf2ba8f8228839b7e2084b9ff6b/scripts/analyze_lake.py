#!/usr/bin/env python3
"""Create trend_result.csv and dominant_factor.csv from lake CSV inputs.

Input: JSON on stdin. Required/default keys: data_dir=/root/data,
output_dir=/root/output. Optional: files, time_key, category_overrides.
Output: JSON diagnostic summary on stdout; CSV artifacts are written to output_dir.
"""
import csv
import itertools
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

CATS = ("Heat", "Flow", "Wind", "Human")
DEFAULT_FILES = {
    "water_temperature": "water_temperature.csv",
    "climate": "climate.csv",
    "hydrology": "hydrology.csv",
    "land_cover": "land_cover.csv",
}


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def fail(message):
    raise ValueError(message)


def load_config():
    raw = sys.stdin.read().strip()
    cfg = json.loads(raw) if raw else {}
    if not isinstance(cfg, dict):
        fail("stdin must contain a JSON object")
    return cfg


def read_tables(cfg):
    base = Path(cfg.get("data_dir", "/root/data"))
    supplied = cfg.get("files", {})
    tables = {}
    for logical, default in DEFAULT_FILES.items():
        path = Path(supplied.get(logical, base / default))
        if not path.is_absolute():
            path = base / path
        if not path.exists():
            fail("missing required input file: " + str(path))
        frame = pd.read_csv(path)
        if frame.empty:
            fail("input table is empty: " + str(path))
        # Preserve provenance so equal driver names never silently overwrite.
        tables[logical] = frame
    return tables


def possible_time_columns(frame):
    found = []
    for col in frame.columns:
        n = norm(col)
        if any(x in n for x in ("date", "year", "month", "time", "period", "season")):
            found.append(col)
    return found


def choose_time_key(tables, requested=None):
    if requested:
        absent = [name for name, f in tables.items() if requested not in f.columns]
        if absent:
            fail("requested time_key is absent from: " + ", ".join(absent))
        return {name: requested for name in tables}
    # Exact normalized shared name is safest.
    maps = {name: {norm(c): c for c in f.columns} for name, f in tables.items()}
    common = set.intersection(*(set(m) for m in maps.values()))
    candidates = [x for x in common if any(k in x for k in ("date", "year", "month", "time", "period", "season"))]
    if not candidates:
        fail("no shared date/year/time-like column found; provide time_key explicitly")
    # Prefer date, then year, then a shorter normalized name for deterministic behavior.
    candidates.sort(key=lambda x: (0 if "date" in x else 1 if "year" in x else 2, len(x), x))
    return {name: maps[name][candidates[0]] for name in tables}


def canonical_time(series):
    """Return merge key and elapsed years suitable for a trend."""
    nonnull = series.dropna()
    if nonnull.empty:
        fail("temporal key contains no values")
    # Numeric years or numeric periods should remain numeric. Strings such as 2001-01 parse as dates.
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() >= max(2, int(0.8 * len(series))):
        key = numeric.astype(float)
        return key, key.astype(float)
    dates = pd.to_datetime(series, errors="coerce")
    if dates.notna().sum() < max(2, int(0.8 * len(series))):
        fail("could not parse temporal key as numeric or date")
    origin = dates.min()
    years = (dates - origin).dt.total_seconds() / (365.2425 * 86400.0)
    # Integer nanoseconds is an exact, stable join representation for parsed dates.
    key = dates.astype("int64").where(dates.notna(), np.nan).astype(float)
    return key, years


def response_column(frame, time_col):
    candidates = []
    for col in frame.columns:
        if col == time_col:
            continue
        numeric = pd.to_numeric(frame[col], errors="coerce")
        if numeric.notna().sum() == 0:
            continue
        n = norm(col)
        score = 0
        if "water" in n: score += 4
        if "lake" in n: score += 3
        if "temp" in n or "temperature" in n: score += 5
        if "surface" in n: score += 2
        candidates.append((score, col))
    if not candidates:
        fail("water_temperature.csv has no numeric response column")
    candidates.sort(key=lambda x: (-x[0], str(x[1])))
    if candidates[0][0] <= 0:
        fail("could not identify a water-temperature column; use a temperature-like column name")
    return candidates[0][1]


def aggregate_table(frame, time_col, response=None):
    key, years = canonical_time(frame[time_col])
    work = frame.copy()
    work["__join_time__"] = key
    work["__trend_years__"] = years
    work = work.dropna(subset=["__join_time__"])
    numeric_cols = [c for c in work.columns if c not in (time_col, "__join_time__", "__trend_years__")
                    and pd.to_numeric(work[c], errors="coerce").notna().any()]
    for c in numeric_cols:
        work[c] = pd.to_numeric(work[c], errors="coerce")
    # Mean is explicit handling for multiple measurements at the same temporal key.
    keep = ["__join_time__", "__trend_years__"] + numeric_cols
    return work[keep].groupby("__join_time__", as_index=False).mean(numeric_only=True), numeric_cols


def classify(column, source, overrides):
    if column in overrides:
        val = overrides[column]
        if val not in CATS:
            fail("override for %s is not one of %s" % (column, ", ".join(CATS)))
        return val
    n = norm(column)
    if any(x in n for x in ("wind", "gust", "u10", "v10")):
        return "Wind"
    if any(x in n for x in ("flow", "discharge", "inflow", "outflow", "runoff", "waterlevel", "stage", "precip", "rain")):
        return "Flow"
    if source == "land_cover" or any(x in n for x in ("urban", "human", "population", "road", "crop", "agri", "forest", "landuse", "landcover", "impervious")):
        return "Human"
    if source == "hydrology":
        return "Flow"
    # Remaining climate energy/atmospheric variables are assigned to the Heat pathway.
    return "Heat"


def r_squared(y, x):
    if x.shape[1] == 0:
        pred = np.repeat(float(np.mean(y)), len(y))
    else:
        design = np.column_stack((np.ones(len(y)), x))
        beta, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
        pred = design @ beta
    sst = float(np.sum((y - np.mean(y)) ** 2))
    if sst <= 0:
        fail("water temperature is constant after temporal alignment")
    return max(0.0, min(1.0, 1.0 - float(np.sum((y - pred) ** 2)) / sst))


def shapley_shares(y, predictors, cat_for_col):
    active = sorted(set(cat_for_col.values()), key=CATS.index)
    if len(active) < 2:
        fail("fewer than two nonconstant driver categories remain after cleaning")
    positions = {c: [i for i, col in enumerate(predictors.columns) if cat_for_col[col] == c] for c in active}
    values = {c: 0.0 for c in active}
    permutations = list(itertools.permutations(active))
    for order in permutations:
        included = []
        before = r_squared(y, predictors.iloc[:, included].to_numpy())
        for cat in order:
            included.extend(positions[cat])
            after = r_squared(y, predictors.iloc[:, included].to_numpy())
            values[cat] += after - before
            before = after
    for cat in values:
        values[cat] /= len(permutations)
    full = r_squared(y, predictors.to_numpy())
    if not np.isfinite(full) or full <= 1e-12:
        fail("driver model has zero explained variance; percentage contribution is undefined")
    shares = {c: max(0.0, values[c] / full * 100.0) for c in active}
    # Numerical rounding may make the total differ infinitesimally; normalize exactly.
    total = sum(shares.values())
    shares = {c: v * 100.0 / total for c, v in shares.items()}
    return full, shares


def main():
    cfg = load_config()
    tables = read_tables(cfg)
    keys = choose_time_key(tables, cfg.get("time_key"))
    response = response_column(tables["water_temperature"], keys["water_temperature"])
    aggregated = {}
    numeric = {}
    for source, frame in tables.items():
        aggregated[source], numeric[source] = aggregate_table(frame, keys[source])

    water = aggregated["water_temperature"]
    if response not in water.columns:
        fail("identified response was lost during numeric conversion")
    trend_data = water[["__trend_years__", response]].dropna()
    if len(trend_data) < 2 or trend_data["__trend_years__"].nunique() < 2:
        fail("need at least two distinct finite water-temperature times for trend analysis")
    lr = stats.linregress(trend_data["__trend_years__"].to_numpy(), trend_data[response].to_numpy())
    if not (np.isfinite(lr.slope) and np.isfinite(lr.pvalue)):
        fail("trend fit produced non-finite slope or p-value")

    merged = water[["__join_time__", response]].copy()
    predictor_categories = {}
    for source in ("climate", "hydrology", "land_cover"):
        part = aggregated[source][["__join_time__"] + numeric[source]].copy()
        rename = {}
        for c in numeric[source]:
            new = source + "__" + str(c)
            rename[c] = new
            predictor_categories[new] = classify(str(c), source, cfg.get("category_overrides", {}))
        part = part.rename(columns=rename)
        merged = merged.merge(part, on="__join_time__", how="inner", validate="one_to_one")
    if len(merged) < 3:
        fail("fewer than three records remain after temporal inner join")
    driver_cols = list(predictor_categories)
    x = merged[driver_cols].copy()
    y = pd.to_numeric(merged[response], errors="coerce")
    valid_y = y.notna() & np.isfinite(y)
    x, y = x.loc[valid_y], y.loc[valid_y].astype(float)
    retained, imputed, dropped = [], [], []
    for c in driver_cols:
        vals = pd.to_numeric(x[c], errors="coerce").replace([np.inf, -np.inf], np.nan)
        if vals.notna().sum() == 0 or vals.dropna().nunique() <= 1:
            dropped.append(c)
            continue
        if vals.isna().any():
            vals = vals.fillna(vals.median())
            imputed.append(c)
        x[c] = vals.astype(float)
        retained.append(c)
    x = x[retained]
    cats = {c: predictor_categories[c] for c in retained}
    if len(x) < 3:
        fail("fewer than three usable numeric driver variables remain")
    full_r2, shares = shapley_shares(y.to_numpy(), x, cats)
    winner = sorted(shares, key=lambda c: (-shares[c], CATS.index(c)))[0]
    contribution = float(shares[winner])

    out = Path(cfg.get("output_dir", "/root/output"))
    out.mkdir(parents=True, exist_ok=True)
    trend_path, dom_path = out / "trend_result.csv", out / "dominant_factor.csv"
    pd.DataFrame([{"slope": float(lr.slope), "p-value": float(lr.pvalue)}]).to_csv(trend_path, index=False)
    pd.DataFrame([{"variable": winner, "contribution": contribution}]).to_csv(dom_path, index=False)
    # Re-read to validate serialization as well as model calculations.
    for path, cols in ((trend_path, ["slope", "p-value"]), (dom_path, ["variable", "contribution"])):
        check = pd.read_csv(path)
        if list(check.columns) != cols or len(check) != 1:
            fail("output validation failed for " + str(path))
    check_trend = pd.read_csv(trend_path)
    check_dom = pd.read_csv(dom_path)
    if not np.isfinite(check_trend[["slope", "p-value"]].to_numpy(dtype=float)).all() or not np.isfinite(float(check_dom.loc[0, "contribution"])):
        fail("output validation found non-finite numeric values")
    if check_dom.loc[0, "variable"] not in CATS or not 0 <= float(check_dom.loc[0, "contribution"]) <= 100:
        fail("output validation found invalid dominant category or percentage")
    print(json.dumps({
        "trend_output": str(trend_path), "dominant_output": str(dom_path),
        "time_keys": keys, "response_column": response,
        "trend_observations": int(len(trend_data)), "joined_observations": int(len(merged)),
        "full_model_r_squared": full_r2, "category_contributions_percent": shares,
        "dropped_predictors": dropped, "median_imputed_predictors": imputed
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(2)
