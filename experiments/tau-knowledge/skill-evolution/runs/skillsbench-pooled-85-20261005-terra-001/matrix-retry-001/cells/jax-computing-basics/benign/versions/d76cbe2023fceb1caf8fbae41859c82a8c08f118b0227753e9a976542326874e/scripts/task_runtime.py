"""Safe manifest, NumPy I/O, and path helpers for JAX task solvers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class TaskDataError(ValueError):
    """Malformed manifest, unsupported data, or invalid portable output."""


def resolve_path(problem_path: str | Path, declared_path: str) -> Path:
    if not isinstance(declared_path, str) or not declared_path:
        raise TaskDataError("declared path must be a nonempty string")
    candidate = Path(declared_path)
    return candidate if candidate.is_absolute() else Path(problem_path).resolve().parent / candidate


def load_manifest(problem_path: str | Path) -> list[dict[str, Any]]:
    path = Path(problem_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskDataError(f"cannot read JSON manifest {path}: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise TaskDataError("manifest root must be a nonempty JSON list")
    ids: set[str] = set()
    outputs: set[Path] = set()
    for number, task in enumerate(raw):
        if not isinstance(task, dict):
            raise TaskDataError(f"task {number} must be an object")
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field]:
                raise TaskDataError(f"task {number} requires nonempty string field {field!r}")
        if task["id"] in ids:
            raise TaskDataError(f"duplicate task id {task['id']!r}")
        ids.add(task["id"])
        out = resolve_path(path, task["output"])
        inp = resolve_path(path, task["input"])
        if out == inp:
            raise TaskDataError(f"task {task['id']!r} output would overwrite its input")
        if out in outputs:
            raise TaskDataError(f"multiple tasks declare output {out}")
        outputs.add(out)
    return raw


def load_input(path: str | Path) -> dict[str, np.ndarray]:
    """Load .npy/.npz without pickle support, copying archive members."""
    path = Path(path)
    if path.suffix.lower() not in {".npy", ".npz"}:
        raise TaskDataError(f"unsupported array format {path}; expected .npy or .npz")
    try:
        loaded = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise TaskDataError(f"cannot load {path}: {exc}") from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            arrays = {key: np.asarray(loaded[key]) for key in loaded.files}
        finally:
            loaded.close()
        if not arrays:
            raise TaskDataError(f"archive {path} has no arrays")
        return arrays
    return {"__array__": np.asarray(loaded)}


def array_metadata(array: np.ndarray) -> dict[str, Any]:
    return {"shape": list(array.shape), "dtype": str(array.dtype), "ndim": array.ndim}


def save_result(path: str | Path, result: Any) -> None:
    """Save a materialized portable numeric result at exactly ``path``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".npy":
        if isinstance(result, Mapping):
            raise TaskDataError("a .npy output requires one array")
        value = np.asarray(result)
        if value.dtype.hasobject or value.dtype.kind not in "biufc":
            raise TaskDataError("output must be a numeric non-object ndarray")
        np.save(path, value, allow_pickle=False)
        return
    if suffix == ".npz":
        if not isinstance(result, Mapping) or len(result) != 1:
            raise TaskDataError("a task .npz output must contain exactly one named result array")
        arrays = {str(k): np.asarray(v) for k, v in result.items()}
        if any(v.dtype.hasobject or v.dtype.kind not in "biufc" for v in arrays.values()):
            raise TaskDataError("output must contain numeric non-object ndarrays")
        np.savez(path, **arrays)
        return
    raise TaskDataError(f"unsupported output format {path}; expected .npy or .npz")
