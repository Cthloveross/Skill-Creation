#!/usr/bin/env python3
"""Validate the produced artifacts against the public output contract.

Stdin : optional JSON {"output_dir": "/app/output"}.
Stdout: {"status":"ok"} or {"status":"fail","problems":[...]}.

Checks are derived from the task request only (schema, finiteness, index range,
report shape, sort direction). It does not assert specific expected values.
"""
import os
import sys
import json
import pandas as pd


def main():
    try:
        raw = sys.stdin.read().strip()
        cfg = json.loads(raw) if raw else {}
    except Exception:
        cfg = {}
    out = cfg.get("output_dir", "/app/output")
    problems = []

    def exists(name):
        p = os.path.join(out, name)
        if not os.path.exists(p):
            problems.append(f"missing file: {name}")
            return None
        return p

    for f in ["survey_cleaned.csv", "amazon-purchases-2019-2020-filtered.csv",
              "category_anomaly_index.csv", "survey_feature_engineered.csv",
              "user_category_period_aggregated_intensive.csv",
              "user_category_period_aggregated_extensive.csv",
              "causal_analysis_report.json"]:
        exists(f)

    p = os.path.join(out, "category_anomaly_index.csv")
    if os.path.exists(p):
        df = pd.read_csv(p)
        if list(df.columns) != ["Category", "Anomaly_Index"]:
            problems.append(f"anomaly columns wrong: {list(df.columns)}")
        else:
            ai = pd.to_numeric(df["Anomaly_Index"], errors="coerce")
            if ai.isna().any():
                problems.append("anomaly index has non-numeric values")
            elif (ai < -100).any() or (ai > 100).any():
                problems.append("anomaly index outside [-100,100]")

    p = os.path.join(out, "survey_feature_engineered.csv")
    if os.path.exists(p):
        df = pd.read_csv(p)
        if "Survey ResponseID" not in df.columns:
            problems.append("feature file missing 'Survey ResponseID'")
        if df.shape[1] < 2:
            problems.append("feature file has no engineered features")

    for name, req in [("user_category_period_aggregated_intensive.csv",
                       ["Survey ResponseID", "Category", "Period", "Total_Spend"]),
                      ("user_category_period_aggregated_extensive.csv",
                       ["Survey ResponseID", "Category", "Period", "Has_Purchase"])]:
        p = os.path.join(out, name)
        if os.path.exists(p):
            df = pd.read_csv(p)
            miss = [c for c in req if c not in df.columns]
            if miss:
                problems.append(f"{name} missing columns {miss}")

    p = os.path.join(out, "causal_analysis_report.json")
    if os.path.exists(p):
        try:
            rep = json.load(open(p))
            md = rep.get("metadata", {})
            for k in ["baseline_start", "baseline_end", "treatment_start",
                      "treatment_end", "total_features_analyzed"]:
                if k not in md:
                    problems.append(f"report metadata missing {k}")
            for grp, direction in [("surge_categories", "desc"),
                                   ("slump_categories", "asc")]:
                for b in rep.get(grp, []):
                    for k in ["category", "anomaly_index", "baseline_avg_spend",
                              "treatment_avg_spend", "n_purchasers_baseline",
                              "n_purchasers_treatment", "baseline_purchase_rate",
                              "treatment_purchase_rate", "n_at_risk",
                              "intensive_margin", "extensive_margin"]:
                        if k not in b:
                            problems.append(f"{grp} entry missing {k}")
                    for margin in ["intensive_margin", "extensive_margin"]:
                        arr = b.get(margin, [])
                        if len(arr) > 3:
                            problems.append(f"{grp}:{margin} has >3 drivers")
                        ests = [d.get("did_estimate") for d in arr
                                if isinstance(d.get("did_estimate"), (int, float))]
                        if len(ests) >= 2:
                            ok = (ests == sorted(ests, reverse=True)) if direction == "desc" \
                                else (ests == sorted(ests))
                            if not ok:
                                problems.append(f"{grp}:{margin} not sorted {direction}")
        except Exception as e:
            problems.append(f"report json unreadable: {e}")

    if problems:
        print(json.dumps({"status": "fail", "problems": problems}, indent=2))
        return 1
    print(json.dumps({"status": "ok"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
