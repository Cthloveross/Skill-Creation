#!/usr/bin/env python3
"""End-to-end receipt OCR -> xlsx entrypoint.

Reads JSON config on stdin (all keys optional):
  {"img_dir": ..., "output": ..., "debug_json": ...}
Defaults match the current task.

Writes a single-sheet workbook `results` with columns
filename/date/total_amount, one row per discovered image sorted by filename,
null (empty cell) for fields that could not be extracted.

Emits a JSON summary on stdout.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocr_receipt as ocr  # noqa: E402

DEFAULT_IMG_DIR = "/app/workspace/dataset/img"
DEFAULT_OUTPUT = "/app/workspace/stat_ocr.xlsx"
HEADER = ["filename", "date", "total_amount"]
SHEET_NAME = "results"


def read_config():
    data = sys.stdin.read() if not sys.stdin.isatty() else ""
    cfg = {}
    if data.strip():
        try:
            cfg = json.loads(data)
        except json.JSONDecodeError:
            cfg = {}
    return cfg


def write_xlsx(output, rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME
    ws.append(HEADER)
    for r in rows:
        ws.append([r["filename"], r["date"], r["total_amount"]])
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    wb.save(output)


def main():
    cfg = read_config()
    img_dir = cfg.get("img_dir", DEFAULT_IMG_DIR)
    output = cfg.get("output", DEFAULT_OUTPUT)
    debug_json = cfg.get("debug_json")

    if not os.path.isdir(img_dir):
        print(json.dumps({"error": "img_dir not found", "img_dir": img_dir}))
        sys.exit(1)

    names = ocr.list_images(img_dir)
    rows = []
    debug = []
    for name in names:
        rec = ocr.extract_record(os.path.join(img_dir, name))
        rows.append({"filename": rec["filename"], "date": rec["date"],
                     "total_amount": rec["total_amount"]})
        if debug_json:
            debug.append({"filename": rec["filename"], "date": rec["date"],
                          "total_amount": rec["total_amount"],
                          "lines": rec.get("_lines", [])})

    rows.sort(key=lambda r: r["filename"])
    write_xlsx(output, rows)

    if debug_json:
        with open(debug_json, "w", encoding="utf-8") as f:
            json.dump(debug, f, ensure_ascii=False, indent=2)

    summary = {
        "output": output,
        "count": len(rows),
        "rows": rows,
        "n_date_null": sum(1 for r in rows if r["date"] is None),
        "n_amount_null": sum(1 for r in rows if r["total_amount"] is None),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
