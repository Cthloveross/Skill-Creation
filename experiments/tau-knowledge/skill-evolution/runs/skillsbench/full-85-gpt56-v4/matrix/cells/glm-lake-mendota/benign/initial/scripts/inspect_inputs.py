#!/usr/bin/env python3
"""Inspect observation and forcing CSV schemas. JSON stdin -> JSON stdout."""
import json, sys
from pathlib import Path
import pandas as pd


def csv_summary(path):
    p = Path(path)
    df = pd.read_csv(p)
    result = {
        "path": str(p), "rows": int(len(df)), "columns": list(df.columns),
        "non_null": {str(k): int(v) for k, v in df.notna().sum().items()},
        "sample": df.head(3).where(pd.notna(df.head(3)), None).to_dict(orient="records"),
    }
    date_info = {}
    for col in df.columns:
        name = col.lower()
        if any(x in name for x in ("date", "time", "datetime")):
            parsed = pd.to_datetime(df[col], errors="coerce", utc=False)
            valid = parsed.dropna()
            date_info[col] = {"parseable": int(len(valid)),
                              "min": str(valid.min()) if len(valid) else None,
                              "max": str(valid.max()) if len(valid) else None}
    result["date_columns"] = date_info
    return result


def main():
    try:
        spec = json.load(sys.stdin)
        out = {"ok": True, "observations": csv_summary(spec["observations"])}
        forcing = spec.get("forcing_dir")
        if forcing:
            root = Path(forcing)
            out["forcing"] = [csv_summary(p) for p in sorted(root.glob("*.csv"))]
            if not out["forcing"]:
                out["warnings"] = ["No CSV files found in forcing_dir"]
        print(json.dumps(out, default=str))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))

if __name__ == "__main__":
    main()
