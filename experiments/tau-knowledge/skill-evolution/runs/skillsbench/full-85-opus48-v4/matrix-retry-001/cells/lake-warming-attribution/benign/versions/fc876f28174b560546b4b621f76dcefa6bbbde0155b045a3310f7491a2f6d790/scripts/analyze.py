#!/usr/bin/env python3
"""End-to-end lake warming trend + driver attribution.

Reads optional JSON config on stdin; writes trend_result.csv and
dominant_factor.csv; prints a JSON summary on stdout.

Stdin config (all optional):
  data_dir       default /root/data
  output_dir     default /root/output
  target_table   default water_temperature.csv
  answer_level   "category" (default) or "variable"
  category_map   {column_name: Heat|Flow|Wind|Human}
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
import lib_lake as L


def main():
    raw = sys.stdin.read().strip()
    cfg = json.loads(raw) if raw else {}
    data_dir = cfg.get("data_dir", "/root/data")
    output_dir = cfg.get("output_dir", "/root/output")
    target_table = cfg.get("target_table", "water_temperature.csv")
    answer_level = cfg.get("answer_level", "category")
    override = cfg.get("category_map", {}) or {}

    os.makedirs(output_dir, exist_ok=True)

    tgt_path = os.path.join(data_dir, target_table)
    if not os.path.exists(tgt_path):
        return _err(f"target table not found: {tgt_path}")
    tdf = pd.read_csv(tgt_path)
    tgt_annual, _ = L.annual_frame(tdf)
    # target series: annual mean of the temperature column(s)
    tdf_y, ok = L.add_year(tdf)
    if not ok:
        return _err("could not detect a temporal key in the target table")
    tseries = L.select_target(tdf_y)
    if tseries is None:
        return _err("no numeric temperature column found in target table")
    tframe = pd.DataFrame({"year": tdf_y["year"], "target": tseries})
    tframe = tframe.dropna()
    tframe["year"] = tframe["year"].astype(int)
    tannual = tframe.groupby("year")["target"].mean().reset_index()

    # temperature units (best effort from column name)
    temp_units = "deg C per year"

    # ----- Trend -----
    try:
        slope, pval, n_years = L.linear_trend(tannual["year"], tannual["target"])
    except Exception as e:
        return _err(f"trend computation failed: {e}")

    trend_df = pd.DataFrame({"slope": [slope], "p-value": [pval]})
    trend_out = os.path.join(output_dir, "trend_result.csv")
    trend_df.to_csv(trend_out, index=False)

    # ----- Predictors / attribution -----
    predictor_tables = []
    for fn in sorted(os.listdir(data_dir)):
        if not fn.lower().endswith(".csv"):
            continue
        if fn == target_table:
            continue
        predictor_tables.append(fn)

    merged = tannual.copy()
    pred_cols = []
    for fn in predictor_tables:
        try:
            df = pd.read_csv(os.path.join(data_dir, fn))
        except Exception:
            continue
        ann, vals = L.annual_frame(df)
        if ann is None or not vals:
            continue
        # avoid name clashes with existing columns
        rename = {}
        for v in vals:
            name = v
            if name in merged.columns or name == "target":
                name = f"{os.path.splitext(fn)[0]}__{v}"
            rename[v] = name
        ann = ann.rename(columns=rename)
        use_cols = [rename[v] for v in vals]
        merged = merged.merge(ann[["year"] + use_cols], on="year", how="inner")
        pred_cols.extend(use_cols)

    result = {
        "status": "ok",
        "trend": {"slope": slope, "p_value": pval, "n_years": n_years,
                   "temp_units": temp_units},
        "outputs": {"trend_result": trend_out},
    }

    if not pred_cols:
        return _err("no usable predictor columns found for attribution",
                    partial=result)

    model_df = merged[["target"] + pred_cols].dropna()
    # drop constant predictors (no variance -> no contribution, cause issues)
    keep = [c for c in pred_cols if model_df[c].nunique() > 1]
    dropped = [c for c in pred_cols if c not in keep]
    pred_cols = keep
    if len(model_df) < max(4, len(pred_cols) + 2) or not pred_cols:
        return _err(
            f"insufficient merged rows ({len(model_df)}) or predictors "
            f"({len(pred_cols)}) for attribution", partial=result)

    X = model_df[pred_cols].to_numpy(dtype=float)
    y = model_df["target"].to_numpy(dtype=float)
    lmg, full_r2 = L.lmg_importance(X, y)
    pct = L.contributions_percent(lmg)
    var_contrib = {c: float(round(p, 6)) for c, p in zip(pred_cols, pct)}

    cat_map = {c: L.categorize(c, override) for c in pred_cols}
    cat_contrib = {}
    for c, p in zip(pred_cols, pct):
        cat = cat_map[c]
        cat_contrib[cat] = cat_contrib.get(cat, 0.0) + float(p)
    cat_contrib = {k: float(round(v, 6)) for k, v in cat_contrib.items()}

    # dominant among the four requested categories only
    known = {k: cat_contrib.get(k, 0.0) for k in L.KNOWN_CATEGORIES}
    dom_cat = max(known, key=known.get)

    if answer_level == "variable":
        top_var = max(var_contrib, key=var_contrib.get)
        dom_variable = top_var
        dom_contrib = var_contrib[top_var]
    else:
        dom_variable = dom_cat
        dom_contrib = round(known[dom_cat], 6)

    dom_df = pd.DataFrame({"variable": [dom_variable],
                           "contribution": [dom_contrib]})
    dom_out = os.path.join(output_dir, "dominant_factor.csv")
    dom_df.to_csv(dom_out, index=False)

    result.update({
        "model_r2": float(round(full_r2, 6)),
        "variable_contrib": var_contrib,
        "category_contrib": cat_contrib,
        "category_map": cat_map,
        "dropped_constant": dropped,
        "n_merged_rows": int(len(model_df)),
        "dominant": {"variable": dom_variable,
                      "contribution": dom_contrib,
                      "answer_level": answer_level},
    })
    result["outputs"]["dominant_factor"] = dom_out
    print(json.dumps(result))
    return 0


def _err(msg, partial=None):
    out = {"status": "error", "message": msg}
    if partial:
        out["partial"] = partial
    print(json.dumps(out))
    return 1


if __name__ == "__main__":
    sys.exit(main())
