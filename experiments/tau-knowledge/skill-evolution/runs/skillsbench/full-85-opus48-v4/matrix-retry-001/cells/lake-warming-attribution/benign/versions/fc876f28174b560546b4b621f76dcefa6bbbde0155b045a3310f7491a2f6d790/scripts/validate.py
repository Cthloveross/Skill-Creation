#!/usr/bin/env python3
"""Validate the two produced output files against the task contract.

Stdin JSON (optional): {"output_dir": "/root/output"}
Stdout JSON: {"status":"ok"|"error", "checks": {...}, "message": ...}

Checks:
  * trend_result.csv exists, has columns exactly [slope, p-value], one row,
    finite values, p-value in [0,1].
  * dominant_factor.csv exists, has columns exactly [variable, contribution],
    one row, finite numeric contribution.
"""
import os
import sys
import json
import math
import pandas as pd


def main():
    raw = sys.stdin.read().strip()
    cfg = json.loads(raw) if raw else {}
    out_dir = cfg.get("output_dir", "/root/output")
    checks = {}
    errors = []

    tp = os.path.join(out_dir, "trend_result.csv")
    if not os.path.exists(tp):
        errors.append("trend_result.csv missing")
    else:
        df = pd.read_csv(tp)
        checks["trend_columns"] = list(df.columns)
        if list(df.columns) != ["slope", "p-value"]:
            errors.append("trend_result.csv columns must be exactly slope,p-value")
        if len(df) != 1:
            errors.append("trend_result.csv must have exactly one row")
        else:
            s = float(df.iloc[0]["slope"]) if "slope" in df else float("nan")
            p = float(df.iloc[0]["p-value"]) if "p-value" in df else float("nan")
            if not math.isfinite(s):
                errors.append("slope not finite")
            if not (math.isfinite(p) and 0.0 <= p <= 1.0):
                errors.append("p-value not in [0,1] or not finite")
            checks["slope"] = s
            checks["p_value"] = p

    dp = os.path.join(out_dir, "dominant_factor.csv")
    if not os.path.exists(dp):
        errors.append("dominant_factor.csv missing")
    else:
        df = pd.read_csv(dp)
        checks["dominant_columns"] = list(df.columns)
        if list(df.columns) != ["variable", "contribution"]:
            errors.append(
                "dominant_factor.csv columns must be exactly variable,contribution")
        if len(df) != 1:
            errors.append("dominant_factor.csv must have exactly one row")
        else:
            c = df.iloc[0]["contribution"] if "contribution" in df else None
            try:
                cf = float(c)
                if not math.isfinite(cf):
                    errors.append("contribution not finite")
                checks["contribution"] = cf
            except Exception:
                errors.append("contribution not numeric")
            checks["variable"] = str(df.iloc[0]["variable"]) if "variable" in df else None

    status = "ok" if not errors else "error"
    print(json.dumps({"status": status, "checks": checks, "errors": errors}))
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
