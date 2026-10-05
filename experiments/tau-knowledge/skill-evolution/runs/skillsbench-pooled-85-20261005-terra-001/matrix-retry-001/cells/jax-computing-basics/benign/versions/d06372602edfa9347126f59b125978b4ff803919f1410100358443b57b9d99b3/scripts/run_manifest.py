"""Runtime solver for a JSON manifest of common JAX numerical tasks.

stdin:  {"problem": "/app/problem.json"}  (problem is optional)
stdout: {"ok": true, "outputs": [{"id", "output", "shape", "dtype"}]}

The program deliberately derives inputs and destinations from the runtime manifest.
It never changes the manifest or its input arrays.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

import jax
import jax.numpy as jnp
import numpy as np


class TaskError(ValueError):
    pass


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def resolve(problem: Path, declared: str) -> Path:
    if not isinstance(declared, str) or not declared:
        raise TaskError("manifest paths must be nonempty strings")
    path = Path(declared)
    return path if path.is_absolute() else problem.resolve().parent / path


def manifest(problem: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(problem.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskError(f"cannot read manifest {problem}: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise TaskError("problem manifest must be a nonempty list")
    ids: set[str] = set()
    outputs: set[Path] = set()
    for index, task in enumerate(raw):
        if not isinstance(task, dict):
            raise TaskError(f"task {index} is not an object")
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field]:
                raise TaskError(f"task {index} lacks nonempty string {field!r}")
        if task["id"] in ids:
            raise TaskError(f"duplicate task id {task['id']!r}")
        ids.add(task["id"])
        source, target = resolve(problem, task["input"]), resolve(problem, task["output"])
        if source == target:
            raise TaskError(f"task {task['id']!r} would overwrite its input")
        if target in outputs:
            raise TaskError(f"multiple tasks use output {target}")
        outputs.add(target)
    return raw


def load_arrays(path: Path) -> dict[str, np.ndarray]:
    if path.suffix.lower() not in {".npy", ".npz"}:
        raise TaskError(f"unsupported array input {path}; expected .npy or .npz")
    try:
        value = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise TaskError(f"cannot load {path}: {exc}") from exc
    if isinstance(value, np.lib.npyio.NpzFile):
        try:
            arrays = {key: np.asarray(value[key]) for key in value.files}
        finally:
            value.close()
        if not arrays:
            raise TaskError(f"archive {path} has no arrays")
        return arrays
    return {"__array__": np.asarray(value)}


def member(arrays: Mapping[str, np.ndarray], *aliases: str) -> np.ndarray:
    wanted = {norm(item) for item in aliases}
    found = [array for key, array in arrays.items() if norm(key) in wanted]
    if len(found) != 1:
        raise TaskError(f"need exactly one input member among {aliases}; found {len(found)}")
    return found[0]


def optional_member(arrays: Mapping[str, np.ndarray], *aliases: str) -> np.ndarray | None:
    wanted = {norm(item) for item in aliases}
    found = [array for key, array in arrays.items() if norm(key) in wanted]
    if len(found) > 1:
        raise TaskError(f"ambiguous optional input member among {aliases}")
    return found[0] if found else None


def primary(arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    if "__array__" in arrays:
        return arrays["__array__"]
    return member(arrays, "x", "xs", "input", "inputs", "data", "features", "sequence")


def described_axis(text: str) -> int | tuple[int, ...] | None:
    match = re.search(r"\baxis(?:es)?\s*(?:=|of|along)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)", text)
    if not match:
        return None
    axes = tuple(int(piece.strip()) for piece in match.group(1).split(","))
    return axes[0] if len(axes) == 1 else axes


def reduction(description: str, arrays: Mapping[str, np.ndarray]):
    text = description.lower()
    x = jnp.asarray(primary(arrays))
    axis = described_axis(text)
    if "sum of squares" in text or "sum the squares" in text:
        return jnp.sum(jnp.square(x), axis=axis)
    if "mean of squares" in text or "mean the squares" in text:
        return jnp.mean(jnp.square(x), axis=axis)
    if re.search(r"\bsum\b", text):
        return jnp.sum(x, axis=axis)
    if re.search(r"\bmean\b|\baverage\b", text):
        return jnp.mean(x, axis=axis)
    if re.search(r"\bmaximum\b|\bmax\b", text):
        return jnp.max(x, axis=axis)
    if re.search(r"\bminimum\b|\bmin\b", text):
        return jnp.min(x, axis=axis)
    raise TaskError("description is not a recognized explicit reduction")


def logistic_gradient(description: str, arrays: Mapping[str, np.ndarray]):
    text = description.lower()
    if "logistic" not in text and "sigmoid" not in text:
        raise TaskError("only an explicit logistic/sigmoid gradient is supported")
    x = jnp.asarray(member(arrays, "x", "features", "inputs"))
    y = jnp.asarray(member(arrays, "y", "labels", "targets"))
    w = jnp.asarray(member(arrays, "w", "weight", "weights"))
    b_raw = optional_member(arrays, "b", "bias")
    bias = jnp.asarray(b_raw) if b_raw is not None else 0
    if x.ndim < 1 or w.ndim < 1 or x.shape[-1] != w.shape[0]:
        raise TaskError("logistic feature and weight dimensions are incompatible")

    def loss(weight):
        logits = jnp.matmul(x, weight) + bias
        # Stable binary cross entropy, averaged over all examples/output terms.
        return jnp.mean(jnp.logaddexp(0, logits) - y * logits)

    return jax.grad(loss)(w)


def mlp_forward(description: str, arrays: Mapping[str, np.ndarray]):
    text = description.lower()
    x = jnp.asarray(member(arrays, "x", "inputs", "features"))
    w1 = jnp.asarray(member(arrays, "w1", "weight1", "weights1"))
    b1 = jnp.asarray(member(arrays, "b1", "bias1"))
    w2 = jnp.asarray(member(arrays, "w2", "weight2", "weights2"))
    b2 = jnp.asarray(member(arrays, "b2", "bias2"))
    if x.ndim < 2 or x.shape[-1] != w1.shape[0] or w1.shape[-1] != w2.shape[0]:
        raise TaskError("MLP batch or matrix dimensions are incompatible")
    if "tanh" in text:
        activation = jnp.tanh
    elif "sigmoid" in text:
        activation = jax.nn.sigmoid
    elif "relu" in text:
        activation = jax.nn.relu
    else:
        # ReLU is used only for wording that explicitly identifies a standard MLP
        # but omits the conventional activation name.
        activation = jax.nn.relu

    def one(example):
        return jnp.matmul(activation(jnp.matmul(example, w1) + b1), w2) + b2

    return jax.vmap(one)(x)


def scan_compute(description: str, arrays: Mapping[str, np.ndarray]):
    text = description.lower()
    x = jnp.asarray(primary(arrays))
    if x.ndim < 1:
        raise TaskError("scan input needs a leading sequence axis")
    if "cumulative sum" in text or "running sum" in text:
        initial = jnp.zeros(x.shape[1:], dtype=x.dtype)
        _, ys = jax.lax.scan(lambda carry, item: (carry + item, carry + item), initial, x)
        return ys
    if "cumulative product" in text or "running product" in text:
        initial = jnp.ones(x.shape[1:], dtype=x.dtype)
        _, ys = jax.lax.scan(lambda carry, item: (carry * item, carry * item), initial, x)
        return ys
    raise TaskError("scan description must explicitly specify a supported recurrence")


def compute(description: str, arrays: Mapping[str, np.ndarray]):
    text = description.lower()
    if "gradient" in text or "derivative" in text:
        return logistic_gradient(description, arrays)
    if "scan" in text or "cumulative" in text or "running sum" in text or "running product" in text:
        return scan_compute(description, arrays)
    if "mlp" in text or "vmap" in text or "vectorized neural" in text:
        return mlp_forward(description, arrays)
    return reduction(description, arrays)


def portable(value: Any, task_id: str) -> np.ndarray:
    array = np.asarray(jax.device_get(value))
    if array.size == 0 or array.dtype.hasobject or array.dtype.kind not in "biufc":
        raise TaskError(f"task {task_id!r} did not produce a nonempty portable numeric array")
    if array.dtype.kind in "fc" and not np.isfinite(array).all():
        raise TaskError(f"task {task_id!r} produced non-finite values")
    return array


def save_one(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".npy":
        np.save(path, value, allow_pickle=False)
    elif path.suffix.lower() == ".npz":
        np.savez(path, result=value)
    else:
        raise TaskError(f"unsupported output {path}; expected .npy or .npz")


def verify_one(path: Path, task_id: str) -> None:
    arrays = load_arrays(path)
    if len(arrays) != 1:
        raise TaskError(f"task {task_id!r} output must contain exactly one array")
    portable(next(iter(arrays.values())), task_id)


def main(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise TaskError("stdin must be a JSON object")
    raw_problem = request.get("problem", "/app/problem.json")
    if not isinstance(raw_problem, str) or not raw_problem:
        raise TaskError("problem must be a nonempty string")
    problem = Path(raw_problem)
    tasks = manifest(problem)
    report: list[dict[str, Any]] = []
    for task in tasks:
        source = resolve(problem, task["input"])
        destination = resolve(problem, task["output"])
        if not source.is_file():
            raise TaskError(f"task {task['id']!r} input is unavailable: {source}")
        result = portable(compute(task["description"], load_arrays(source)), task["id"])
        save_one(destination, result)
        report.append({"id": task["id"], "output": str(destination),
                       "shape": list(result.shape), "dtype": str(result.dtype)})
    for task in tasks:
        verify_one(resolve(problem, task["output"]), task["id"])
    return {"ok": True, "outputs": report}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        print(json.dumps(main(request), sort_keys=True))
    except (TaskError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)
