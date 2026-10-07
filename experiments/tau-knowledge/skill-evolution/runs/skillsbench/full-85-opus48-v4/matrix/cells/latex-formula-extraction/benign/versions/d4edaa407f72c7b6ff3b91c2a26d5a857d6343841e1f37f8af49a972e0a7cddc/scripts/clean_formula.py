#!/usr/bin/env python3
"""Clean raw display-formula strings.

stdin:  {"formulas": ["raw", ...]}
stdout: {"cleaned": ["cleaned", ...]}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from formula_utils import clean_formula  # noqa: E402


def main():
    data = json.load(sys.stdin)
    formulas = data.get("formulas", [])
    cleaned = [clean_formula(f) for f in formulas]
    json.dump({"cleaned": cleaned}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
