#!/usr/bin/env python3
"""Apply value/formula writes to a workbook and save, preserving everything else.

stdin  : {"in_path": str, "out_path": str,
          "cells": [{"sheet": str, "cell": "A1",
                     "value": <any>?, "formula": "=..."?}, ...]}
stdout : {"written": int, "out_path": str}

- Exactly one of "value" / "formula" per entry. A formula string must start with
  "=". Addresses, sheets, and formulas are supplied by the caller (derive them
  from runtime inspection; do not invent a fixed layout).
- Existing cells, styles, and untouched sheets are preserved by openpyxl.
"""
import json
import sys

from openpyxl import load_workbook


def main():
    req = json.load(sys.stdin)
    wb = load_workbook(req["in_path"], data_only=False)
    n = 0
    for item in req["cells"]:
        ws = wb[item["sheet"]]
        cell = item["cell"]
        if "formula" in item and item["formula"] is not None:
            f = item["formula"]
            if not str(f).startswith("="):
                f = "=" + str(f)
            ws[cell] = f
        else:
            ws[cell] = item.get("value")
        n += 1
    wb.save(req["out_path"])
    json.dump({"written": n, "out_path": req["out_path"]}, sys.stdout)


if __name__ == "__main__":
    main()
