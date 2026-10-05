"""Run all numerical tasks in a problem.json manifest.

stdin:  {"problem": "/app/problem.json", "engine": "numpy" | "jax"}
stdout: {"ok": bool, "engine": str, "outputs": [{"id", "output", "shape", "dtype"}]}

Empty stdin deliberately means the default /app/problem.json request, so that a
normal direct execution still produces task artifacts.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

# These must precede an optional JAX import. They make its CPU mode less likely
# to oversubscribe the small task runtime.
os.environ.setdefault("JAX_PLATFORMS", "cpu")
os.environ.setdefault("JAX_DISABLE_JIT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import numpy as np


class TaskError(ValueError):
    """A manifest, input, description, or result violates the task contract."""


def normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def resolve(manifest: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise TaskError("input and output paths must be nonempty strings")
    candidate = Path(value)
    return candidate if candidate.is_absolute() else manifest.parent / candidate


def read_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(value, list) or not value:
        raise TaskError("problem manifest must be a nonempty list")

    ids: set[str] = set()
    destinations: set[Path] = set()
    for number, task in enumerate(value):
        if not isinstance(task, dict):
            raise TaskError(f"manifest entry {number} is not an object")
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise TaskError(f"manifest entry {number} has no nonempty {field!r}")
        task_id = str(task["id"])
        if task_id in ids:
            raise TaskError(f"duplicate task id {task_id!r}")
        ids.add(task_id)
        input_path = resolve(path, task["input"])
        output_path = resolve(path, task["output"])
        if input_path == output_path:
            raise TaskError(f"task {task_id!r} would overwrite its input")
        if output_path in destinations:
            raise TaskError(f"multiple tasks use output {output_path}")
        destinations.add(output_path)
    return value


def load_arrays(path: Path) -> dict[str, np.ndarray]:
    if path.suffix.lower() not in {".npy", ".npz"}:
        raise TaskError(f"unsupported array-file extension: {path}")
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
            raise TaskError(f"input archive {path} has no arrays")
        return result
    return {"__array__": np.asarray(loaded)}


def member(arrays: Mapping[str, np.ndarray], *names: str, optional: bool = False) -> np.ndarray | None:
    aliases = {normalized(name) for name in names}
    matches = [array for key, array in arrays.items() if normalized(key) in aliases]
    if len(matches) == 1:
        return matches[0]
    if not matches and optional:
        return None
    if not matches:
        raise TaskError(f"missing required array; expected one of {names}, found {list(arrays)}")
    raise TaskError(f"ambiguous archive arrays for {names}")


def primary(arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    if "__array__" in arrays:
        return arrays["__array__"]
    if len(arrays) == 1:
        return next(iter(arrays.values()))
    selected = member(arrays, "x", "xs", "data", "input", "inputs", "values", "sequence", "seq", optional=True)
    if selected is None:
        raise TaskError(f"cannot determine primary input from archive keys {list(arrays)}")
    return selected


def parse_axis(description: str) -> int | tuple[int, ...] | None:
    text = description.lower()
    match = re.search(
        r"\baxis(?:es)?\s*(?:=|of|along|over|across)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)",
        text,
    )
    if match:
        axes = tuple(int(part.strip()) for part in match.group(1).split(","))
        return axes[0] if len(axes) == 1 else axes
    if any(phrase in text for phrase in ("last axis", "each row", "across columns")):
        return -1
    if any(phrase in text for phrase in ("first axis", "leading axis", "each column", "across rows")):
        return 0
    return None


def reduce_array(description: str, arrays: Mapping[str, np.ndarray], xp: Any) -> Any:
    text = description.lower()
    values = xp.asarray(primary(arrays))
    axis = parse_axis(description)
    if any(phrase in text for phrase in ("sum of squares", "squared sum", "sum the squares")):
        return xp.sum(xp.square(values), axis=axis)
    if any(phrase in text for phrase in ("mean of squares", "mean the squares")):
        return xp.mean(xp.square(values), axis=axis)
    if "l2 norm" in text or "euclidean norm" in text:
        return xp.sqrt(xp.sum(xp.square(values), axis=axis))
    if re.search(r"\b(product|prod)\b", text):
        return xp.prod(values, axis=axis)
    if re.search(r"\b(maximum|max)\b", text):
        return xp.max(values, axis=axis)
    if re.search(r"\b(minimum|min)\b", text):
        return xp.min(values, axis=axis)
    if re.search(r"\b(mean|average)\b", text):
        return xp.mean(values, axis=axis)
    if re.search(r"\b(sum|reduce|total)\b", text):
        return xp.sum(values, axis=axis)
    raise TaskError("description does not identify a supported reduction")


def logistic_inputs(arrays: Mapping[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    features = np.asarray(member(arrays, "x", "features", "inputs", "data"))
    labels = np.ravel(np.asarray(member(arrays, "y", "labels", "targets", "target")))
    weights = np.asarray(member(arrays, "w", "weight", "weights", "theta", "params"))
    bias_value = member(arrays, "b", "bias", "intercept", optional=True)
    bias = np.asarray(0 if bias_value is None else bias_value)
    if features.ndim != 2 or weights.ndim != 1:
        raise TaskError("logistic features must be rank two and weights rank one")
    if features.shape[1] != weights.shape[0] or labels.size != features.shape[0]:
        raise TaskError("incompatible logistic feature, label, and weight shapes")
    return features, labels, weights, bias


def logistic_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    x, y, w, b = logistic_inputs(arrays)
    logits = x @ w + b
    probabilities = np.empty(logits.shape, dtype=np.result_type(logits, np.float32))
    positive = logits >= 0
    probabilities[positive] = 1 / (1 + np.exp(-logits[positive]))
    exp_logits = np.exp(logits[~positive])
    probabilities[~positive] = exp_logits / (1 + exp_logits)
    gradient = x.T @ (probabilities - y)
    text = description.lower()
    summed = "sum" in text and "mean" not in text and "average" not in text
    return gradient if summed else gradient / x.shape[0]


def logistic_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any) -> Any:
    x0, y0, w0, b0 = logistic_inputs(arrays)
    x, y, w, b = map(jnp.asarray, (x0, y0, w0, b0))
    text = description.lower()
    summed = "sum" in text and "mean" not in text and "average" not in text

    def loss(weights: Any) -> Any:
        logits = x @ weights + b
        terms = jnp.logaddexp(0, logits) - y * logits
        return jnp.sum(terms) if summed else jnp.mean(terms)

    return jax.grad(loss)(w)


def choose_activation(description: str, xp: Any, jax: Any | None = None) -> Any:
    text = description.lower()
    if "tanh" in text:
        return xp.tanh
    if "sigmoid" in text:
        return jax.nn.sigmoid if jax is not None else lambda z: 1 / (1 + xp.exp(-z))
    if "linear" in text or "identity" in text:
        return lambda z: z
    return jax.nn.relu if jax is not None else lambda z: xp.maximum(z, 0)


def affine(values: Any, weights: Any, bias: Any, xp: Any) -> Any:
    if weights.ndim != 2:
        raise TaskError("MLP weight arrays must have rank two")
    if values.shape[-1] == weights.shape[0]:
        output = xp.matmul(values, weights)
    elif values.shape[-1] == weights.shape[1]:
        output = xp.matmul(values, xp.swapaxes(weights, -1, -2))
    else:
        raise TaskError("MLP input and weight dimensions disagree")
    try:
        return output + bias
    except Exception as exc:
        raise TaskError("MLP bias shape is incompatible") from exc


def mlp_inputs(arrays: Mapping[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray(member(arrays, "x", "inputs", "features", "data"))
    w1 = np.asarray(member(arrays, "w1", "weight1", "weights1", "layer1weight"))
    b1 = np.asarray(member(arrays, "b1", "bias1", "biases1", "layer1bias"))
    w2 = np.asarray(member(arrays, "w2", "weight2", "weights2", "layer2weight"))
    b2 = np.asarray(member(arrays, "b2", "bias2", "biases2", "layer2bias"))
    if x.ndim < 2:
        raise TaskError("batched MLP input must have a batch axis")
    return x, w1, b1, w2, b2


def mlp_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    x, w1, b1, w2, b2 = mlp_inputs(arrays)
    hidden = choose_activation(description, np)(affine(x, w1, b1, np))
    return affine(hidden, w2, b2, np)


def mlp_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any) -> Any:
    source = mlp_inputs(arrays)
    x, w1, b1, w2, b2 = map(jnp.asarray, source)
    activation = choose_activation(description, jnp, jax)

    def one(example: Any) -> Any:
        return affine(activation(affine(example, w1, b1, jnp)), w2, b2, jnp)

    return jax.vmap(one)(x)


def scan_kind(description: str) -> bool:
    text = description.lower()
    add = any(word in text for word in ("cumulative sum", "running sum", "prefix sum"))
    multiply = any(word in text for word in ("cumulative product", "running product", "prefix product"))
    if add == multiply:
        raise TaskError("scan description must specify exactly one cumulative sum or product")
    return add


def scan_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    values = np.asarray(primary(arrays))
    if values.ndim < 1:
        raise TaskError("scan input needs a leading sequence dimension")
    addition = scan_kind(description)
    initial_value = member(arrays, "initial", "init", "carry", "initialcarry", optional=True)
    if initial_value is None:
        carry = np.zeros(values.shape[1:], dtype=values.dtype) if addition else np.ones(values.shape[1:], dtype=values.dtype)
    else:
        carry = np.asarray(initial_value).copy()
    output = []
    for value in values:
        carry = carry + value if addition else carry * value
        output.append(carry)
    return np.stack(output, axis=0)


def scan_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any) -> Any:
    values = jnp.asarray(primary(arrays))
    if values.ndim < 1:
        raise TaskError("scan input needs a leading sequence dimension")
    addition = scan_kind(description)
    initial_value = member(arrays, "initial", "init", "carry", "initialcarry", optional=True)
    if initial_value is None:
        initial = jnp.zeros(values.shape[1:], dtype=values.dtype) if addition else jnp.ones(values.shape[1:], dtype=values.dtype)
    else:
        initial = jnp.asarray(initial_value)

    def step(carry: Any, value: Any) -> tuple[Any, Any]:
        next_carry = carry + value if addition else carry * value
        return next_carry, next_carry

    return jax.lax.scan(step, initial, values)[1]


def family(description: str) -> str:
    text = description.lower()
    if "gradient" in text or "derivative" in text or re.search(r"\bgrad\b", text):
        return "logistic"
    if any(word in text for word in ("cumulative", "prefix", "running sum", "running product", "scan")):
        return "scan"
    if any(word in text for word in ("mlp", "vmap", "two-layer", "two layer", "neural network")):
        return "mlp"
    return "reduction"


def compute(description: str, arrays: Mapping[str, np.ndarray], engine: str) -> tuple[Any, Any]:
    kind = family(description)
    if engine == "jax":
        import jax
        import jax.numpy as jnp
        if kind == "logistic":
            return logistic_jax(description, arrays, jax, jnp), jax.device_get
        if kind == "mlp":
            return mlp_jax(description, arrays, jax, jnp), jax.device_get
        if kind == "scan":
            return scan_jax(description, arrays, jax, jnp), jax.device_get
        return reduce_array(description, arrays, jnp), jax.device_get
    if kind == "logistic":
        return logistic_numpy(description, arrays), np.asarray
    if kind == "mlp":
        return mlp_numpy(description, arrays), np.asarray
    if kind == "scan":
        return scan_numpy(description, arrays), np.asarray
    return reduce_array(description, arrays, np), np.asarray


def checked_result(value: Any, task_id: str, materialize: Any) -> np.ndarray:
    result = np.asarray(materialize(value))
    if result.size == 0 or result.dtype.hasobject or result.dtype.kind not in "biufc":
        raise TaskError(f"task {task_id!r} produced no nonempty numeric ndarray")
    if result.dtype.kind in "fc" and not np.isfinite(result).all():
        raise TaskError(f"task {task_id!r} produced NaN or infinity")
    return result


def save_result(path: Path, result: np.ndarray) -> None:
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


def verify_result(path: Path, task_id: str) -> None:
    arrays = load_arrays(path)
    if len(arrays) != 1:
        raise TaskError(f"task {task_id!r} output must contain exactly one array")
    checked_result(next(iter(arrays.values())), task_id, np.asarray)


def run(request: Mapping[str, Any]) -> dict[str, Any]:
    raw_manifest = request.get("problem", "/app/problem.json")
    engine = request.get("engine", "numpy")
    if not isinstance(raw_manifest, str) or not raw_manifest:
        raise TaskError("problem must be a nonempty path string")
    if engine not in {"numpy", "jax"}:
        raise TaskError("engine must be numpy or jax")
    manifest = Path(raw_manifest).resolve()
    tasks = read_manifest(manifest)
    written = []
    for task in tasks:
        source = resolve(manifest, task["input"])
        destination = resolve(manifest, task["output"])
        if not source.is_file():
            raise TaskError(f"task {task['id']!r} input is unavailable: {source}")
        value, materialize = compute(task["description"], load_arrays(source), engine)
        result = checked_result(value, str(task["id"]), materialize)
        save_result(destination, result)
        written.append({"id": str(task["id"]), "output": str(destination), "shape": list(result.shape), "dtype": str(result.dtype)})
    for task in tasks:
        verify_result(resolve(manifest, task["output"]), str(task["id"]))
    return {"ok": True, "engine": engine, "outputs": written}


def main() -> None:
    try:
        raw = sys.stdin.read()
        request = {} if not raw.strip() else json.loads(raw)
        if not isinstance(request, dict):
            raise TaskError("stdin must contain one JSON object")
        print(json.dumps(run(request), sort_keys=True))
    except (TaskError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
