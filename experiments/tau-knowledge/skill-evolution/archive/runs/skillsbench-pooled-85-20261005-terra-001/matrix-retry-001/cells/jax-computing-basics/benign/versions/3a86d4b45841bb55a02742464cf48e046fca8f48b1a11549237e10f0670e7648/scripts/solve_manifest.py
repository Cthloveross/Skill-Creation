#!/usr/bin/env python3
"""Run numerical tasks declared by a problem.json manifest.

stdin:  {"problem": "/app/problem.json"} (optional field)
stdout: {"ok": bool, "backend": str, "outputs": [...]} or an error object.

The parent intentionally does not import JAX. A child process executes JAX with
CPU-safe settings. If that child suffers a native runtime abort, the parent uses
NumPy formulas with identical supported semantics and still writes the manifest
outputs. Both paths inspect inputs and descriptions at runtime.
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
    pass


def normalized(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def task_path(manifest, value):
    if not isinstance(value, str) or not value.strip():
        raise TaskError("input and output paths must be nonempty strings")
    path = Path(value)
    return path if path.is_absolute() else manifest.parent / path


def read_manifest(manifest):
    try:
        tasks = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TaskError("cannot read manifest %s: %s" % (manifest, exc)) from exc
    if not isinstance(tasks, list) or not tasks:
        raise TaskError("problem.json must be a nonempty task list")

    ids, outputs = set(), set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise TaskError("manifest item %d is not an object" % index)
        for field in ("id", "description", "input", "output"):
            if field not in task or task[field] in (None, ""):
                raise TaskError("manifest item %d lacks %r" % (index, field))
        task_id = str(task["id"])
        if task_id in ids:
            raise TaskError("duplicate task id %r" % task_id)
        ids.add(task_id)
        source = task_path(manifest, task["input"])
        destination = task_path(manifest, task["output"])
        if source == destination:
            raise TaskError("task %r would overwrite its input" % task_id)
        if destination in outputs:
            raise TaskError("multiple tasks declare output %s" % destination)
        outputs.add(destination)
    return tasks


def load_arrays(path):
    if path.suffix.lower() not in (".npy", ".npz"):
        raise TaskError("unsupported input type: %s" % path)
    try:
        loaded = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError("cannot load %s: %s" % (path, exc)) from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            result = {key: np.asarray(loaded[key]) for key in loaded.files}
        finally:
            loaded.close()
        if not result:
            raise TaskError("input archive has no arrays: %s" % path)
        return result
    return {"__array__": np.asarray(loaded)}


def choose(arrays, aliases, optional=False):
    aliases = {normalized(name) for name in aliases}
    found = [value for key, value in arrays.items() if normalized(key) in aliases]
    if len(found) == 1:
        return np.asarray(found[0])
    if not found and optional:
        return None
    if not found:
        raise TaskError("missing required archive member; available keys: %r" % sorted(arrays))
    raise TaskError("ambiguous archive member selection")


def primary_array(arrays):
    if "__array__" in arrays:
        return arrays["__array__"]
    if len(arrays) == 1:
        return next(iter(arrays.values()))
    value = choose(arrays, ("x", "xs", "data", "input", "inputs", "values", "sequence", "seq"), True)
    if value is None:
        raise TaskError("cannot identify primary array; available keys: %r" % sorted(arrays))
    return value


def stated_axis(description):
    text = description.lower()
    match = re.search(r"\baxis(?:es)?\s*(?:=|:|of|along|over|across)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)", text)
    if match:
        axes = tuple(int(part.strip()) for part in match.group(1).split(","))
        return axes[0] if len(axes) == 1 else axes
    if any(phrase in text for phrase in ("each row", "rows", "last axis", "columns")):
        return -1
    if any(phrase in text for phrase in ("each column", "first axis", "leading axis")):
        return 0
    return None


def reduce_task(description, arrays, xp):
    x = xp.asarray(primary_array(arrays))
    text = description.lower()
    axis = stated_axis(description)
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
    if re.search(r"\b(sum|reduce)\b", text):
        return xp.sum(x, axis=axis)
    raise TaskError("description does not identify a supported reduction")


def logistic_inputs(arrays):
    x = choose(arrays, ("x", "features", "inputs", "data"))
    y = np.ravel(choose(arrays, ("y", "label", "labels", "target", "targets")))
    weights = choose(arrays, ("w", "weight", "weights", "theta"))
    bias = choose(arrays, ("b", "bias", "intercept"), optional=True)
    if x.ndim != 2 or weights.ndim != 1 or x.shape[1] != weights.size or x.shape[0] != y.size:
        raise TaskError("incompatible logistic input shapes")
    return x, y, weights, np.asarray(0 if bias is None else bias)


def logistic_gradient(description, arrays, jax, xp):
    raw_x, raw_y, raw_w, raw_b = logistic_inputs(arrays)
    x = xp.asarray(raw_x, dtype=xp.float32)
    y = xp.asarray(raw_y, dtype=xp.float32)
    w = xp.asarray(raw_w, dtype=xp.float32)
    b = xp.asarray(raw_b, dtype=xp.float32)
    text = description.lower()
    use_sum = "sum" in text and "mean" not in text and "average" not in text

    if jax is None:
        probabilities = 1.0 / (1.0 + xp.exp(-(x @ w + b)))
        answer = x.T @ (probabilities - y)
        return answer if use_sum else answer / x.shape[0]

    def loss(candidate_weights):
        logits = x @ candidate_weights + b
        terms = xp.logaddexp(0.0, logits) - y * logits
        return xp.sum(terms) if use_sum else xp.mean(terms)

    return jax.grad(loss)(w)


def affine(x, weight, bias, xp):
    if weight.ndim != 2:
        raise TaskError("MLP weights must be matrices")
    if x.shape[-1] == weight.shape[0]:
        return xp.matmul(x, weight) + bias
    if x.shape[-1] == weight.shape[1]:
        return xp.matmul(x, xp.swapaxes(weight, -1, -2)) + bias
    raise TaskError("MLP weight and feature dimensions disagree")


def mlp_task(description, arrays, jax, xp):
    x = xp.asarray(choose(arrays, ("x", "inputs", "features", "data")))
    w1 = xp.asarray(choose(arrays, ("w1", "weight1", "weights1", "layer1weight")))
    b1 = xp.asarray(choose(arrays, ("b1", "bias1", "layer1bias")))
    w2 = xp.asarray(choose(arrays, ("w2", "weight2", "weights2", "layer2weight")))
    b2 = xp.asarray(choose(arrays, ("b2", "bias2", "layer2bias")))
    if x.ndim < 1:
        raise TaskError("batched MLP input needs a batch axis")
    text = description.lower()
    if "tanh" in text:
        activation = xp.tanh
    elif "sigmoid" in text:
        activation = jax.nn.sigmoid if jax is not None else lambda z: 1 / (1 + xp.exp(-z))
    elif "linear" in text or "identity" in text:
        activation = lambda z: z
    else:
        activation = jax.nn.relu if jax is not None else lambda z: xp.maximum(z, 0)

    def one_example(row):
        hidden = activation(affine(row, w1, b1, xp))
        return affine(hidden, w2, b2, xp)

    if jax is not None:
        return jax.vmap(one_example)(x)
    return xp.stack([one_example(row) for row in x])


def scan_task(description, arrays, jax, xp):
    sequence = xp.asarray(primary_array(arrays))
    if sequence.ndim < 1:
        raise TaskError("scan sequence needs a leading time axis")
    text = description.lower()
    product = any(phrase in text for phrase in ("cumulative product", "running product", "prefix product"))
    supplied_initial = choose(arrays, ("initial", "init", "carry", "initialcarry"), optional=True)
    if supplied_initial is None:
        initial = xp.ones(sequence.shape[1:], dtype=sequence.dtype) if product else xp.zeros(sequence.shape[1:], dtype=sequence.dtype)
    else:
        initial = xp.asarray(supplied_initial)

    if jax is not None:
        def step(carry, item):
            next_carry = carry * item if product else carry + item
            return next_carry, next_carry
        return jax.lax.scan(step, initial, sequence)[1]

    prefixes = xp.cumprod(sequence, axis=0) if product else xp.cumsum(sequence, axis=0)
    return prefixes * initial if product else prefixes + initial


def compute(task, arrays, jax, xp):
    text = str(task["description"]).lower()
    if "gradient" in text or "derivative" in text or re.search(r"\bgrad\b", text):
        return logistic_gradient(text, arrays, jax, xp)
    if any(word in text for word in ("cumulative", "prefix", "running sum", "running product", "lax.scan", " scan")):
        return scan_task(text, arrays, jax, xp)
    if any(word in text for word in ("mlp", "vmap", "two-layer", "two layer", "neural network")):
        return mlp_task(text, arrays, jax, xp)
    return reduce_task(text, arrays, xp)


def numeric_result(value, task_id, device_get=None):
    array = np.asarray(device_get(value) if device_get is not None else value)
    if array.size == 0 or array.dtype.hasobject or array.dtype.kind not in "biufc":
        raise TaskError("task %r did not produce a nonempty numeric ndarray" % task_id)
    if array.dtype.kind in "fc" and not np.isfinite(array).all():
        raise TaskError("task %r produced NaN or infinity" % task_id)
    return array


def save_array(destination, value):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".result-", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            if destination.suffix.lower() == ".npz":
                np.savez(handle, result=value)
            else:
                np.save(handle, value, allow_pickle=False)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(destination)


def validate_output(path, task_id):
    try:
        loaded = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError("output for %r is unreadable: %s" % (task_id, exc)) from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            if len(loaded.files) != 1:
                raise TaskError("output for %r must contain one array" % task_id)
            result = np.asarray(loaded[loaded.files[0]])
        finally:
            loaded.close()
    else:
        result = np.asarray(loaded)
    numeric_result(result, task_id)


def engine(request, jax=None, xp=np):
    if not isinstance(request, dict):
        raise TaskError("stdin must decode to a JSON object")
    manifest = Path(request.get("problem", "/app/problem.json")).resolve()
    tasks = read_manifest(manifest)
    output_info = []
    materialize = jax.device_get if jax is not None else None
    for task in tasks:
        task_id = str(task["id"])
        source = task_path(manifest, task["input"])
        destination = task_path(manifest, task["output"])
        if not source.is_file():
            raise TaskError("input for %r is unavailable: %s" % (task_id, source))
        arrays = load_arrays(source)
        result = numeric_result(compute(task, arrays, jax, xp), task_id, materialize)
        save_array(destination, result)
        output_info.append({"id": task_id, "output": str(destination), "shape": list(result.shape), "dtype": str(result.dtype)})
    for task in tasks:
        validate_output(task_path(manifest, task["output"]), str(task["id"]))
    return output_info


def jax_worker(request):
    # These settings must be established before importing JAX.
    os.environ.setdefault("JAX_PLATFORMS", "cpu")
    os.environ.setdefault("JAX_DISABLE_JIT", "true")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
    os.environ.setdefault("XLA_FLAGS", "--xla_force_host_platform_device_count=1 --xla_cpu_multi_thread_eigen=false")
    import jax
    import jax.numpy as jnp
    return engine(request, jax=jax, xp=jnp)


def run(request):
    manifest = Path(request.get("problem", "/app/problem.json")).resolve()
    read_manifest(manifest)
    child = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--jax-worker"],
        input=json.dumps(request), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if child.returncode == 0:
        try:
            reply = json.loads(child.stdout)
            if reply.get("ok") is True:
                for task in read_manifest(manifest):
                    validate_output(task_path(manifest, task["output"]), str(task["id"]))
                return {"ok": True, "backend": "jax", "outputs": reply["outputs"]}
        except Exception:
            pass
    return {"ok": True, "backend": "numpy-fallback", "outputs": engine(request, jax=None, xp=np)}


def main():
    try:
        request = json.loads(sys.stdin.read() or "{}")
        if len(sys.argv) > 1 and sys.argv[1] == "--jax-worker":
            reply = {"ok": True, "outputs": jax_worker(request)}
        else:
            reply = run(request)
        print(json.dumps(reply, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
