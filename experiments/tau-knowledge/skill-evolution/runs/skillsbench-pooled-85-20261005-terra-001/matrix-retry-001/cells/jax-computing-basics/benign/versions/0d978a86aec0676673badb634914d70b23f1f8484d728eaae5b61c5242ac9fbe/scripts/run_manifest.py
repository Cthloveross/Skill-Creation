"""Run numerical tasks declared by a problem.json manifest.

stdin JSON:
  {"problem": "/app/problem.json", "engine": "auto"}
stdout JSON on success:
  {"ok": true, "engine": "jax"|"numpy", "outputs": [{id, output, shape, dtype}]}

The auto engine isolates JAX in a child process.  This lets a parent process
finish all required artifacts with equivalent eager array formulas when a JAX
native runtime aborts (which cannot be handled with Python try/except).
"""
from __future__ import annotations

# These must precede a possible JAX import in the child.
import os
os.environ.setdefault("JAX_PLATFORMS", "cpu")
os.environ.setdefault("JAX_DISABLE_JIT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
os.environ.setdefault("XLA_FLAGS", "--xla_cpu_multi_thread_eigen=false --xla_force_host_platform_device_count=1")

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class TaskError(ValueError):
    """A task cannot be interpreted safely from public manifest information."""


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def resolve(manifest: Path, raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise TaskError("manifest input/output paths must be nonempty strings")
    candidate = Path(raw)
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
    for i, task in enumerate(value):
        if not isinstance(task, dict):
            raise TaskError(f"manifest entry {i} is not an object")
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise TaskError(f"manifest entry {i} lacks nonempty {field!r}")
        task_id = task["id"]
        if task_id in ids:
            raise TaskError(f"duplicate task id {task_id!r}")
        ids.add(task_id)
        source, target = resolve(path, task["input"]), resolve(path, task["output"])
        if source == target:
            raise TaskError(f"task {task_id!r} would overwrite its input")
        if target in destinations:
            raise TaskError(f"multiple tasks declare output {target}")
        destinations.add(target)
    return value


def load_arrays(path: Path) -> dict[str, np.ndarray]:
    if path.suffix.lower() not in {".npy", ".npz"}:
        raise TaskError(f"unsupported array input format: {path}")
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
            raise TaskError(f"archive {path} has no members")
        return arrays
    return {"__array__": np.asarray(loaded)}


def named(arrays: Mapping[str, np.ndarray], *aliases: str) -> np.ndarray:
    wanted = {norm(a) for a in aliases}
    matches = [value for key, value in arrays.items() if norm(key) in wanted]
    if len(matches) != 1:
        raise TaskError(f"expected exactly one array named one of {aliases}; found {len(matches)}")
    return matches[0]


def optional_named(arrays: Mapping[str, np.ndarray], *aliases: str) -> np.ndarray | None:
    wanted = {norm(a) for a in aliases}
    matches = [value for key, value in arrays.items() if norm(key) in wanted]
    if len(matches) > 1:
        raise TaskError(f"ambiguous arrays named one of {aliases}")
    return matches[0] if matches else None


def primary(arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    if "__array__" in arrays:
        return arrays["__array__"]
    if len(arrays) == 1:
        return next(iter(arrays.values()))
    return named(arrays, "x", "xs", "input", "inputs", "data", "values", "sequence", "seq")


def described_axis(description: str) -> int | tuple[int, ...] | None:
    text = description.lower()
    match = re.search(r"\baxis(?:es)?\s*(?:=|of|along|over)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)", text)
    if match:
        values = tuple(int(v.strip()) for v in match.group(1).split(","))
        return values[0] if len(values) == 1 else values
    if "last axis" in text:
        return -1
    if "first axis" in text or "leading axis" in text:
        return 0
    return None


def reduction(description: str, arrays: Mapping[str, np.ndarray], xp: Any):
    text, x, axis = description.lower(), xp.asarray(primary(arrays)), described_axis(description)
    if "sum of squares" in text or "sum the squares" in text or "squared sum" in text:
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
    raise TaskError("unrecognized reduction operation")


def logistic_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    x = np.asarray(named(arrays, "x", "features", "inputs", "data"))
    y = np.asarray(named(arrays, "y", "labels", "targets", "target"))
    w = np.asarray(named(arrays, "w", "weight", "weights", "theta", "params"))
    bias_array = optional_named(arrays, "b", "bias", "intercept")
    bias = np.asarray(bias_array) if bias_array is not None else 0
    if x.ndim != 2 or w.ndim != 1 or x.shape[1] != w.shape[0] or y.size != x.shape[0]:
        raise TaskError("incompatible logistic feature, label, and weight dimensions")
    logits = np.matmul(x, w) + bias
    # Stable sigmoid for the derivative of binary cross entropy.
    probabilities = np.empty_like(logits, dtype=np.result_type(logits, np.float32))
    positive = logits >= 0
    probabilities[positive] = 1 / (1 + np.exp(-logits[positive]))
    exp_logits = np.exp(logits[~positive])
    probabilities[~positive] = exp_logits / (1 + exp_logits)
    gradient = np.matmul(x.T, probabilities - np.ravel(y))
    text = description.lower()
    return gradient if "sum" in text and "mean" not in text and "average" not in text else gradient / x.shape[0]


def logistic_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any):
    x = jnp.asarray(named(arrays, "x", "features", "inputs", "data"))
    y = jnp.asarray(named(arrays, "y", "labels", "targets", "target"))
    w = jnp.asarray(named(arrays, "w", "weight", "weights", "theta", "params"))
    raw_bias = optional_named(arrays, "b", "bias", "intercept")
    bias = jnp.asarray(raw_bias) if raw_bias is not None else 0
    if x.ndim != 2 or w.ndim != 1 or x.shape[1] != w.shape[0] or y.size != x.shape[0]:
        raise TaskError("incompatible logistic feature, label, and weight dimensions")
    use_sum = "sum" in description.lower() and "mean" not in description.lower() and "average" not in description.lower()
    def loss(weights):
        logits = jnp.matmul(x, weights) + bias
        terms = jnp.logaddexp(0, logits) - jnp.ravel(y) * logits
        return jnp.sum(terms) if use_sum else jnp.mean(terms)
    return jax.grad(loss)(w)


def activation(description: str, xp: Any, jax: Any | None = None):
    text = description.lower()
    if "tanh" in text:
        return xp.tanh
    if "sigmoid" in text:
        if jax is not None:
            return jax.nn.sigmoid
        return lambda value: 1 / (1 + np.exp(-value))
    if "gelu" in text and jax is not None:
        return jax.nn.gelu
    if "gelu" in text:
        return lambda value: 0.5 * value * (1 + np.tanh(np.sqrt(2 / np.pi) * (value + 0.044715 * value ** 3)))
    if "identity" in text or "linear activation" in text:
        return lambda value: value
    if jax is not None:
        return jax.nn.relu
    return lambda value: xp.maximum(value, 0)


def linear(value: Any, weights: Any, bias: Any, xp: Any):
    if weights.ndim != 2:
        raise TaskError("MLP weights must be rank two")
    if value.shape[-1] == weights.shape[0]:
        output = xp.matmul(value, weights)
    elif value.shape[-1] == weights.shape[1]:
        output = xp.matmul(weights, value)
    else:
        raise TaskError("MLP layer dimensions are incompatible")
    try:
        return output + bias
    except Exception as exc:
        raise TaskError("MLP bias dimensions are incompatible") from exc


def mlp_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    x = np.asarray(named(arrays, "x", "inputs", "features", "data"))
    w1, b1 = np.asarray(named(arrays, "w1", "weight1", "weights1", "layer1weight")), np.asarray(named(arrays, "b1", "bias1", "biases1", "layer1bias"))
    w2, b2 = np.asarray(named(arrays, "w2", "weight2", "weights2", "layer2weight")), np.asarray(named(arrays, "b2", "bias2", "biases2", "layer2bias"))
    if x.ndim < 2:
        raise TaskError("batched MLP input needs a batch axis")
    act = activation(description, np)
    return linear(act(linear(x, w1, b1, np)), w2, b2, np)


def mlp_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any):
    x = jnp.asarray(named(arrays, "x", "inputs", "features", "data"))
    w1, b1 = jnp.asarray(named(arrays, "w1", "weight1", "weights1", "layer1weight")), jnp.asarray(named(arrays, "b1", "bias1", "biases1", "layer1bias"))
    w2, b2 = jnp.asarray(named(arrays, "w2", "weight2", "weights2", "layer2weight")), jnp.asarray(named(arrays, "b2", "bias2", "biases2", "layer2bias"))
    if x.ndim < 2:
        raise TaskError("batched MLP input needs a batch axis")
    act = activation(description, jnp, jax)
    def one(example):
        return linear(act(linear(example, w1, b1, jnp)), w2, b2, jnp)
    return jax.vmap(one)(x)


def scan_numpy(description: str, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    text, values = description.lower(), np.asarray(primary(arrays))
    if values.ndim < 1:
        raise TaskError("scan input needs a leading sequence axis")
    is_sum = any(s in text for s in ("cumulative sum", "running sum", "prefix sum"))
    is_product = any(s in text for s in ("cumulative product", "running product", "prefix product"))
    if not is_sum and not is_product:
        raise TaskError("scan must specify cumulative sum or product")
    raw = optional_named(arrays, "initial", "init", "carry", "initialcarry")
    carry = np.asarray(raw).copy() if raw is not None else (np.zeros(values.shape[1:], values.dtype) if is_sum else np.ones(values.shape[1:], values.dtype))
    result = []
    for item in values:
        carry = carry + item if is_sum else carry * item
        result.append(carry)
    return np.stack(result)


def scan_jax(description: str, arrays: Mapping[str, np.ndarray], jax: Any, jnp: Any):
    text, values = description.lower(), jnp.asarray(primary(arrays))
    if values.ndim < 1:
        raise TaskError("scan input needs a leading sequence axis")
    is_sum = any(s in text for s in ("cumulative sum", "running sum", "prefix sum"))
    is_product = any(s in text for s in ("cumulative product", "running product", "prefix product"))
    if not is_sum and not is_product:
        raise TaskError("scan must specify cumulative sum or product")
    raw = optional_named(arrays, "initial", "init", "carry", "initialcarry")
    initial = jnp.asarray(raw) if raw is not None else (jnp.zeros(values.shape[1:], values.dtype) if is_sum else jnp.ones(values.shape[1:], values.dtype))
    def step(carry, item):
        updated = carry + item if is_sum else carry * item
        return updated, updated
    return jax.lax.scan(step, initial, values)[1]


def compute(description: str, arrays: Mapping[str, np.ndarray], engine: str):
    text = description.lower()
    if engine == "jax":
        import jax
        import jax.numpy as jnp
        if "gradient" in text or re.search(r"\bgrad\b|derivative", text):
            return logistic_jax(description, arrays, jax, jnp), jax.device_get
        if "scan" in text or "cumulative" in text or "running sum" in text or "running product" in text:
            return scan_jax(description, arrays, jax, jnp), jax.device_get
        if "mlp" in text or "vmap" in text or "two-layer" in text or "neural network" in text:
            return mlp_jax(description, arrays, jax, jnp), jax.device_get
        return reduction(description, arrays, jnp), jax.device_get
    if "gradient" in text or re.search(r"\bgrad\b|derivative", text):
        return logistic_numpy(description, arrays), np.asarray
    if "scan" in text or "cumulative" in text or "running sum" in text or "running product" in text:
        return scan_numpy(description, arrays), np.asarray
    if "mlp" in text or "vmap" in text or "two-layer" in text or "neural network" in text:
        return mlp_numpy(description, arrays), np.asarray
    return reduction(description, arrays, np), np.asarray


def validate_value(value: Any, task_id: str, materialize: Any) -> np.ndarray:
    result = np.asarray(materialize(value))
    if result.size == 0 or result.dtype.hasobject or result.dtype.kind not in "biufc":
        raise TaskError(f"task {task_id!r} did not produce a nonempty numeric array")
    if result.dtype.kind in "fc" and not np.isfinite(result).all():
        raise TaskError(f"task {task_id!r} produced NaN or infinity")
    return result


def save_result(path: Path, value: np.ndarray) -> None:
    if path.suffix.lower() not in {".npy", ".npz"}:
        raise TaskError(f"unsupported output format {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".manifest-result-", delete=False) as handle:
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
    arrays = load_arrays(path)
    if len(arrays) != 1:
        raise TaskError(f"task {task_id!r} output must have exactly one array")
    validate_value(next(iter(arrays.values())), task_id, np.asarray)


def run_direct(request: dict[str, Any], engine: str) -> dict[str, Any]:
    raw_problem = request.get("problem", "/app/problem.json")
    if not isinstance(raw_problem, str) or not raw_problem:
        raise TaskError("problem must be a nonempty path string")
    manifest = Path(raw_problem).resolve()
    tasks = read_manifest(manifest)
    report = []
    for task in tasks:
        source, target = resolve(manifest, task["input"]), resolve(manifest, task["output"])
        if not source.is_file():
            raise TaskError(f"task {task['id']!r} input is unavailable: {source}")
        value, materialize = compute(task["description"], load_arrays(source), engine)
        result = validate_value(value, str(task["id"]), materialize)
        save_result(target, result)
        report.append({"id": str(task["id"]), "output": str(target), "shape": list(result.shape), "dtype": str(result.dtype)})
    for task in tasks:
        verify(resolve(manifest, task["output"]), str(task["id"]))
    return {"ok": True, "engine": engine, "outputs": report}


def run_auto(request: dict[str, Any]) -> dict[str, Any]:
    child_request = dict(request)
    child_request["engine"] = "jax"
    try:
        child = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())], input=json.dumps(child_request),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=os.getcwd(), timeout=300,
        )
        if child.returncode == 0:
            response = json.loads(child.stdout)
            if response.get("ok") is True and response.get("engine") == "jax":
                return response
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    # A JAX child might have crashed after writing some outputs. Recompute every
    # task atomically, rather than trusting a partial set of child artifacts.
    return run_direct(request, "numpy")


def main() -> None:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise TaskError("stdin must be one JSON object")
        engine = request.get("engine", "auto")
        if engine not in {"auto", "jax", "numpy"}:
            raise TaskError("engine must be auto, jax, or numpy")
        response = run_auto(request) if engine == "auto" else run_direct(request, engine)
        print(json.dumps(response, sort_keys=True))
    except (TaskError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
