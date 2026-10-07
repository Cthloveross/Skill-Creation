#!/usr/bin/env python3
"""Deterministic entrypoint for the dialogue-parser task.

Running this ONE command (no stdin required) fully completes the task:
  1. installs the deliverable parser module to the import path the validator
     uses (default /app/solution.py), so `import solution` / `parse_script`
     work regardless of the current working directory;
  2. parses the script and writes the JSON graph and the DOT visualization;
  3. prints a JSON summary and exits nonzero if any constraint is violated.

Optional JSON config on stdin (all keys optional; shown with defaults):
  {"script_path": "/app/script.txt",
   "out_json":    "/app/dialogue.json",
   "out_dot":     "/app/dialogue.dot",
   "solution_dst":"/app/solution.py"}

Stdout JSON schema:
  {"solution_path": "...", "script_path": "...", "out_json": "...",
   "out_dot": "...", "nodes": N, "edges": M, "first_node": "...",
   "errors": [...]}
An empty "errors" list means all three graph constraints hold.
"""
import json
import os
import shutil
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)
import solution  # noqa: E402  (packaged helper in the same scripts/ dir)


def _read_cfg():
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read().strip()
    except Exception:
        raw = ""
    return json.loads(raw) if raw else {}


def main():
    cfg = _read_cfg()
    script_path = cfg.get("script_path", "/app/script.txt")
    out_json = cfg.get("out_json", "/app/dialogue.json")
    out_dot = cfg.get("out_dot", "/app/dialogue.dot")
    solution_dst = cfg.get("solution_dst", "/app/solution.py")

    # 1) Install the deliverable module where the validator imports `solution`.
    src = os.path.join(_SCRIPTS_DIR, "solution.py")
    dst = os.path.abspath(solution_dst)
    if os.path.abspath(src) != dst:
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copyfile(src, dst)

    # 2) Parse and write the artifacts.
    graph = solution.build_outputs(script_path, out_json, out_dot)

    # 3) Validate and report.
    errors = solution.validate(graph)
    summary = {
        "solution_path": dst,
        "script_path": script_path,
        "out_json": out_json,
        "out_dot": out_dot,
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "first_node": graph["nodes"][0]["id"] if graph["nodes"] else None,
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
