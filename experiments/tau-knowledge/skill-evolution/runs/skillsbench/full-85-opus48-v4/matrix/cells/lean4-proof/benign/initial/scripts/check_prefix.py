#!/usr/bin/env python3
"""Verify that the fixed prefix of a Lean solution file is unchanged.

stdin  JSON: {"file": str, "reference": str (optional backup of original),
              "lines": int (optional, # of fixed prefix lines)}
stdout JSON: {"file_total_lines", "head",
              and when reference given: "prefix_match", "diffs"}

Split on "\n" so that a leading blank line is counted as line 1, matching the
grader's exact-prefix check (including the leading blank line).
"""
import json
import sys


def read_lines(path: str):
    with open(path, encoding="utf-8") as fh:
        return fh.read().split("\n")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    f = data.get("file", "/app/workspace/solution.lean")
    ref = data.get("reference")
    n = data.get("lines")

    cur = read_lines(f)
    res = {"file_total_lines": len(cur)}
    if ref:
        r = read_lines(ref)
        nn = n if n is not None else len(r)
        a = cur[:nn]
        b = r[:nn]
        res["prefix_match"] = a == b
        if a != b:
            diffs = []
            for i in range(max(len(a), len(b))):
                x = a[i] if i < len(a) else "<none>"
                y = b[i] if i < len(b) else "<none>"
                if x != y:
                    diffs.append({"line": i + 1, "current": x, "reference": y})
            res["diffs"] = diffs
    head_n = n if n is not None else 20
    res["head"] = cur[:head_n]
    print(json.dumps(res))


if __name__ == "__main__":
    main()
