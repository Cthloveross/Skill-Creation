#!/usr/bin/env python3
"""Validate a saved NumPy-compatible output.

stdin: {"path": "/app/file.npy", "expected_shape": [..], "expected_dtype": "float32",
        "require_finite": true}
stdout: metadata JSON; exits nonzero on a validation failure.
"""
import json
import sys
from pathlib import Path
import numpy as np


def main():
    spec = json.load(sys.stdin)
    path = Path(spec["path"])
    if not path.exists():
        raise FileNotFoundError(f"output does not exist: {path}")
    loaded = np.load(path, allow_pickle=False)
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            key = spec.get("archive_key", "result")
            if key not in loaded.files:
                raise KeyError(f"archive lacks key {key!r}; keys={loaded.files}")
            value = loaded[key]
        finally:
            loaded.close()
    else:
        value = loaded
    if spec.get("expected_shape") is not None and tuple(value.shape) != tuple(spec["expected_shape"]):
        raise ValueError(f"shape {value.shape} != expected {tuple(spec['expected_shape'])}")
    if spec.get("expected_dtype") is not None and value.dtype != np.dtype(spec["expected_dtype"]):
        raise ValueError(f"dtype {value.dtype} != expected {spec['expected_dtype']}")
    if spec.get("require_finite", True) and np.issubdtype(value.dtype, np.inexact) and not np.isfinite(value).all():
        raise ValueError("output contains NaN or infinity")
    print(json.dumps({"path": str(path), "shape": list(value.shape), "dtype": str(value.dtype), "finite": bool(np.isfinite(value).all()) if np.issubdtype(value.dtype, np.inexact) else None}))


if __name__ == "__main__":
    main()
