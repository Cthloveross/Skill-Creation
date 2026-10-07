#!/usr/bin/env python3
"""Standalone \\left/\\right bracket validator.

Stdin JSON: {"formula": "<latex content, $$ optional>"}
Stdout JSON: {"formula", "cleaned", "tokens", "mismatches", "unmatched", "auto_fix"}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from formula_utils import clean_formula, validate_brackets, auto_fix_brackets  # noqa: E402


def main():
    data = json.load(sys.stdin)
    raw = data.get("formula", "")
    cleaned = clean_formula(raw)
    res = validate_brackets(cleaned)
    out = {
        "formula": raw,
        "cleaned": cleaned,
        "tokens": res["tokens"],
        "mismatches": res["mismatches"],
        "unmatched": res["unmatched"],
        "auto_fix": auto_fix_brackets(cleaned),
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
