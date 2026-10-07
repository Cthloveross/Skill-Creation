#!/usr/bin/env python3
"""JSON stdin/stdout wrapper around solution.py.

Input (stdin JSON, all keys optional):
  {"script_path": "/app/script.txt",
   "out_json": "/app/dialogue.json",
   "out_dot": "/app/dialogue.dot"}
Output (stdout JSON):
  {"nodes": N, "edges": M, "first_node": "...", "errors": [...]}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import solution  # noqa: E402


def main():
    raw = sys.stdin.read().strip()
    cfg = json.loads(raw) if raw else {}
    script_path = cfg.get("script_path", "/app/script.txt")
    out_json = cfg.get("out_json", "/app/dialogue.json")
    out_dot = cfg.get("out_dot", "/app/dialogue.dot")
    graph = solution.build_outputs(script_path, out_json, out_dot)
    errors = solution.validate(graph)
    print(json.dumps({
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "first_node": graph["nodes"][0]["id"] if graph["nodes"] else None,
        "errors": errors,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
