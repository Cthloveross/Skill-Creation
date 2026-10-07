#!/usr/bin/env python3
"""Incrementally generate replay-valid plan files for every manifest task."""
import json
import sys
import time
from pathlib import Path

from fd_setup import ensure_fast_downward
from solve_pddl import solve


def _resolve(manifest, value):
    path = Path(value)
    return str(path if path.is_absolute() else manifest.parent / path)


def _existing(spec):
    target = Path(spec["plan_output"])
    if not target.is_file():
        return None
    checked = solve({"domain": spec["domain"], "problem": spec["problem"], "validate_plan": str(target)})
    if checked.get("ok"):
        checked.update({"plan_output": str(target), "method": "existing replay-valid plan"})
        return checked
    return None


def _slice_seconds(remaining, remaining_rows):
    # Preserve eight seconds for each later unresolved row, but permit a useful
    # bounded search attempt now. Unused time automatically rolls to later rows.
    reserve = 8 * max(0, remaining_rows - 1)
    available = max(1, remaining - reserve)
    return max(8, min(30, available))


def main():
    try:
        request = json.load(sys.stdin)
        manifest = Path(request.get("problem_json", "/app/problem.json"))
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            raise ValueError("manifest must be a nonempty JSON array")
        required = ("id", "domain", "problem", "plan_output")
        if any(not isinstance(row, dict) or not all(isinstance(row.get(key), str) and row[key] for key in required)
               for row in rows):
            raise ValueError("each row requires nonempty id, domain, problem, and plan_output strings")
        total = max(1, int(request.get("timeout_sec", 590)))
        deadline = time.monotonic() + total
        setup_budget = max(1, min(int(request.get("planner_setup_timeout_sec", 150)), total // 3))
        executable, setup = ensure_fast_downward(request.get("fast_downward"), timeout=setup_budget)
        results = []
        for index, row in enumerate(rows):
            spec = dict(row)
            for key in ("domain", "problem", "plan_output"):
                spec[key] = _resolve(manifest, spec[key])
            prior = _existing(spec)
            if prior is not None:
                result = prior
            elif not executable:
                result = {"ok": False, "valid": False, "error": setup, "plan_output": spec["plan_output"]}
            else:
                remaining = int(deadline - time.monotonic())
                if remaining <= 0:
                    result = {"ok": False, "valid": False, "error": "shared batch timeout expired",
                              "plan_output": spec["plan_output"]}
                else:
                    spec["fast_downward"] = executable
                    spec["timeout_sec"] = _slice_seconds(remaining, len(rows) - index)
                    result = solve(spec)
            result["id"] = row["id"]
            results.append(result)
        missing = [result["plan_output"] for result in results
                   if not result.get("ok") or not Path(result["plan_output"]).is_file()]
        print(json.dumps({"ok": not missing, "setup": setup,
                          "solved": sum(bool(result.get("ok")) for result in results),
                          "total": len(rows), "missing_outputs": missing, "results": results}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "manifest processing failed: %s" % exc}))


if __name__ == "__main__":
    main()
