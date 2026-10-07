#!/usr/bin/env python3
"""Syntactic check of generated plan files (local verification, not grading).

Stdin  (JSON): {"problem_json": str?, "base_dir": str?}
Stdout (JSON): {"items": [...], "summary": {...}}

For each manifest entry it verifies that plan_output exists and that every
non-blank line matches the required `name(arg, arg, ...)` shape.
"""
import json
import os
import re
import sys

LINE_RE = re.compile(r"^[^()\s]+\((|[^()]*)\)$")


def resolve(base_dir, p):
    if os.path.isabs(p):
        return p
    return os.path.normpath(os.path.join(base_dir, p))


def main():
    try:
        raw = sys.stdin.read()
        cfg = json.loads(raw) if raw.strip() else {}
    except Exception:
        cfg = {}
    problem_json = cfg.get("problem_json", "/app/problem.json")
    if not os.path.exists(problem_json):
        print(json.dumps({"items": [], "summary": {"error": "manifest missing"}}))
        return
    base_dir = cfg.get("base_dir") or os.path.dirname(
        os.path.abspath(problem_json))
    with open(problem_json) as f:
        manifest = json.load(f)
    if isinstance(manifest, dict):
        manifest = [manifest]

    items = []
    for item in manifest:
        out = item.get("plan_output")
        rec = {"id": item.get("id"), "plan_output": out,
               "exists": False, "lines": 0, "malformed": 0, "empty": True}
        if not out:
            items.append(rec)
            continue
        out_p = resolve(base_dir, out)
        rec["exists"] = os.path.exists(out_p)
        if rec["exists"]:
            with open(out_p) as f:
                for line in f:
                    s = line.strip()
                    if not s:
                        continue
                    rec["lines"] += 1
                    if not LINE_RE.match(s):
                        rec["malformed"] += 1
            rec["empty"] = rec["lines"] == 0
        items.append(rec)

    summary = {
        "total": len(items),
        "missing_files": sum(1 for r in items if not r["exists"]),
        "empty_files": sum(1 for r in items if r["exists"] and r["empty"]),
        "files_with_malformed_lines":
            sum(1 for r in items if r["malformed"] > 0),
        "nonempty_files": sum(1 for r in items
                              if r["exists"] and not r["empty"]),
    }
    print(json.dumps({"items": items, "summary": summary}))


if __name__ == "__main__":
    main()
