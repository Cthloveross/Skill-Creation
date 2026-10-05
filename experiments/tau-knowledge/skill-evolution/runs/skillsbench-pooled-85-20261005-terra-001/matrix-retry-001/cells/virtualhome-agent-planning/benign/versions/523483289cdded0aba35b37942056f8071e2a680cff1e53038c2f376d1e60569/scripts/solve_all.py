#!/usr/bin/env python3
"""Solve every row of a public PDDL problem.json manifest sequentially."""
import json, sys
from pathlib import Path
from solve_pddl import solve

def main():
    try:
        request = json.load(sys.stdin)
        manifest_path = Path(request.get("problem_json", "/app/problem.json"))
        rows = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list): raise ValueError("manifest must be a JSON array")
        results = []
        for row in rows:
            if not isinstance(row, dict): raise ValueError("manifest row is not an object")
            spec = dict(row)
            # Manifest-relative paths remain usable when a manifest does not use /app paths.
            for key in ("domain", "problem", "plan_output"):
                if key in spec and not Path(spec[key]).is_absolute(): spec[key] = str(manifest_path.parent / spec[key])
            for key in ("fast_downward", "timeout_sec", "max_states", "use_external"):
                if key in request: spec[key] = request[key]
            result = solve(spec); result["id"] = row.get("id")
            results.append(result)
        solved = sum(bool(x.get("ok")) for x in results)
        print(json.dumps({"ok": solved == len(results), "solved": solved, "total": len(results), "results": results}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "manifest processing failed: %s" % exc}))
if __name__ == "__main__": main()
