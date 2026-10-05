#!/usr/bin/env python3
"""Report runtime manifest and NumPy input metadata.

stdin:  {"problem_path": "/app/problem.json"}
stdout: {"tasks": [{"id", "description", "input", "output", "arrays"}, ...]}
"""
import json
import sys
from pathlib import Path
import numpy as np


def resolve(base, value):
    path = Path(value)
    return path if path.is_absolute() else base / path


def metadata(path):
    value = np.load(path, allow_pickle=False)
    if isinstance(value, np.lib.npyio.NpzFile):
        try:
            return [{"key": k, "shape": list(value[k].shape), "dtype": str(value[k].dtype)}
                    for k in value.files]
        finally:
            value.close()
    return [{"key": "input", "shape": list(value.shape), "dtype": str(value.dtype)}]


def main():
    request = json.load(sys.stdin)
    manifest_path = Path(request.get("problem_path", "/app/problem.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise ValueError("problem manifest must be a JSON list")
    tasks = []
    for task in manifest:
        if not isinstance(task, dict) or not {"id", "description", "input", "output"} <= set(task):
            raise ValueError("each manifest item needs id, description, input, and output")
        tasks.append({
            "id": task["id"], "description": task["description"],
            "input": task["input"], "output": task["output"],
            "arrays": metadata(resolve(manifest_path.parent, task["input"])),
        })
    print(json.dumps({"tasks": tasks}, indent=2))


if __name__ == "__main__":
    main()
