#!/usr/bin/env python3
"""Incrementally solve every manifest task and commit only replay-valid plans."""
import json
import sys
import time
from pathlib import Path
from fd_setup import ensure_fast_downward
from solve_pddl import solve


def resolve(manifest, value):
    path = Path(value)
    return str(path if path.is_absolute() else manifest.parent / path)


def existing(spec):
    target = Path(spec["plan_output"])
    if not target.is_file():
        return None
    result = solve({"domain": spec["domain"], "problem": spec["problem"], "validate_plan": str(target)})
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
        if not isinstance(rows, list) or not rows or any(not isinstance(r, dict) or not all(isinstance(r.get(k), str) and r[k] for k in required) for r in rows):
            raise ValueError("manifest must be a nonempty array of id/domain/problem/plan_output rows")
        specs = []
        results = []
        for row in rows:
            spec = dict(row)
            for key in ("domain", "problem", "plan_output"):
                spec[key] = resolve(manifest, spec[key])
            specs.append(spec); results.append(existing(spec))
        todo = [i for i, value in enumerate(results) if value is None]
        deadline = time.monotonic() + max(1, int(request.get("timeout_sec", 590)))
        driver = profile = None
        setup = "not needed"
        if todo:
            budget = min(int(request.get("planner_setup_timeout_sec", 360)), max(1, int(deadline - time.monotonic()) - 10))
            driver, profile = ensure_fast_downward(request.get("fast_downward"), timeout=budget)
            setup = "Fast Downward ready" if driver else str(profile)
        cap = max(1, int(request.get("per_task_timeout_sec", 100)))
        for position, index in enumerate(todo):
            left = len(todo) - position
            remaining = int(deadline - time.monotonic())
            # Fair sharing prevents an early hard instance from consuming the entire batch.
            allotted = min(cap, max(1, remaining // left))
            if not driver:
                result = {"ok": False, "valid": False, "error": setup, "plan_output": specs[index]["plan_output"]}
            elif allotted <= 0:
                result = {"ok": False, "valid": False, "error": "shared batch timeout expired", "plan_output": specs[index]["plan_output"]}
            else:
                payload = dict(specs[index], fast_downward=driver, fast_downward_build=profile,
                               timeout_sec=allotted, no_setup=True)
                result = solve(payload)
            result["id"] = rows[index]["id"]
            results[index] = result
        for index, result in enumerate(results):
            result["id"] = rows[index]["id"]
        missing = [r["plan_output"] for r in results if not r.get("ok") or not Path(r["plan_output"]).is_file()]
        print(json.dumps({"ok": not missing, "setup": setup, "solved": sum(bool(r.get("ok")) for r in results),
                          "total": len(rows), "missing_outputs": missing, "results": results}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "manifest processing failed: %s" % exc}))

if __name__ == "__main__": main()
