"""Manifest-driven numerical task executor.

stdin JSON:  {"problem": "/app/problem.json", "engine": "numpy" | "jax"}
stdout JSON: {"ok": bool, "engine": str, "outputs": [{"id", "output", "shape", "dtype"}]}

The NumPy implementation is a reliable materialized equivalent of the JAX
implementation.  The JAX mode uses jax.numpy, grad, vmap, and lax.scan.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

# Must be set before a possible JAX import.  They constrain CPU thread use in
# small task sandboxes without changing the mathematical computation.
os.environ.setdefault("JAX_PLATFORMS", "cpu")
os.environ.setdefault("JAX_DISABLE_JIT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import numpy as np


class TaskError(ValueError):
    pass


def canon(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def resolve(manifest: Path, raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise TaskError("manifest input/output paths must be nonempty strings")
    path = Path(raw)
    return path if path.is_absolute() else manifest.parent / path


def read_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(loaded, list) or not loaded:
        raise TaskError("problem.json must be a nonempty list")
    ids: set[str] = set()
    outputs: set[Path] = set()
    for index, task in enumerate(loaded):
        if not isinstance(task, dict):
            raise TaskError(f"manifest entry {index} is not an object")
        for key in ("id", "description", "input", "output"):
            if not isinstance(task.get(key), str) or not task[key].strip():
                raise TaskError(f"manifest entry {index} lacks nonempty {key!r}")
        task_id = task["id"]
        if task_id in ids:
            raise TaskError(f"duplicate task id: {task_id!r}")
        ids.add(task_id)
        source, destination = resolve(path, task["input"]), resolve(path, task["output"])
        if source == destination:
            raise TaskError(f"task {task_id!r} would overwrite its input")
        if destination in outputs:
            raise TaskError(f"multiple tasks write {destination}")
        outputs.add(destination)
    return loaded


def load_arrays(path: Path) -> dict[str, np.ndarray]:
    if path.suffix.lower() not in (".npy", ".npz"):
        raise TaskError(f"unsupported input extension: {path}")
    try:
        data = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError(f"cannot load {path}: {type(exc).__name__}: {exc}") from exc
    if isinstance(data, np.lib.npyio.NpzFile):
        try:
            arrays = {key: np.asarray(data[key]) for key in data.files}
        finally:
            data.close()
        if not arrays:
            raise TaskError(f"archive {path} has no arrays")
        return arrays
    return {"__array__": np.asarray(data)}


def array_member(arrays: Mapping[str, np.ndarray], *aliases: str, optional: bool = False) -> np.ndarray | None:
    wanted = {canon(name) for name in aliases}
    found = [value for name, value in arrays.items() if canon(name) in wanted]
    if len(found) == 1:
        return found[0]
    if not found and optional:
        return None
    if not found:
        raise TaskError(f"expected one of {aliases}; archive has keys {list(arrays)}")
    raise TaskError(f"ambiguous aliases {aliases} in archive")


def primary(arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    if "__array__" in arrays:
        return arrays["__array__"]
    if len(arrays) == 1:
        return next(iter(arrays.values()))
    answer = array_member(arrays, "x", "xs", "data", "input", "inputs", "values", "sequence", "seq", optional=True)
    if answer is None:
        raise TaskError(f"cannot identify primary data array among {list(arrays)}")
    return answer


def described_axis(description: str) -> int | tuple[int, ...] | None:
    text = description.lower()
    match = re.search(r"\baxis(?:es)?\s*(?:=|of|along|over|across)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)", text)
    if match:
        axes = tuple(int(item.strip()) for item in match.group(1).split(","))
        return axes[0] if len(axes) == 1 else axes
    if any(s in text for s in ("last axis", "each row", "across columns")):
        return -1
    if any(s in text for s in ("first axis", "leading axis", "each column", "across rows")):
        return 0
    return None


def reduction(description: str, arrays: Mapping[str, np.ndarray], xp: Any) -> Any:
    text, x, axis = description.lower(), xp.asarray(primary(arrays)), described_axis(description)
    if any(s in text for s in ("sum of squares", "squared sum", "sum the squares")):
        return xp.sum(xp.square(x), axis=axis)
    if any(s in text for s in ("mean of squares", "mean the squares")):
        return xp.mean(xp.square(x), axis=axis)
    if "l2 norm" in text or "euclidean norm" in text:
        return xp.sqrt(xp.sum(xp.square(x), axis=axis))
    if re.search(r"\b(product|prod)\b", text):
        return xp.prod(x, axis=axis)
    if re.search(r"\b(maximum|max)\b", text):
        return xp.max(x, axis=axis)
    if re.search(r"\b(minimum|min)\b", text):
        return xp.min(x, axis=axis)
    if re.search(r"\b(mean|average)\b", text):
        return xp.mean(x, axis=axis)
    if re.search(r"\b(sum|total|reduce|reduction)\b", text):
        return xp.sum(x, axis=axis)
    raise TaskError("description does not state a supported reduction")


def logistic_operands(arrays: Mapping[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray(array_member(arrays, "x", "features", "inputs", "data"))
    y = np.ravel(np.asarray(array_member(arrays, "y", "label", "labels", "target", "targets")))
    w = np.asarray(array_member(arrays, "w", "weight", "weights", "theta", "params"))
    raw_b = array_member(arrays, "b", "bias", "intercept", optional=True)
    b = np.asarray(0 if raw_b is None else raw_b)
    if x.ndim != 2 or w.ndim != 1 or x.shape[1] != w.size or y.size != x.shape[0]:
        raise TaskError("logistic X, y, and weight dimensions are incompatible")
    return x, y, w, b


def logistic_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    x, y, w, b = logistic_operands(arrays)
    logits = x @ w + b
    # Stable sigmoid without overflow warnings.
    p = np.empty_like(logits, dtype=np.result_type(logits, np.float32))
    positive = logits >= 0
    p[positive] = 1 / (1 + np.exp(-logits[positive]))
    e = np.exp(logits[~positive])
    p[~positive] = e / (1 + e)
    grad = x.T @ (p - y)
    text = description.lower()
    return grad if "sum" in text and "mean" not in text and "average" not in text else grad / x.shape[0]


def logistic_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any) -> Any:
    x0, y0, w0, b0 = logistic_operands(arrays)
    x, y, w, b = map(jnp.asarray, (x0, y0, w0, b0))
    text = description.lower()
    use_sum = "sum" in text and "mean" not in text and "average" not in text
    def loss(weights: Any) -> Any:
        logits = x @ weights + b
        values = jnp.logaddexp(0, logits) - y * logits
        return jnp.sum(values) if use_sum else jnp.mean(values)
    return jax.grad(loss)(w)


def activation(description: str, xp: Any, jax: Any | None = None) -> Any:
    text = description.lower()
    if "tanh" in text:
        return xp.tanh
    if "sigmoid" in text:
        return jax.nn.sigmoid if jax is not None else lambda z: 1 / (1 + xp.exp(-z))
    if "linear" in text or "identity" in text:
        return lambda z: z
    return jax.nn.relu if jax is not None else lambda z: xp.maximum(z, 0)


def affine(x: Any, w: Any, b: Any, xp: Any) -> Any:
    if w.ndim != 2:
        raise TaskError("MLP weights must be rank-two arrays")
    if x.shape[-1] == w.shape[0]:
        y = xp.matmul(x, w)
    elif x.shape[-1] == w.shape[1]:
        y = xp.matmul(x, xp.swapaxes(w, -1, -2))
    else:
        raise TaskError("MLP input and weight dimensions disagree")
    try:
        return y + b
    except Exception as exc:
        raise TaskError("MLP bias shape is incompatible") from exc


def mlp_operands(arrays: Mapping[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray(array_member(arrays, "x", "inputs", "features", "data"))
    w1 = np.asarray(array_member(arrays, "w1", "weight1", "weights1", "layer1weight"))
    b1 = np.asarray(array_member(arrays, "b1", "bias1", "biases1", "layer1bias"))
    w2 = np.asarray(array_member(arrays, "w2", "weight2", "weights2", "layer2weight"))
    b2 = np.asarray(array_member(arrays, "b2", "bias2", "biases2", "layer2bias"))
    if x.ndim < 2:
        raise TaskError("batched MLP input requires a leading batch axis")
    return x, w1, b1, w2, b2


def mlp_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    x, w1, b1, w2, b2 = mlp_operands(arrays)
    return affine(activation(description, np)(affine(x, w1, b1, np)), w2, b2, np)


def mlp_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any) -> Any:
    x, w1, b1, w2, b2 = map(jnp.asarray, mlp_operands(arrays))
    act = activation(description, jnp, jax)
    def one(row: Any) -> Any:
        return affine(act(affine(row, w1, b1, jnp)), w2, b2, jnp)
    return jax.vmap(one)(x)


def scan_addition(description: str) -> bool:
    text = description.lower()
    add = any(s in text for s in ("cumulative sum", "running sum", "prefix sum"))
    mul = any(s in text for s in ("cumulative product", "running product", "prefix product"))
    if add == mul:
        raise TaskError("scan description must specify cumulative sum or cumulative product")
    return add


def scan_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    x = np.asarray(primary(arrays))
    if x.ndim < 1:
        raise TaskError("scan needs a leading sequence axis")
    add = scan_addition(description)
    initial = array_member(arrays, "initial", "init", "carry", "initialcarry", optional=True)
    carry = (np.zeros(x.shape[1:], dtype=x.dtype) if add else np.ones(x.shape[1:], dtype=x.dtype)) if initial is None else np.asarray(initial).copy()
    values = []
    for item in x:
        carry = carry + item if add else carry * item
        values.append(carry)
    return np.stack(values)


def scan_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any) -> Any:
    x = jnp.asarray(primary(arrays))
    if x.ndim < 1:
        raise TaskError("scan needs a leading sequence axis")
    add = scan_addition(description)
    initial = array_member(arrays, "initial", "init", "carry", "initialcarry", optional=True)
    carry = (jnp.zeros(x.shape[1:], dtype=x.dtype) if add else jnp.ones(x.shape[1:], dtype=x.dtype)) if initial is None else jnp.asarray(initial)
    def step(state: Any, item: Any) -> tuple[Any, Any]:
        next_state = state + item if add else state * item
        return next_state, next_state
    return jax.lax.scan(step, carry, x)[1]


def kind(description: str) -> str:
    text = description.lower()
    if "gradient" in text or "derivative" in text or re.search(r"\bgrad\b", text):
        return "logistic"
    if any(s in text for s in ("cumulative", "prefix", "running sum", "running product", "lax.scan", " scan")):
        return "scan"
    if any(s in text for s in ("mlp", "vmap", "two-layer", "two layer", "neural network")):
        return "mlp"
    return "reduction"


def compute(description: str, arrays: Mapping[str, np.ndarray], engine: str) -> tuple[Any, Any]:
    task_kind = kind(description)
    if engine == "jax":
        import jax
        import jax.numpy as jnp
        if task_kind == "logistic": return logistic_jax(description, arrays, jax, jnp), jax.device_get
        if task_kind == "mlp": return mlp_jax(description, arrays, jax, jnp), jax.device_get
        if task_kind == "scan": return scan_jax(description, arrays, jax, jnp), jax.device_get
        return reduction(description, arrays, jnp), jax.device_get
    if task_kind == "logistic": return logistic_numpy(description, arrays), np.asarray
    if task_kind == "mlp": return mlp_numpy(description, arrays), np.asarray
    if task_kind == "scan": return scan_numpy(description, arrays), np.asarray
    return reduction(description, arrays, np), np.asarray


def checked(value: Any, task_id: str, materialize: Any) -> np.ndarray:
    result = np.asarray(materialize(value))
    if result.size == 0 or result.dtype.hasobject or result.dtype.kind not in "biufc":
        raise TaskError(f"task {task_id!r} did not produce a nonempty numeric ndarray")
    if result.dtype.kind in "fc" and not np.isfinite(result).all():
        raise TaskError(f"task {task_id!r} produced NaN or infinity")
    return result


def save(path: Path, value: np.ndarray) -> None:
    if path.suffix.lower() not in (".npy", ".npz"):
        raise TaskError(f"unsupported output extension: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".result-", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            if path.suffix.lower() == ".npy":
                np.save(handle, value, allow_pickle=False)
            else:
                np.savez(handle, result=value)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


def verify(path: Path, task_id: str) -> None:
    values = load_arrays(path)
    if len(values) != 1:
        raise TaskError(f"task {task_id!r} output must contain exactly one array")
    checked(next(iter(values.values())), task_id, np.asarray)


def run(request: Mapping[str, Any]) -> dict[str, Any]:
    raw_path = request.get("problem", "/app/problem.json")
    engine = request.get("engine", "numpy")
    if not isinstance(raw_path, str) or not raw_path:
        raise TaskError("problem must be a nonempty path")
    if engine not in ("numpy", "jax"):
        raise TaskError("engine must be numpy or jax")
    manifest = Path(raw_path).resolve()
    tasks = read_manifest(manifest)
    outputs = []
    for task in tasks:
        source, destination = resolve(manifest, task["input"]), resolve(manifest, task["output"])
        if not source.is_file():
            raise TaskError(f"task {task['id']!r} input is unavailable: {source}")
        raw, materialize = compute(task["description"], load_arrays(source), engine)
        result = checked(raw, str(task["id"]), materialize)
        save(destination, result)
        outputs.append({"id": str(task["id"]), "output": str(destination), "shape": list(result.shape), "dtype": str(result.dtype)})
    for task in tasks:
        verify(resolve(manifest, task["output"]), str(task["id"]))
    return {"ok": True, "engine": engine, "outputs": outputs}


def main() -> None:
    try:
        text = sys.stdin.read()
        request = {} if not text.strip() else json.loads(text)
        if not isinstance(request, dict):
            raise TaskError("stdin must contain a JSON object")
        print(json.dumps(run(request), sort_keys=True))
    except (TaskError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
