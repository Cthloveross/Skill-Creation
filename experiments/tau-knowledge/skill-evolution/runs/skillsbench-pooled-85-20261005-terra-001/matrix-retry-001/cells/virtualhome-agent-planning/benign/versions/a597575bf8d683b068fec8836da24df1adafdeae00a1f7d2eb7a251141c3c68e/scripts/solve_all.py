#!/usr/bin/env python3
"""Incrementally generate validated plan files for every problem.json row."""
import json
import sys
import time
from pathlib import Path
from fd_setup import ensure_fast_downward
from solve_pddl import solve

def main():
    try:
        request = json.load(sys.stdin)
        manifest = Path(request.get("problem_json", "/app/problem.json"))
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            raise ValueError("manifest must be a nonempty JSON array")
        for row in rows:
            if not isinstance(row, dict) or not all(isinstance(row.get(k), str) and row[k] for k in ("id", "domain", "problem", "plan_output")):
                raise ValueError("each row requires nonempty id, domain, problem, and plan_output strings")
        total_timeout = max(1, int(request.get("timeout_sec", 590)))
        deadline = time.monotonic() + total_timeout
        build_limit = max(1, min(int(request.get("planner_build_timeout_sec", 300)), total_timeout - 1))
        executable, setup = ensure_fast_downward(request.get("fast_downward"), timeout=build_limit)
        results = []
        for index, row in enumerate(rows):
            spec = dict(row)
            for key in ("domain", "problem", "plan_output"):
                value = Path(spec[key]); spec[key] = str(value if value.is_absolute() else manifest.parent / value)
            remaining = int(deadline - time.monotonic())
            left = len(rows) - index
            if not executable:
                result = {"ok": False, "valid": False, "error": setup, "plan_output": spec["plan_output"]}
            elif remaining <= 0:
                result = {"ok": False, "valid": False, "error": "shared batch timeout expired", "plan_output": spec["plan_output"]}
            else:
                # Early small instances cannot monopolize the whole batch; unused time rolls forward.
                spec["fast_downward"] = executable
                spec["timeout_sec"] = max(1, max(10, remaining // left))
                result = solve(spec)
            result["id"] = row["id"]
            results.append(result)
        missing = [r["plan_output"] for r in results if not r.get("ok") or not Path(r["plan_output"]).is_file()]
        print(json.dumps({"ok": not missing, "setup": setup, "solved": sum(bool(r.get("ok")) for r in results),
                          "total": len(rows), "missing_outputs": missing, "results": results}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "manifest processing failed: %s" % exc}))
if __name__ == "__main__":
    main()
