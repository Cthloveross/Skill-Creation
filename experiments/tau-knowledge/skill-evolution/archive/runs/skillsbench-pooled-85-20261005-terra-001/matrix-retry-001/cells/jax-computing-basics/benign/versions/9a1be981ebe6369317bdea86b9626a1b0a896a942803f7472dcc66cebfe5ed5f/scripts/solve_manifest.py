"""Solve every numerical task in a problem.json manifest.

stdin JSON: {"problem": "/app/problem.json", "engine": "auto"}
stdout JSON: {"ok": bool, "engine": str, "outputs": [{id, output, shape, dtype}]}

The auto mode imports JAX only in a subprocess.  A fatal native JAX failure is
therefore contained and the parent can save equivalent portable results.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

# These limits are inherited by an isolated JAX worker before it imports JAX.
os.environ.setdefault("JAX_PLATFORMS", "cpu")
os.environ.setdefault("JAX_DISABLE_JIT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")

import numpy as np


class TaskError(ValueError):
    pass


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _path(manifest: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise TaskError("input and output values must be nonempty path strings")
    path = Path(value)
    return path if path.is_absolute() else manifest.parent / path


def read_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        tasks = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(tasks, list) or not tasks:
        raise TaskError("manifest must be a nonempty list")
    ids: set[str] = set()
    outputs: set[Path] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise TaskError(f"manifest entry {index} is not an object")
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise TaskError(f"manifest entry {index} lacks a nonempty {field!r}")
        ident = str(task["id"])
        if ident in ids:
            raise TaskError(f"duplicate task id {ident!r}")
        ids.add(ident)
        source, target = _path(path, task["input"]), _path(path, task["output"])
        if source == target:
            raise TaskError(f"task {ident!r} would overwrite its input")
        if target in outputs:
            raise TaskError(f"multiple tasks declare output {target}")
        outputs.add(target)
    return tasks


def load_arrays(path: Path) -> dict[str, np.ndarray]:
    if path.suffix.lower() not in {".npy", ".npz"}:
        raise TaskError(f"unsupported input format: {path}")
    try:
        loaded = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError(f"cannot load {path}: {type(exc).__name__}: {exc}") from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            result = {key: np.asarray(loaded[key]) for key in loaded.files}
        finally:
            loaded.close()
        if not result:
            raise TaskError(f"archive {path} contains no arrays")
        return result
    return {"__array__": np.asarray(loaded)}


def required(arrays: Mapping[str, np.ndarray], *names: str) -> np.ndarray:
    acceptable = {_normal(name) for name in names}
    matches = [value for key, value in arrays.items() if _normal(key) in acceptable]
    if len(matches) != 1:
        raise TaskError(f"expected exactly one archive member among {names}; found {len(matches)}")
    return matches[0]


def optional(arrays: Mapping[str, np.ndarray], *names: str) -> np.ndarray | None:
    acceptable = {_normal(name) for name in names}
    matches = [value for key, value in arrays.items() if _normal(key) in acceptable]
    if len(matches) > 1:
        raise TaskError(f"ambiguous archive members among {names}")
    return matches[0] if matches else None


def primary(arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    if "__array__" in arrays:
        return arrays["__array__"]
    if len(arrays) == 1:
        return next(iter(arrays.values()))
    return required(arrays, "x", "xs", "input", "inputs", "data", "values", "sequence", "seq")


def axis_from(description: str) -> int | tuple[int, ...] | None:
    text = description.lower()
    found = re.search(r"\baxis(?:es)?\s*(?:=|of|along|over)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)", text)
    if found:
        values = tuple(int(part.strip()) for part in found.group(1).split(","))
        return values[0] if len(values) == 1 else values
    if "each row" in text or "across columns" in text or "last axis" in text:
        return -1
    if "each column" in text or "across rows" in text or "first axis" in text or "leading axis" in text:
        return 0
    return None


def reduce_value(description: str, arrays: Mapping[str, np.ndarray], xp: Any) -> Any:
    text = description.lower()
    value = xp.asarray(primary(arrays))
    axis = axis_from(description)
    if "sum of squares" in text or "squared sum" in text or "sum the squares" in text:
        return xp.sum(xp.square(value), axis=axis)
    if "mean of squares" in text or "mean the squares" in text:
        return xp.mean(xp.square(value), axis=axis)
    if "l2 norm" in text or "euclidean norm" in text:
        return xp.sqrt(xp.sum(xp.square(value), axis=axis))
    if re.search(r"\b(product|prod)\b", text):
        return xp.prod(value, axis=axis)
    if re.search(r"\b(maximum|max)\b", text):
        return xp.max(value, axis=axis)
    if re.search(r"\b(minimum|min)\b", text):
        return xp.min(value, axis=axis)
    if re.search(r"\b(mean|average)\b", text):
        return xp.mean(value, axis=axis)
    if re.search(r"\b(sum|reduce|total)\b", text):
        return xp.sum(value, axis=axis)
    raise TaskError("unsupported reduction description")


def logistic_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    x = np.asarray(required(arrays, "x", "features", "inputs", "data"))
    y = np.ravel(np.asarray(required(arrays, "y", "labels", "targets", "target")))
    w = np.asarray(required(arrays, "w", "weight", "weights", "theta", "params"))
    raw_b = optional(arrays, "b", "bias", "intercept")
    b = np.asarray(raw_b) if raw_b is not None else 0
    if x.ndim != 2 or w.ndim != 1 or x.shape[1] != w.shape[0] or y.size != x.shape[0]:
        raise TaskError("incompatible logistic x, y, and weight shapes")
    logits = x @ w + b
    positive = logits >= 0
    probabilities = np.empty_like(logits, dtype=np.result_type(logits, np.float32))
    probabilities[positive] = 1 / (1 + np.exp(-logits[positive]))
    exponent = np.exp(logits[~positive])
    probabilities[~positive] = exponent / (1 + exponent)
    grad = x.T @ (probabilities - y)
    text = description.lower()
    return grad if "sum" in text and "mean" not in text and "average" not in text else grad / x.shape[0]


def logistic_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any) -> Any:
    x = jnp.asarray(required(arrays, "x", "features", "inputs", "data"))
    y = jnp.ravel(jnp.asarray(required(arrays, "y", "labels", "targets", "target")))
    w = jnp.asarray(required(arrays, "w", "weight", "weights", "theta", "params"))
    raw_b = optional(arrays, "b", "bias", "intercept")
    b = jnp.asarray(raw_b) if raw_b is not None else 0
    if x.ndim != 2 or w.ndim != 1 or x.shape[1] != w.shape[0] or y.size != x.shape[0]:
        raise TaskError("incompatible logistic x, y, and weight shapes")
    text = description.lower()
    summed = "sum" in text and "mean" not in text and "average" not in text
    def loss(weights: Any) -> Any:
        logits = x @ weights + b
        terms = jnp.logaddexp(0, logits) - y * logits
        return jnp.sum(terms) if summed else jnp.mean(terms)
    return jax.grad(loss)(w)


def activation(description: str, xp: Any, jax: Any | None = None) -> Any:
    text = description.lower()
    if "tanh" in text:
        return xp.tanh
    if "sigmoid" in text:
        return jax.nn.sigmoid if jax is not None else lambda z: 1 / (1 + np.exp(-z))
    if "identity" in text or "linear activation" in text:
        return lambda z: z
    return jax.nn.relu if jax is not None else lambda z: xp.maximum(z, 0)


def layer(value: Any, weights: Any, bias: Any, xp: Any) -> Any:
    if weights.ndim != 2:
        raise TaskError("MLP weights must be rank two")
    if value.shape[-1] == weights.shape[0]:
        output = xp.matmul(value, weights)
    elif value.shape[-1] == weights.shape[1]:
        output = xp.matmul(value, xp.swapaxes(weights, -1, -2))
    else:
        raise TaskError("MLP layer dimensions are incompatible")
    try:
        return output + bias
    except Exception as exc:
        raise TaskError("MLP bias dimensions are incompatible") from exc


def mlp_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    x = np.asarray(required(arrays, "x", "inputs", "features", "data"))
    w1 = np.asarray(required(arrays, "w1", "weight1", "weights1", "layer1weight"))
    b1 = np.asarray(required(arrays, "b1", "bias1", "biases1", "layer1bias"))
    w2 = np.asarray(required(arrays, "w2", "weight2", "weights2", "layer2weight"))
    b2 = np.asarray(required(arrays, "b2", "bias2", "biases2", "layer2bias"))
    if x.ndim < 2:
        raise TaskError("batched MLP input needs a batch axis")
    return layer(activation(description, np)(layer(x, w1, b1, np)), w2, b2, np)


def mlp_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any) -> Any:
    x = jnp.asarray(required(arrays, "x", "inputs", "features", "data"))
    w1 = jnp.asarray(required(arrays, "w1", "weight1", "weights1", "layer1weight"))
    b1 = jnp.asarray(required(arrays, "b1", "bias1", "biases1", "layer1bias"))
    w2 = jnp.asarray(required(arrays, "w2", "weight2", "weights2", "layer2weight"))
    b2 = jnp.asarray(required(arrays, "b2", "bias2", "biases2", "layer2bias"))
    if x.ndim < 2:
        raise TaskError("batched MLP input needs a batch axis")
    act = activation(description, jnp, jax)
    def one(example: Any) -> Any:
        return layer(act(layer(example, w1, b1, jnp)), w2, b2, jnp)
    return jax.vmap(one)(x)


def scan_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    values = np.asarray(primary(arrays))
    text = description.lower()
    if values.ndim < 1:
        raise TaskError("scan input needs a leading sequence axis")
    add = any(word in text for word in ("cumulative sum", "running sum", "prefix sum"))
    multiply = any(word in text for word in ("cumulative product", "running product", "prefix product"))
    if not add and not multiply:
        raise TaskError("scan description must specify sum or product")
    raw_initial = optional(arrays, "initial", "init", "carry", "initialcarry")
    carry = np.asarray(raw_initial).copy() if raw_initial is not None else (np.zeros(values.shape[1:], values.dtype) if add else np.ones(values.shape[1:], values.dtype))
    output = []
    for item in values:
        carry = carry + item if add else carry * item
        output.append(carry)
    return np.stack(output)


def scan_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any) -> Any:
    values = jnp.asarray(primary(arrays))
    text = description.lower()
    if values.ndim < 1:
        raise TaskError("scan input needs a leading sequence axis")
    add = any(word in text for word in ("cumulative sum", "running sum", "prefix sum"))
    multiply = any(word in text for word in ("cumulative product", "running product", "prefix product"))
    if not add and not multiply:
        raise TaskError("scan description must specify sum or product")
    raw_initial = optional(arrays, "initial", "init", "carry", "initialcarry")
    initial = jnp.asarray(raw_initial) if raw_initial is not None else (jnp.zeros(values.shape[1:], values.dtype) if add else jnp.ones(values.shape[1:], values.dtype))
    def step(carry: Any, item: Any) -> tuple[Any, Any]:
        updated = carry + item if add else carry * item
        return updated, updated
    return jax.lax.scan(step, initial, values)[1]


def kind(description: str) -> str:
    text = description.lower()
    if "gradient" in text or re.search(r"\bgrad\b|derivative", text):
        return "logistic"
    if "scan" in text or "cumulative" in text or "running sum" in text or "running product" in text:
        return "scan"
    if "mlp" in text or "vmap" in text or "two-layer" in text or "neural network" in text:
        return "mlp"
    return "reduction"


def compute(description: str, arrays: Mapping[str, np.ndarray], engine: str) -> tuple[Any, Any]:
    family = kind(description)
    if engine == "jax":
        import jax
        import jax.numpy as jnp
        if family == "logistic":
            return logistic_jax(description, arrays, jax, jnp), jax.device_get
        if family == "scan":
            return scan_jax(description, arrays, jax, jnp), jax.device_get
        if family == "mlp":
            return mlp_jax(description, arrays, jax, jnp), jax.device_get
        return reduce_value(description, arrays, jnp), jax.device_get
    if family == "logistic":
        return logistic_numpy(description, arrays), np.asarray
    if family == "scan":
        return scan_numpy(description, arrays), np.asarray
    if family == "mlp":
        return mlp_numpy(description, arrays), np.asarray
    return reduce_value(description, arrays, np), np.asarray


def checked(value: Any, task_id: str, materialize: Any) -> np.ndarray:
    result = np.asarray(materialize(value))
    if result.size == 0 or result.dtype.hasobject or result.dtype.kind not in "biufc":
        raise TaskError(f"task {task_id!r} did not produce a nonempty numeric array")
    if result.dtype.kind in "fc" and not np.isfinite(result).all():
        raise TaskError(f"task {task_id!r} produced NaN or infinity")
    return result


def save(path: Path, result: np.ndarray) -> None:
    if path.suffix.lower() not in {".npy", ".npz"}:
        raise TaskError(f"unsupported output format: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".result-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            if path.suffix.lower() == ".npy":
                np.save(stream, result, allow_pickle=False)
            else:
                np.savez(stream, result=result)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


def verify(path: Path, task_id: str) -> None:
    loaded = load_arrays(path)
    if len(loaded) != 1:
        raise TaskError(f"task {task_id!r} output must contain exactly one array")
    checked(next(iter(loaded.values())), task_id, np.asarray)


def direct(request: Mapping[str, Any], engine: str) -> dict[str, Any]:
    raw_manifest = request.get("problem", "/app/problem.json")
    if not isinstance(raw_manifest, str) or not raw_manifest:
        raise TaskError("problem must be a nonempty path string")
    manifest = Path(raw_manifest).resolve()
    tasks = read_manifest(manifest)
    report = []
    for task in tasks:
        source = _path(manifest, task["input"])
        target = _path(manifest, task["output"])
        if not source.is_file():
            raise TaskError(f"task {task['id']!r} input is unavailable: {source}")
        value, materialize = compute(task["description"], load_arrays(source), engine)
        result = checked(value, str(task["id"]), materialize)
        save(target, result)
        report.append({"id": str(task["id"]), "output": str(target), "shape": list(result.shape), "dtype": str(result.dtype)})
    for task in tasks:
        verify(_path(manifest, task["output"]), str(task["id"]))
    return {"ok": True, "engine": engine, "outputs": report}


def automatic(request: Mapping[str, Any]) -> dict[str, Any]:
    child_request = dict(request)
    child_request["engine"] = "jax"
    try:
        child = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())],
            input=json.dumps(child_request), text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=240, cwd=os.getcwd(),
        )
        if child.returncode == 0:
            response = json.loads(child.stdout)
            if response.get("ok") is True and response.get("engine") == "jax":
                return response
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    # Do not trust any partial artifacts a failed JAX child may have written.
    return direct(request, "numpy")


def main() -> None:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise TaskError("stdin must contain one JSON object")
        engine = request.get("engine", "auto")
        if engine not in {"auto", "jax", "numpy"}:
            raise TaskError("engine must be auto, jax, or numpy")
        response = automatic(request) if engine == "auto" else direct(request, engine)
        print(json.dumps(response, sort_keys=True))
    except (TaskError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
