"""Execute JAX numerical tasks specified by a problem.json manifest.

Input (stdin):  {"problem": "/app/problem.json"}
Output (stdout): {"ok": true, "outputs": [{"id", "output", "shape", "dtype"}, ...]}

The program never modifies an input or manifest.  It writes each result at the
manifest's exact output path and reloads all written files before success.
"""
from __future__ import annotations

# Set these before importing NumPy/JAX.  They make JAX usable in a small,
# single-CPU sandbox without changing the numerical meaning of the tasks.
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
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class TaskError(ValueError):
    """A manifest task cannot be completed safely or unambiguously."""


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def resolve(manifest: Path, raw: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise TaskError("input and output paths must be nonempty strings")
    path = Path(raw)
    return path if path.is_absolute() else manifest.parent / path


def read_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(value, list) or not value:
        raise TaskError("problem manifest must be a nonempty list")

    ids: set[str] = set()
    outputs: set[Path] = set()
    for index, task in enumerate(value):
        if not isinstance(task, dict):
            raise TaskError(f"manifest entry {index} is not an object")
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise TaskError(f"manifest entry {index} lacks a nonempty {field!r}")
        task_id = str(task["id"])
        if task_id in ids:
            raise TaskError(f"duplicate task id {task_id!r}")
        ids.add(task_id)
        source = resolve(path, task["input"])
        destination = resolve(path, task["output"])
        if source == destination:
            raise TaskError(f"task {task_id!r} would overwrite its input")
        if destination in outputs:
            raise TaskError(f"more than one task writes {destination}")
        outputs.add(destination)
    return value


def load_arrays(path: Path) -> dict[str, np.ndarray]:
    if path.suffix.lower() not in {".npy", ".npz"}:
        raise TaskError(f"unsupported numerical input format: {path}")
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


def named(arrays: Mapping[str, np.ndarray], *aliases: str) -> np.ndarray:
    wanted = {normalized(alias) for alias in aliases}
    matches = [array for key, array in arrays.items() if normalized(key) in wanted]
    if len(matches) != 1:
        raise TaskError(f"need exactly one archive member among {aliases}; found {len(matches)}")
    return matches[0]


def optional_named(arrays: Mapping[str, np.ndarray], *aliases: str) -> np.ndarray | None:
    wanted = {normalized(alias) for alias in aliases}
    matches = [array for key, array in arrays.items() if normalized(key) in wanted]
    if len(matches) > 1:
        raise TaskError(f"ambiguous archive members among {aliases}")
    return matches[0] if matches else None


def primary(arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    if "__array__" in arrays:
        return arrays["__array__"]
    if len(arrays) == 1:
        return next(iter(arrays.values()))
    return named(arrays, "x", "xs", "input", "inputs", "data", "values", "sequence", "seq")


def described_axis(text: str) -> int | tuple[int, ...] | None:
    lower = text.lower()
    match = re.search(
        r"\baxis(?:es)?\s*(?:=|of|along|over)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)",
        lower,
    )
    if match:
        axes = tuple(int(item.strip()) for item in match.group(1).split(","))
        return axes[0] if len(axes) == 1 else axes
    if "last axis" in lower:
        return -1
    if "first axis" in lower or "leading axis" in lower:
        return 0
    return None


def reduction(description: str, arrays: Mapping[str, np.ndarray], jnp):
    text = description.lower()
    x = jnp.asarray(primary(arrays))
    axis = described_axis(text)
    if "sum of squares" in text or "sum the squares" in text or "squared sum" in text:
        return jnp.sum(jnp.square(x), axis=axis)
    if "mean of squares" in text or "mean the squares" in text:
        return jnp.mean(jnp.square(x), axis=axis)
    if "l2 norm" in text or "euclidean norm" in text:
        return jnp.sqrt(jnp.sum(jnp.square(x), axis=axis))
    if re.search(r"\b(product|prod)\b", text):
        return jnp.prod(x, axis=axis)
    if re.search(r"\b(maximum|max)\b", text):
        return jnp.max(x, axis=axis)
    if re.search(r"\b(minimum|min)\b", text):
        return jnp.min(x, axis=axis)
    if re.search(r"\b(mean|average)\b", text):
        return jnp.mean(x, axis=axis)
    if re.search(r"\b(sum|reduce|total)\b", text):
        return jnp.sum(x, axis=axis)
    raise TaskError("unrecognized reduction operation")


def logistic_gradient(description: str, arrays: Mapping[str, np.ndarray], jax, jnp):
    x = jnp.asarray(named(arrays, "x", "features", "inputs", "data"))
    y = jnp.asarray(named(arrays, "y", "labels", "targets", "target"))
    weights = jnp.asarray(named(arrays, "w", "weight", "weights", "theta", "params"))
    raw_bias = optional_named(arrays, "b", "bias", "intercept")
    bias = jnp.asarray(raw_bias) if raw_bias is not None else 0
    if x.ndim < 2 or weights.ndim != 1 or x.shape[-1] != weights.shape[0]:
        raise TaskError("logistic feature and weight dimensions are incompatible")
    if y.size != x.shape[0]:
        raise TaskError("logistic labels must have one value per example")
    text = description.lower()
    use_sum = "sum" in text and "mean" not in text and "average" not in text

    def loss(w):
        logits = jnp.matmul(x, w) + bias
        # logaddexp form is stable for large positive or negative logits.
        terms = jnp.logaddexp(0, logits) - y * logits
        return jnp.sum(terms) if use_sum else jnp.mean(terms)

    return jax.grad(loss)(weights)


def activation(description: str, jnp, jax):
    text = description.lower()
    if "tanh" in text:
        return jnp.tanh
    if "sigmoid" in text:
        return jax.nn.sigmoid
    if "gelu" in text:
        return jax.nn.gelu
    if "identity" in text or "linear activation" in text:
        return lambda x: x
    # ReLU is the conventional two-layer MLP activation and is also the task
    # family default when the description calls it simply an MLP.
    return jax.nn.relu


def linear(value, weights, bias, jnp):
    if weights.ndim != 2:
        raise TaskError("MLP weight arrays must be rank two")
    if value.shape[-1] == weights.shape[0]:
        output = jnp.matmul(value, weights)
    elif value.shape[-1] == weights.shape[1]:
        output = jnp.matmul(weights, value)
    else:
        raise TaskError("MLP layer dimensions are incompatible")
    try:
        return output + bias
    except Exception as exc:
        raise TaskError("MLP bias dimensions are incompatible") from exc


def mlp(description: str, arrays: Mapping[str, np.ndarray], jax, jnp):
    x = jnp.asarray(named(arrays, "x", "inputs", "features", "data"))
    w1 = jnp.asarray(named(arrays, "w1", "weight1", "weights1", "layer1weight"))
    b1 = jnp.asarray(named(arrays, "b1", "bias1", "biases1", "layer1bias"))
    w2 = jnp.asarray(named(arrays, "w2", "weight2", "weights2", "layer2weight"))
    b2 = jnp.asarray(named(arrays, "b2", "bias2", "biases2", "layer2bias"))
    if x.ndim < 2:
        raise TaskError("batched MLP input must have a batch axis")
    hidden_activation = activation(description, jnp, jax)

    def one(example):
        return linear(hidden_activation(linear(example, w1, b1, jnp)), w2, b2, jnp)

    return jax.vmap(one)(x)


def scan(description: str, arrays: Mapping[str, np.ndarray], jax, jnp):
    text = description.lower()
    values = jnp.asarray(primary(arrays))
    if values.ndim < 1:
        raise TaskError("scan input needs a leading sequence axis")
    is_sum = any(phrase in text for phrase in ("cumulative sum", "running sum", "prefix sum"))
    is_product = any(phrase in text for phrase in ("cumulative product", "running product", "prefix product"))
    if not is_sum and not is_product:
        raise TaskError("scan description must name cumulative sum or product")
    raw_initial = optional_named(arrays, "initial", "init", "carry", "initialcarry")
    if raw_initial is None:
        initial = jnp.zeros(values.shape[1:], values.dtype) if is_sum else jnp.ones(values.shape[1:], values.dtype)
    else:
        initial = jnp.asarray(raw_initial)

    if is_sum:
        def step(carry, item):
            updated = carry + item
            return updated, updated
    else:
        def step(carry, item):
            updated = carry * item
            return updated, updated
    _, result = jax.lax.scan(step, initial, values)
    return result


def compute(description: str, arrays: Mapping[str, np.ndarray], jax, jnp):
    text = description.lower()
    if "gradient" in text or re.search(r"\bgrad\b|derivative", text):
        return logistic_gradient(description, arrays, jax, jnp)
    if "scan" in text or "cumulative" in text or "running sum" in text or "running product" in text:
        return scan(description, arrays, jax, jnp)
    if "mlp" in text or "vmap" in text or "two-layer" in text or "neural network" in text:
        return mlp(description, arrays, jax, jnp)
    return reduction(description, arrays, jnp)


def portable(value: Any, task_id: str, device_get) -> np.ndarray:
    result = np.asarray(device_get(value))
    if result.size == 0:
        raise TaskError(f"task {task_id!r} produced an empty array")
    if result.dtype.hasobject or result.dtype.kind not in "biufc":
        raise TaskError(f"task {task_id!r} produced non-numeric dtype {result.dtype}")
    if result.dtype.kind in "fc" and not np.isfinite(result).all():
        raise TaskError(f"task {task_id!r} produced NaN or infinity")
    return result


def save_result(path: Path, value: np.ndarray) -> None:
    suffix = path.suffix.lower()
    if suffix not in {".npy", ".npz"}:
        raise TaskError(f"unsupported output format {path}; use .npy or .npz")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Writing through an open temporary file prevents np.save from changing a
    # declared filename and avoids exposing a partial result on interruption.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".result-", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            if suffix == ".npy":
                np.save(handle, value, allow_pickle=False)
            else:
                np.savez(handle, result=value)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


def verify_result(path: Path, task_id: str) -> None:
    arrays = load_arrays(path)
    if len(arrays) != 1:
        raise TaskError(f"task {task_id!r} output must contain exactly one array")
    array = next(iter(arrays.values()))
    if array.size == 0 or array.dtype.hasobject or array.dtype.kind not in "biufc":
        raise TaskError(f"task {task_id!r} output is not a nonempty numeric array")
    if array.dtype.kind in "fc" and not np.isfinite(array).all():
        raise TaskError(f"task {task_id!r} output contains NaN or infinity")


def run(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise TaskError("stdin must contain one JSON object")
    raw_problem = request.get("problem", "/app/problem.json")
    if not isinstance(raw_problem, str) or not raw_problem:
        raise TaskError("problem must be a nonempty path string")
    manifest = Path(raw_problem).resolve()
    tasks = read_manifest(manifest)

    import jax
    import jax.numpy as jnp
    jax.config.update("jax_disable_jit", True)

    report: list[dict[str, Any]] = []
    for task in tasks:
        source = resolve(manifest, task["input"])
        destination = resolve(manifest, task["output"])
        if not source.is_file():
            raise TaskError(f"task {task['id']!r} input is unavailable: {source}")
        result = portable(compute(task["description"], load_arrays(source), jax, jnp), str(task["id"]), jax.device_get)
        save_result(destination, result)
        report.append({
            "id": str(task["id"]),
            "output": str(destination),
            "shape": list(result.shape),
            "dtype": str(result.dtype),
        })

    for task in tasks:
        verify_result(resolve(manifest, task["output"]), str(task["id"]))
    return {"ok": True, "outputs": report}


def main() -> None:
    try:
        request = json.load(sys.stdin)
        print(json.dumps(run(request), sort_keys=True))
    except (TaskError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
