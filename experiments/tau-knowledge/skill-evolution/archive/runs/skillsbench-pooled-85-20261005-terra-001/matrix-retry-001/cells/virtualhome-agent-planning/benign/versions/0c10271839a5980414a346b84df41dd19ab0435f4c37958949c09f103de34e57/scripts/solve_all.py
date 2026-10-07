#!/usr/bin/env python3
"""Generate validated plan files for every row in a problem.json manifest."""
import json, sys, time
from pathlib import Path
from solve_pddl import solve

def main():
    try:
        request = json.load(sys.stdin)
        manifest = Path(request.get("problem_json", "/app/problem.json"))
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows: raise ValueError("manifest must be a nonempty JSON array")
        deadline = time.monotonic() + int(request.get("timeout_sec", 570))
        results = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or not all(isinstance(row.get(k), str) and row[k] for k in ("id", "domain", "problem", "plan_output")):
                raise ValueError("each manifest row requires id, domain, problem, and plan_output strings")
            spec = dict(row)
            for key in ("domain", "problem", "plan_output"):
                p = Path(spec[key]); spec[key] = str(p if p.is_absolute() else manifest.parent / p)
            for key in ("fast_downward", "max_states", "use_external"):
                if key in request: spec[key] = request[key]
            remaining = int(deadline - time.monotonic())
            if remaining <= 0:
                result = {"ok": False, "error": "shared batch timeout expired", "plan_output": spec["plan_output"]}
            else:
                spec["timeout_sec"] = remaining
                result = solve(spec)
            result["id"] = row["id"]; results.append(result)
        missing = [r["plan_output"] for r in results if not r.get("ok") or not Path(r["plan_output"]).is_file()]
        solved = sum(bool(r.get("ok")) for r in results)
        print(json.dumps({"ok": not missing, "solved": solved, "total": len(rows), "missing_outputs": missing, "results": results}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "manifest processing failed: %s" % exc}))
if __name__ == "__main__": main()
