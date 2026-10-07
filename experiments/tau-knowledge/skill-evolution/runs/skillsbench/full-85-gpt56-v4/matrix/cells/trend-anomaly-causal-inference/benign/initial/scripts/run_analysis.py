#!/usr/bin/env python3
"""JSON-stdin entrypoint for robust e-commerce anomaly and DiD analysis."""
import sys, os, json, re, math, shutil
from pathlib import Path
import numpy as np
import pandas as pd

ID_OUT = "Survey ResponseID"
REQ_INT = [ID_OUT, "Category", "Period", "Total_Spend"]
REQ_EXT = [ID_OUT, "Category", "Period", "Has_Purchase"]

def norm_label(x):
    return re.sub(r"[^a-z0-9]+", "", str(x).strip().lower())

def choose_col(columns, exact, contains=(), avoid=()):
    pairs = [(c, norm_label(c)) for c in columns]
    for wanted in exact:
        for c, n in pairs:
            if n == wanted: return c
    for token in contains:
        for c, n in pairs:
            if token in n and not any(a in n for a in avoid): return c
    return None

def read_csv(path):
    errors = []
    for enc in ("utf-8-sig", "utf-8", "latin1"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=object, on_bad_lines="skip")
        except Exception as exc: errors.append(str(exc))
    raise ValueError("Could not read CSV %s: %s" % (path, errors[-1]))

def clean_text(s):
    s = s.astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    return s.mask(s.str.lower().isin(["", "nan", "none", "null", "na", "n/a", "np", "unknown"]))

def parse_amount(s):
    z = clean_text(s).str.replace(r"[,$£€]", "", regex=True)
    # Parentheses convention for negative amounts.
    z = z.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    return pd.to_numeric(z, errors="coerce")

def canonical_category(s):
    raw = clean_text(s)
    key = raw.str.casefold()
    # preserve the most frequent observed spelling while merging whitespace/case variants
    counts = key.value_counts(dropna=True)
    mapping = {}
    for k in counts.index:
        variants = raw[key == k].dropna()
        mapping[k] = variants.value_counts().index[0]
    return key.map(mapping)

def normal_p(z):
    if not np.isfinite(z): return 1.0
    return float(max(0.0, min(1.0, math.erfc(abs(float(z)) / math.sqrt(2.0)))))

def find_schema(survey, purchases):
    sid = choose_col(survey.columns, ["surveyresponseid", "responseid", "respondentid", "customerid", "userid"],
                     ["responseid", "respondentid", "customerid", "userid"])
    pid = choose_col(purchases.columns, [norm_label(sid)] if sid else [],
                     ["surveyresponseid", "responseid", "respondentid", "customerid", "userid", "memberid"])
    date = choose_col(purchases.columns, ["purchasedate", "orderdate", "transactiondate", "date"],
                      ["purchasedate", "orderdate", "transactiondate", "timestamp", "date"])
    cat = choose_col(purchases.columns, ["category", "productcategory", "itemcategory", "producttype"],
                     ["category", "producttype", "department"])
    amount = choose_col(purchases.columns, ["amount", "purchaseamount", "totalspend", "sales", "price", "orderamount", "spend"],
                        ["amount", "spend", "sales", "revenue", "price", "total"] , avoid=("quantity", "count", "discount"))
    missing = [name for name, val in [("survey identifier", sid), ("purchase identifier", pid), ("purchase date", date), ("category", cat), ("amount", amount)] if not val]
    if missing:
        raise ValueError("Unable to discover required fields: " + ", ".join(missing) + ". Available survey columns: " + ", ".join(map(str,survey.columns)) + "; purchase columns: " + ", ".join(map(str,purchases.columns)))
    return sid, pid, date, cat, amount

