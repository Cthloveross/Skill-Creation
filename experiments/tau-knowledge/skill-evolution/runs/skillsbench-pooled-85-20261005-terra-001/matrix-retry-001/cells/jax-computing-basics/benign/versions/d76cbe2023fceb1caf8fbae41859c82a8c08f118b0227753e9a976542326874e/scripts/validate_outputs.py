"""Validate all manifest outputs.
stdin: {"problem":"path", "checks": {task_id: optional constraints}}
stdout: {"ok", "failures", "outputs"}
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any
import numpy as np
from task_runtime import TaskDataError, array_metadata, load_input, load_manifest, resolve_path


def _check(value: np.ndarray, check: dict[str, Any], label: str) -> list[str]:
    meta = array_metadata(value)
    failures: list[str] = []
    if "shape" in check and list(check["shape"]) != meta["shape"]:
        failures.append(f"{label}: shape {meta['shape']} != {list(check['shape'])}")
    if "ndim" in check and check["ndim"] != meta["ndim"]:
        failures.append(f"{label}: ndim {meta['ndim']} != {check['ndim']}")
    if "dtype" in check and str(check["dtype"]) != meta["dtype"]:
        failures.append(f"{label}: dtype {meta['dtype']} != {check['dtype']}")
    if check.get("finite") and np.issubdtype(value.dtype, np.inexact) and not np.isfinite(value).all():
        failures.append(f"{label}: non-finite values")
    return failures


def main(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict) or not isinstance(request.get("problem"), str):
        raise TaskDataError("stdin must be an object with string field 'problem'")
    checks = request.get("checks", {})
    if not isinstance(checks, dict):
        raise TaskDataError("checks must be an object")
    problem = Path(request["problem"])
    failures, outputs = [], []
    for task in load_manifest(problem):
        path = resolve_path(problem, task["output"])
        if not path.is_file():
            failures.append(f"{task['id']}: missing output {path}")
            continue
        try:
            arrays = load_input(path)
        except TaskDataError as exc:
            failures.append(f"{task['id']}: {exc}")
            continue
        if len(arrays) != 1:
            failures.append(f"{task['id']}: output must contain exactly one array")
            continue
        check = checks.get(task["id"], {})
        if not isinstance(check, dict):
            raise TaskDataError(f"check for {task['id']!r} must be an object")
        value = next(iter(arrays.values()))
        if value.size == 0 or value.dtype.hasobject or value.dtype.kind not in "biufc":
            failures.append(f"{task['id']}: output is not a nonempty portable numeric array")
        if value.dtype.kind in "fc" and not np.isfinite(value).all():
            failures.append(f"{task['id']}: output has non-finite values")
        failures.extend(_check(value, check, task["id"]))
        outputs.append({"id": task["id"], "output": str(path),
                        "arrays": {k: array_metadata(v) for k, v in arrays.items()}})
    return {"ok": not failures, "failures": failures, "outputs": outputs}


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
        print(json.dumps(result, sort_keys=True))
        raise SystemExit(0 if result["ok"] else 1)
    except (TaskDataError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)
