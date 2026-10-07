#!/usr/bin/env python3
"""Validate that every manifest output is a readable NumPy artifact.
Reads {"problem": path, "root": path} on stdin and emits a JSON report.
"""
import json
import sys
from pathlib import Path
import numpy as np


def schema(array):
    return {"shape": list(array.shape), "dtype": str(array.dtype), "ndim": int(array.ndim)}


def resolved(path_text, root):
    p = Path(path_text)
    return p if p.is_absolute() else root / p


def inspect_output(path):
    if not path.is_file():
        return {"path": str(path), "error": "missing"}
    suffix = path.suffix.lower()
    if suffix not in {".npy", ".npz"}:
        return {"path": str(path), "error": f"unsupported output extension {suffix!r}"}
    try:
        loaded = np.load(path, allow_pickle=False)
        if isinstance(loaded, np.lib.npyio.NpzFile):
            try:
                return {"path": str(path), "kind": "npz", "keys": list(loaded.files),
                        "arrays": {k: schema(loaded[k]) for k in loaded.files}}
            finally:
                loaded.close()
        return {"path": str(path), "kind": "npy", "array": schema(loaded)}
    except Exception as exc:
        return {"path": str(path), "error": f"{type(exc).__name__}: {exc}"}


def main():
    request = json.load(sys.stdin)
    problem = Path(request.get("problem", ""))
    root = Path(request.get("root", "."))
    try:
        tasks = json.loads(problem.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"cannot read manifest: {type(exc).__name__}: {exc}"}))
        raise SystemExit(2)
    if not isinstance(tasks, list):
        print(json.dumps({"ok": False, "error": "manifest root is not a list"}))
        raise SystemExit(2)
    reports = []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or not isinstance(task.get("output"), str):
            reports.append({"task_index": index, "error": "task has no string output field"})
            continue
        report = inspect_output(resolved(task["output"], root))
        report["task_index"] = index
        report["id"] = task.get("id")
        reports.append(report)
    ok = all("error" not in item for item in reports)
    print(json.dumps({"ok": ok, "outputs": reports}, indent=2, sort_keys=True))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
