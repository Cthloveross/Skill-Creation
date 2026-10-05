#!/usr/bin/env python3
"""Solve manifest rows incrementally and commit only replay-valid plan files."""
import json
import sys
import time
from pathlib import Path
from fd_setup import ensure_fast_downward
from solve_pddl import solve


def resolve(manifest, value):
    path = Path(value)
    return str(path if path.is_absolute() else manifest.parent / path)


def retained(spec):
    target = Path(spec["plan_output"])
    if not target.is_file():
        return None
    result = solve({"domain": spec["domain"], "problem": spec["problem"],
                    "validate_plan": str(target)})
    if result.get("ok"):
        result.update({"plan_output": str(target), "method": "existing replay-valid plan"})
        return result
    return None


def main():
    try:
        request = json.load(sys.stdin)
        manifest = Path(request.get("problem_json", "/app/problem.json"))
        rows = json.loads(manifest.read_text(encoding="utf8"))
        required = ("id", "domain", "problem", "plan_output")
        if (not isinstance(rows, list) or not rows or
                any(not isinstance(row, dict) or
                    not all(isinstance(row.get(key), str) and row[key] for key in required)
                    for row in rows)):
            raise ValueError("manifest must be a nonempty array of id/domain/problem/plan_output rows")

        specs, results = [], []
        for row in rows:
            spec = dict(row)
            for key in ("domain", "problem", "plan_output"):
                spec[key] = resolve(manifest, spec[key])
            specs.append(spec)
            results.append(retained(spec))

        todo = [i for i, result in enumerate(results) if result is None]
        deadline = time.monotonic() + max(1, int(request.get("timeout_sec", 585)))
        driver = profile = None
        setup = "not needed; all artifacts already replay-valid"
        if todo:
            setup_budget = min(int(request.get("planner_setup_timeout_sec", 240)),
                               max(1, int(deadline - time.monotonic()) - 15))
            driver, profile = ensure_fast_downward(request.get("fast_downward"), timeout=setup_budget)
            setup = "Fast Downward ready" if driver else str(profile)

        cap = max(1, int(request.get("per_task_timeout_sec", 300)))
        for position, index in enumerate(todo):
            remaining_rows = len(todo) - position
            remaining_seconds = int(deadline - time.monotonic())
            # Give the current task a substantial usable budget while reserving time
            # for later required outputs. A successfully committed row is never lost.
            fair_share = max(1, remaining_seconds // remaining_rows)
            allotted = min(cap, fair_share)
            if not driver:
                result = {"ok": False, "valid": False, "error": setup,
                          "plan_output": specs[index]["plan_output"]}
            elif remaining_seconds <= 0:
                result = {"ok": False, "valid": False, "error": "shared batch timeout expired",
                          "plan_output": specs[index]["plan_output"]}
            else:
                payload = dict(specs[index], fast_downward=driver,
                               fast_downward_build=profile, no_setup=True,
                               timeout_sec=allotted)
                result = solve(payload)
            result["id"] = rows[index]["id"]
            results[index] = result

        for index, result in enumerate(results):
            result["id"] = rows[index]["id"]
        missing = [result["plan_output"] for result in results
                   if not result.get("ok") or not Path(result["plan_output"]).is_file()]
        print(json.dumps({"ok": not missing, "setup": setup,
                          "solved": sum(bool(result.get("ok")) for result in results),
                          "total": len(rows), "missing_outputs": missing,
                          "results": results}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "manifest processing failed: %s" % exc}))


if __name__ == "__main__":
    main()
