#!/usr/bin/env python3
"""Discover the structure of an xlsx workbook without assuming its schema.

stdin:  {"xlsx_path": "/root/data.xlsx", "sample_rows": 20}
stdout: {"sheets": [ {name, max_row, max_col, header_candidates, columns, sample} ], ...}

Each column entry gives the normalized header guess and inferred type over the sampled
rows. Sample cells report value and whether the cell holds a formula.
"""
import sys, json


def norm(v):
    if v is None:
        return ""
    return str(v).strip().lower()


def infer_type(vals):
    seen = set()
    for v in vals:
        if v is None or v == "":
            continue
        if isinstance(v, bool):
            seen.add("bool")
        elif isinstance(v, (int, float)):
            seen.add("number")
        else:
            seen.add("text")
    if not seen:
        return "empty"
    if seen == {"number"}:
        return "number"
    return "mixed" if len(seen) > 1 else next(iter(seen))


def main():
    req = json.load(sys.stdin)
    path = req["xlsx_path"]
    n = int(req.get("sample_rows", 20))
    try:
        from openpyxl import load_workbook
    except ImportError:
        print(json.dumps({"error": "no_openpyxl",
                          "hint": "pip install openpyxl then re-run"}))
        return
    wb_vals = load_workbook(path, data_only=True, read_only=True)
    wb_frm = load_workbook(path, data_only=False, read_only=True)
    out = {"sheets": []}
    for name in wb_vals.sheetnames:
        ws = wb_vals[name]
        wf = wb_frm[name]
        max_row = ws.max_row or 0
        max_col = ws.max_column or 0
        rows_v = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            rows_v.append(list(row))
            if i + 1 >= n:
                break
        rows_f = []
        for i, row in enumerate(wf.iter_rows()):
            rows_f.append([bool(c.data_type == 'f') for c in row])
            if i + 1 >= n:
                break
        # header candidates: first few rows that are mostly text
        header_candidates = []
        for idx, r in enumerate(rows_v[:5]):
            texty = sum(1 for v in r if isinstance(v, str) and v.strip())
            if texty >= max(1, (len([v for v in r if v is not None]) // 2)):
                header_candidates.append({"row_index": idx,
                                           "values": [norm(v) for v in r]})
        ncols = max((len(r) for r in rows_v), default=0)
        columns = []
        for c in range(ncols):
            colvals = [r[c] if c < len(r) else None for r in rows_v]
            columns.append({"index": c, "inferred_type": infer_type(colvals)})
        sample = []
        for ri, r in enumerate(rows_v):
            frm = rows_f[ri] if ri < len(rows_f) else []
            cells = []
            for ci, v in enumerate(r):
                cells.append({"v": v if not isinstance(v, float) else round(v, 6),
                              "formula": frm[ci] if ci < len(frm) else False})
            sample.append(cells)
        out["sheets"].append({
            "name": name,
            "max_row": max_row,
            "max_col": max_col,
            "header_candidates": header_candidates,
            "columns": columns,
            "sample": sample,
        })
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    main()
