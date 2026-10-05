#!/usr/bin/env python3
"""Validate every .npy output declared in a task manifest.

stdin:  {"manifest_path": "/app/problem.json"}  (path optional)
stdout: {"outputs": [{"id", "path", "shape", "dtype"}, ...]}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
import numpy as np


def resolve(base: Path, name: str) -> Path:
    path = Path(str(name))
    return path if path.is_absolute() else base / path


def main():
    request = json.load(sys.stdin)
    if not isinstance(request, dict):
        raise ValueError("stdin must be a JSON object")
    manifest_path = Path(request.get("manifest_path", "/app/problem.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("manifest must be a nonempty list")

    seen, report = set(), []
    for task in manifest:
        if not isinstance(task, dict) or not {"id", "output"}.issubset(task):
            raise ValueError("invalid manifest task")
        path = resolve(manifest_path.parent, task["output"])
        if path in seen:
            raise ValueError("duplicate output path: %s" % path)
        seen.add(path)
        if not path.is_file():
            raise FileNotFoundError("missing output for %r: %s" % (task["id"], path))
        value = np.load(path, allow_pickle=False)
        if not isinstance(value, np.ndarray):
            raise ValueError("output is not a single array: %s" % path)
        if value.dtype == object or value.size == 0:
            raise ValueError("output is object dtype or empty: %s" % path)
        if not (np.issubdtype(value.dtype, np.number) or np.issubdtype(value.dtype, np.bool_)):
            raise ValueError("output is nonnumeric (%s): %s" % (value.dtype, path))
        if np.issubdtype(value.dtype, np.inexact) and not np.isfinite(value).all():
            raise ValueError("output contains NaN or infinity: %s" % path)
        report.append({"id": task["id"], "path": str(path),
                       "shape": list(value.shape), "dtype": str(value.dtype)})
    print(json.dumps({"outputs": report}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("validate_outputs failed: %s" % exc, file=sys.stderr)
        raise
