#!/usr/bin/env python3
"""End-to-end pipeline for the trend-anomaly + causal (DiD) task.

Stdin  : optional JSON {"survey_path","purchases_path","output_dir"} (all optional).
Stdout : JSON summary {"status":"ok"|"error", ...}.

Writes the 7 required artifacts under output_dir (default /app/output).
All analytical values come from the current cleaned data; nothing is hard-coded
from any prior dataset.
"""
import sys
import json
import itertools

import os
for _v in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS","VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "4")
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers as H  # noqa: E402

BASELINE_START = pd.Timestamp("2020-01-01")
BASELINE_END = pd.Timestamp("2020-02-29")
TREAT_START = pd.Timestamp("2020-03-01")
TREAT_END = pd.Timestamp("2020-03-31")
SPLIT_DATE = TREAT_START  # training uses days strictly before this


def _load_cfg():
    try:
        raw = sys.stdin.read().strip()
        cfg = json.loads(raw) if raw else {}
    except Exception:
        cfg = {}
    cfg.setdefault("survey_path", "/app/data/survey_dirty.csv")
    cfg.setdefault("purchases_path", "/app/data/amazon-purchases-2019-2020_dirty.csv")
    cfg.setdefault("output_dir", "/app/output")
    return cfg


def clean_purchases(path):
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    df.columns = [c.strip() for c in df.columns]
    date_c = H.find_col(df, "date")
    price_c = H.find_col(df, "price")
    qty_c = H.find_col(df, "quantity") or H.find_col(df, "qty")
    cat_c = H.find_col(df, "category")
    id_c = H.find_col(df, "response")
    missing = [n for n, c in [("date", date_c), ("price", price_c),
                              ("quantity", qty_c), ("category", cat_c),
                              ("responseid", id_c)] if c is None]
    if missing:
        raise ValueError(f"purchases: cannot locate columns for {missing}")
    # trim strings
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    df[date_c] = pd.to_datetime(df[date_c], errors="coerce")
    df[price_c] = H.to_numeric_money(df[price_c])
    df[qty_c] = pd.to_numeric(df[qty_c].astype(str).str.replace(r"[^0-9.\-]", "", regex=True),
                              errors="coerce")
    df[cat_c] = H.normalize_text(df[cat_c]).str.upper()
    df[id_c] = H.normalize_text(df[id_c])
    df = df.drop_duplicates()
    df = df.dropna(subset=[date_c, price_c, qty_c, cat_c, id_c])
    df = df[(df[price_c] > 0) & (df[qty_c] > 0)]
    df["__line_total"] = df[price_c] * df[qty_c]
    df = df.rename(columns={date_c: "__date", cat_c: "__category", id_c: "__rid"})
    return df, {"id": "__rid", "date": "__date", "category": "__category",
               "total": "__line_total", "orig_cols": [date_c, price_c, qty_c, cat_c, id_c]}


def clean_survey(path):
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    df.columns = [c.strip() for c in df.columns]
    id_c = H.find_col(df, "response")
    if id_c is None:
        raise ValueError("survey: cannot locate Survey ResponseID column")
    for c in df.columns:
        df[c] = H.normalize_text(df[c])
    df = df.drop_duplicates()
    df = df.dropna(subset=[id_c])
    df = df.drop_duplicates(subset=[id_c], keep="first")
    return df, id_c


def compute_anomaly(purch, cols):
    df = purch[[cols["date"], cols["category"], cols["total"]]].copy()
    daily = (df.groupby([cols["category"], df[cols["date"]].dt.normalize()])[cols["total"]]
               .sum().reset_index())
    daily.columns = ["Category", "date", "spend"]
    full_start = daily["date"].min()
    full_end = max(daily["date"].max(), TREAT_END)
    full_index = pd.date_range(full_start, full_end, freq="D")
    rows = []
    for cat, g in daily.groupby("Category"):
        s = g.set_index("date")["spend"].reindex(full_index, fill_value=0.0)
        res = H.category_anomaly_index(s, SPLIT_DATE, TREAT_START, TREAT_END)
        if res is None:
            rows.append({"Category": cat, "Anomaly_Index": 0.0, "__q": False})
        else:
            rows.append({"Category": cat, "Anomaly_Index": res["index"],
                         "__q": res["qualifies"]})
    adf = pd.DataFrame(rows).sort_values("Anomaly_Index", ascending=False).reset_index(drop=True)
    return adf


def select_top(adf, k=10):
    q = adf[adf["__q"]].copy()
    surge = q.sort_values("Anomaly_Index", ascending=False).head(k)
    slump = q.sort_values("Anomaly_Index", ascending=True).head(k)
    return surge, slump


