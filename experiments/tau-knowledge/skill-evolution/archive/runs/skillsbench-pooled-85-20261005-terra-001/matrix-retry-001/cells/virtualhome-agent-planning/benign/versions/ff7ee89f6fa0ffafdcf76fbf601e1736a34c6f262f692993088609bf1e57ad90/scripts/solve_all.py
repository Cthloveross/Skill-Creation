#!/usr/bin/env python3
"""Incrementally solve every manifest row and commit only replay-valid plans."""
import json
import sys
import time
from pathlib import Path
from fd_setup import build_for, ensure_fast_downward, find_fast_downward
from solve_pddl import solve

def resolve(manifest, value):
    path = Path(value)
    return str(path if path.is_absolute() else manifest.parent / path)

def valid_existing(spec):
    output = Path(spec["plan_output"])
    if not output.is_file(): return None
    result = solve({"domain": spec["domain"], "problem": spec["problem"], "validate_plan": str(output)})
    if result.get("ok"):
        result.update({"plan_output": str(output), "method": "existing replay-valid plan"})
        return result
    return None

def main():
    try:
        request = json.load(sys.stdin)
        manifest = Path(request.get("problem_json", "/app/problem.json"))
        rows = json.loads(manifest.read_text(encoding="utf8"))
        required = ("id", "domain", "problem", "plan_output")
        if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) or not all(isinstance(row.get(k), str) and row[k] for k in required) for row in rows):
            raise ValueError("manifest must be a nonempty array of complete task rows")
        specs, results = [], []
        for row in rows:
            spec = dict(row)
            for key in ("domain", "problem", "plan_output"): spec[key] = resolve(manifest, spec[key])
            specs.append(spec); results.append(valid_existing(spec))
        todo = [i for i, result in enumerate(results) if result is None]
        deadline = time.monotonic() + max(1, int(request.get("timeout_sec", 590)))
        wrapper = find_fast_downward(request.get("fast_downward"))
        setup = "not needed"
        if todo and not wrapper:
            budget = min(max(1, int(request.get("planner_setup_timeout_sec", 180))), max(1, int(deadline - time.monotonic()) - 15))
            wrapper, setup = ensure_fast_downward(request.get("fast_downward"), timeout=budget)
        elif wrapper: setup = "existing Fast Downward"
        profile = build_for(wrapper)
        cap = max(1, int(request.get("per_task_timeout_sec", 45)))
        for position, index in enumerate(todo):
            remaining = int(deadline - time.monotonic())
            still_after = len(todo) - position - 1
            # Give each early task enough time to produce a usable artifact while reserving a
            # short invocation opportunity for every remaining manifest entry.
            seconds = min(cap, remaining - 2 * still_after)
            if not wrapper:
                result = {"ok": False, "valid": False, "error": setup, "plan_output": specs[index]["plan_output"]}
            elif seconds <= 0:
                result = {"ok": False, "valid": False, "error": "shared batch timeout expired", "plan_output": specs[index]["plan_output"]}
            else:
                result = solve(dict(specs[index], fast_downward=wrapper, fast_downward_build=profile,
                                    timeout_sec=seconds, no_setup=True))
            result["id"] = rows[index]["id"]
            results[index] = result
        for index, result in enumerate(results): result["id"] = rows[index]["id"]
        missing = [r["plan_output"] for r in results if not r.get("ok") or not Path(r["plan_output"]).is_file()]
        print(json.dumps({"ok": not missing, "setup": setup, "solved": sum(bool(r.get("ok")) for r in results),
                          "total": len(rows), "missing_outputs": missing, "results": results}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "manifest processing failed: %s" % exc}))
if __name__ == "__main__": main()
