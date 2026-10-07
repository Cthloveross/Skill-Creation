#!/usr/bin/env python3
"""JSON-stdin launcher that installs the required solution artifact and writes outputs."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin must contain a JSON object")
        script_path = Path(request.get("script_path", "/app/script.txt"))
        solution_path = Path(request.get("solution_path", "/app/solution.py"))
        json_path = Path(request.get("json_path", "/app/dialogue.json"))
        dot_path = Path(request.get("dot_path", "/app/dialogue.dot"))
        if not script_path.is_file():
            raise FileNotFoundError(f"script file not found: {script_path}")

        template = Path(__file__).with_name("solution.py")
        solution_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template, solution_path)

        spec = importlib.util.spec_from_file_location("deployed_dialogue_solution", solution_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("could not load deployed solution")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        graph = module.parse_script(script_path.read_text(encoding="utf-8"))
        module.validate_graph(graph)
        module.write_outputs(graph, json_path, dot_path)
        print(json.dumps({
            "ok": True,
            "solution_path": str(solution_path),
            "json_path": str(json_path),
            "dot_path": str(dot_path),
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
        }, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stdout)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
