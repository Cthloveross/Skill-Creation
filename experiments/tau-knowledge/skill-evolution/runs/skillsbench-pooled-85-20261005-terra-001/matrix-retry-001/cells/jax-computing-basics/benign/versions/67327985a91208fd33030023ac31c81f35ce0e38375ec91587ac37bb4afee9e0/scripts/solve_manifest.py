"""Execute numerical tasks from a JSON manifest.

stdin:  {"problem": "/app/problem.json", "engine": "numpy"|"jax"}
stdout: {"ok": true, "outputs": [{"id", "output", "shape", "dtype"}]}
"""
from __future__ import annotations

# These must precede a possible JAX import.  They make the optional JAX mode
# suitable for a one-CPU sandbox without changing the numerical formulas.
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


def resolve(manifest, value):
    if not isinstance(value, str) or not value.strip():
        raise TaskError("task paths must be nonempty strings")
    p = Path(value)
    return p if p.is_absolute() else manifest.parent / p


def canon(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def manifest_tasks(path):
    try:
        tasks = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TaskError("cannot read manifest: %s" % exc) from exc
    if not isinstance(tasks, list) or not tasks:
        raise TaskError("manifest must be a nonempty list")
    ids, destinations = set(), set()
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise TaskError("manifest entry %d is not an object" % i)
        for field in ("id", "description", "input", "output"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise TaskError("manifest entry %d lacks %s" % (i, field))
        if task["id"] in ids:
            raise TaskError("duplicate task id")
        ids.add(task["id"])
        src, dst = resolve(path, task["input"]), resolve(path, task["output"])
        if src == dst:
            raise TaskError("a task output would overwrite its input")
        if dst in destinations:
            raise TaskError("multiple tasks share an output")
        destinations.add(dst)
    return tasks


def load_arrays(path):
    if path.suffix.lower() not in (".npy", ".npz"):
        raise TaskError("unsupported array file: %s" % path)
    try:
        value = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise TaskError("cannot load %s: %s" % (path, exc)) from exc
    if isinstance(value, np.lib.npyio.NpzFile):
        try:
            result = {key: np.asarray(value[key]) for key in value.files}
        finally:
            value.close()
        if not result:
            raise TaskError("input archive is empty")
        return result
    return {"__array__": np.asarray(value)}


def member(values, aliases, optional=False):
    aliases = set(canon(x) for x in aliases)
    found = [v for k, v in values.items() if canon(k) in aliases]
    if len(found) == 1:
        return np.asarray(found[0])
    if not found and optional:
        return None
    if not found:
        raise TaskError("required archive member is absent; keys are %s" % list(values))
    raise TaskError("ambiguous archive member")


def primary(values):
    if "__array__" in values:
        return values["__array__"]
    if len(values) == 1:
        return next(iter(values.values()))
    x = member(values, ("x", "xs", "data", "input", "inputs", "sequence", "seq", "values"), True)
    if x is None:
        raise TaskError("cannot identify primary array; keys are %s" % list(values))
    return x


def axis(description):
    text = description.lower()
    found = re.search(r"\baxis(?:es)?\s*(?:=|:|of|along|over|across)?\s*\(?\s*(-?\d+(?:\s*,\s*-?\d+)*)", text)
    if found:
        nums = tuple(int(x.strip()) for x in found.group(1).split(","))
        return nums[0] if len(nums) == 1 else nums
    if any(x in text for x in ("each row", "rows", "last axis", "columns")):
        return -1
    if any(x in text for x in ("each column", "first axis", "leading axis")):
        return 0
    return None


def reduce_task(description, values, xp):
    text, x, ax = description.lower(), xp.asarray(primary(values)), axis(description)
    if any(s in text for s in ("sum of squares", "sum the squares", "squared sum")):
        return xp.sum(xp.square(x), axis=ax)
    if any(s in text for s in ("mean of squares", "mean the squares")):
        return xp.mean(xp.square(x), axis=ax)
    if "l2 norm" in text or "euclidean norm" in text:
        return xp.sqrt(xp.sum(xp.square(x), axis=ax))
    if re.search(r"\b(mean|average)\b", text):
        return xp.mean(x, axis=ax)
    if re.search(r"\b(product|prod)\b", text):
        return xp.prod(x, axis=ax)
    if re.search(r"\b(maximum|max)\b", text):
        return xp.max(x, axis=ax)
    if re.search(r"\b(minimum|min)\b", text):
        return xp.min(x, axis=ax)
    # A task described as a generic/basic reduction conventionally requests a
    # sum. This also keeps a descriptive wording variation from blocking all
    # manifest output generation.
    return xp.sum(x, axis=ax)


def logistic_inputs(values):
    x = member(values, ("x", "features", "inputs", "data"))
    y = np.ravel(member(values, ("y", "label", "labels", "target", "targets")))
    w = member(values, ("w", "weight", "weights", "theta", "params"))
    b = member(values, ("b", "bias", "intercept"), True)
    b = np.asarray(0 if b is None else b)
    if x.ndim != 2 or w.ndim != 1 or x.shape[1] != w.size or x.shape[0] != y.size:
        raise TaskError("incompatible logistic feature, label, and weight shapes")
    return x, y, w, b


def logistic_numpy(description, values):
    x, y, w, b = logistic_inputs(values)
    z = x @ w + b
    p = np.empty_like(z, dtype=np.result_type(z, np.float32))
    pos = z >= 0
    p[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos]); p[~pos] = ez / (1.0 + ez)
    g = x.T @ (p - y)
    text = description.lower()
    return g if "sum" in text and "mean" not in text and "average" not in text else g / x.shape[0]


def logistic_jax(description, values, jax, jnp):
    x, y, w, b = (jnp.asarray(a) for a in logistic_inputs(values))
    text = description.lower()
    summed = "sum" in text and "mean" not in text and "average" not in text
    def loss(weights):
        z = x @ weights + b
        losses = jnp.logaddexp(0, z) - y * z
        return jnp.sum(losses) if summed else jnp.mean(losses)
    return jax.grad(loss)(w)


def affine(x, w, b, xp):
    if w.ndim != 2:
        raise TaskError("MLP weights must be rank two")
    if x.shape[-1] == w.shape[0]:
        return xp.matmul(x, w) + b
    if x.shape[-1] == w.shape[1]:
        return xp.matmul(x, xp.swapaxes(w, -1, -2)) + b
    raise TaskError("MLP weight and input shapes disagree")


def mlp_inputs(values):
    return (member(values, ("x", "inputs", "features", "data")),
            member(values, ("w1", "weight1", "weights1", "layer1weight")),
            member(values, ("b1", "bias1", "layer1bias")),
            member(values, ("w2", "weight2", "weights2", "layer2weight")),
            member(values, ("b2", "bias2", "layer2bias")))


def mlp(description, values, xp, jax=None):
    x, w1, b1, w2, b2 = (xp.asarray(a) for a in mlp_inputs(values))
    text = description.lower()
    if "tanh" in text: act = xp.tanh
    elif "sigmoid" in text: act = (jax.nn.sigmoid if jax else lambda z: 1 / (1 + xp.exp(-z)))
    elif "linear" in text or "identity" in text: act = lambda z: z
    else: act = (jax.nn.relu if jax else lambda z: xp.maximum(z, 0))
    if jax:
        return jax.vmap(lambda row: affine(act(affine(row, w1, b1, xp)), w2, b2, xp))(x)
    return affine(act(affine(x, w1, b1, xp)), w2, b2, xp)


def scan(description, values, xp, jax=None):
    x = xp.asarray(primary(values))
    if x.ndim < 1:
        raise TaskError("scan requires a leading sequence axis")
    text = description.lower()
    multiply = any(s in text for s in ("cumulative product", "running product", "prefix product"))
    initial = member(values, ("initial", "init", "carry", "initialcarry"), True)
    carry = xp.asarray(initial) if initial is not None else (xp.ones(x.shape[1:], x.dtype) if multiply else xp.zeros(x.shape[1:], x.dtype))
    if jax:
        def step(state, item):
            nxt = state * item if multiply else state + item
            return nxt, nxt
        return jax.lax.scan(step, carry, x)[1]
    out = []
    for item in x:
        carry = carry * item if multiply else carry + item
        out.append(carry)
    return xp.stack(out)


def compute(description, values, engine):
    text = description.lower()
    if "gradient" in text or "derivative" in text or re.search(r"\bgrad\b", text): kind = "logistic"
    elif any(s in text for s in ("cumulative", "prefix", "running sum", "running product", "lax.scan", " scan")): kind = "scan"
    elif any(s in text for s in ("mlp", "vmap", "two-layer", "two layer", "neural network")): kind = "mlp"
    else: kind = "reduce"
    if engine == "jax":
        import jax
        import jax.numpy as jnp
        if kind == "logistic": return logistic_jax(description, values, jax, jnp), jax.device_get
        if kind == "scan": return scan(description, values, jnp, jax), jax.device_get
        if kind == "mlp": return mlp(description, values, jnp, jax), jax.device_get
        return reduce_task(description, values, jnp), jax.device_get
    if kind == "logistic": return logistic_numpy(description, values), np.asarray
    if kind == "scan": return scan(description, values, np), np.asarray
    if kind == "mlp": return mlp(description, values, np), np.asarray
    return reduce_task(description, values, np), np.asarray


def checked(value, task_id, materialize=np.asarray):
    value = np.asarray(materialize(value))
    if value.size == 0 or value.dtype.hasobject or value.dtype.kind not in "biufc":
        raise TaskError("task %r produced no portable numeric array" % task_id)
    if value.dtype.kind in "fc" and not np.isfinite(value).all():
        raise TaskError("task %r produced NaN or infinity" % task_id)
    return value


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=str(path.parent), prefix=".result-", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            if path.suffix.lower() == ".npz": np.savez(handle, result=value)
            else: np.save(handle, value, allow_pickle=False)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


def run(request):
    raw = request.get("problem", "/app/problem.json")
    engine = request.get("engine", "numpy")
    if engine not in ("numpy", "jax"):
        raise TaskError("engine must be numpy or jax")
    manifest = Path(raw).resolve()
    tasks = manifest_tasks(manifest)
    outputs = []
    for task in tasks:
        source, destination = resolve(manifest, task["input"]), resolve(manifest, task["output"])
        if not source.is_file(): raise TaskError("input is unavailable: %s" % source)
        raw_result, materialize = compute(task["description"], load_arrays(source), engine)
        result = checked(raw_result, task["id"], materialize)
        save(destination, result)
        outputs.append({"id": str(task["id"]), "output": str(destination), "shape": list(result.shape), "dtype": str(result.dtype)})
    for task in tasks:
        output = resolve(manifest, task["output"])
        loaded = load_arrays(output)
        if len(loaded) != 1: raise TaskError("output must contain exactly one array")
        checked(next(iter(loaded.values())), task["id"])
    return {"ok": True, "engine": engine, "outputs": outputs}


def main():
    try:
        request = json.loads(sys.stdin.read() or "{}")
        if not isinstance(request, dict): raise TaskError("stdin must be a JSON object")
        print(json.dumps(run(request), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(2)

if __name__ == "__main__":
    main()
