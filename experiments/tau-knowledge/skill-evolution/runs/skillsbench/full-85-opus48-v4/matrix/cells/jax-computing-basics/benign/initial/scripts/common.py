"""Shared helpers for the JAX computing-basics solver.

All scripts read a JSON object from stdin:
  {"problem": <path to problem.json>, "root": <dir to resolve relative paths>}
Both keys are optional; defaults are /app/problem.json and the problem file's
directory (falling back to /app).
"""
import json
import os
import sys

import numpy as np


def read_config():
    raw = sys.stdin.read().strip()
    cfg = json.loads(raw) if raw else {}
    problem = cfg.get("problem") or "/app/problem.json"
    problem = os.path.abspath(problem)
    root = cfg.get("root") or os.path.dirname(problem) or "/app"
    root = os.path.abspath(root)
    return problem, root


def load_tasks(problem_path):
    with open(problem_path) as fh:
        tasks = json.load(fh)
    if isinstance(tasks, dict):
        tasks = [tasks]
    return tasks


def resolve(root, path):
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(root, path))


def load_input(path):
    """Return (kind, obj). kind is 'npy' (ndarray) or 'npz' (dict of arrays)."""
    obj = np.load(path, allow_pickle=False)
    if isinstance(obj, np.lib.npyio.NpzFile):
        data = {k: obj[k] for k in obj.files}
        return "npz", data
    return "npy", np.asarray(obj)


def describe_array(arr):
    arr = np.asarray(arr)
    prev = arr
    try:
        flat = arr.ravel()
        prev = flat[: min(8, flat.size)].tolist()
    except Exception:
        prev = None
    return {"shape": list(arr.shape), "dtype": str(arr.dtype), "preview": prev}


def save_output(path, result):
    """Save a materialized NumPy result. Dict -> .npz, else -> .npy."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if isinstance(result, dict):
        mats = {k: np.asarray(v) for k, v in result.items()}
        if not path.endswith(".npz"):
            path = path + ".npz" if not path.endswith(".npy") else path[:-4] + ".npz"
        np.savez(path, **mats)
    else:
        mat = np.asarray(result)
        np.save(path, mat)
        if not path.endswith(".npy"):
            # np.save appends .npy; honor the exact manifest path too.
            if os.path.exists(path + ".npy") and not os.path.exists(path):
                os.replace(path + ".npy", path)
    return path
