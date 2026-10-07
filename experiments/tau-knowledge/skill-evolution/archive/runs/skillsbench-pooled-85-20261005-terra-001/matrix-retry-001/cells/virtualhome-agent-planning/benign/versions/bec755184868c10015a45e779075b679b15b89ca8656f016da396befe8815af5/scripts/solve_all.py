#!/usr/bin/env python3
"""Incrementally solve a complete manifest while preserving valid artifacts."""
import json
import sys
import time
from pathlib import Path
from fd_setup import ensure_fast_downward, find_fast_downward
from solve_pddl import solve


def _resolve(manifest, value):
    path = Path(value)
    return str(path if path.is_absolute() else manifest.parent / path)


def _existing(spec):
    path = Path(spec["plan_output"])
    if not path.is_file():
        return None
    result = solve({"domain": spec["domain"], "problem": spec["problem"], "validate_plan": str(path)})
    if result.get("ok"):
        result.update({"plan_output": str(path), "method": "existing replay-valid plan"})
        return result
    return None


def main():
    try:
        request = json.load(sys.stdin)
        manifest = Path(request.get("problem_json", "/app/problem.json"))
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        required = ("id", "domain", "problem", "plan_output")
        if not isinstance(rows, list) or not rows or any(
            not isinstance(row, dict) or not all(isinstance(row.get(key), str) and row[key] for key in required)
            for row in rows
        ):
            raise ValueError("manifest must be a nonempty array of complete task rows")

        specs, results = [], [None] * len(rows)
        for index, row in enumerate(rows):
            spec = dict(row)
            for key in ("domain", "problem", "plan_output"):
                spec[key] = _resolve(manifest, spec[key])
            specs.append(spec)
            results[index] = _existing(spec)

        unresolved = [i for i, result in enumerate(results) if result is None]
        deadline = time.monotonic() + max(1, int(request.get("timeout_sec", 590)))
        executable = find_fast_downward(request.get("fast_downward"))
        setup = "not needed"
        if unresolved and not executable:
            # Retain a substantial solve budget after a one-time compiler build.
            allowed = min(max(1, int(request.get("planner_setup_timeout_sec", 250))),
                          max(1, int(deadline - time.monotonic()) - 45))
            executable, setup = ensure_fast_downward(request.get("fast_downward"), timeout=allowed)
        elif executable:
            setup = "existing Fast Downward"

        for ordinal, index in enumerate(unresolved):
            spec = specs[index]
            remaining_rows = len(unresolved) - ordinal
            remaining = max(0, int(deadline - time.monotonic()))
            if not executable:
                result = {"ok": False, "valid": False, "error": setup, "plan_output": spec["plan_output"]}
            elif remaining <= 0:
                result = {"ok": False, "valid": False, "error": "shared batch timeout expired", "plan_output": spec["plan_output"]}
            else:
                # Fair slices ensure an early difficult instance cannot prevent all
                # later mandatory files from being attempted.
                seconds = max(1, remaining // remaining_rows)
                result = solve(dict(spec, fast_downward=executable, timeout_sec=seconds, no_setup=True))
            result["id"] = rows[index]["id"]
            results[index] = result

        for index, result in enumerate(results):
            result["id"] = rows[index]["id"]
        missing = [result["plan_output"] for result in results
                   if not result.get("ok") or not Path(result["plan_output"]).is_file()]
        print(json.dumps({"ok": not missing, "setup": setup,
                          "solved": sum(bool(result.get("ok")) for result in results),
                          "total": len(rows), "missing_outputs": missing, "results": results}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "manifest processing failed: %s" % exc}))

if __name__ == "__main__":
    main()
