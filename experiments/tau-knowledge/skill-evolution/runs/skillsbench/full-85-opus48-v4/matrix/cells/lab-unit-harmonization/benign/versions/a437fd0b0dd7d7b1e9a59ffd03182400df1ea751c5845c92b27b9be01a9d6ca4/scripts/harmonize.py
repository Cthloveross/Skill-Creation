#!/usr/bin/env python3
"""End-to-end lab unit harmonization.

stdin  : optional JSON {input_csv, descriptions_csv, output_csv, registry}
stdout : JSON summary (see SKILL.md)
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lab_lib as L  # noqa: E402

DEFAULTS = {
    "input_csv": "/root/environment/data/ckd_lab_data.csv",
    "descriptions_csv": "/root/environment/data/ckd_feature_descriptions.csv",
    "output_csv": "/root/ckd_lab_data_harmonized.csv",
}


def main():
    raw = sys.stdin.read().strip()
    cfg = dict(DEFAULTS)
    if raw:
        try:
            cfg.update({k: v for k, v in json.loads(raw).items() if v})
        except json.JSONDecodeError as e:
            print(json.dumps({"ok": False, "error": "bad JSON: %s" % e}))
            return 1

    in_csv = cfg["input_csv"]
    if not os.path.exists(in_csv):
        print(json.dumps({"ok": False, "error": "missing input_csv %s" % in_csv}))
        return 1

    registry = L.load_registry(cfg.get("registry"))
    descriptions = L.load_descriptions(cfg.get("descriptions_csv"))

    header, rows = L.read_csv(in_csv)
    if not header:
        print(json.dumps({"ok": False, "error": "empty input"}))
        return 1
    ncol = len(header)

    # 1) drop rows with any missing cell
    kept = [r for r in rows if not any(L.is_missing(c) for c in r)]
    dropped = len(rows) - len(kept)

    # identify numeric columns
    numeric_cols = []
    for j in range(ncol):
        col_vals = [r[j] for r in kept]
        if L.is_numeric_column(col_vals):
            numeric_cols.append(j)

    # resolve analytes for numeric columns
    resolved = {}
    entries = {}
    for j in numeric_cols:
        text = L.column_match_text(header[j], descriptions)
        e = L.resolve_analyte(text, registry)
        entries[j] = e
        resolved[header[j]] = e.get("name") if e else None

    # 2-4) parse, convert, format
    conversions = {header[j]: 0 for j in numeric_cols}
    out_rows = []
    for r in kept:
        new = list(r)
        for j in numeric_cols:
            v = L.parse_num(r[j])
            if v is None:
                # keep original token for a cell that is non-numeric in an
                # otherwise-numeric column (rare); leave as-is
                continue
            v2, converted = L.harmonize_value(v, entries[j])
            if converted:
                conversions[header[j]] += 1
            new[j] = L.fmt2(v2)
        out_rows.append(new)

    out_path = cfg["output_csv"]
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(out_rows)

    print(json.dumps({
        "ok": True,
        "input_rows": len(rows),
        "output_rows": len(out_rows),
        "dropped_rows": dropped,
        "columns": ncol,
        "numeric_columns": [header[j] for j in numeric_cols],
        "resolved": resolved,
        "conversions": conversions,
        "output_csv": out_path,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
