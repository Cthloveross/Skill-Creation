"""Execute JAX numerical tasks declared in a JSON manifest.

stdin:  {"problem": "/app/problem.json"}
stdout: {"ok": true, "outputs": [{"id", "output", "shape", "dtype"}]}

The process only reads manifest-declared inputs and only writes manifest-declared
outputs.  Thread-related environment variables must be established before JAX is
imported because constrained runners may otherwise abort in the XLA CPU backend.
"""
from __future__ import annotations

import os

# Do not override a deliberate executor choice, but provide safe defaults for a
# one-CPU sandbox before NumPy/JAX can initialize a native thread pool.
os.environ.setdefault("JAX_PLATFORMS", "cpu")
os.environ.setdefault("JAX_DISABLE_JIT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
os.environ.setdefault(
    "XLA_FLAGS",
    "--xla_cpu_multi_thread_eigen=false --xla_force_host_platform_device_count=1",
)

import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

import jax
import jax.numpy as jnp
import numpy as np

# Also disable tracing compilation through JAX's public configuration API. Array
# operations and transforms remain JAX operations, while tiny manifest tasks do
# not need compilation and are more reliable in restricted containers.
jax.config.update("jax_disable_jit", True)


class TaskError(ValueError):
    """A manifest, input, or description cannot be safely interpreted."""


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def resolve(problem: Path, declared: str) -> Path:
    if not isinstance(declared, str) or not declared:
        raise TaskError("manifest input/output paths must be nonempty strings")
    candidate = Path(declared)
    return candidate if candidate.is_absolute() else problem.resolve().parent / candidate


def read_manifest(problem: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(problem.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskError(f"cannot read manifest {problem}: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise TaskError("problem manifest must be a nonempty JSON list")

    ids: set[str] = set()
    outputs: set[Path] = set()
    for index, task in enumerate(raw):
        if not isinstance(task, dict):
            raise TaskError(f"manifest task {index} is not an object")
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise TaskError(f"manifest task {index} lacks nonempty string {field!r}")
        task_id = task["id"]
        if task_id in ids:
            raise TaskError(f"duplicate task id {task_id!r}")
        ids.add(task_id)
        source = resolve(problem, task["input"])
        destination = resolve(problem, task["output"])
        if source == destination:
            raise TaskError(f"task {task_id!r} would overwrite its input")
        if destination in outputs:
            raise TaskError(f"multiple tasks declare output {destination}")
        outputs.add(destination)
    return raw


def load_arrays(path: Path) -> dict[str, np.ndarray]:
    suffix = path.suffix.lower()
    if suffix not in {".npy", ".npz"}:
        raise TaskError(f"unsupported input format {path}; expected .npy or .npz")
    try:
        loaded = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise TaskError(f"cannot load input {path}: {exc}") from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            result = {key: np.asarray(loaded[key]) for key in loaded.files}
        finally:
            loaded.close()
        if not result:
            raise TaskError(f"input archive {path} contains no arrays")
        return result
    return {"__array__": np.asarray(loaded)}


def member(arrays: Mapping[str, np.ndarray], *aliases: str) -> np.ndarray:
    wanted = {normalized(alias) for alias in aliases}
    matches = [value for key, value in arrays.items() if normalized(key) in wanted]
    if len(matches) != 1:
        raise TaskError(f"need exactly one archive member among {aliases}; found {len(matches)}")
    return matches[0]


def optional_member(arrays: Mapping[str, np.ndarray], *aliases: str) -> np.ndarray | None:
    wanted = {normalized(alias) for alias in aliases}
    matches = [value for key, value in arrays.items() if normalized(key) in wanted]
    if len(matches) > 1:
        raise TaskError(f"ambiguous optional archive member among {aliases}")
    return matches[0] if matches else None


def primary(arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    if "__array__" in arrays:
        return arrays["__array__"]
    return member(arrays, "x", "xs", "input", "inputs", "data", "features", "sequence", "values")


def described_axis(description: str) -> int | tuple[int, ...] | None:
    # Handles wording such as "axis=0", "along axis 1", and "axes (0, 2)".
    match = re.search(
        r"\baxis(?:es)?\s*(?:=|of|along)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)",
        description.lower(),
    )
    if not match:
        return None
    values = tuple(int(piece.strip()) for piece in match.group(1).split(","))
    return values[0] if len(values) == 1 else values


def reduction(description: str, arrays: Mapping[str, np.ndarray]):
    text = description.lower()
    x = jnp.asarray(primary(arrays))
    axis = described_axis(text)
    if "sum of squares" in text or "sum the squares" in text or "squared sum" in text:
        return jnp.sum(jnp.square(x), axis=axis)
    if "mean of squares" in text or "mean the squares" in text:
        return jnp.mean(jnp.square(x), axis=axis)
    if "l2 norm" in text or "euclidean norm" in text:
        return jnp.sqrt(jnp.sum(jnp.square(x), axis=axis))
    if re.search(r"\bproduct\b|\bprod\b", text):
        return jnp.prod(x, axis=axis)
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
        raise TaskError("gradient task is not explicitly logistic/sigmoid")
    x = jnp.asarray(member(arrays, "x", "features", "inputs", "data"))
    y = jnp.asarray(member(arrays, "y", "labels", "targets", "target"))
    w = jnp.asarray(member(arrays, "w", "weight", "weights", "theta", "params"))
    raw_bias = optional_member(arrays, "b", "bias", "intercept")
    bias = jnp.asarray(raw_bias) if raw_bias is not None else 0
    if x.ndim < 1 or w.ndim < 1 or x.shape[-1] != w.shape[0]:
        raise TaskError("logistic feature and weight dimensions are incompatible")

    def loss(weights):
        logits = jnp.matmul(x, weights) + bias
        # logaddexp form is stable binary cross entropy. Mean agrees with the
        # usual stated mean logistic loss over all example/output terms.
        return jnp.mean(jnp.logaddexp(0, logits) - y * logits)

    return jax.grad(loss)(w)


def apply_linear(vector, weights, bias):
    """Apply a named dense matrix, accepting the orientation implied by shape."""
    if vector.shape[-1] == weights.shape[0]:
        result = jnp.matmul(vector, weights)
    elif vector.shape[-1] == weights.shape[1]:
        result = jnp.matmul(weights, vector)
    else:
        raise TaskError("MLP layer input and weight dimensions are incompatible")
    try:
        return result + bias
    except TypeError as exc:
        raise TaskError("MLP bias shape is incompatible with layer output") from exc


def mlp_forward(description: str, arrays: Mapping[str, np.ndarray]):
    text = description.lower()
    x = jnp.asarray(member(arrays, "x", "inputs", "features", "data"))
    w1 = jnp.asarray(member(arrays, "w1", "weight1", "weights1", "layer1weight"))
    b1 = jnp.asarray(member(arrays, "b1", "bias1", "layer1bias"))
    w2 = jnp.asarray(member(arrays, "w2", "weight2", "weights2", "layer2weight"))
    b2 = jnp.asarray(member(arrays, "b2", "bias2", "layer2bias"))
    if x.ndim < 2 or w1.ndim != 2 or w2.ndim != 2:
        raise TaskError("batched MLP requires rank-2 batch and weight arrays")
    if "tanh" in text:
        activation = jnp.tanh
    elif "sigmoid" in text:
        activation = jax.nn.sigmoid
    elif "relu" in text:
        activation = jax.nn.relu
    elif "identity" in text or "linear activation" in text:
        activation = lambda value: value
    else:
        raise TaskError("MLP description must state ReLU, tanh, sigmoid, or identity activation")

    def one(example):
        hidden = activation(apply_linear(example, w1, b1))
        return apply_linear(hidden, w2, b2)

    return jax.vmap(one)(x)


def scan_compute(description: str, arrays: Mapping[str, np.ndarray]):
    text = description.lower()
    values = jnp.asarray(primary(arrays))
    if values.ndim < 1:
        raise TaskError("scan input needs a leading sequence axis")
    if "cumulative sum" in text or "running sum" in text or "prefix sum" in text:
        initial = jnp.zeros(values.shape[1:], dtype=values.dtype)
        _, output = jax.lax.scan(lambda carry, item: (carry + item, carry + item), initial, values)
        return output
    if "cumulative product" in text or "running product" in text or "prefix product" in text:
        initial = jnp.ones(values.shape[1:], dtype=values.dtype)
        _, output = jax.lax.scan(lambda carry, item: (carry * item, carry * item), initial, values)
        return output
    raise TaskError("scan description must explicitly specify cumulative sum or product")


def compute(description: str, arrays: Mapping[str, np.ndarray]):
    text = description.lower()
    if "gradient" in text or "derivative" in text:
        return logistic_gradient(description, arrays)
    if "scan" in text or "cumulative" in text or "running sum" in text or "running product" in text:
        return scan_compute(description, arrays)
    if "mlp" in text or "vmap" in text or "vectorized neural" in text or "two-layer" in text:
        return mlp_forward(description, arrays)
    return reduction(description, arrays)


def portable(value: Any, task_id: str) -> np.ndarray:
    array = np.asarray(jax.device_get(value))
    if array.size == 0 or array.dtype.hasobject or array.dtype.kind not in "biufc":
        raise TaskError(f"task {task_id!r} did not produce a nonempty portable numeric array")
    if array.dtype.kind in "fc" and not np.isfinite(array).all():
        raise TaskError(f"task {task_id!r} produced NaN or infinity")
    return array


def save_one(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".npy":
        np.save(path, value, allow_pickle=False)
    elif path.suffix.lower() == ".npz":
        np.savez(path, result=value)
    else:
        raise TaskError(f"unsupported output format {path}; expected .npy or .npz")


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
    tasks = read_manifest(problem)
    report: list[dict[str, Any]] = []

    for task in tasks:
        source = resolve(problem, task["input"])
        destination = resolve(problem, task["output"])
        if not source.is_file():
            raise TaskError(f"task {task['id']!r} input is unavailable: {source}")
        result = portable(compute(task["description"], load_arrays(source)), task["id"])
        save_one(destination, result)
        report.append({
            "id": task["id"],
            "output": str(destination),
            "shape": list(result.shape),
            "dtype": str(result.dtype),
        })

    # Validate every output after writing, not merely the final result.
    for task in tasks:
        verify_one(resolve(problem, task["output"]), task["id"])
    return {"ok": True, "outputs": report}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (TaskError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)
