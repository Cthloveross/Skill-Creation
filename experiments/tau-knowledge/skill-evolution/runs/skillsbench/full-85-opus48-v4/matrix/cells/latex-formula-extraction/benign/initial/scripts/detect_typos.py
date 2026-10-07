#!/usr/bin/env python3
"""Flag unknown / possibly-misspelled LaTeX commands.

stdin:  {"formulas": ["...", ...]}
stdout: {"results": [{"index", "formula", "unknown": [{command, pos, suggestion}]}]}

Heuristic only. Custom macros defined by a paper are legitimate; always confirm
a flagged command against the rendered PDF before correcting.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from formula_utils import detect_unknown_commands  # noqa: E402


def main():
    data = json.load(sys.stdin)
    formulas = data.get("formulas", [])
    results = []
    for i, f in enumerate(formulas):
        results.append({"index": i, "formula": f,
                        "unknown": detect_unknown_commands(f)})
    json.dump({"results": results}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
