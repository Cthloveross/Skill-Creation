#!/usr/bin/env python3
"""Validate answers.json against the required schema.

Reads JSON from stdin (or a path argv[1]); exits non-zero with messages on any
schema violation. Checks structure only, not correctness of values.
"""
import json
import re
import sys

CUSIP_RE = re.compile(r"^[A-Za-z0-9]{6,9}$")


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    errs = []
    for k in ("q1_answer", "q2_answer", "q3_answer", "q4_answer"):
        if k not in data:
            errs.append(f"missing key {k}")

    if "q1_answer" in data and not isinstance(data["q1_answer"], (int, float)):
        errs.append("q1_answer must be a number")
    if "q2_answer" in data and not isinstance(data["q2_answer"], (int, float)):
        errs.append("q2_answer must be a number")

    q3 = data.get("q3_answer")
    if not isinstance(q3, list) or len(q3) != 5:
        errs.append("q3_answer must be a list of 5 CUSIPs")
    else:
        for i, c in enumerate(q3):
            if not isinstance(c, str) or not CUSIP_RE.match(c.strip()):
                errs.append(f"q3_answer[{i}] not CUSIP-shaped: {c!r}")

    q4 = data.get("q4_answer")
    if not isinstance(q4, list) or len(q4) != 3:
        errs.append("q4_answer must be a list of 3 names")
    else:
        for i, n in enumerate(q4):
            if not isinstance(n, str) or not n.strip():
                errs.append(f"q4_answer[{i}] empty/not a string")

    if errs:
        print("INVALID:")
        for msg in errs:
            print(" -", msg)
        sys.exit(1)
    print("VALID")


if __name__ == "__main__":
    main()
