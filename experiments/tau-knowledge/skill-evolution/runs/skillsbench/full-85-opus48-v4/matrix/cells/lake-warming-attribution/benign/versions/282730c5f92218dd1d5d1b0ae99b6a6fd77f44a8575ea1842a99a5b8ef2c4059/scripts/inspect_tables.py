"""Inspect the supplied lake tables.

stdin JSON: {"data_dir": "/root/data"}
stdout JSON: per-table schema, dtypes, rows, detected time key, year range, nulls.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd  # noqa: E402
from common import detect_time_key  # noqa: E402


def main():
    raw = sys.stdin.read().strip()
    cfg = json.loads(raw) if raw else {}
    data_dir = cfg.get("data_dir", "/root/data")
    report = {}
    for fn in sorted(os.listdir(data_dir)) if os.path.isdir(data_dir) else []:
        if not fn.lower().endswith(".csv"):
            continue
        path = os.path.join(data_dir, fn)
        try:
            df = pd.read_csv(path)
        except Exception as e:  # noqa: BLE001
            report[fn] = {"error": str(e)}
            continue
        info = {
            "columns": list(df.columns),
            "dtypes": {c: str(df[c].dtype) for c in df.columns},
            "rows": int(len(df)),
            "nulls": {c: int(df[c].isna().sum()) for c in df.columns},
        }
        try:
            years, key = detect_time_key(df)
            yv = years.dropna().astype(int)
            info["time_key"] = key
            info["year_min"] = int(yv.min()) if len(yv) else None
            info["year_max"] = int(yv.max()) if len(yv) else None
            info["n_years"] = int(yv.nunique())
        except Exception as e:  # noqa: BLE001
            info["time_key_error"] = str(e)
        report[fn] = info
    print(json.dumps({"data_dir": data_dir, "tables": report}, indent=2))


if __name__ == "__main__":
    main()
