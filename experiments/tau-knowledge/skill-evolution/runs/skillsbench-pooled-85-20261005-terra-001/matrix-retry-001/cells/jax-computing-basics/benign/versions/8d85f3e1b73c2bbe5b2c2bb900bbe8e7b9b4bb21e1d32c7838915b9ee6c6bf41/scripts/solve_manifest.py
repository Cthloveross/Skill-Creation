#!/usr/bin/env python3
"""Execute all numerical tasks declared by a problem.json manifest.

stdin:  {"problem": "/app/problem.json"}  (the field is optional)
stdout: {"ok": true, "backend": "jax"|"numpy-fallback", "outputs": [...]}.

The process that receives the request deliberately does not import JAX.  A child
performs JAX work with CPU-safe environment settings.  If that child aborts at the
native runtime level, the parent completes the same supported array computations
with NumPy so all required portable artifacts can still be written.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


class TaskError(ValueError):
    """A manifest, input, or description cannot be safely interpreted."""


def norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def resolve(manifest: Path, raw: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise TaskError("manifest input and output values must be nonempty strings")
    path = Path(raw)
    return path if path.is_absolute() else manifest.parent / path


def read_manifest(path: Path):
    try:
        tasks = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TaskError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(tasks, list) or not tasks:
        raise TaskError("problem manifest must be a nonempty list")
    ids, destinations = set(), set()
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise TaskError(f"manifest item {i} is not an object")
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise TaskError(f"manifest item {i} lacks nonempty {field!r}")
        if task["id"] in ids:
            raise TaskError(f"duplicate task id {task['id']!r}")
        ids.add(task["id"])
        source, destination = resolve(path, task["input"]), resolve(path, task["output"])
        if source == destination:
            raise TaskError(f"task {task['id']!r} would overwrite its input")
        if destination in destinations:
            raise TaskError(f"multiple tasks use output {destination}")
        destinations.add(destination)
    return tasks


def load_input(path: Path):
    if path.suffix.lower() not in (".npy", ".npz"):
        raise TaskError(f"unsupported input extension for {path}")
    try:
        loaded = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError(f"cannot load {path}: {exc}") from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            arrays = {key: np.asarray(loaded[key]) for key in loaded.files}
        finally:
            loaded.close()
        if not arrays:
            raise TaskError(f"archive {path} has no arrays")
        return arrays
    return {"__array__": np.asarray(loaded)}


def select(arrays, aliases, optional=False):
    names = {norm(alias) for alias in aliases}
    found = [value for key, value in arrays.items() if norm(key) in names]
    if len(found) == 1:
        return np.asarray(found[0])
    if not found and optional:
        return None
    if not found:
        raise TaskError("needed archive array is absent; keys are " + repr(sorted(arrays)))
    raise TaskError("more than one archive array matches " + repr(sorted(names)))


def primary(arrays):
    if "__array__" in arrays:
        return arrays["__array__"]
    if len(arrays) == 1:
        return next(iter(arrays.values()))
    value = select(arrays, ("x", "xs", "data", "input", "inputs", "values", "seq", "sequence"), True)
    if value is None:
        raise TaskError("cannot choose primary archive array; keys are " + repr(sorted(arrays)))
    return value


def described_axis(description: str):
    text = description.lower()
    match = re.search(r"\baxis(?:es)?\s*(?:=|:|of|along|over|across)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)", text)
    if match:
        values = tuple(int(item.strip()) for item in match.group(1).split(","))
        return values[0] if len(values) == 1 else values
    if any(word in text for word in ("each row", "rows", "last axis", "columns")):
        return -1
    if any(word in text for word in ("each column", "first axis", "leading axis")):
        return 0
    return None


def reduction(description, arrays, xp):
    x = xp.asarray(primary(arrays))
    text, axis = description.lower(), described_axis(description)
    if any(phrase in text for phrase in ("sum of squares", "sum the squares", "squared sum")):
        return xp.sum(xp.square(x), axis=axis)
    if any(phrase in text for phrase in ("mean of squares", "mean the squares")):
        return xp.mean(xp.square(x), axis=axis)
    if "l2 norm" in text or "euclidean norm" in text:
        return xp.sqrt(xp.sum(xp.square(x), axis=axis))
    if re.search(r"\b(mean|average)\b", text):
        return xp.mean(x, axis=axis)
    if re.search(r"\b(product|prod)\b", text):
        return xp.prod(x, axis=axis)
    if re.search(r"\b(maximum|max)\b", text):
        return xp.max(x, axis=axis)
    if re.search(r"\b(minimum|min)\b", text):
        return xp.min(x, axis=axis)
    return xp.sum(x, axis=axis)


def logistic_parts(arrays):
    x = select(arrays, ("x", "features", "inputs", "data"))
    y = np.ravel(select(arrays, ("y", "label", "labels", "target", "targets")))
    w = select(arrays, ("w", "weight", "weights", "theta"))
    b = select(arrays, ("b", "bias", "intercept"), optional=True)
    if x.ndim != 2 or w.ndim != 1 or x.shape[1] != w.size or x.shape[0] != y.size:
        raise TaskError("logistic x, y, and w shapes are incompatible")
    return x, y, w, np.asarray(0 if b is None else b)


def logistic_gradient(description, arrays, jax, xp):
    raw_x, raw_y, raw_w, raw_b = logistic_parts(arrays)
    x = xp.asarray(raw_x, dtype=xp.float32)
    y = xp.asarray(raw_y, dtype=xp.float32)
    w = xp.asarray(raw_w, dtype=xp.float32)
    b = xp.asarray(raw_b, dtype=xp.float32)
    text = description.lower()
    summed = "sum" in text and "mean" not in text and "average" not in text
    if jax is None:
        probabilities = 1.0 / (1.0 + xp.exp(-(x @ w + b)))
        result = x.T @ (probabilities - y)
        return result if summed else result / x.shape[0]

    def objective(weights):
        logits = x @ weights + b
        loss = xp.logaddexp(0.0, logits) - y * logits
        return xp.sum(loss) if summed else xp.mean(loss)

    return jax.grad(objective)(w)


def affine(x, w, b, xp):
    if w.ndim != 2:
        raise TaskError("MLP weight arrays must be rank two")
    if x.shape[-1] == w.shape[0]:
        return xp.matmul(x, w) + b
    if x.shape[-1] == w.shape[1]:
        return xp.matmul(x, xp.swapaxes(w, -1, -2)) + b
    raise TaskError("MLP feature and weight dimensions disagree")


def mlp(description, arrays, jax, xp):
    x = xp.asarray(select(arrays, ("x", "inputs", "features", "data")))
    w1 = xp.asarray(select(arrays, ("w1", "weight1", "weights1", "layer1weight")))
    b1 = xp.asarray(select(arrays, ("b1", "bias1", "layer1bias")))
    w2 = xp.asarray(select(arrays, ("w2", "weight2", "weights2", "layer2weight")))
    b2 = xp.asarray(select(arrays, ("b2", "bias2", "layer2bias")))
    text = description.lower()
    if "tanh" in text:
        activation = xp.tanh
    elif "sigmoid" in text:
        activation = jax.nn.sigmoid if jax is not None else lambda z: 1 / (1 + xp.exp(-z))
    elif "linear" in text or "identity" in text:
        activation = lambda z: z
    else:
        activation = jax.nn.relu if jax is not None else lambda z: xp.maximum(z, 0)

    def one(row):
        return affine(activation(affine(row, w1, b1, xp)), w2, b2, xp)

    if x.ndim < 1:
        raise TaskError("a batched MLP needs a leading batch dimension")
    return jax.vmap(one)(x) if jax is not None else xp.stack([one(row) for row in x])


def scan(description, arrays, jax, xp):
    x = xp.asarray(primary(arrays))
    if x.ndim < 1:
        raise TaskError("scan input needs a leading sequence axis")
    text = description.lower()
    product = any(p in text for p in ("cumulative product", "running product", "prefix product"))
    initial = select(arrays, ("initial", "init", "carry", "initialcarry"), optional=True)
    carry = xp.asarray(initial) if initial is not None else (xp.ones(x.shape[1:], dtype=x.dtype) if product else xp.zeros(x.shape[1:], dtype=x.dtype))
    if jax is not None:
        def step(state, item):
            next_state = state * item if product else state + item
            return next_state, next_state
        return jax.lax.scan(step, carry, x)[1]
    result = xp.cumprod(x, axis=0) if product else xp.cumsum(x, axis=0)
    return result * carry if product else result + carry


def compute(task, arrays, jax, xp):
    text = task["description"].lower()
    if "gradient" in text or "derivative" in text or re.search(r"\bgrad\b", text):
        return logistic_gradient(task["description"], arrays, jax, xp)
    if any(word in text for word in ("cumulative", "prefix", "running sum", "running product", "lax.scan", " scan")):
        return scan(task["description"], arrays, jax, xp)
    if any(word in text for word in ("mlp", "vmap", "two-layer", "two layer", "neural network")):
        return mlp(task["description"], arrays, jax, xp)
    return reduction(task["description"], arrays, xp)


def checked(value, task_id, device_get=None):
    value = np.asarray(device_get(value) if device_get is not None else value)
    if value.size == 0 or value.dtype.hasobject or value.dtype.kind not in "biufc":
        raise TaskError(f"task {task_id!r} did not produce a nonempty numeric ndarray")
    if value.dtype.kind in "fc" and not np.isfinite(value).all():
        raise TaskError(f"task {task_id!r} produced NaN or infinity")
    return value


def save_result(destination: Path, value):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".task-result-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            if destination.suffix.lower() == ".npz":
                np.savez(stream, result=value)
            else:
                np.save(stream, value, allow_pickle=False)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(destination)


def validate_result(path: Path, task_id):
    try:
        loaded = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError(f"output for {task_id!r} is unreadable: {exc}") from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            if len(loaded.files) != 1:
                raise TaskError(f"output for {task_id!r} is not a single result array")
            array = np.asarray(loaded[loaded.files[0]])
        finally:
            loaded.close()
    else:
        array = np.asarray(loaded)
    checked(array, task_id)


def run_engine(request, jax=None, xp=np):
    if not isinstance(request, dict):
        raise TaskError("stdin must be a JSON object")
    manifest = Path(request.get("problem", "/app/problem.json")).resolve()
    tasks = read_manifest(manifest)
    outputs = []
    getter = jax.device_get if jax is not None else None
    for task in tasks:
        source = resolve(manifest, task["input"])
        destination = resolve(manifest, task["output"])
        if not source.is_file():
            raise TaskError(f"input for {task['id']!r} is unavailable: {source}")
        result = checked(compute(task, load_input(source), jax, xp), task["id"], getter)
        save_result(destination, result)
        outputs.append({"id": str(task["id"]), "output": str(destination), "shape": list(result.shape), "dtype": str(result.dtype)})
    for task in tasks:
        validate_result(resolve(manifest, task["output"]), task["id"])
    return outputs


def run_jax_worker(request):
    # Must be set before JAX import.  This task has one CPU and no GPU.
    os.environ.setdefault("JAX_PLATFORMS", "cpu")
    os.environ.setdefault("JAX_DISABLE_JIT", "true")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
    os.environ.setdefault("XLA_FLAGS", "--xla_force_host_platform_device_count=1 --xla_cpu_multi_thread_eigen=false")
    import jax
    import jax.numpy as jnp
    return run_engine(request, jax=jax, xp=jnp)


def run_parent(request):
    manifest = Path(request.get("problem", "/app/problem.json")).resolve()
    read_manifest(manifest)  # validate before either backend writes anything
    child = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--jax-worker"],
        input=json.dumps(request), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if child.returncode == 0:
        try:
            reply = json.loads(child.stdout)
            if reply.get("ok") is True:
                for task in read_manifest(manifest):
                    validate_result(resolve(manifest, task["output"]), task["id"])
                return {"ok": True, "backend": "jax", "outputs": reply["outputs"]}
        except Exception:
            pass
    # The fallback is deliberately parent-side, so a native child abort cannot
    # prevent declared outputs from being created.
    return {"ok": True, "backend": "numpy-fallback", "outputs": run_engine(request, jax=None, xp=np)}


def main():
    try:
        request = json.loads(sys.stdin.read() or "{}")
        if len(sys.argv) > 1 and sys.argv[1] == "--jax-worker":
            response = {"ok": True, "outputs": run_jax_worker(request)}
        else:
            response = run_parent(request)
        print(json.dumps(response, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
