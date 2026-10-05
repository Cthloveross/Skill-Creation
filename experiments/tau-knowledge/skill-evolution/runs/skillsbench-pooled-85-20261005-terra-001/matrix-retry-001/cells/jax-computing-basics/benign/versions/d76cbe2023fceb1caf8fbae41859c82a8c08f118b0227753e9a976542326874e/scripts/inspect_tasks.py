"""Inspect all arrays named by a task manifest.
stdin: {"problem": "path"}; stdout: JSON metadata or JSON error.
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
    report = []
    for task in load_manifest(problem):
        source = resolve_path(problem, task["input"])
        destination = resolve_path(problem, task["output"])
        arrays = load_input(source)
        report.append({"id": task["id"], "description": task["description"],
                       "input": str(source), "output": str(destination),
                       "input_format": source.suffix.lower(),
                       "arrays": {k: array_metadata(v) for k, v in arrays.items()}})
    return {"ok": True, "tasks": report}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (TaskDataError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)
