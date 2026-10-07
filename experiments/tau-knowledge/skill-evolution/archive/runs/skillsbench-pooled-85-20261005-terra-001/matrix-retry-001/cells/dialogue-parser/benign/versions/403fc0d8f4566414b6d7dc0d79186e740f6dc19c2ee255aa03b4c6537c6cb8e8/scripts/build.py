#!/usr/bin/env python3
"""Install the packaged parser and generate dialogue artifacts.

Optional stdin JSON: {"input_path": str, "solution_path": str,
"json_path": str, "dot_path": str}.  Output is one JSON status object.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    try:
        raw = sys.stdin.read().strip()
        request = json.loads(raw) if raw else {}
        if not isinstance(request, dict):
            raise ValueError("stdin request must be a JSON object")
        defaults = {
            "input_path": "/app/script.txt",
            "solution_path": "/app/solution.py",
            "json_path": "/app/dialogue.json",
            "dot_path": "/app/dialogue.dot",
        }
        paths = {}
        for key, default in defaults.items():
            value = request.get(key, default)
            if not isinstance(value, str) or not value:
                raise ValueError("%s must be a nonempty path string" % key)
            paths[key] = Path(value)

        source = Path(__file__).resolve().parent.parent / "references" / "solution.py"
        paths["solution_path"].parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, paths["solution_path"])

        spec = importlib.util.spec_from_file_location("dialogue_solution", paths["solution_path"])
        if spec is None or spec.loader is None:
            raise RuntimeError("could not load installed solution")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        graph = module.parse_script(paths["input_path"].read_text(encoding="utf-8"))
        paths["json_path"].parent.mkdir(parents=True, exist_ok=True)
        paths["dot_path"].parent.mkdir(parents=True, exist_ok=True)
        paths["json_path"].write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths["dot_path"].write_text(module.graph_to_dot(graph), encoding="utf-8")
        print(json.dumps({"ok": True, "paths": [str(paths[k]) for k in ("solution_path", "json_path", "dot_path")]}))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
