"""Run JAX numerical tasks declared by a JSON manifest.

stdin:  {"problem": "/app/problem.json"}
stdout: {"ok": true, "outputs": [{"id", "output", "shape", "dtype"}]}
"""
from __future__ import annotations

# Configure a conservative single-CPU JAX process before importing JAX.
import os
os.environ.setdefault("JAX_PLATFORMS", "cpu")
os.environ.setdefault("JAX_DISABLE_JIT", "1")
os.environ.setdefault("XLA_FLAGS", "--xla_cpu_multi_thread_eigen=false --xla_force_host_platform_device_count=1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import json
import re
import sys
import tempfile
from pathlib import Path

import numpy as np


class TaskError(ValueError):
    pass


def canon(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def resolve(manifest_path, raw_path):
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise TaskError("input and output paths must be nonempty strings")
    path = Path(raw_path)
    return path if path.is_absolute() else manifest_path.parent / path


def read_tasks(manifest_path):
    try:
        tasks = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TaskError("cannot read manifest %s: %s" % (manifest_path, exc)) from exc
    if not isinstance(tasks, list) or not tasks:
        raise TaskError("manifest must be a nonempty list")

    ids, outputs = set(), set()
    for number, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise TaskError("manifest entry %d is not an object" % number)
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise TaskError("manifest entry %d lacks a nonempty %s" % (number, field))
        if task["id"] in ids:
            raise TaskError("duplicate task id %r" % task["id"])
        ids.add(task["id"])
        source = resolve(manifest_path, task["input"])
        destination = resolve(manifest_path, task["output"])
        if source == destination:
            raise TaskError("task %r would overwrite its input" % task["id"])
        if destination in outputs:
            raise TaskError("multiple tasks share output %s" % destination)
        outputs.add(destination)
    return tasks


def load_input(path):
    if path.suffix.lower() not in (".npy", ".npz"):
        raise TaskError("unsupported input format %s" % path)
    try:
        loaded = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError("cannot load %s: %s" % (path, exc)) from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            arrays = {key: np.asarray(loaded[key]) for key in loaded.files}
        finally:
            loaded.close()
        if not arrays:
            raise TaskError("archive %s contains no arrays" % path)
        return arrays
    return {"__array__": np.asarray(loaded)}


def member(arrays, aliases, optional=False):
    wanted = {canon(alias) for alias in aliases}
    matches = [value for key, value in arrays.items() if canon(key) in wanted]
    if len(matches) == 1:
        return np.asarray(matches[0])
    if not matches and optional:
        return None
    if not matches:
        raise TaskError("required archive member absent; available keys: %s" % list(arrays))
    raise TaskError("ambiguous archive members for %s" % sorted(wanted))


def primary(arrays):
    if "__array__" in arrays:
        return arrays["__array__"]
    if len(arrays) == 1:
        return next(iter(arrays.values()))
    result = member(arrays, ("x", "xs", "data", "input", "inputs", "sequence", "seq", "values"), optional=True)
    if result is None:
        raise TaskError("cannot identify primary array; available keys: %s" % list(arrays))
    return result


def described_axis(description):
    text = description.lower()
    match = re.search(r"\baxis(?:es)?\s*(?:=|:|of|along|over|across)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)", text)
    if match:
        values = tuple(int(part.strip()) for part in match.group(1).split(","))
        return values[0] if len(values) == 1 else values
    if any(term in text for term in ("each row", "rows", "last axis", "columns")):
        return -1
    if any(term in text for term in ("each column", "first axis", "leading axis")):
        return 0
    return None


def reduction(description, arrays, jnp):
    text = description.lower()
    x = jnp.asarray(primary(arrays))
    axis = described_axis(description)
    if any(term in text for term in ("sum of squares", "sum the squares", "squared sum")):
        return jnp.sum(jnp.square(x), axis=axis)
    if any(term in text for term in ("mean of squares", "mean the squares")):
        return jnp.mean(jnp.square(x), axis=axis)
    if "l2 norm" in text or "euclidean norm" in text:
        return jnp.sqrt(jnp.sum(jnp.square(x), axis=axis))
    if re.search(r"\b(mean|average)\b", text):
        return jnp.mean(x, axis=axis)
    if re.search(r"\b(product|prod)\b", text):
        return jnp.prod(x, axis=axis)
    if re.search(r"\b(maximum|max)\b", text):
        return jnp.max(x, axis=axis)
    if re.search(r"\b(minimum|min)\b", text):
        return jnp.min(x, axis=axis)
    return jnp.sum(x, axis=axis)


def logistic_arguments(arrays):
    x = member(arrays, ("x", "features", "inputs", "data"))
    y = np.ravel(member(arrays, ("y", "label", "labels", "target", "targets")))
    w = member(arrays, ("w", "weight", "weights", "theta", "params"))
    b = member(arrays, ("b", "bias", "intercept"), optional=True)
    b = np.asarray(0 if b is None else b)
    if x.ndim != 2 or w.ndim != 1 or x.shape[1] != w.size or x.shape[0] != y.size:
        raise TaskError("incompatible logistic x, y, and weight shapes")
    return x, y, w, b


def logistic_gradient(description, arrays, jax, jnp):
    x0, y0, w0, b0 = logistic_arguments(arrays)
    x, y, w, b = (jnp.asarray(value) for value in (x0, y0, w0, b0))
    text = description.lower()
    use_sum = "sum" in text and "mean" not in text and "average" not in text

    def loss(weights):
        logits = x @ weights + b
        per_example = jnp.logaddexp(0, logits) - y * logits
        return jnp.sum(per_example) if use_sum else jnp.mean(per_example)

    return jax.grad(loss)(w)


def affine(x, weights, bias, jnp):
    if weights.ndim != 2:
        raise TaskError("MLP weights must be rank two")
    if x.shape[-1] == weights.shape[0]:
        return jnp.matmul(x, weights) + bias
    if x.shape[-1] == weights.shape[1]:
        return jnp.matmul(x, jnp.swapaxes(weights, -1, -2)) + bias
    raise TaskError("MLP input and weight dimensions disagree")


def mlp_arguments(arrays):
    return (
        member(arrays, ("x", "inputs", "features", "data")),
        member(arrays, ("w1", "weight1", "weights1", "layer1weight")),
        member(arrays, ("b1", "bias1", "layer1bias")),
        member(arrays, ("w2", "weight2", "weights2", "layer2weight")),
        member(arrays, ("b2", "bias2", "layer2bias")),
    )


def batched_mlp(description, arrays, jax, jnp):
    x, w1, b1, w2, b2 = (jnp.asarray(value) for value in mlp_arguments(arrays))
    text = description.lower()
    if "tanh" in text:
        activation = jnp.tanh
    elif "sigmoid" in text:
        activation = jax.nn.sigmoid
    elif "softmax" in text:
        activation = jax.nn.softmax
    elif "linear" in text or "identity" in text:
        activation = lambda value: value
    else:
        activation = jax.nn.relu

    def one_example(row):
        hidden = activation(affine(row, w1, b1, jnp))
        return affine(hidden, w2, b2, jnp)

    if x.ndim < 1:
        raise TaskError("batched MLP input needs a batch axis")
    return jax.vmap(one_example)(x)


def scan_task(description, arrays, jax, jnp):
    x = jnp.asarray(primary(arrays))
    if x.ndim < 1:
        raise TaskError("scan input needs a leading sequence axis")
    text = description.lower()
    is_product = any(term in text for term in ("cumulative product", "running product", "prefix product"))
    initial = member(arrays, ("initial", "init", "carry", "initialcarry"), optional=True)
    if initial is None:
        carry = jnp.ones(x.shape[1:], dtype=x.dtype) if is_product else jnp.zeros(x.shape[1:], dtype=x.dtype)
    else:
        carry = jnp.asarray(initial)

    def step(state, item):
        next_state = state * item if is_product else state + item
        return next_state, next_state

    return jax.lax.scan(step, carry, x)[1]


def compute(task, arrays, jax, jnp):
    text = task["description"].lower()
    if "gradient" in text or "derivative" in text or re.search(r"\bgrad\b", text):
        return logistic_gradient(task["description"], arrays, jax, jnp)
    if any(term in text for term in ("cumulative", "prefix", "running sum", "running product", "lax.scan", " scan")):
        return scan_task(task["description"], arrays, jax, jnp)
    if any(term in text for term in ("mlp", "vmap", "two-layer", "two layer", "neural network")):
        return batched_mlp(task["description"], arrays, jax, jnp)
    return reduction(task["description"], arrays, jnp)


def validate(value, task_id, jax):
    result = np.asarray(jax.device_get(value))
    if result.size == 0:
        raise TaskError("task %r produced an empty array" % task_id)
    if result.dtype.hasobject or result.dtype.kind not in "biufc":
        raise TaskError("task %r produced nonportable dtype %s" % (task_id, result.dtype))
    if result.dtype.kind in "fc" and not np.isfinite(result).all():
        raise TaskError("task %r produced NaN or infinity" % task_id)
    return result


def save_result(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=str(path.parent), prefix=".jax-result-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            if path.suffix.lower() == ".npz":
                np.savez(stream, result=result)
            else:
                np.save(stream, result, allow_pickle=False)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


def reload_and_validate(path, task_id):
    try:
        loaded = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError("saved output for %r cannot be reloaded: %s" % (task_id, exc)) from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            if len(loaded.files) != 1:
                raise TaskError("saved output for %r contains multiple arrays" % task_id)
            result = np.asarray(loaded[loaded.files[0]])
        finally:
            loaded.close()
    else:
        result = np.asarray(loaded)
    if result.size == 0 or result.dtype.hasobject or result.dtype.kind not in "biufc":
        raise TaskError("saved output for %r is not a nonempty numeric ndarray" % task_id)
    if result.dtype.kind in "fc" and not np.isfinite(result).all():
        raise TaskError("saved output for %r contains NaN or infinity" % task_id)


def run(request):
    if not isinstance(request, dict):
        raise TaskError("stdin must decode to a JSON object")
    manifest = Path(request.get("problem", "/app/problem.json")).resolve()
    tasks = read_tasks(manifest)

    # Import only after CPU limits are configured and only once per execution.
    import jax
    import jax.numpy as jnp

    report = []
    for task in tasks:
        source = resolve(manifest, task["input"])
        destination = resolve(manifest, task["output"])
        if not source.is_file():
            raise TaskError("input for task %r is unavailable: %s" % (task["id"], source))
        result = validate(compute(task, load_input(source), jax, jnp), task["id"], jax)
        save_result(destination, result)
        report.append({
            "id": str(task["id"]),
            "output": str(destination),
            "shape": list(result.shape),
            "dtype": str(result.dtype),
        })

    for task in tasks:
        reload_and_validate(resolve(manifest, task["output"]), task["id"])
    return {"ok": True, "outputs": report}


def main():
    try:
        request = json.loads(sys.stdin.read() or "{}")
        print(json.dumps(run(request), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
