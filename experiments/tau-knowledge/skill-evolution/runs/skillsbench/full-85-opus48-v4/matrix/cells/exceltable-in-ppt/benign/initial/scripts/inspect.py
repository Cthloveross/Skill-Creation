"""Inspect a pptx: list embedded workbooks, dump each sheet grid and slide text.

stdin JSON:  {"pptx_in": "/root/input.pptx"}
stdout JSON: discovery report (no edits are made).
"""
import json
import sys

import pptx_xlsx as P


def main():
    req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    pptx_in = req.get("pptx_in", "/root/input.pptx")
    data = P.read_zip(pptx_in)
    report = {"pptx_in": pptx_in, "embeddings": [], "slides": {}}
    for name, xb in P.list_embeddings(data):
        try:
            wb, ws, grid = P.load_sheet_grid(xb)
            mx = P.find_matrix(grid)
            report["embeddings"].append({
                "part": name,
                "sheet": ws.title,
                "grid": [[str(v) if v is not None else "" for v in row]
                          for row in grid],
                "matrix": None if mx is None else {
                    "currencies": sorted(mx["currencies"]),
                    "header_row": mx["header_row"],
                    "label_col": mx["label_col"],
                },
            })
        except Exception as exc:  # noqa: BLE001
            report["embeddings"].append({"part": name, "error": repr(exc)})
    report["slides"] = P.slide_texts(data)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
