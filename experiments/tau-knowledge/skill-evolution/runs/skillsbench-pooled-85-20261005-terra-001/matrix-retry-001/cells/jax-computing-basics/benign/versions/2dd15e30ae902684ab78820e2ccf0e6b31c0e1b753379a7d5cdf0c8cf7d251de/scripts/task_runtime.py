"""I/O helpers for manifest-driven JAX numerical tasks.

This module is importable by a solver.  It deliberately performs only file and
format handling; the task-specific numerical computation remains in JAX code.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class TaskDataError(ValueError):
    """Raised for malformed manifests, unsupported files, or invalid outputs."""


def resolve_path(problem_path: str | Path, declared_path: str) -> Path:
    if not isinstance(declared_path, str) or not declared_path:
        raise TaskDataError("declared path must be a nonempty string")
    path = Path(declared_path)
    return path if path.is_absolute() else Path(problem_path).resolve().parent / path


def load_manifest(problem_path: str | Path) -> list[dict[str, Any]]:
    path = Path(problem_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskDataError(f"cannot read JSON manifest {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise TaskDataError("manifest root must be a JSON list")
    seen_ids: set[str] = set()
    for index, task in enumerate(raw):
        if not isinstance(task, dict):
            raise TaskDataError(f"task {index} must be an object")
        for field in ("id", "description", "input", "output"):
            if field not in task or not isinstance(task[field], str) or not task[field]:
                raise TaskDataError(f"task {index} requires nonempty string field {field!r}")
        if task["id"] in seen_ids:
            raise TaskDataError(f"duplicate task id {task['id']!r}")
        seen_ids.add(task["id"])
    return raw


def load_input(path: str | Path) -> dict[str, np.ndarray]:
    """Load a NumPy input without pickle support.

    Returns {"__array__": array} for .npy and a copied key-to-array mapping
    for .npz. Copying archive members prevents use after the NpzFile closes.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in {".npy", ".npz"}:
        raise TaskDataError(f"unsupported input format {path}; expected .npy or .npz")
    try:
        loaded = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise TaskDataError(f"cannot load {path}: {exc}") from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            return {name: np.asarray(loaded[name]) for name in loaded.files}
        finally:
            loaded.close()
    return {"__array__": np.asarray(loaded)}


def array_metadata(array: np.ndarray) -> dict[str, Any]:
    return {"shape": list(array.shape), "dtype": str(array.dtype), "ndim": array.ndim}


def save_result(path: str | Path, result: Any) -> None:
    """Save an already materialized result at its requested NumPy path."""
    path = Path(path)
    suffix = path.suffix.lower()
    path.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".npy":
        if isinstance(result, Mapping):
            raise TaskDataError(".npy output requires one array, not a mapping")
        array = np.asarray(result)
        if array.dtype.hasobject:
            raise TaskDataError("object arrays are not supported output")
        np.save(path, array, allow_pickle=False)
        return
    if suffix == ".npz":
        if not isinstance(result, Mapping) or not result:
            raise TaskDataError(".npz output requires a nonempty mapping of named arrays")
        arrays = {str(key): np.asarray(value) for key, value in result.items()}
        if any(value.dtype.hasobject for value in arrays.values()):
            raise TaskDataError("object arrays are not supported output")
        np.savez(path, **arrays)
        return
    raise TaskDataError(f"unsupported output format {path}; expected .npy or .npz")
