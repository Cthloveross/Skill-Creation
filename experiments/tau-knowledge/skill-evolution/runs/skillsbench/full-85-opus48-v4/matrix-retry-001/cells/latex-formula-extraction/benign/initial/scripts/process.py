#!/usr/bin/env python3
"""End-to-end assembly for LaTeX display-formula extraction.

Stdin JSON:
  {
    "output_path": "/root/latex_formula_extraction.md",   # optional
    "formulas": ["<raw latex, $$ optional>", ...],         # required
    "manual_corrections": [{"original": "...", "fixed": "..."}],  # optional
    "auto_fix_brackets": true                              # optional, default true
  }

Behaviour:
  1. clean every formula (strip tags/trailing punctuation/numbering, normalize ws)
  2. de-duplicate (order preserved) -> the "originals" section
  3. validate \\left/\\right pairing on each original
  4. build the "corrected" section: a manual correction wins; otherwise, when
     auto_fix_brackets is on and the formula has a delimiter mismatch, append the
     auto-fixed candidate. A correction is appended only if it differs from the
     original, is not already an original, and is not already appended.
  5. write the markdown file: originals first, a blank line, then corrections.

Stdout JSON: report with cleaned list, corrected list, per-formula bracket issues.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from formula_utils import (  # noqa: E402
    clean_formula,
    dedup,
    validate_brackets,
    auto_fix_brackets,
)

DEFAULT_OUTPUT = "/root/latex_formula_extraction.md"


def build_file(cleaned, corrected):
    lines = [f"$${f}$$" for f in cleaned]
    content = "\n".join(lines)
    if lines:
        content += "\n"
    if corrected:
        content += "\n" + "\n".join(f"$${f}$$" for f in corrected) + "\n"
    return content


def main():
    data = json.load(sys.stdin)
    output_path = data.get("output_path") or DEFAULT_OUTPUT
    raw_formulas = data.get("formulas", [])
    auto = data.get("auto_fix_brackets", True)
    manual_in = data.get("manual_corrections", []) or []

    cleaned = dedup([clean_formula(f) for f in raw_formulas if clean_formula(f)])

    manual = {}
    for c in manual_in:
        o = clean_formula(c.get("original", ""))
        f = clean_formula(c.get("fixed", ""))
        if o:
            manual[o] = f

    corrected = []
    bracket_issues = []
    for orig in cleaned:
        res = validate_brackets(orig)
        if res["mismatches"] or res["unmatched"]:
            bracket_issues.append({
                "formula": orig,
                "mismatches": res["mismatches"],
                "unmatched": res["unmatched"],
            })
        fix = None
        if orig in manual:
            fix = manual[orig]
        elif auto and res["mismatches"]:
            cand = auto_fix_brackets(orig)
            if cand != orig:
                fix = cand
        if fix and fix != orig and fix not in cleaned and fix not in corrected:
            corrected.append(fix)

    # Also honour manual corrections whose original was not among cleaned originals
    # (e.g. the executor passed a slightly different original form) by appending
    # their fixed version if non-trivial and not already present.
    for o, f in manual.items():
        if o not in cleaned and f and f != o and f not in cleaned and f not in corrected:
            corrected.append(f)

    content = build_file(cleaned, corrected)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    report = {
        "output_path": output_path,
        "cleaned": cleaned,
        "corrected": corrected,
        "bracket_issues": bracket_issues,
        "written": len(content.encode("utf-8")),
    }
    json.dump(report, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