def clean_inputs(survey_path, purchase_path):
    survey_raw, purchase_raw = read_csv(survey_path), read_csv(purchase_path)
    sid, pid, datecol, catcol, amountcol = find_schema(survey_raw, purchase_raw)
    survey = survey_raw.copy()
    survey[sid] = clean_text(survey[sid])
    survey = survey.dropna(subset=[sid]).drop_duplicates()
    # A customer belongs once in the at-risk population: choose its most complete response.
    completeness = survey.notna().sum(axis=1)
    survey = survey.assign(_complete=completeness).sort_values("_complete", ascending=False).drop_duplicates(sid, keep="first").drop(columns="_complete")
    survey = survey.rename(columns={sid: ID_OUT})

    p = purchase_raw.copy().drop_duplicates()
    p[pid] = clean_text(p[pid]); p[catcol] = canonical_category(p[catcol])
    p["_date"] = pd.to_datetime(clean_text(p[datecol]), errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    p["_amount"] = parse_amount(p[amountcol])
    p = p.dropna(subset=[pid, catcol, "_date", "_amount"])
    p = p[np.isfinite(p["_amount"]) & (p["_amount"] > 0)].copy()
    p = p.rename(columns={pid: ID_OUT, catcol: "Category"})
    # Preserve original cleaned columns but ensure analysis canonical fields are present.
    p[ID_OUT] = clean_text(p[ID_OUT]); p["Category"] = canonical_category(p["Category"])
    p = p.dropna(subset=[ID_OUT, "Category"])
    p["Purchase_Date"] = p["_date"].dt.strftime("%Y-%m-%d")
    p["Purchase_Amount"] = p["_amount"].astype(float)
    p = p.drop(columns=["_date", "_amount"], errors="ignore")
    return survey.reset_index(drop=True), p.reset_index(drop=True)

def anomaly_scores(p, tstart, tend):
    x = p.copy(); x["date"] = pd.to_datetime(x["Purchase_Date"])
    pre = x[x.date < tstart]
    if pre.empty: raise ValueError("No purchases precede treatment start; counterfactual cannot be trained.")
    march_days = pd.date_range(tstart, tend, freq="D")
    rows = []
    for category in sorted(pre.Category.dropna().unique()):
        cp = pre[pre.Category == category].groupby("date").Purchase_Amount.sum()
        # A complete category calendar makes zero-sale days part of the counterfactual.
        days = pd.date_range(pre.date.min(), tstart - pd.Timedelta(days=1), freq="D")
        y = cp.reindex(days, fill_value=0.0).astype(float).to_numpy()
        t = np.arange(len(days), dtype=float)
        dow = np.array([d.dayofweek for d in days])
        design = np.column_stack([np.ones(len(days)), t, *[(dow == k).astype(float) for k in range(1,7)]])
        beta, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
        resid = y - design.dot(beta)
        sigma = float(np.std(resid, ddof=min(1, max(0, len(resid)-1))))
        sigma = max(sigma, 1e-8)
        ft = np.arange(len(days), len(days)+len(march_days), dtype=float)
        mdow = np.array([d.dayofweek for d in march_days])
        md = np.column_stack([np.ones(len(ft)), ft, *[(mdow == k).astype(float) for k in range(1,7)]])
        forecast = np.maximum(0.0, md.dot(beta))
        actual = x[(x.Category == category) & (x.date >= tstart) & (x.date <= tend)].groupby("date").Purchase_Amount.sum().reindex(march_days, fill_value=0.0).to_numpy()
        z = float((actual - forecast).sum() / (sigma * math.sqrt(len(march_days))))
        rows.append({"Category": category, "_z": z})
    result = pd.DataFrame(rows)
    if result.empty: raise ValueError("No eligible categories before treatment.")
    scale = float(result._z.abs().max())
    result["Anomaly_Index"] = 0.0 if scale <= 1e-12 else (100.0 * result._z / scale)
    return result[["Category", "Anomaly_Index"]].sort_values("Anomaly_Index", ascending=False).reset_index(drop=True)

def engineered_features(survey):
    work = survey.copy(); features = pd.DataFrame({ID_OUT: work[ID_OUT].astype(str)})
    for col in survey.columns:
        if col == ID_OUT: continue
        label = str(col)
        nl = norm_label(label)
        vals = clean_text(survey[col])
        n = len(vals); nunique = vals.nunique(dropna=True)
        # Identifier/contact fields can leak identity and cannot define reusable demographics.
        if any(tok in nl for tok in ("email", "phone", "address", "name", "ip", "uuid", "id")) or nunique == 0:
            continue
        num = parse_amount(vals)
        numeric_share = float(num.notna().mean())
        safe = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_") or "feature"
        if numeric_share >= 0.85:
            if num.nunique(dropna=True) <= 1: continue
            med = float(num.median())
            filled = num.fillna(med)
            sd = float(filled.std(ddof=0))
            if sd > 0:
                features["ENG_" + safe] = (filled - float(filled.mean())) / sd
                if num.isna().any(): features["ENG_" + safe + "_missing"] = num.isna().astype(int)
        elif 1 < nunique <= min(30, max(2, n // 3)):
            cats = vals.fillna("__MISSING__")
            # One binary column per level permits direct heterogeneous DiD interpretation.
            for level in sorted(cats.unique(), key=lambda a: str(a)):
                lname = re.sub(r"[^A-Za-z0-9]+", "_", str(level)).strip("_") or "missing"
                features["ENG_" + safe + "__" + lname] = (cats == level).astype(int)
    # Remove accidental constants and duplicate column names deterministically.
    keep = [ID_OUT] + [c for c in features.columns[1:] if features[c].nunique(dropna=False) > 1]
    return features.loc[:, keep]

def did_for_feature(panel, feature, outcome):
    vals = []
    for g in (0, 1):
        for period in ("baseline", "treatment"):
            a = panel[(panel[feature] == g) & (panel.Period == period)][outcome].astype(float).to_numpy()
            if len(a) == 0: return None
            vals.append((float(np.mean(a)), float(np.var(a, ddof=1) / len(a)) if len(a) > 1 else 0.0))
    # order: g0 baseline, g0 treatment, g1 baseline, g1 treatment
    est = (vals[3][0] - vals[2][0]) - (vals[1][0] - vals[0][0])
    se2 = sum(v for _, v in vals)
    p = normal_p(est / math.sqrt(se2)) if se2 > 0 else (1.0 if abs(est) < 1e-12 else 0.0)
    return {"feature": feature, "did_estimate": float(est), "p_value": float(p)}

def make_panels(survey, p, chosen, bstart, bend, tstart, tend):
    ids = survey[ID_OUT].astype(str).drop_duplicates().tolist()
    q = p[p.Category.isin(chosen)].copy(); q[ID_OUT] = q[ID_OUT].astype(str)
    q["dt"] = pd.to_datetime(q.Purchase_Date)
    q["Period"] = np.where((q.dt >= bstart) & (q.dt <= bend), "baseline", np.where((q.dt >= tstart) & (q.dt <= tend), "treatment", None))
    q = q[q.Period.notna()]
    base = pd.MultiIndex.from_product([ids, chosen, ["baseline", "treatment"]], names=[ID_OUT, "Category", "Period"]).to_frame(index=False)
    totals = q.groupby([ID_OUT,"Category","Period"], as_index=False).Purchase_Amount.sum().rename(columns={"Purchase_Amount":"Total_Spend"})
    full = base.merge(totals, on=[ID_OUT,"Category","Period"], how="left")
    full.Total_Spend = full.Total_Spend.fillna(0.0).astype(float)
    extensive = full[[ID_OUT,"Category","Period"]].copy(); extensive["Has_Purchase"] = (full.Total_Spend > 0).astype(int)
    # Intensive margin conditions on making a purchase in that category-period.
    intensive = full[full.Total_Spend > 0][REQ_INT].copy()
    return intensive, extensive

def category_report(category, score, p, at_risk, intensive, extensive, feats, direction, bstart, bend, tstart, tend):
    cp = p[p.Category == category].copy(); cp["dt"] = pd.to_datetime(cp.Purchase_Date)
    base = cp[(cp.dt >= bstart) & (cp.dt <= bend)]; treat = cp[(cp.dt >= tstart) & (cp.dt <= tend)]
    # Daily category totals make baseline/treatment averages comparable despite unequal days.
    bdays = max(1, (bend-bstart).days+1); tdays = max(1, (tend-tstart).days+1)
    out = {"category": str(category), "anomaly_index": float(score),
           "baseline_avg_spend": float(base.Purchase_Amount.sum()/bdays), "treatment_avg_spend": float(treat.Purchase_Amount.sum()/tdays),
           "n_purchasers_baseline": int(base[ID_OUT].nunique()), "n_purchasers_treatment": int(treat[ID_OUT].nunique()),
           "baseline_purchase_rate": float(base[ID_OUT].nunique()/max(1,at_risk)), "treatment_purchase_rate": float(treat[ID_OUT].nunique()/max(1,at_risk)), "n_at_risk": int(at_risk)}
    def drivers(frame, outcome, method):
        panel = frame[frame.Category == category].merge(feats, on=ID_OUT, how="inner")
        ds = []
        for f in feats.columns[1:]:
            r = did_for_feature(panel, f, outcome)
            if r:
                r["method"] = method; ds.append(r)
        ds.sort(key=lambda r: r["did_estimate"], reverse=(direction == "surge"))
        return ds[:3]
    out["intensive_margin"] = drivers(intensive, "Total_Spend", "Univariate DiD")
    out["extensive_margin"] = drivers(extensive, "Has_Purchase", "Multivariate Heterogeneous DiD")
    return out

def validate(outdir):
    required = ["survey_cleaned.csv", "amazon-purchases-2019-2020-filtered.csv", "category_anomaly_index.csv", "survey_feature_engineered.csv", "user_category_period_aggregated_intensive.csv", "user_category_period_aggregated_extensive.csv", "causal_analysis_report.json"]
    missing = [x for x in required if not (outdir/x).exists()]
    if missing: raise ValueError("Missing output files: " + ", ".join(missing))
    a = pd.read_csv(outdir/"category_anomaly_index.csv")
    if list(a.columns) != ["Category", "Anomaly_Index"] or a.Category.duplicated().any() or not np.isfinite(a.Anomaly_Index).all() or (a.Anomaly_Index.abs() > 100.000001).any(): raise ValueError("Invalid anomaly output")
    for name, cols in [("user_category_period_aggregated_intensive.csv", REQ_INT), ("user_category_period_aggregated_extensive.csv", REQ_EXT)]:
        if list(pd.read_csv(outdir/name).columns) != cols: raise ValueError("Invalid schema for " + name)
    report = json.loads((outdir/"causal_analysis_report.json").read_text())
    cats = {str(x) for x in a.Category}
    if any(x["category"] not in cats for x in report["surge_categories"] + report["slump_categories"]): raise ValueError("Report category absent from anomaly file")

def main(config):
    survey_path = config.get("survey_path", "/app/data/survey_dirty.csv"); purchase_path = config.get("purchase_path", "/app/data/amazon-purchases-2019-2020_dirty.csv")
    outdir = Path(config.get("output_dir", "/app/output")); outdir.mkdir(parents=True, exist_ok=True)
    bstart=pd.Timestamp(config.get("baseline_start","2020-01-01")); bend=pd.Timestamp(config.get("baseline_end","2020-02-29")); tstart=pd.Timestamp(config.get("treatment_start","2020-03-01")); tend=pd.Timestamp(config.get("treatment_end","2020-03-31")); topn=int(config.get("top_n",10))
    if not (bstart <= bend < tstart <= tend) or topn < 1: raise ValueError("Require ordered non-overlapping baseline/treatment dates and positive top_n")
    survey, p = clean_inputs(survey_path, purchase_path)
    survey.to_csv(outdir/"survey_cleaned.csv", index=False); p.to_csv(outdir/"amazon-purchases-2019-2020-filtered.csv", index=False)
    anomaly = anomaly_scores(p, tstart, tend); anomaly.to_csv(outdir/"category_anomaly_index.csv", index=False)
    feats = engineered_features(survey); feats.to_csv(outdir/"survey_feature_engineered.csv", index=False)
    highs = anomaly.head(topn); lows = anomaly.sort_values("Anomaly_Index", ascending=True).head(topn)
    surge = highs.Category.tolist(); slump = lows.Category.tolist(); chosen = list(dict.fromkeys(surge + slump))
    intensive, extensive = make_panels(survey, p, chosen, bstart, bend, tstart, tend)
    intensive.to_csv(outdir/"user_category_period_aggregated_intensive.csv", index=False); extensive.to_csv(outdir/"user_category_period_aggregated_extensive.csv", index=False)
    amap = dict(zip(anomaly.Category, anomaly.Anomaly_Index)); n = int(survey[ID_OUT].nunique())
    sr = [category_report(c, amap[c], p, n, intensive, extensive, feats, "surge", bstart,bend,tstart,tend) for c in surge]
    lr = [category_report(c, amap[c], p, n, intensive, extensive, feats, "slump", bstart,bend,tstart,tend) for c in slump]
    report = {"metadata":{"baseline_start":bstart.strftime("%m-%d-%Y"),"baseline_end":bend.strftime("%m-%d-%Y"),"treatment_start":tstart.strftime("%m-%d-%Y"),"treatment_end":tend.strftime("%m-%d-%Y"),"total_features_analyzed":int(len(feats.columns)-1)}, "surge_categories":sr, "slump_categories":lr,
              "summary":{"surge":{"total_categories":len(sr),"total_intensive_drivers":sum(len(x["intensive_margin"]) for x in sr),"total_extensive_drivers":sum(len(x["extensive_margin"]) for x in sr)},"slump":{"total_categories":len(lr),"total_intensive_drivers":sum(len(x["intensive_margin"]) for x in lr),"total_extensive_drivers":sum(len(x["extensive_margin"]) for x in lr)}}}
    (outdir/"causal_analysis_report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    validate(outdir)
    return {"output_dir":str(outdir), "cleaned_survey_rows":len(survey), "cleaned_purchase_rows":len(p), "categories":len(anomaly), "features":len(feats.columns)-1}
if __name__ == "__main__":
    try:
        raw=sys.stdin.read().strip(); config=json.loads(raw) if raw else {}
        print(json.dumps(main(config), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"error":str(exc)})); sys.exit(1)