def engineer_features(survey, id_c, max_levels=25):
    df = survey.copy()
    out = pd.DataFrame({"Survey ResponseID": df[id_c].values})
    feat_cols = []
    _used = set()
    def _uniq(name):
        if name not in _used:
            _used.add(name)
            return name
        i = 1
        while f"{name}_dup{i}" in _used:
            i += 1
        nm = f"{name}_dup{i}"
        _used.add(nm)
        return nm
    for c in df.columns:
        if c == id_c:
            continue
        col = df[c]
        num = pd.to_numeric(col, errors="coerce")
        # treat as numeric only if most non-null values parse as numbers
        nonnull = col.notna().sum()
        if nonnull > 0 and num.notna().sum() >= 0.8 * nonnull:
            vals = num.astype(float)
            mu, sd = vals.mean(), vals.std(ddof=0)
            z = (vals - mu) / sd if sd and sd > 0 else vals * 0.0
            name = _uniq(f"ENG_{_safe(c)}")
            out[name] = z.fillna(0.0).values
            feat_cols.append(name)
        else:
            filled = col.fillna("Missing")
            vc = filled.value_counts()
            # Group sparse/invalid categorical levels (e.g. data-entry errors that
            # appear only a handful of times) into a single "Other" bucket so they
            # do not become near-constant one-hot columns that destabilise the DiD.
            n_rows = len(filled)
            min_count = max(10, int(round(0.002 * n_rows)))
            common = [lv for lv in vc.index if vc[lv] >= min_count]
            if len(common) > max_levels:
                common = common[:max_levels]
            common_set = set(common)
            has_rare = bool((~filled.isin(common_set)).any())
            for lv in common:
                name = _uniq(f"ENG_{_safe(c)}__{_safe(str(lv))}")
                out[name] = (filled == lv).astype(int).values
                feat_cols.append(name)
            if has_rare:
                name = _uniq(f"ENG_{_safe(c)}__Other")
                out[name] = (~filled.isin(common_set)).astype(int).values
                feat_cols.append(name)
    # drop zero-variance features globally
    keep = ["Survey ResponseID"]
    for fc in feat_cols:
        if out[fc].nunique() > 1:
            keep.append(fc)
    out = out[keep]
    feat_cols = [c for c in keep if c != "Survey ResponseID"]
    return out, feat_cols


def _safe(s):
    return "".join(ch if (ch.isalnum() or ch in "-") else "_" for ch in str(s))[:60]


def build_panels(purch, cols, top_cats, universe):
    df = purch[[cols["id"], cols["date"], cols["category"], cols["total"]]].copy()
    df.columns = ["rid", "date", "Category", "total"]
    df = df[df["Category"].isin(top_cats) & df["rid"].isin(universe)]
    def period_of(d):
        if BASELINE_START <= d <= BASELINE_END:
            return "Baseline"
        if TREAT_START <= d <= TREAT_END:
            return "Treatment"
        return None
    df["Period"] = df["date"].apply(period_of)
    df = df.dropna(subset=["Period"])
    # intensive: purchasers only
    intensive = (df.groupby(["rid", "Category", "Period"])["total"].sum()
                   .reset_index().rename(columns={"rid": "Survey ResponseID",
                                                   "total": "Total_Spend"}))
    # extensive: full grid of universe x top_cats x periods
    periods = ["Baseline", "Treatment"]
    purchased = set(zip(df["rid"], df["Category"], df["Period"]))
    grid = pd.DataFrame(itertools.product(sorted(universe), sorted(top_cats), periods),
                        columns=["Survey ResponseID", "Category", "Period"])
    grid["Has_Purchase"] = [1 if (r, c, p) in purchased else 0
                            for r, c, p in zip(grid["Survey ResponseID"],
                                               grid["Category"], grid["Period"])]
    return intensive, grid


def did_for_category(cat, direction, intensive, extensive, feats, feat_cols, universe_n):
    pcode = {"Baseline": 0, "Treatment": 1}
    ci = intensive[intensive["Category"] == cat].copy()
    ce = extensive[extensive["Category"] == cat].copy()
    ci["Period"] = ci["Period"].map(pcode)
    ce["Period"] = ce["Period"].map(pcode)
    ci = ci.merge(feats, on="Survey ResponseID", how="left")
    ce = ce.merge(feats, on="Survey ResponseID", how="left")
    for fc in feat_cols:
        if fc in ci:
            ci[fc] = ci[fc].fillna(0.0)
        if fc in ce:
            ce[fc] = ce[fc].fillna(0.0)
    # descriptive stats
    b = ci[ci["Period"] == 0]["Total_Spend"]
    t = ci[ci["Period"] == 1]["Total_Spend"]
    n_pb = int((b > 0).sum() if len(b) else 0)
    n_pt = int((t > 0).sum() if len(t) else 0)
    stats = {
        "baseline_avg_spend": round(float(b.mean()), 2) if len(b) else 0.0,
        "treatment_avg_spend": round(float(t.mean()), 2) if len(t) else 0.0,
        "n_purchasers_baseline": n_pb,
        "n_purchasers_treatment": n_pt,
        "n_at_risk": int(universe_n),
        "baseline_purchase_rate": round(n_pb / universe_n, 4) if universe_n else 0.0,
        "treatment_purchase_rate": round(n_pt / universe_n, 4) if universe_n else 0.0,
    }
    # intensive: univariate DiD per feature
    intensive_results = []
    for fc in feat_cols:
        if fc not in ci:
            continue
        r = H.univariate_did(ci, fc)
        if r is not None:
            intensive_results.append({"feature": fc, "did_estimate": round(r[0], 4),
                                      "p_value": round(r[1], 4),
                                      "method": "Univariate DiD"})
    # extensive: multivariate heterogeneous DiD
    ext_map = H.multivariate_heterogeneous_did(ce, feat_cols)
    extensive_results = [{"feature": f, "did_estimate": round(v[0], 4),
                          "p_value": round(v[1], 4),
                          "method": "Multivariate Heterogeneous DiD"}
                         for f, v in ext_map.items()]
    asc = (direction == "slump")
    intensive_results.sort(key=lambda d: d["did_estimate"], reverse=not asc)
    extensive_results.sort(key=lambda d: d["did_estimate"], reverse=not asc)
    return stats, intensive_results[:3], extensive_results[:3]


