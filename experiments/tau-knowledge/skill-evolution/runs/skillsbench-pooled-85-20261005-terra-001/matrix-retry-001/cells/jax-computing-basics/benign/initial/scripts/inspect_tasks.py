"""Emit metadata for every input named by a manifest.

stdin schema:  {"problem": "/absolute/or/relative/problem.json"}
stdout schema: {"ok": true, "tasks": [{"id", "description", "input",
                "output", "input_format", "arrays"}]}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from task_runtime import TaskDataError, array_metadata, load_input, load_manifest, resolve_path


def main(request: dict) -> dict:
    if not isinstance(request, dict) or not isinstance(request.get("problem"), str):
        raise TaskDataError("stdin must be an object with string field 'problem'")
    problem = Path(request["problem"])
    tasks = load_manifest(problem)
    report = []
    for task in tasks:
        input_path = resolve_path(problem, task["input"])
        output_path = resolve_path(problem, task["output"])
        arrays = load_input(input_path)
        report.append({
            "id": task["id"],
            "description": task["description"],
            "input": str(input_path),
            "output": str(output_path),
            "input_format": input_path.suffix.lower(),
            "arrays": {name: array_metadata(value) for name, value in arrays.items()},
        })
    return {"ok": True, "tasks": report}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        print(json.dumps(main(request), sort_keys=True))
    except (TaskDataError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)
