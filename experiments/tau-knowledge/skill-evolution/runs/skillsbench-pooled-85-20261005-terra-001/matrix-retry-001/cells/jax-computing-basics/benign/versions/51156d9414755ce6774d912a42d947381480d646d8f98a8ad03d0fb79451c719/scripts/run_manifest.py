"""Manifest-driven numerical task executor.

stdin:  {"problem": "/app/problem.json", "backend": "auto"}
stdout: {"ok": true, "backend": "jax"|"numpy", "outputs": [...]}

In auto mode a separately spawned JAX worker protects output creation from a
fatal native JAX/XLA initialization failure.  The normal successful path remains
JAX; NumPy is a mathematical safety fallback for constrained runtimes.
"""
from __future__ import annotations

# These must precede any JAX import.  The runner is commonly used in a one-CPU
# sandbox where native libraries otherwise attempt to create excessive threads.
import os
os.environ.setdefault("JAX_PLATFORMS", "cpu")
os.environ.setdefault("JAX_DISABLE_JIT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
os.environ.setdefault(
    "XLA_FLAGS", "--xla_cpu_multi_thread_eigen=false --xla_force_host_platform_device_count=1"
)

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class TaskError(ValueError):
    """A declared task cannot be safely completed."""


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def resolve(problem: Path, value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise TaskError("manifest paths must be nonempty strings")
    path = Path(value)
    return path if path.is_absolute() else problem.resolve().parent / path


def read_manifest(problem: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(problem.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskError(f"cannot read manifest {problem}: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise TaskError("problem.json must be a nonempty list")
    ids: set[str] = set()
    destinations: set[Path] = set()
    for number, task in enumerate(raw):
        if not isinstance(task, dict):
            raise TaskError(f"manifest entry {number} is not an object")
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise TaskError(f"manifest entry {number} lacks nonempty {field!r}")
        task_id = task["id"]
        if task_id in ids:
            raise TaskError(f"duplicate task id {task_id!r}")
        ids.add(task_id)
        source, destination = resolve(problem, task["input"]), resolve(problem, task["output"])
        if source == destination:
            raise TaskError(f"task {task_id!r} would overwrite its input")
        if destination in destinations:
            raise TaskError(f"multiple tasks declare output {destination}")
        destinations.add(destination)
    return raw


def load_arrays(path: Path) -> dict[str, np.ndarray]:
    if path.suffix.lower() not in {".npy", ".npz"}:
        raise TaskError(f"unsupported array file {path}")
    try:
        loaded = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError(f"cannot load {path}: {type(exc).__name__}: {exc}") from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            arrays = {key: np.asarray(loaded[key]) for key in loaded.files}
        finally:
            loaded.close()
        if not arrays:
            raise TaskError(f"archive {path} has no arrays")
        return arrays
    return {"__array__": np.asarray(loaded)}


def member(arrays: Mapping[str, np.ndarray], *aliases: str) -> np.ndarray:
    names = {norm(alias) for alias in aliases}
    values = [value for key, value in arrays.items() if norm(key) in names]
    if len(values) != 1:
        raise TaskError(f"need exactly one archive member among {aliases}; found {len(values)}")
    return values[0]


def optional_member(arrays: Mapping[str, np.ndarray], *aliases: str) -> np.ndarray | None:
    names = {norm(alias) for alias in aliases}
    values = [value for key, value in arrays.items() if norm(key) in names]
    if len(values) > 1:
        raise TaskError(f"ambiguous archive member among {aliases}")
    return values[0] if values else None


def primary(arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    if "__array__" in arrays:
        return arrays["__array__"]
    if len(arrays) == 1:
        return next(iter(arrays.values()))
    return member(arrays, "x", "xs", "input", "inputs", "data", "values", "sequence", "features")


def described_axis(text: str) -> int | tuple[int, ...] | None:
    found = re.search(
        r"\baxis(?:es)?\s*(?:=|of|along)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)",
        text.lower(),
    )
    if not found:
        if "last axis" in text.lower():
            return -1
        return None
    values = tuple(int(x.strip()) for x in found.group(1).split(","))
    return values[0] if len(values) == 1 else values


def activation_for(text: str, xp, sigmoid):
    lower = text.lower()
    if "relu" in lower:
        return lambda x: xp.maximum(x, 0)
    if "tanh" in lower:
        return xp.tanh
    if "sigmoid" in lower:
        return sigmoid
    if "gelu" in lower:
        return lambda x: 0.5 * x * (1 + xp.tanh(np.sqrt(2 / np.pi) * (x + 0.044715 * x ** 3)))
    if "identity" in lower or "linear activation" in lower:
        return lambda x: x
    raise TaskError("MLP description must name its hidden activation")


def apply_linear(x, weights, bias, xp):
    if weights.ndim != 2:
        raise TaskError("MLP weights must be matrices")
    if x.shape[-1] == weights.shape[0]:
        value = xp.matmul(x, weights)
    elif x.shape[-1] == weights.shape[1]:
        value = xp.matmul(weights, x)
    else:
        raise TaskError("MLP layer dimensions are incompatible")
    try:
        return value + bias
    except Exception as exc:
        raise TaskError("MLP bias dimensions are incompatible") from exc


def reduce_compute(description: str, arrays: Mapping[str, np.ndarray], xp):
    text, x = description.lower(), xp.asarray(primary(arrays))
    axis = described_axis(text)
    if "sum of squares" in text or "sum the squares" in text or "squared sum" in text:
        return xp.sum(xp.square(x), axis=axis)
    if "mean of squares" in text or "mean the squares" in text:
        return xp.mean(xp.square(x), axis=axis)
    if "l2 norm" in text or "euclidean norm" in text:
        return xp.sqrt(xp.sum(xp.square(x), axis=axis))
    if re.search(r"\bproduct\b|\bprod\b", text):
        return xp.prod(x, axis=axis)
    if re.search(r"\bmaximum\b|\bmax\b", text):
        return xp.max(x, axis=axis)
    if re.search(r"\bminimum\b|\bmin\b", text):
        return xp.min(x, axis=axis)
    if re.search(r"\bmean\b|\baverage\b", text):
        return xp.mean(x, axis=axis)
    if re.search(r"\bsum\b|\breduce\b", text):
        return xp.sum(x, axis=axis)
    raise TaskError("unrecognized reduction description")


def logistic_inputs(arrays: Mapping[str, np.ndarray], xp):
    x = xp.asarray(member(arrays, "x", "features", "inputs", "data"))
    y = xp.asarray(member(arrays, "y", "labels", "targets", "target"))
    w = xp.asarray(member(arrays, "w", "weight", "weights", "theta", "params"))
    raw_bias = optional_member(arrays, "b", "bias", "intercept")
    bias = xp.asarray(raw_bias) if raw_bias is not None else 0
    if x.ndim < 2 or w.ndim < 1 or x.shape[-1] != w.shape[0]:
        raise TaskError("logistic feature and weight dimensions are incompatible")
    return x, y, w, bias


def logistic_numpy(description: str, arrays: Mapping[str, np.ndarray]):
    x, y, w, bias = logistic_inputs(arrays, np)
    logits = np.matmul(x, w) + bias
    probability = np.where(logits >= 0, 1 / (1 + np.exp(-logits)), np.exp(logits) / (1 + np.exp(logits)))
    error = probability - y
    gradient = np.matmul(np.swapaxes(x, -1, -2), error)
    if "sum" not in description.lower() or "mean" in description.lower() or "average" in description.lower():
        gradient = gradient / y.size
    return gradient


def logistic_jax(description: str, arrays: Mapping[str, np.ndarray], jax, jnp):
    x, y, w, bias = logistic_inputs(arrays, jnp)
    average = "sum" not in description.lower() or "mean" in description.lower() or "average" in description.lower()
    def loss(weights):
        logits = jnp.matmul(x, weights) + bias
        terms = jnp.logaddexp(0, logits) - y * logits
        return jnp.mean(terms) if average else jnp.sum(terms)
    return jax.grad(loss)(w)


def mlp_compute(description: str, arrays: Mapping[str, np.ndarray], xp, sigmoid, vmap=None):
    x = xp.asarray(member(arrays, "x", "inputs", "features", "data"))
    w1 = xp.asarray(member(arrays, "w1", "weight1", "weights1", "layer1weight"))
    b1 = xp.asarray(member(arrays, "b1", "bias1", "biases1", "layer1bias"))
    w2 = xp.asarray(member(arrays, "w2", "weight2", "weights2", "layer2weight"))
    b2 = xp.asarray(member(arrays, "b2", "bias2", "biases2", "layer2bias"))
    if x.ndim < 2:
        raise TaskError("MLP input must include a batch dimension")
    activation = activation_for(description, xp, sigmoid)
    def one(example):
        return apply_linear(activation(apply_linear(example, w1, b1, xp)), w2, b2, xp)
    return vmap(one)(x) if vmap is not None else xp.stack([one(example) for example in x])


def scan_compute(description: str, arrays: Mapping[str, np.ndarray], xp, scan=None):
    text, values = description.lower(), xp.asarray(primary(arrays))
    if values.ndim < 1:
        raise TaskError("scan requires a leading sequence axis")
    is_sum = "cumulative sum" in text or "running sum" in text or "prefix sum" in text
    is_product = "cumulative product" in text or "running product" in text or "prefix product" in text
    if not (is_sum or is_product):
        raise TaskError("scan description must specify cumulative sum or product")
    if scan is None:
        return xp.cumsum(values, axis=0) if is_sum else xp.cumprod(values, axis=0)
    initial = xp.zeros(values.shape[1:], dtype=values.dtype) if is_sum else xp.ones(values.shape[1:], dtype=values.dtype)
    operation = (lambda a, b: a + b) if is_sum else (lambda a, b: a * b)
    _, output = scan(lambda carry, item: (operation(carry, item), operation(carry, item)), initial, values)
    return output


def task_kind(description: str) -> str:
    text = description.lower()
    if "gradient" in text or "derivative" in text:
        return "logistic"
    if "scan" in text or "cumulative" in text or "running sum" in text or "running product" in text:
        return "scan"
    if "mlp" in text or "vmap" in text or "two-layer" in text or "neural network" in text:
        return "mlp"
    return "reduce"


def compute_numpy(description: str, arrays: Mapping[str, np.ndarray]):
    kind = task_kind(description)
    if kind == "logistic":
        return logistic_numpy(description, arrays)
    if kind == "scan":
        return scan_compute(description, arrays, np)
    if kind == "mlp":
        sigmoid = lambda x: 1 / (1 + np.exp(-x))
        return mlp_compute(description, arrays, np, sigmoid)
    return reduce_compute(description, arrays, np)


def compute_jax(description: str, arrays: Mapping[str, np.ndarray], jax, jnp):
    kind = task_kind(description)
    if kind == "logistic":
        return logistic_jax(description, arrays, jax, jnp)
    if kind == "scan":
        return scan_compute(description, arrays, jnp, jax.lax.scan)
    if kind == "mlp":
        return mlp_compute(description, arrays, jnp, jax.nn.sigmoid, jax.vmap)
    return reduce_compute(description, arrays, jnp)


def portable(value: Any, task_id: str, device_get=None) -> np.ndarray:
    if device_get is not None:
        value = device_get(value)
    result = np.asarray(value)
    if result.size == 0 or result.dtype.hasobject or result.dtype.kind not in "biufc":
        raise TaskError(f"task {task_id!r} did not produce a nonempty numeric array")
    if result.dtype.kind in "fc" and not np.isfinite(result).all():
        raise TaskError(f"task {task_id!r} produced NaN or infinity")
    return result


def save_one(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".npy":
        np.save(path, value, allow_pickle=False)
    elif path.suffix.lower() == ".npz":
        np.savez(path, result=value)
    else:
        raise TaskError(f"unsupported output format {path}")


def verify_one(path: Path, task_id: str) -> None:
    arrays = load_arrays(path)
    if len(arrays) != 1:
        raise TaskError(f"task {task_id!r} output must contain exactly one array")
    portable(next(iter(arrays.values())), task_id)


def run(request: dict[str, Any], backend: str) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise TaskError("stdin must be a JSON object")
    raw_problem = request.get("problem", "/app/problem.json")
    if not isinstance(raw_problem, str) or not raw_problem:
        raise TaskError("problem must be a nonempty string")
    problem = Path(raw_problem)
    tasks = read_manifest(problem)
    if backend == "jax":
        import jax
        import jax.numpy as jnp
        jax.config.update("jax_disable_jit", True)
        compute = lambda description, arrays: compute_jax(description, arrays, jax, jnp)
        materialize = jax.device_get
    elif backend == "numpy":
        compute, materialize = compute_numpy, None
    else:
        raise TaskError(f"unknown backend {backend!r}")
    report = []
    for task in tasks:
        source, destination = resolve(problem, task["input"]), resolve(problem, task["output"])
        if not source.is_file():
            raise TaskError(f"task {task['id']!r} input is unavailable: {source}")
        value = portable(compute(task["description"], load_arrays(source)), task["id"], materialize)
        save_one(destination, value)
        report.append({"id": task["id"], "output": str(destination), "shape": list(value.shape), "dtype": str(value.dtype)})
    for task in tasks:
        verify_one(resolve(problem, task["output"]), task["id"])
    return {"ok": True, "backend": backend, "outputs": report}


def emit(result: dict[str, Any], status: int = 0) -> None:
    print(json.dumps(result, sort_keys=True))
    if status:
        raise SystemExit(status)


def main() -> None:
    try:
        request = json.load(sys.stdin)
        requested = request.get("backend", "auto") if isinstance(request, dict) else None
        if requested not in {"auto", "jax", "numpy"}:
            raise TaskError("backend must be 'auto', 'jax', or 'numpy'")
        if "--jax-worker" in sys.argv:
            emit(run(request, "jax"))
        if requested == "auto":
            worker = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--jax-worker"],
                input=json.dumps(request), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=os.getcwd(), env=os.environ.copy(), check=False,
            )
            if worker.returncode == 0:
                try:
                    result = json.loads(worker.stdout)
                    if result.get("ok") is True:
                        emit(result)
                except (json.JSONDecodeError, AttributeError):
                    pass
            # A native JAX abort cannot be caught inside that process.  Continue
            # in this intact parent with equivalent NumPy array operations.
            emit(run(request, "numpy"))
        emit(run(request, requested))
    except (TaskError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        emit({"ok": False, "error": str(exc)}, 2)


if __name__ == "__main__":
    main()
