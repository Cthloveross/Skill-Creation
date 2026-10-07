#!/usr/bin/env python3
"""Validate /root/pareto_frontier.csv against the task's output contract.

stdin JSON: {"output_path": "/root/pareto_frontier.csv"}
stdout JSON: {"ok": bool, "problems": [...], "n_rows": int}

Checks (derived from the public request and background rules):
  - header is exactly F1,delta,min_samples,epsilon,shape_weight
  - min_samples, epsilon are integers; shape_weight has <=1 decimal
  - F1 and delta rounded to <=5 decimals; all F1 > 0.5; delta finite
  - internal Pareto consistency: no row dominates another
    (maximize F1, minimize delta)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _decimals(x):
    s = ("%r" % float(x))
    if "e" in s or "E" in s:
        return 99
    return len(s.split(".")[1]) if "." in s else 0


def main():
    try:
        raw = sys.stdin.read().strip()
        cfg = json.loads(raw) if raw else {}
    except Exception:
        cfg = {}
    path = cfg.get("output_path", "/root/pareto_frontier.csv")

    problems = []
    if not os.path.exists(path):
        print(json.dumps({"ok": False, "problems": ["file missing"],
                          "n_rows": 0}))
        return

    import pandas as pd
    import numpy as np

    df = pd.read_csv(path)
    expected = ["F1", "delta", "min_samples", "epsilon", "shape_weight"]
    if list(df.columns) != expected:
        problems.append(f"columns {list(df.columns)} != {expected}")
        print(json.dumps({"ok": False, "problems": problems,
                          "n_rows": len(df)}))
        return

    for _, r in df.iterrows():
        if float(r["min_samples"]) != int(r["min_samples"]):
            problems.append("min_samples not integer")
        if float(r["epsilon"]) != int(r["epsilon"]):
            problems.append("epsilon not integer")
        if _decimals(r["shape_weight"]) > 1:
            problems.append(f"shape_weight {r['shape_weight']} >1 decimal")
        if _decimals(r["F1"]) > 5:
            problems.append(f"F1 {r['F1']} >5 decimals")
        if _decimals(r["delta"]) > 5:
            problems.append(f"delta {r['delta']} >5 decimals")
        if not (float(r["F1"]) > 0.5):
            problems.append(f"F1 {r['F1']} not > 0.5")
        if not np.isfinite(float(r["delta"])):
            problems.append("delta not finite")

    f1 = df["F1"].to_numpy(dtype=float)
    dl = df["delta"].to_numpy(dtype=float)
    n = len(df)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if (f1[j] >= f1[i] and dl[j] <= dl[i]
                    and (f1[j] > f1[i] or dl[j] < dl[i])):
                problems.append(f"row {i} dominated by row {j}")
                break

    problems = sorted(set(problems))
    print(json.dumps({"ok": len(problems) == 0, "problems": problems,
                      "n_rows": n}))


if __name__ == "__main__":
    main()
