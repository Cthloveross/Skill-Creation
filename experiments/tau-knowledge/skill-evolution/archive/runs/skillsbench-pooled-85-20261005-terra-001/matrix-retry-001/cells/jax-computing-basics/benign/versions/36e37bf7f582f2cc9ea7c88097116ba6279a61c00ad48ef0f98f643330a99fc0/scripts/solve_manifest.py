"""Manifest-driven JAX/NumPy numerical task solver.

stdin:  {"problem": "/app/problem.json", "engine": "numpy" | "jax"}
stdout: {"ok": bool, "engine": str, "outputs": [{"id", "output", "shape", "dtype"}]}

The NumPy engine is a crash-safe equivalent of the JAX formulas.  The JAX engine
is available when the runtime can initialize JAX normally.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

# Set before a possible JAX import.  These values keep CPU JAX conservative.
os.environ.setdefault("JAX_PLATFORMS", "cpu")
os.environ.setdefault("JAX_DISABLE_JIT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import numpy as np


class TaskError(ValueError):
    pass


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def resolve(manifest: Path, raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise TaskError("input and output paths must be nonempty strings")
    path = Path(raw)
    return path if path.is_absolute() else manifest.parent / path


def read_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(decoded, list) or not decoded:
        raise TaskError("problem manifest must be a nonempty list")
    ids: set[str] = set()
    targets: set[Path] = set()
    for index, task in enumerate(decoded):
        if not isinstance(task, dict):
            raise TaskError(f"manifest entry {index} is not an object")
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise TaskError(f"manifest entry {index} has no nonempty {field!r}")
        ident = str(task["id"])
        if ident in ids:
            raise TaskError(f"duplicate task id {ident!r}")
        ids.add(ident)
        source = resolve(path, task["input"])
        target = resolve(path, task["output"])
        if source == target:
            raise TaskError(f"task {ident!r} would overwrite its input")
        if target in targets:
            raise TaskError(f"multiple tasks use output {target}")
        targets.add(target)
    return decoded


def load_input(path: Path) -> dict[str, np.ndarray]:
    if path.suffix.lower() not in {".npy", ".npz"}:
        raise TaskError(f"unsupported input extension for {path}")
    try:
        loaded = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError(f"cannot load {path}: {type(exc).__name__}: {exc}") from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            arrays = {name: np.asarray(loaded[name]) for name in loaded.files}
        finally:
            loaded.close()
        if not arrays:
            raise TaskError(f"input archive {path} has no arrays")
        return arrays
    return {"__array__": np.asarray(loaded)}


def find(arrays: Mapping[str, np.ndarray], *names: str, optional: bool = False) -> np.ndarray | None:
    wanted = {norm(name) for name in names}
    values = [value for key, value in arrays.items() if norm(key) in wanted]
    if len(values) == 1:
        return values[0]
    if not values and optional:
        return None
    if not values:
        raise TaskError(f"missing required array; expected one of {names}, found {list(arrays)}")
    raise TaskError(f"ambiguous archive members for {names}")


def primary(arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    if "__array__" in arrays:
        return arrays["__array__"]
    if len(arrays) == 1:
        return next(iter(arrays.values()))
    value = find(arrays, "x", "xs", "data", "input", "inputs", "values", "sequence", "seq", optional=True)
    if value is None:
        raise TaskError(f"cannot determine primary array from archive keys {list(arrays)}")
    return value


def parse_axis(description: str) -> int | tuple[int, ...] | None:
    text = description.lower()
    match = re.search(r"\baxis(?:es)?\s*(?:=|of|along|over)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)", text)
    if match:
        axes = tuple(int(item.strip()) for item in match.group(1).split(","))
        return axes[0] if len(axes) == 1 else axes
    if "last axis" in text or "each row" in text or "across columns" in text:
        return -1
    if "first axis" in text or "leading axis" in text or "each column" in text or "across rows" in text:
        return 0
    return None


def reduction(description: str, arrays: Mapping[str, np.ndarray], xp: Any) -> Any:
    text = description.lower()
    x = xp.asarray(primary(arrays))
    axis = parse_axis(description)
    if "sum of squares" in text or "squared sum" in text or "sum the squares" in text:
        return xp.sum(xp.square(x), axis=axis)
    if "mean of squares" in text or "mean the squares" in text:
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
    if re.search(r"\b(sum|reduce|total)\b", text):
        return xp.sum(x, axis=axis)
    raise TaskError("description does not identify a supported reduction")


def logistic_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    x = np.asarray(find(arrays, "x", "features", "inputs", "data"))
    y = np.ravel(np.asarray(find(arrays, "y", "labels", "targets", "target")))
    w = np.asarray(find(arrays, "w", "weight", "weights", "theta", "params"))
    raw_bias = find(arrays, "b", "bias", "intercept", optional=True)
    b = 0 if raw_bias is None else np.asarray(raw_bias)
    if x.ndim != 2 or w.ndim != 1 or x.shape[1] != w.shape[0] or y.size != x.shape[0]:
        raise TaskError("incompatible logistic feature, label, and weight shapes")
    logits = x @ w + b
    # Stable sigmoid without importing scipy.
    p = np.empty(np.shape(logits), dtype=np.result_type(logits, np.float32))
    positive = logits >= 0
    p[positive] = 1 / (1 + np.exp(-logits[positive]))
    exp_logits = np.exp(logits[~positive])
    p[~positive] = exp_logits / (1 + exp_logits)
    result = x.T @ (p - y)
    text = description.lower()
    return result if "sum" in text and "mean" not in text and "average" not in text else result / x.shape[0]


def logistic_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any) -> Any:
    x = jnp.asarray(find(arrays, "x", "features", "inputs", "data"))
    y = jnp.ravel(jnp.asarray(find(arrays, "y", "labels", "targets", "target")))
    w = jnp.asarray(find(arrays, "w", "weight", "weights", "theta", "params"))
    raw_bias = find(arrays, "b", "bias", "intercept", optional=True)
    b = 0 if raw_bias is None else jnp.asarray(raw_bias)
    if x.ndim != 2 or w.ndim != 1 or x.shape[1] != w.shape[0] or y.size != x.shape[0]:
        raise TaskError("incompatible logistic feature, label, and weight shapes")
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
        return (jax.nn.sigmoid if jax is not None else lambda z: 1 / (1 + xp.exp(-z)))
    if "linear" in text or "identity" in text:
        return lambda z: z
    return (jax.nn.relu if jax is not None else lambda z: xp.maximum(z, 0))


def affine(x: Any, w: Any, b: Any, xp: Any) -> Any:
    if w.ndim != 2:
        raise TaskError("MLP weight arrays must have rank two")
    if x.shape[-1] == w.shape[0]:
        result = xp.matmul(x, w)
    elif x.shape[-1] == w.shape[1]:
        result = xp.matmul(x, xp.swapaxes(w, -1, -2))
    else:
        raise TaskError("MLP input and weight dimensions disagree")
    try:
        return result + b
    except Exception as exc:
        raise TaskError("MLP bias shape is incompatible") from exc


def mlp_arrays(arrays: Mapping[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray(find(arrays, "x", "inputs", "features", "data"))
    w1 = np.asarray(find(arrays, "w1", "weight1", "weights1", "layer1weight"))
    b1 = np.asarray(find(arrays, "b1", "bias1", "biases1", "layer1bias"))
    w2 = np.asarray(find(arrays, "w2", "weight2", "weights2", "layer2weight"))
    b2 = np.asarray(find(arrays, "b2", "bias2", "biases2", "layer2bias"))
    if x.ndim < 2:
        raise TaskError("batched MLP input must have a batch axis")
    return x, w1, b1, w2, b2


def mlp_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    x, w1, b1, w2, b2 = mlp_arrays(arrays)
    return affine(activation(description, np)(affine(x, w1, b1, np)), w2, b2, np)


def mlp_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any) -> Any:
    x0, w10, b10, w20, b20 = mlp_arrays(arrays)
    x, w1, b1, w2, b2 = map(jnp.asarray, (x0, w10, b10, w20, b20))
    act = activation(description, jnp, jax)
    def one(example: Any) -> Any:
        return affine(act(affine(example, w1, b1, jnp)), w2, b2, jnp)
    return jax.vmap(one)(x)


def scan_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    values = np.asarray(primary(arrays))
    if values.ndim < 1:
        raise TaskError("scan input needs a leading sequence dimension")
    text = description.lower()
    addition = any(term in text for term in ("cumulative sum", "running sum", "prefix sum"))
    multiplication = any(term in text for term in ("cumulative product", "running product", "prefix product"))
    if not addition and not multiplication:
        raise TaskError("scan description must specify cumulative sum or product")
    raw_initial = find(arrays, "initial", "init", "carry", "initialcarry", optional=True)
    carry = (np.asarray(raw_initial).copy() if raw_initial is not None else
             (np.zeros(values.shape[1:], dtype=values.dtype) if addition else np.ones(values.shape[1:], dtype=values.dtype)))
    output = []
    for value in values:
        carry = carry + value if addition else carry * value
        output.append(carry)
    return np.stack(output, axis=0)


def scan_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any) -> Any:
    values = jnp.asarray(primary(arrays))
    if values.ndim < 1:
        raise TaskError("scan input needs a leading sequence dimension")
    text = description.lower()
    addition = any(term in text for term in ("cumulative sum", "running sum", "prefix sum"))
    multiplication = any(term in text for term in ("cumulative product", "running product", "prefix product"))
    if not addition and not multiplication:
        raise TaskError("scan description must specify cumulative sum or product")
    raw_initial = find(arrays, "initial", "init", "carry", "initialcarry", optional=True)
    initial = (jnp.asarray(raw_initial) if raw_initial is not None else
               (jnp.zeros(values.shape[1:], dtype=values.dtype) if addition else jnp.ones(values.shape[1:], dtype=values.dtype)))
    def step(carry: Any, value: Any) -> tuple[Any, Any]:
        new_carry = carry + value if addition else carry * value
        return new_carry, new_carry
    return jax.lax.scan(step, initial, values)[1]


def family(description: str) -> str:
    text = description.lower()
    if "gradient" in text or "derivative" in text or re.search(r"\bgrad\b", text):
        return "logistic"
    if "cumulative" in text or "prefix" in text or "running sum" in text or "running product" in text or "scan" in text:
        return "scan"
    if "mlp" in text or "vmap" in text or "two-layer" in text or "neural network" in text:
        return "mlp"
    return "reduction"


def compute(description: str, arrays: Mapping[str, np.ndarray], engine: str) -> tuple[Any, Any]:
    which = family(description)
    if engine == "jax":
        import jax
        import jax.numpy as jnp
        if which == "logistic":
            return logistic_jax(description, arrays, jax, jnp), jax.device_get
        if which == "mlp":
            return mlp_jax(description, arrays, jax, jnp), jax.device_get
        if which == "scan":
            return scan_jax(description, arrays, jax, jnp), jax.device_get
        return reduction(description, arrays, jnp), jax.device_get
    if which == "logistic":
        return logistic_numpy(description, arrays), np.asarray
    if which == "mlp":
        return mlp_numpy(description, arrays), np.asarray
    if which == "scan":
        return scan_numpy(description, arrays), np.asarray
    return reduction(description, arrays, np), np.asarray


def validate(value: Any, task_id: str, materialize: Any) -> np.ndarray:
    result = np.asarray(materialize(value))
    if result.size == 0 or result.dtype.hasobject or result.dtype.kind not in "biufc":
        raise TaskError(f"task {task_id!r} produced no nonempty numeric ndarray")
    if result.dtype.kind in "fc" and not np.isfinite(result).all():
        raise TaskError(f"task {task_id!r} produced NaN or infinity")
    return result


def save(path: Path, result: np.ndarray) -> None:
    if path.suffix.lower() not in {".npy", ".npz"}:
        raise TaskError(f"unsupported output extension for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".manifest-result-", delete=False) as stream:
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
    loaded = load_input(path)
    if len(loaded) != 1:
        raise TaskError(f"task {task_id!r} output must contain exactly one array")
    validate(next(iter(loaded.values())), task_id, np.asarray)


def run(request: Mapping[str, Any]) -> dict[str, Any]:
    raw_problem = request.get("problem", "/app/problem.json")
    if not isinstance(raw_problem, str) or not raw_problem:
        raise TaskError("problem must be a nonempty path string")
    engine = request.get("engine", "numpy")
    if engine not in {"numpy", "jax"}:
        raise TaskError("engine must be numpy or jax")
    manifest = Path(raw_problem).resolve()
    tasks = read_manifest(manifest)
    outputs = []
    for task in tasks:
        source = resolve(manifest, task["input"])
        target = resolve(manifest, task["output"])
        if not source.is_file():
            raise TaskError(f"task {task['id']!r} input is unavailable: {source}")
        value, materialize = compute(task["description"], load_input(source), engine)
        result = validate(value, str(task["id"]), materialize)
        save(target, result)
        outputs.append({"id": str(task["id"]), "output": str(target), "shape": list(result.shape), "dtype": str(result.dtype)})
    for task in tasks:
        verify(resolve(manifest, task["output"]), str(task["id"]))
    return {"ok": True, "engine": engine, "outputs": outputs}


def main() -> None:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise TaskError("stdin must contain one JSON object")
        print(json.dumps(run(request), sort_keys=True))
    except (TaskError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
