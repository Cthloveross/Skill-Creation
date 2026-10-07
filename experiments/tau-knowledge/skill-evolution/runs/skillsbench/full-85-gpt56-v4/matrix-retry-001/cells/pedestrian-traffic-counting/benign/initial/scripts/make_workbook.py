#!/usr/bin/env python3
"""Read {output: str, rows: [{filename: str, number: int}]} from stdin; write strict XLSX."""
import json
import os
import sys
from pathlib import Path

from openpyxl import Workbook


def fail(message):
    print(json.dumps({"ok": False, "error": message}), file=sys.stdout)
    raise SystemExit(2)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        fail(f"invalid JSON input: {exc}")
    output = payload.get("output")
    rows = payload.get("rows")
    if not isinstance(output, str) or not output:
        fail("output must be a nonempty path string")
    if not isinstance(rows, list):
        fail("rows must be a list")
    normalized = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            fail("each row must be an object")
        filename, number = row.get("filename"), row.get("number")
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            fail("filename must be a nonempty basename")
        if filename in seen:
            fail(f"duplicate filename: {filename}")
        # bool is an int subclass but is not a valid count.
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            fail(f"number for {filename} must be a nonnegative integer")
        seen.add(filename)
        normalized.append((filename, number))
    normalized.sort(key=lambda item: item[0])
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "results"
    ws.append(["filename", "number"])
    for filename, number in normalized:
        ws.append([filename, number])
    wb.save(path)
    print(json.dumps({"ok": True, "output": str(path), "rows": [{"filename": f, "number": n} for f, n in normalized]}))

if __name__ == "__main__":
    main()
