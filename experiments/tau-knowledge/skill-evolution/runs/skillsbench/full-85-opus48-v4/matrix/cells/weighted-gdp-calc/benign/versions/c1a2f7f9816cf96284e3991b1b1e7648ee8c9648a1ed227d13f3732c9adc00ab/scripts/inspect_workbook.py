"""Inspect a workbook so the executor can confirm/override defaults.

stdin JSON:  {"path": "/root/gdp.xlsx",
              "task_sheet": "Task", "data_sheet": "Data"}
stdout JSON: sheet dims, Task labels (non-numeric cells in cols A-G),
             fill signatures of candidate yellow cells, and candidate Data
             layout (year header row + code column) inferred from Task keys.
"""
import json
import sys

from openpyxl import load_workbook

sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import as_key, cl, fill_signature, norm_val  # noqa: E402


def main():
    cfg = json.load(sys.stdin)
    path = cfg["path"]
    task_name = cfg.get("task_sheet", "Task")
    data_name = cfg.get("data_sheet", "Data")
    wb = load_workbook(path, data_only=False)
    out = {"sheets": wb.sheetnames}

    if task_name in wb.sheetnames:
        ws = wb[task_name]
        out["task"] = {"max_row": ws.max_row, "max_col": ws.max_column}
        labels = []
        fills = []
        for row in ws.iter_rows():
            for c in row:
                if c.value is None:
                    sig = fill_signature(c)
                    if sig and sig[0]:
                        fills.append({"cell": c.coordinate, "fill": sig})
                    continue
                if isinstance(c.value, str):
                    labels.append({"cell": c.coordinate, "text": c.value})
        out["task"]["labels"] = labels[:200]
        out["task"]["filled_blank_cells"] = fills[:200]
        out["task"]["row10"] = {
            cl(i): norm_val(ws.cell(10, i).value) for i in range(1, min(ws.max_column, 20) + 1)
        }

    if data_name in wb.sheetnames:
        ds = wb[data_name]
        out["data"] = {"max_row": ds.max_row, "max_col": ds.max_column}
        # Try to locate the year header row + code column using Task keys.
        if task_name in wb.sheetnames:
            ts = wb[task_name]
            years = {as_key(ts.cell(10, i).value) for i in range(8, 13)}
            years.discard(None)
            codes = set()
            for r in range(1, ts.max_row + 1):
                v = as_key(ts.cell(r, 4).value)
                if v is not None:
                    codes.add(v)
            best_year_row, best_year_hits = None, 0
            for r in range(1, ds.max_row + 1):
                hits = sum(1 for i in range(1, ds.max_column + 1) if as_key(ds.cell(r, i).value) in years)
                if hits > best_year_hits:
                    best_year_hits, best_year_row = hits, r
            best_code_col, best_code_hits = None, 0
            for i in range(1, ds.max_column + 1):
                hits = sum(1 for r in range(1, ds.max_row + 1) if as_key(ds.cell(r, i).value) in codes)
                if hits > best_code_hits:
                    best_code_hits, best_code_col = hits, i
            out["data"]["candidate_year_row"] = best_year_row
            out["data"]["candidate_year_row_hits"] = best_year_hits
            out["data"]["candidate_code_col"] = best_code_col
            out["data"]["candidate_code_col_letter"] = cl(best_code_col) if best_code_col else None
            out["data"]["candidate_code_col_hits"] = best_code_hits

    json.dump(out, sys.stdout, default=str)


if __name__ == "__main__":
    main()
