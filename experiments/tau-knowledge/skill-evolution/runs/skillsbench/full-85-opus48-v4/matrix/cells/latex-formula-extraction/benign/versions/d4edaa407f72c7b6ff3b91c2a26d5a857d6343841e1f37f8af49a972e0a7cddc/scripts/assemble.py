#!/usr/bin/env python3
"""Assemble the final markdown output file.

stdin:
  {
    "formulas":   ["raw original", ...],   # required
    "corrected":  ["raw fixed", ...],       # optional, appended after originals
    "output_path": "/root/latex_formula_extraction.md",  # required
    "clean_corrected": true                 # optional, default true
  }
stdout:
  {"written": true, "output_path": ..., "n_originals": N, "n_corrected": M,
   "bracket_report": [...]}  # bracket mismatches still present in originals

Behaviour:
  * Originals are cleaned (tags/numbers/trailing punctuation removed, whitespace
    normalized) and deduplicated preserving first-seen order.
  * Corrected entries are optionally cleaned, then appended after a blank line.
    They are NOT deduplicated against originals (a fix is an additional entry).
  * Writes '$$formula$$' one per line.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from formula_utils import (clean_formula, dedup_preserve_order,  # noqa: E402
                           build_markdown, check_brackets)


def main():
    data = json.load(sys.stdin)
    raw = data.get("formulas", [])
    corrected_raw = data.get("corrected", []) or []
    out_path = data["output_path"]
    clean_corr = data.get("clean_corrected", True)

    originals = [clean_formula(f) for f in raw]
    originals = [f for f in originals if f]
    originals = dedup_preserve_order(originals)

    if clean_corr:
        corrected = [clean_formula(f) for f in corrected_raw]
    else:
        corrected = list(corrected_raw)
    corrected = [f for f in corrected if f]

    content = build_markdown(originals, corrected)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    report = []
    for i, f in enumerate(originals):
        mm = check_brackets(f)
        if mm:
            report.append({"index": i, "formula": f, "mismatches": mm})

    json.dump({"written": True, "output_path": out_path,
               "n_originals": len(originals), "n_corrected": len(corrected),
               "bracket_report": report}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
