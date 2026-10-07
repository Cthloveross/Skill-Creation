"""Execute unambiguous common JAX operations stated in a task manifest.

stdin schema: {"problem": "/app/problem.json"}
stdout schema: {"ok": true, "outputs": [{"id", "output", "shape", "dtype"}]}

This is deliberately a conservative dispatcher, not a natural-language guesser.
Unsupported descriptions raise TaskDataError so an executor can supply the exact
small JAX expression required by the manifest rather than saving bogus data.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Callable

import jax
import jax.numpy as jnp
import numpy as np

from task_runtime import TaskDataError, load_input, load_manifest, resolve_path, save_result


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _member(arrays: dict[str, np.ndarray], *names: str) -> np.ndarray:
    wanted = {_norm(name) for name in names}
    matches = [value for key, value in arrays.items() if _norm(key) in wanted]
    if len(matches) != 1:
        raise TaskDataError(f"need exactly one archive member among {names}; found {len(matches)}")
    return matches[0]


def _primary(arrays: dict[str, np.ndarray]) -> np.ndarray:
    if "__array__" in arrays:
        return arrays["__array__"]
    return _member(arrays, "x", "input", "inputs", "data", "features")


def _axis(description: str) -> int | tuple[int, ...] | None:
    found = re.search(r"\baxis(?:es)?\s*(?:=|of|along)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)", description)
    if not found:
        return None
    values = tuple(int(x.strip()) for x in found.group(1).split(","))
    return values[0] if len(values) == 1 else values


def _reduction(description: str, arrays: dict[str, np.ndarray]):
    text = description.lower()
    x = jnp.asarray(_primary(arrays))
    axis = _axis(text)
    if "sum of squares" in text or "sum the squares" in text:
        return jnp.sum(jnp.square(x), axis=axis)
    if "mean of squares" in text or "mean the squares" in text:
        return jnp.mean(jnp.square(x), axis=axis)
    # Require an explicit reduction word.  Do not treat arbitrary prose as one.
    if re.search(r"\bsum\b", text):
        return jnp.sum(x, axis=axis)
    if re.search(r"\bmean\b|\baverage\b", text):
        return jnp.mean(x, axis=axis)
    if re.search(r"\bmaximum\b|\bmax\b", text):
        return jnp.max(x, axis=axis)
    if re.search(r"\bminimum\b|\bmin\b", text):
        return jnp.min(x, axis=axis)
    raise TaskDataError("description is not an explicitly supported reduction")


def _logistic_weight_gradient(description: str, arrays: dict[str, np.ndarray]):
    """Gradient of mean binary logistic cross entropy with respect to weights."""
    text = description.lower()
    if not ("gradient" in text and "logistic" in text and
            ("cross entropy" in text or "binary" in text)):
        raise TaskDataError("not an explicit binary logistic-loss gradient task")
    x = jnp.asarray(_member(arrays, "x", "features", "inputs"))
    y = jnp.asarray(_member(arrays, "y", "labels", "targets"))
    w = jnp.asarray(_member(arrays, "w", "weight", "weights"))
    # A named bias is optional. Its gradient is intentionally not packed into a
    # weight-gradient result unless the description explicitly asks for it.
    bias_matches = [v for k, v in arrays.items() if _norm(k) in {"b", "bias"}]
    bias = jnp.asarray(bias_matches[0]) if len(bias_matches) == 1 else 0
    if x.shape[-1] != w.shape[0]:
        raise TaskDataError("feature and weight dimensions are incompatible")
    def loss(weight):
        logits = jnp.matmul(x, weight) + bias
        return jnp.mean(jnp.logaddexp(0, logits) - y * logits)
    return jax.grad(loss)(w)


def _mlp_forward(description: str, arrays: dict[str, np.ndarray]):
    text = description.lower()
    if not ("mlp" in text or ("vmap" in text and "layer" in text)):
        raise TaskDataError("not an explicit vectorized MLP forward task")
    x = jnp.asarray(_member(arrays, "x", "inputs", "features"))
    w1 = jnp.asarray(_member(arrays, "w1", "weight1", "weights1"))
    b1 = jnp.asarray(_member(arrays, "b1", "bias1"))
    w2 = jnp.asarray(_member(arrays, "w2", "weight2", "weights2"))
    b2 = jnp.asarray(_member(arrays, "b2", "bias2"))
    if x.shape[-1] != w1.shape[0] or w1.shape[-1] != w2.shape[0]:
        raise TaskDataError("MLP matrix dimensions are incompatible")
    activation: Callable = jnp.tanh if "tanh" in text else jax.nn.relu
    def one(example):
        return jnp.matmul(activation(jnp.matmul(example, w1) + b1), w2) + b2
    return jax.vmap(one)(x)


def _cumulative_scan(description: str, arrays: dict[str, np.ndarray]):
    text = description.lower()
    if not ("scan" in text and ("cumulative sum" in text or "running sum" in text)):
        raise TaskDataError("not an explicit cumulative-sum scan task")
    x = jnp.asarray(_primary(arrays))
    if x.ndim < 1:
        raise TaskDataError("scan requires an input with a leading time axis")
    init = jnp.zeros(x.shape[1:], dtype=x.dtype)
    _, output = jax.lax.scan(lambda carry, item: (carry + item, carry + item), init, x)
    return output


def compute(description: str, arrays: dict[str, np.ndarray]):
    text = description.lower()
    if "gradient" in text:
        return _logistic_weight_gradient(description, arrays)
    if "scan" in text:
        return _cumulative_scan(description, arrays)
    if "mlp" in text or "vmap" in text:
        return _mlp_forward(description, arrays)
    return _reduction(description, arrays)


def main(request: dict) -> dict:
    if not isinstance(request, dict) or not isinstance(request.get("problem"), str):
        raise TaskDataError("stdin must be an object with string field 'problem'")
    problem = Path(request["problem"])
    report = []
    for task in load_manifest(problem):
        result = compute(task["description"], load_input(resolve_path(problem, task["input"])))
        value = np.asarray(jax.device_get(result))
        if value.size == 0 or value.dtype.kind not in "biufc" or value.dtype.hasobject:
            raise TaskDataError(f"task {task['id']!r} produced no portable numeric result")
        if value.dtype.kind in "fc" and not np.isfinite(value).all():
            raise TaskDataError(f"task {task['id']!r} produced non-finite result")
        output = resolve_path(problem, task["output"])
        save_result(output, value if output.suffix.lower() == ".npy" else {"result": value})
        report.append({"id": task["id"], "output": str(output),
                       "shape": list(value.shape), "dtype": str(value.dtype)})
    return {"ok": True, "outputs": report}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (TaskDataError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)
