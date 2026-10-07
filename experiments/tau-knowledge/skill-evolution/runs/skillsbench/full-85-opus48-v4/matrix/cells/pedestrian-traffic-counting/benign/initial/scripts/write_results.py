#!/usr/bin/env python3
"""Strict openpyxl writer for the pedestrian-count workbook.

Contract enforced:
- exactly one sheet named 'results'
- row 1 header: filename, number
- one data row per entry, counts stored as native int
- no extra rows/columns/sheets

Importable: write_results(output_path, rows) where rows is a list of
{'filename': str, 'number': int}. CLI: reads JSON {'output_path','results'}.
"""
from __future__ import annotations
import json
import sys


def write_results(output_path, rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "results"
    ws.append(["filename", "number"])
    for r in sorted(rows, key=lambda x: str(x["filename"])):
        ws.append([str(r["filename"]), int(r["number"])])
    wb.save(output_path)
    return output_path


def main():
    req = json.load(sys.stdin)
    out = req["output_path"]
    rows = req["results"]
    write_results(out, rows)
    print(json.dumps({"output_path": out, "written": len(rows)}))


if __name__ == "__main__":
    main()
