#!/usr/bin/env python3
"""Validate \\left/\\right delimiter pairing in formulas.

stdin:  {"formulas": ["...", ...]}
stdout: {"results": [{"index", "formula", "ok", "mismatches": [...]}]}

Each mismatch offers two candidate rewrites: fix_match_close (make the closing
delimiter match the opening) and fix_match_open (make the opening match the
closing). The correct choice is context dependent -- confirm against the PDF.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from formula_utils import check_brackets  # noqa: E402


def main():
    data = json.load(sys.stdin)
    formulas = data.get("formulas", [])
    results = []
    for i, f in enumerate(formulas):
        mm = check_brackets(f)
        results.append({"index": i, "formula": f, "ok": not mm,
                        "mismatches": mm})
    json.dump({"results": results}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
