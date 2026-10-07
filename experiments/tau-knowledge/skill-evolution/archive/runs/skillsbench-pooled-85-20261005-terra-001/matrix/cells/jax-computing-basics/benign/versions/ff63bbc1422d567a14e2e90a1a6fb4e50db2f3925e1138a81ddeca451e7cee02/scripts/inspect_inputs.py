#!/usr/bin/env python3
"""Inspect a task manifest and its NumPy inputs without reading array values.

stdin:  {"problem_path": "/app/problem.json"}
stdout: {"tasks": [{"id", "description", "input", "output", "arrays": [...]}, ...]}
"""
import json
import sys
from pathlib import Path
import numpy as np


def resolve(base: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else base / p


def array_metadata(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"input does not exist: {path}")
    loaded = np.load(path, allow_pickle=False)
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            return [
                {"key": key, "shape": list(loaded[key].shape), "dtype": str(loaded[key].dtype)}
                for key in loaded.files
            ]
        finally:
            loaded.close()
    return [{"key": "input", "shape": list(loaded.shape), "dtype": str(loaded.dtype)}]


def main():
    request = json.load(sys.stdin)
    manifest_path = Path(request.get("problem_path", "/app/problem.json"))
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("problem manifest must be a JSON list")
    tasks = []
    for task in raw:
        if not isinstance(task, dict) or not {"id", "description", "input", "output"} <= task.keys():
            raise ValueError("each task requires id, description, input, and output")
        input_path = resolve(manifest_path.parent, task["input"])
        tasks.append({
            "id": task["id"], "description": task["description"],
            "input": task["input"], "output": task["output"],
            "arrays": array_metadata(input_path),
        })
    print(json.dumps({"tasks": tasks}, indent=2))


if __name__ == "__main__":
    main()