def main():
    cfg = _load_cfg()
    out_dir = cfg["output_dir"]
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.exists(cfg["survey_path"]) or not os.path.exists(cfg["purchases_path"]):
        print(json.dumps({"status": "error",
                          "message": "input CSVs missing; run `python /tmp/download_data.py` first"}))
        return 1

    survey, sid = clean_survey(cfg["survey_path"])
    purch, cols = clean_purchases(cfg["purchases_path"])

    # 1 & 2: cleaned data (preserve original column names)
    survey_out = survey.rename(columns={sid: "Survey ResponseID"}) if sid != "Survey ResponseID" else survey.copy()
    survey_out.to_csv(os.path.join(out_dir, "survey_cleaned.csv"), index=False)
    orig = cols["orig_cols"]
    # reconstruct a tidy filtered purchases frame
    purch_out = purch.copy()
    purch_out = purch_out.rename(columns={cols["date"]: "Order Date",
                                          cols["category"]: "Category",
                                          cols["id"]: "Survey ResponseID",
                                          cols["total"]: "Line_Total"})
    purch_out.to_csv(os.path.join(out_dir, "amazon-purchases-2019-2020-filtered.csv"), index=False)

    # 3: anomaly index
    adf = compute_anomaly(purch, cols)
    adf[["Category", "Anomaly_Index"]].to_csv(
        os.path.join(out_dir, "category_anomaly_index.csv"), index=False)
    surge, slump = select_top(adf, 10)
    idx_lookup = dict(zip(adf["Category"], adf["Anomaly_Index"]))

    # 4: feature engineering
    feats, feat_cols = engineer_features(survey, sid)
    feats.to_csv(os.path.join(out_dir, "survey_feature_engineered.csv"), index=False)

    # universe = users in both survey & purchases
    survey_ids = set(survey[sid])
    purch_ids = set(purch[cols["id"]])
    universe = survey_ids & purch_ids
    universe_n = len(universe)

    top_cats = list(dict.fromkeys(list(surge["Category"]) + list(slump["Category"])))
    intensive, extensive = build_panels(purch, cols, set(top_cats), universe)
    intensive.to_csv(os.path.join(out_dir, "user_category_period_aggregated_intensive.csv"), index=False)
    extensive.to_csv(os.path.join(out_dir, "user_category_period_aggregated_extensive.csv"), index=False)

    # 7: causal report
    def build_block(frame, direction):
        blocks = []
        for cat in frame["Category"]:
            stats, inten, exten = did_for_category(
                cat, direction, intensive, extensive, feats, feat_cols, universe_n)
            entry = {"category": cat, "anomaly_index": float(idx_lookup.get(cat, 0.0))}
            entry.update(stats)
            entry["intensive_margin"] = inten
            entry["extensive_margin"] = exten
            blocks.append(entry)
        return blocks

    surge_blocks = build_block(surge, "surge")
    slump_blocks = build_block(slump, "slump")

    def count_drivers(blocks, key):
        return int(sum(len(b[key]) for b in blocks))

    report = {
        "metadata": {
            "baseline_start": BASELINE_START.strftime("%m-%d-%Y"),
            "baseline_end": BASELINE_END.strftime("%m-%d-%Y"),
            "treatment_start": TREAT_START.strftime("%m-%d-%Y"),
            "treatment_end": TREAT_END.strftime("%m-%d-%Y"),
            "total_features_analyzed": int(len(feat_cols)),
        },
        "surge_categories": surge_blocks,
        "slump_categories": slump_blocks,
        "summary": {
            "surge": {
                "total_categories": len(surge_blocks),
                "total_intensive_drivers": count_drivers(surge_blocks, "intensive_margin"),
                "total_extensive_drivers": count_drivers(surge_blocks, "extensive_margin"),
            },
            "slump": {
                "total_categories": len(slump_blocks),
                "total_intensive_drivers": count_drivers(slump_blocks, "intensive_margin"),
                "total_extensive_drivers": count_drivers(slump_blocks, "extensive_margin"),
            },
        },
    }
    with open(os.path.join(out_dir, "causal_analysis_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps({
        "status": "ok",
        "output_dir": out_dir,
        "n_categories": int(adf.shape[0]),
        "n_surge": len(surge_blocks),
        "n_slump": len(slump_blocks),
        "universe_n": universe_n,
        "total_features_analyzed": int(len(feat_cols)),
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # surface failures clearly
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)
