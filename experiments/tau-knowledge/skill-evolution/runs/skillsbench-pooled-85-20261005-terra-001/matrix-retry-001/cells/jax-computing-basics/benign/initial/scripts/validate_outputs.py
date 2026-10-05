"""Validate that manifest outputs exist, are NumPy-loadable, and meet checks.

stdin schema:
{"problem": "...", "checks": {
  "task-id": {"shape": [...], "ndim": 2, "dtype": "float32",
              "finite": true, "npz_keys": ["..."]}
}}
All check fields are optional.  stdout contains metadata and a list of failures.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from task_runtime import TaskDataError, array_metadata, load_input, load_manifest, resolve_path


def _check_array(meta: dict[str, Any], array: np.ndarray, check: dict[str, Any], label: str) -> list[str]:
    failures: list[str] = []
    if "shape" in check and list(check["shape"]) != meta["shape"]:
        failures.append(f"{label}: shape {meta['shape']} != expected {list(check['shape'])}")
    if "ndim" in check and check["ndim"] != meta["ndim"]:
        failures.append(f"{label}: ndim {meta['ndim']} != expected {check['ndim']}")
    if "dtype" in check and str(check["dtype"]) != meta["dtype"]:
        failures.append(f"{label}: dtype {meta['dtype']} != expected {check['dtype']}")
    if check.get("finite") is True and np.issubdtype(array.dtype, np.number) and not np.all(np.isfinite(array)):
        failures.append(f"{label}: contains non-finite numeric values")
    return failures


def main(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict) or not isinstance(request.get("problem"), str):
        raise TaskDataError("stdin must be an object with string field 'problem'")
    checks = request.get("checks", {})
    if not isinstance(checks, dict):
        raise TaskDataError("checks must be an object keyed by task id")
    problem = Path(request["problem"])
    failures: list[str] = []
    outputs: list[dict[str, Any]] = []
    for task in load_manifest(problem):
        path = resolve_path(problem, task["output"])
        check = checks.get(task["id"], {})
        if not isinstance(check, dict):
            raise TaskDataError(f"check for {task['id']!r} must be an object")
        if not path.is_file():
            failures.append(f"{task['id']}: missing output {path}")
            continue
        try:
            arrays = load_input(path)
        except TaskDataError as exc:
            failures.append(f"{task['id']}: {exc}")
            continue
        if path.suffix.lower() == ".npz" and "npz_keys" in check:
            expected = list(check["npz_keys"])
            if sorted(arrays) != sorted(expected):
                failures.append(f"{task['id']}: archive keys {sorted(arrays)} != expected {sorted(expected)}")
        # Scalar checks apply to a .npy result. Archive members are reported and
        # can still be checked for finite values by task-specific solver checks.
        if path.suffix.lower() == ".npy":
            array = arrays["__array__"]
            failures.extend(_check_array(array_metadata(array), array, check, task["id"]))
        outputs.append({"id": task["id"], "output": str(path),
                        "arrays": {name: array_metadata(value) for name, value in arrays.items()}})
    return {"ok": not failures, "failures": failures, "outputs": outputs}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        result = main(request)
        print(json.dumps(result, sort_keys=True))
        if not result["ok"]:
            raise SystemExit(1)
    except (TaskDataError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)
