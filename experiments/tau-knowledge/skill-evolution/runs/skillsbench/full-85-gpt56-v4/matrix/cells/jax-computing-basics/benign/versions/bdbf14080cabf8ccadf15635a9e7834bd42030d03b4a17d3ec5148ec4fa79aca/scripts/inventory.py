#!/usr/bin/env python3
"""Inspect runtime NumPy input files. Reads {"paths":[...]} from stdin, emits JSON."""
import json
import sys
from pathlib import Path
import numpy as np


def array_schema(a):
    return {"shape": list(a.shape), "dtype": str(a.dtype), "ndim": int(a.ndim)}


def inspect(path):
    p = Path(path)
    entry = {"path": str(p)}
    if not p.is_file():
        entry.update(error="file does not exist")
        return entry
    try:
        loaded = np.load(p, allow_pickle=False)
        if isinstance(loaded, np.lib.npyio.NpzFile):
            try:
                entry["kind"] = "npz"
                entry["keys"] = list(loaded.files)
                entry["arrays"] = {key: array_schema(loaded[key]) for key in loaded.files}
            finally:
                loaded.close()
        else:
            entry["kind"] = "npy"
            entry["array"] = array_schema(loaded)
    except Exception as exc:
        entry["error"] = f"{type(exc).__name__}: {exc}"
    return entry


def main():
    request = json.load(sys.stdin)
    paths = request.get("paths")
    if not isinstance(paths, list) or not all(isinstance(x, str) for x in paths):
        raise SystemExit('input must be JSON object with string list field "paths"')
    print(json.dumps({"inputs": [inspect(path) for path in paths]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
