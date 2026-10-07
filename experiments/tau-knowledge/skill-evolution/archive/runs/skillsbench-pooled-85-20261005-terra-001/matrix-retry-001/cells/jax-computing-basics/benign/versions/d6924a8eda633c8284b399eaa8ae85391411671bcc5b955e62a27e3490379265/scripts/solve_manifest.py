"""Execute numerical tasks listed by a problem.json manifest.

stdin:  {"problem": "/app/problem.json"}
stdout: {"ok": bool, "backend": str, "outputs": [...]} or an error object

The parent process deliberately does not import JAX.  It launches a constrained JAX
worker, so a native JAX/XLA abort cannot prevent the parent from completing a safe
portable fallback calculation and saving all manifest outputs.
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


def canonical(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def resolve(manifest, raw):
    if not isinstance(raw, str) or not raw.strip():
        raise TaskError("input and output paths must be nonempty strings")
    path = Path(raw)
    return path if path.is_absolute() else manifest.parent / path


def read_tasks(manifest):
    try:
        tasks = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TaskError("cannot read manifest %s: %s" % (manifest, exc)) from exc
    if not isinstance(tasks, list) or not tasks:
        raise TaskError("manifest must be a nonempty list")
    ids, outputs = set(), set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise TaskError("manifest entry %d is not an object" % index)
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise TaskError("manifest entry %d lacks a nonempty %s" % (index, field))
        if task["id"] in ids:
            raise TaskError("duplicate task id %r" % task["id"])
        ids.add(task["id"])
        src, dst = resolve(manifest, task["input"]), resolve(manifest, task["output"])
        if src == dst:
            raise TaskError("task %r would overwrite its input" % task["id"])
        if dst in outputs:
            raise TaskError("multiple tasks declare output %s" % dst)
        outputs.add(dst)
    return tasks


def load_arrays(path):
    if path.suffix.lower() not in (".npy", ".npz"):
        raise TaskError("unsupported input type %s" % path)
    try:
        loaded = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError("cannot load %s: %s" % (path, exc)) from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            values = {key: np.asarray(loaded[key]) for key in loaded.files}
        finally:
            loaded.close()
        if not values:
            raise TaskError("archive %s has no arrays" % path)
        return values
    return {"__array__": np.asarray(loaded)}


def member(arrays, names, optional=False):
    wanted = {canonical(name) for name in names}
    found = [value for key, value in arrays.items() if canonical(key) in wanted]
    if len(found) == 1:
        return np.asarray(found[0])
    if not found and optional:
        return None
    if not found:
        raise TaskError("required archive key is absent; available keys: %s" % sorted(arrays))
    raise TaskError("multiple archive keys match %s" % sorted(wanted))


def primary(arrays):
    if "__array__" in arrays:
        return arrays["__array__"]
    if len(arrays) == 1:
        return next(iter(arrays.values()))
    value = member(arrays, ("x", "xs", "data", "input", "inputs", "sequence", "seq", "values"), True)
    if value is None:
        raise TaskError("cannot identify primary array; available keys: %s" % sorted(arrays))
    return value


def axis_from(description):
    text = description.lower()
    match = re.search(r"\baxis(?:es)?\s*(?:=|:|of|along|over|across)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)", text)
    if match:
        axes = tuple(int(x.strip()) for x in match.group(1).split(","))
        return axes[0] if len(axes) == 1 else axes
    if any(word in text for word in ("each row", "rows", "last axis", "columns")):
        return -1
    if any(word in text for word in ("each column", "first axis", "leading axis")):
        return 0
    return None


def reduce_task(description, arrays, xp):
    x = xp.asarray(primary(arrays))
    axis = axis_from(description)
    text = description.lower()
    if any(s in text for s in ("sum of squares", "sum the squares", "squared sum")):
        return xp.sum(xp.square(x), axis=axis)
    if any(s in text for s in ("mean of squares", "mean the squares")):
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


def logistic_inputs(arrays):
    x = member(arrays, ("x", "features", "inputs", "data"))
    y = np.ravel(member(arrays, ("y", "label", "labels", "target", "targets")))
    w = member(arrays, ("w", "weight", "weights", "theta"))
    b = member(arrays, ("b", "bias", "intercept"), True)
    if x.ndim != 2 or w.ndim != 1 or x.shape[1] != w.size or x.shape[0] != y.size:
        raise TaskError("incompatible logistic feature, label, and weight shapes")
    return x, y, w, np.asarray(0 if b is None else b)


def logistic_gradient(description, arrays, jax, xp):
    x0, y0, w0, b0 = logistic_inputs(arrays)
    x = xp.asarray(x0, dtype=xp.float32)
    y = xp.asarray(y0, dtype=xp.float32)
    w = xp.asarray(w0, dtype=xp.float32)
    b = xp.asarray(b0, dtype=xp.float32)
    use_sum = "sum" in description.lower() and "mean" not in description.lower() and "average" not in description.lower()
    if jax is None:
        logits = x @ w + b
        probabilities = 1.0 / (1.0 + xp.exp(-logits))
        gradient = x.T @ (probabilities - y)
        return gradient if use_sum else gradient / x.shape[0]

    def loss(weights):
        logits = x @ weights + b
        values = xp.logaddexp(0.0, logits) - y * logits
        return xp.sum(values) if use_sum else xp.mean(values)
    return jax.grad(loss)(w)


def affine(value, weights, bias, xp):
    if weights.ndim != 2:
        raise TaskError("MLP weights must be rank two")
    if value.shape[-1] == weights.shape[0]:
        return xp.matmul(value, weights) + bias
    if value.shape[-1] == weights.shape[1]:
        return xp.matmul(value, xp.swapaxes(weights, -1, -2)) + bias
    raise TaskError("MLP input and weight dimensions disagree")


def mlp_task(description, arrays, jax, xp):
    x = xp.asarray(member(arrays, ("x", "inputs", "features", "data")))
    w1 = xp.asarray(member(arrays, ("w1", "weight1", "weights1", "layer1weight")))
    b1 = xp.asarray(member(arrays, ("b1", "bias1", "layer1bias")))
    w2 = xp.asarray(member(arrays, ("w2", "weight2", "weights2", "layer2weight")))
    b2 = xp.asarray(member(arrays, ("b2", "bias2", "layer2bias")))
    text = description.lower()
    if "tanh" in text:
        act = xp.tanh
    elif "sigmoid" in text:
        act = (jax.nn.sigmoid if jax is not None else lambda z: 1.0 / (1.0 + xp.exp(-z)))
    elif "linear" in text or "identity" in text:
        act = lambda z: z
    else:
        act = (jax.nn.relu if jax is not None else lambda z: xp.maximum(z, 0))

    def one(row):
        return affine(act(affine(row, w1, b1, xp)), w2, b2, xp)
    if x.ndim < 1:
        raise TaskError("batched MLP requires a leading batch axis")
    if jax is not None:
        return jax.vmap(one)(x)
    return xp.stack([one(row) for row in x], axis=0)


def scan_task(description, arrays, jax, xp):
    x = xp.asarray(primary(arrays))
    if x.ndim < 1:
        raise TaskError("scan requires a leading sequence axis")
    text = description.lower()
    product = any(s in text for s in ("cumulative product", "running product", "prefix product"))
    initial = member(arrays, ("initial", "init", "carry", "initialcarry"), True)
    if initial is None:
        carry = xp.ones(x.shape[1:], dtype=x.dtype) if product else xp.zeros(x.shape[1:], dtype=x.dtype)
    else:
        carry = xp.asarray(initial)
    if jax is not None:
        def step(state, item):
            next_state = state * item if product else state + item
            return next_state, next_state
        return jax.lax.scan(step, carry, x)[1]
    # Include the explicit initial carry, matching lax.scan state semantics.
    values = xp.cumprod(x, axis=0) if product else xp.cumsum(x, axis=0)
    return values * carry if product else values + carry


def compute(task, arrays, jax, xp):
    text = task["description"].lower()
    if "gradient" in text or "derivative" in text or re.search(r"\bgrad\b", text):
        return logistic_gradient(task["description"], arrays, jax, xp)
    if any(s in text for s in ("cumulative", "prefix", "running sum", "running product", "lax.scan", " scan")):
        return scan_task(task["description"], arrays, jax, xp)
    if any(s in text for s in ("mlp", "vmap", "two-layer", "two layer", "neural network")):
        return mlp_task(task["description"], arrays, jax, xp)
    return reduce_task(task["description"], arrays, xp)


def checked_array(value, task_id, device_get=None):
    result = np.asarray(device_get(value) if device_get is not None else value)
    if result.size == 0 or result.dtype.hasobject or result.dtype.kind not in "biufc":
        raise TaskError("task %r did not produce a nonempty numeric ndarray" % task_id)
    if result.dtype.kind in "fc" and not np.isfinite(result).all():
        raise TaskError("task %r produced NaN or infinity" % task_id)
    return result


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".result-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            if path.suffix.lower() == ".npz":
                np.savez(stream, result=value)
            else:
                np.save(stream, value, allow_pickle=False)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


def verify(path, task_id):
    try:
        loaded = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError("output for %r is unreadable: %s" % (task_id, exc)) from exc
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            if len(loaded.files) != 1:
                raise TaskError("output for %r contains more than one array" % task_id)
            value = np.asarray(loaded[loaded.files[0]])
        finally:
            loaded.close()
    else:
        value = np.asarray(loaded)
    checked_array(value, task_id)


def engine(request, jax=None, xp=np):
    if not isinstance(request, dict):
        raise TaskError("stdin must contain a JSON object")
    manifest = Path(request.get("problem", "/app/problem.json")).resolve()
    tasks = read_tasks(manifest)
    report = []
    getter = jax.device_get if jax is not None else None
    for task in tasks:
        source, output = resolve(manifest, task["input"]), resolve(manifest, task["output"])
        if not source.is_file():
            raise TaskError("input for task %r is unavailable: %s" % (task["id"], source))
        value = checked_array(compute(task, load_arrays(source), jax, xp), task["id"], getter)
        save(output, value)
        report.append({"id": str(task["id"]), "output": str(output), "shape": list(value.shape), "dtype": str(value.dtype)})
    for task in tasks:
        verify(resolve(manifest, task["output"]), task["id"])
    return report


def jax_worker(request):
    # These must precede the JAX import in this child process.
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


def parent(request):
    # Confirm manifest validity before creating any child or outputs.
    manifest = Path(request.get("problem", "/app/problem.json")).resolve()
    read_tasks(manifest)
    payload = json.dumps(request)
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--jax-worker"], input=payload, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if child.returncode == 0:
        try:
            response = json.loads(child.stdout)
            if response.get("ok"):
                # Independently check the child wrote all declared portable files.
                for task in read_tasks(manifest):
                    verify(resolve(manifest, task["output"]), task["id"])
                return {"ok": True, "backend": "jax", "outputs": response["outputs"]}
        except Exception:
            pass
    # A native child failure is contained.  Recompute every output reliably in parent.
    return {"ok": True, "backend": "numpy-fallback", "outputs": engine(request, jax=None, xp=np)}


def main():
    try:
        request = json.loads(sys.stdin.read() or "{}")
        if len(sys.argv) > 1 and sys.argv[1] == "--jax-worker":
            print(json.dumps({"ok": True, "outputs": jax_worker(request)}, sort_keys=True))
        else:
            print(json.dumps(parent(request), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
