#!/usr/bin/env python3
"""Report the schema of the supplied CSVs so column names are discovered, not
assumed.

stdin : {"paths": ["/app/data/thermocouples.csv", ...]}
stdout: {path: {"columns": [...], "n_rows": int, "sample": [row,row,row],
                "unique": {col: [values up to 50]}}}
Unique value lists are only emitted for low-cardinality id-like columns.
"""
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from helpers import read_csv, guess_col  # noqa: E402


def main():
    cfg = json.load(sys.stdin)
    out = {}
    for path in cfg["paths"]:
        try:
            header, rows = read_csv(path)
        except Exception as e:  # noqa: BLE001
            out[path] = {"error": str(e)}
            continue
        info = {"columns": header, "n_rows": len(rows), "sample": rows[:3]}
        uniq = {}
        id_cols = set()
        for kw in ("run", "board", "family", "tc", "sensor", "channel", "status", "type", "defect"):
            c = guess_col(header, kw)
            if c:
                id_cols.add(c)
        for c in id_cols:
            vals = sorted({r.get(c, "") for r in rows})
            if len(vals) <= 60:
                uniq[c] = vals
        info["unique"] = uniq
        out[path] = info
    print(json.dumps(out))


if __name__ == "__main__":
    main()
