#!/usr/bin/env python3
"""Validate every output declared by a manifest.

stdin: {"manifest_path": "/app/problem.json"}
stdout: {"outputs": [{"id", "path", "shape", "dtype"}, ...]}
"""
import json
import sys
from pathlib import Path
import numpy as np


def resolve(base, value):
    path = Path(value)
    return path if path.is_absolute() else base / path


def main():
    spec = json.load(sys.stdin)
    manifest_path = Path(spec.get("manifest_path", "/app/problem.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("manifest must be a nonempty JSON list")
    seen, report = set(), []
    for task in manifest:
        path = resolve(manifest_path.parent, task["output"])
        if path in seen:
            raise ValueError(f"duplicate output path: {path}")
        seen.add(path)
        if not path.is_file():
            raise FileNotFoundError(f"missing output for {task['id']!r}: {path}")
        value = np.load(path, allow_pickle=False)
        if not isinstance(value, np.ndarray):
            raise ValueError(f"{path} is an archive; a single array is required")
        if value.dtype == object or value.size == 0:
            raise ValueError(f"{path} has object dtype or no elements")
        if not (np.issubdtype(value.dtype, np.number) or np.issubdtype(value.dtype, np.bool_)):
            raise ValueError(f"{path} has nonnumeric dtype {value.dtype}")
        if np.issubdtype(value.dtype, np.inexact) and not np.isfinite(value).all():
            raise ValueError(f"{path} contains NaN or infinity")
        report.append({"id": task["id"], "path": str(path),
                       "shape": list(value.shape), "dtype": str(value.dtype)})
    print(json.dumps({"outputs": report}, indent=2))


if __name__ == "__main__":
    main()
