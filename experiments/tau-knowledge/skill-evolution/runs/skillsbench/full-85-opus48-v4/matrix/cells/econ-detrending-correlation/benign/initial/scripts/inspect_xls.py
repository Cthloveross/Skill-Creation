#!/usr/bin/env python3
"""Dump a worksheet to inspect its real layout.

Stdin JSON: {"path": "...", "max_rows": 400}
Stdout JSON: detected year/total columns plus each row's cells.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import econ_utils as eu  # noqa: E402


def main():
    cfg = json.loads(sys.stdin.read() or "{}")
    path = cfg["path"]
    max_rows = int(cfg.get("max_rows", 400))
    rows = eu.read_sheet(path)
    ncols = max((len(r) for r in rows), default=0)
    rows = [list(r) + [None] * (ncols - len(r)) for r in rows]
    try:
        yc = eu.detect_year_col(rows, ncols)
        tc = eu.detect_total_col(rows, ncols, yc)
    except Exception as e:
        yc, tc = None, "error: %s" % e
    out = {"path": path, "ncols": ncols, "nrows": len(rows),
           "detected_year_col": yc, "detected_total_col": tc, "rows": []}
    for i, r in enumerate(rows[:max_rows]):
        out["rows"].append({"i": i, "cells": [str(c) for c in r]})
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    main()
