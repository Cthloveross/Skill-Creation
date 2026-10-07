#!/usr/bin/env python3
"""Validate a harmonized CSV against the output contract.

stdin  : JSON {output_csv, input_csv?, descriptions_csv?, registry?}
stdout : JSON report
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lab_lib as L  # noqa: E402

NUM_RE = re.compile(r"^-?\d+\.\d{2}$")


def main():
    raw = sys.stdin.read().strip()
    cfg = json.loads(raw) if raw else {}
    out_csv = cfg.get("output_csv", "/root/ckd_lab_data_harmonized.csv")
    in_csv = cfg.get("input_csv", "/root/environment/data/ckd_lab_data.csv")
    desc = cfg.get("descriptions_csv",
                   "/root/environment/data/ckd_feature_descriptions.csv")

    issues = []
    if not os.path.exists(out_csv):
        print(json.dumps({"ok": False, "issues": ["output missing"]}))
        return 1

    registry = L.load_registry(cfg.get("registry"))
    descriptions = L.load_descriptions(desc)
    header, rows = L.read_csv(out_csv)
    ncol = len(header)

    col_match = True
    if os.path.exists(in_csv):
        ih, _ = L.read_csv(in_csv)
        col_match = (len(ih) == ncol)
        if not col_match:
            issues.append("column count differs from input (%d vs %d)" % (ncol, len(ih)))

    # numeric columns of the output
    numeric_cols = []
    for j in range(ncol):
        if L.is_numeric_column([r[j] for r in rows]):
            numeric_cols.append(j)

    bad = []
    for j in numeric_cols:
        for i, r in enumerate(rows):
            cell = r[j].strip()
            if cell == "":
                continue
            if not NUM_RE.match(cell):
                bad.append({"row": i, "col": header[j], "value": cell})
            if "," in cell or "e" in cell.lower():
                bad.append({"row": i, "col": header[j], "value": cell})

    out_of_range = {}
    for j in numeric_cols:
        text = L.column_match_text(header[j], descriptions)
        e = L.resolve_analyte(text, registry)
        if not e:
            continue
        cnt = 0
        for r in rows:
            v = L.parse_num(r[j])
            if v is None:
                continue
            if not L.in_range(v, e):
                cnt += 1
        if cnt:
            out_of_range[header[j]] = cnt

    ok = col_match and not bad
    print(json.dumps({
        "ok": ok,
        "column_count_match": col_match,
        "rows": len(rows),
        "numeric_columns": [header[j] for j in numeric_cols],
        "bad_format_cells": bad[:50],
        "bad_format_count": len(bad),
        "out_of_range": out_of_range,
        "issues": issues,
    }))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
