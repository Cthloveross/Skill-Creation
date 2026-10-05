#!/usr/bin/env python3
"""Run all JAX computations declared by a JSON manifest.

stdin:  {"manifest_path": "/app/problem.json"}  (optional path)
stdout: {"written": [{"id", "path", "shape", "dtype"}, ...]}
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
from jax import config
config.update("jax_enable_x64", True)
import jax
import jax.numpy as jnp


def resolve(base: Path, name: str) -> Path:
    path = Path(name)
    return path if path.is_absolute() else base / path


def description(task):
    return " ".join(str(task["description"]).lower().split())


def keynorm(key):
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def ordered(items):
    def order(name):
        return [int(v) if v.isdigit() else v for v in re.split(r"(\d+)", str(name).lower())]
    return sorted(items, key=lambda pair: order(pair[0]))


def load_arrays(path):
    loaded = np.load(path, allow_pickle=False)
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            return {name: jnp.asarray(loaded[name]) for name in loaded.files}
        finally:
            loaded.close()
    if not isinstance(loaded, np.ndarray):
        raise ValueError("input is not a NumPy array: %s" % path)
    return {"input": jnp.asarray(loaded)}


def find(arrays, aliases, required=True):
    """Find an array from conventional names without relying on task IDs."""
    wanted = [keynorm(a) for a in aliases]
    for alias in wanted:
        for key, value in arrays.items():
            if keynorm(key) == alias:
                return key, value
    # Single-letter aliases (x, y, w, b) must match exactly, not a substring of another key.
    for alias in wanted:
        if len(alias) < 2:
            continue
        for key, value in arrays.items():
            name = keynorm(key)
            if alias in name or name in alias:
                return key, value
    if required:
        raise KeyError("expected one of %s; available keys are %s" % (aliases, list(arrays)))
    return None, None


def primary(arrays):
    key, value = find(arrays, ("input", "x", "features", "data", "values", "array"), False)
    if value is not None:
        return key, value
    excluded = ("label", "target", "weight", "kernel", "bias", "theta", "state", "init")
    choices = [(k, v) for k, v in arrays.items() if not any(w in keynorm(k) for w in excluded)]
    choices = choices or list(arrays.items())
    return max(choices, key=lambda pair: (pair[1].ndim, pair[1].size))


def activation(text, value):
    if "relu" in text:
        return jax.nn.relu(value)
    if "sigmoid" in text:
        return jax.nn.sigmoid(value)
    if "tanh" in text:
        return jnp.tanh(value)
    if "gelu" in text:
        return jax.nn.gelu(value)
    return value


def elementary(text, arrays):
    _, x = primary(arrays)
    if "cumulative sum" in text or "cumsum" in text:
        return jnp.cumsum(x)
    if "softmax" in text:
        return jax.nn.softmax(x, axis=-1)
    if ("sum of squares" in text or
            re.search(r"sum\s*\(\s*x\s*\*\s*x\s*\)", text) or
            re.search(r"sum\s*\(\s*x\s*\*\*\s*2\s*\)", text)):
        return jnp.sum(jnp.square(x))
    if "l2 norm" in text or "euclidean norm" in text:
        return jnp.sqrt(jnp.sum(jnp.square(x)))
    if ("elementwise square" in text or "square each element" in text or
            re.search(r"x\s*\*\*\s*2", text)):
        return jnp.square(x)
    if "mean" in text:
        if "row" in text:
            if x.ndim < 2:
                raise ValueError("row mean needs a rank-two-or-higher input")
            return jnp.mean(x, axis=1)
        if "column" in text:
            if x.ndim < 2:
                raise ValueError("column mean needs a rank-two-or-higher input")
            return jnp.mean(x, axis=0)
        return jnp.mean(x)
    if "sum" in text:
        if "row" in text:
            if x.ndim < 2:
                raise ValueError("row sum needs a rank-two-or-higher input")
            return jnp.sum(x, axis=1)
        if "column" in text:
            if x.ndim < 2:
                raise ValueError("column sum needs a rank-two-or-higher input")
            return jnp.sum(x, axis=0)
        return jnp.sum(x)
    raise ValueError("unsupported single-array description: %r" % text)


def logistic(text, arrays):
    _, x = find(arrays, ("x", "features", "inputs", "data"))
    _, y = find(arrays, ("labels", "label", "targets", "target", "y"))
    _, w = find(arrays, ("weights", "weight", "theta", "beta", "params", "w"))
    _, b = find(arrays, ("bias", "intercept", "b"), False)
    if x.ndim != 2 or w.ndim not in (1, 2):
        raise ValueError("logistic features must be rank 2 and weights rank 1 or 2")

    def logits(weight):
        if x.shape[-1] == weight.shape[0]:
            z = x @ weight
        elif weight.ndim == 2 and x.shape[-1] == weight.shape[1]:
            z = x @ weight.T
        else:
            raise ValueError("feature shape %s incompatible with weight shape %s" % (x.shape, weight.shape))
        return z if b is None else z + b

    def loss(weight):
        z = logits(weight)
        return jnp.mean(jax.nn.softplus(z) - y * z)

    if "gradient" in text or re.search(r"\bgrad\b", text):
        return jax.grad(loss)(w)
    return loss(w)


def dense(value, weight, bias):
    if value.shape[-1] == weight.shape[0]:
        result = value @ weight
    elif value.shape[-1] == weight.shape[1]:
        result = value @ weight.T
    else:
        raise ValueError("dense value shape %s incompatible with weight %s" % (value.shape, weight.shape))
    if bias is not None:
        if bias.ndim != 1 or bias.shape[0] != result.shape[-1]:
            raise ValueError("bias shape %s incompatible with dense output %s" % (bias.shape, result.shape))
        result = result + bias
    return result


def mlp(text, arrays):
    _, value = find(arrays, ("x", "input", "inputs", "features", "data"))
    weights = []
    biases = []
    for key, value0 in arrays.items():
        name = keynorm(key)
        if value0.ndim == 2 and ("weight" in name or "kernel" in name or name.startswith("w")):
            weights.append((key, value0))
        if value0.ndim == 1 and ("bias" in name or name.startswith("b")):
            biases.append((key, value0))
    weights, biases = ordered(weights), ordered(biases)
    if not weights:
        raise ValueError("could not find rank-2 MLP weights in archive")
    for index, (_, weight) in enumerate(weights):
        bias = biases[index][1] if index < len(biases) else None
        value = dense(value, weight, bias)
        final = index == len(weights) - 1
        if not final or any(phrase in text for phrase in
                            ("each layer", "every layer", "final activation", "output activation")):
            value = activation(text, value)
    return value


def project(value, matrix):
    if value.shape[-1] == matrix.shape[0]:
        return value @ matrix
    if value.shape[-1] == matrix.shape[1]:
        return value @ matrix.T
    raise ValueError("cannot multiply value shape %s by matrix shape %s" % (value.shape, matrix.shape))


def scan_task(text, arrays):
    sequence_key, xs = find(arrays, ("xs", "sequence", "sequences", "inputs", "input", "x", "values"))
    _, initial = find(arrays, ("h0", "initialstate", "initial", "init", "carry", "state"), False)
    if initial is None:
        initial = jnp.zeros(xs.shape[1:] if xs.ndim > 1 else (), dtype=xs.dtype)
    _, bias = find(arrays, ("bias", "b"), False)
    matrices = [(k, v) for k, v in arrays.items() if v.ndim == 2 and k != sequence_key]
    if not matrices:
        def body(carry, item):
            nxt = carry + item
            return nxt, nxt
    else:
        hidden = initial.shape[-1] if initial.ndim else 1
        incoming_size = xs.shape[-1] if xs.ndim > 1 else 1
        recurrent = next((v for _, v in matrices if v.shape[0] == v.shape[1] and hidden in v.shape), None)
        incoming = next((v for _, v in matrices if v is not recurrent and incoming_size in v.shape), None)
        if recurrent is None or incoming is None:
            raise ValueError("cannot identify recurrent and input matrices from archive shapes")
        use_text = text if any(a in text for a in ("relu", "sigmoid", "tanh", "gelu")) else "tanh"
        def body(carry, item):
            nxt = project(carry, recurrent) + project(item, incoming)
            if bias is not None:
                nxt = nxt + bias
            nxt = activation(use_text, nxt)
            return nxt, nxt
    final, states = jax.lax.scan(body, initial, xs)
    if "final" in text and not any(w in text for w in ("all states", "all outputs", "sequence of", "outputs")):
        return final
    return states


def compute(task, arrays):
    text = description(task)
    if any(word in text for word in ("scan", "recurrent", "recurrence", "rnn")):
        return scan_task(text, arrays)
    if any(word in text for word in ("mlp", "multi-layer perceptron", "dense layer")):
        return mlp(text, arrays)
    if any(word in text for word in ("logistic", "binary cross entropy", "binary cross-entropy")):
        return logistic(text, arrays)
    return elementary(text, arrays)


def save_checked(path, result):
    value = np.asarray(result)
    if value.dtype == object or value.size == 0:
        raise ValueError("invalid empty or object result for %s" % path)
    if not (np.issubdtype(value.dtype, np.number) or np.issubdtype(value.dtype, np.bool_)):
        raise ValueError("nonnumeric result dtype %s for %s" % (value.dtype, path))
    if np.issubdtype(value.dtype, np.inexact) and not np.isfinite(value).all():
        raise ValueError("nonfinite result for %s" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        np.save(handle, value, allow_pickle=False)
    reread = np.load(path, allow_pickle=False)
    if not isinstance(reread, np.ndarray) or reread.dtype == object or reread.size == 0:
        raise ValueError("saved file is not one valid array: %s" % path)
    return value


def main():
    request = json.load(sys.stdin)
    if not isinstance(request, dict):
        raise ValueError("stdin must contain a JSON object")
    manifest_path = Path(request.get("manifest_path", "/app/problem.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"id", "description", "input", "output"}
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("manifest must be a nonempty list")
    if any(not isinstance(t, dict) or not required.issubset(t) for t in manifest):
        raise ValueError("each task must contain id, description, input, output")
    outputs = [resolve(manifest_path.parent, t["output"]) for t in manifest]
    if len(set(outputs)) != len(outputs):
        raise ValueError("manifest contains duplicate output paths")
    report = []
    for task, output in zip(manifest, outputs):
        arrays = load_arrays(resolve(manifest_path.parent, task["input"]))
        result = save_checked(output, compute(task, arrays))
        report.append({"id": task["id"], "path": str(output),
                       "shape": list(result.shape), "dtype": str(result.dtype)})
    print(json.dumps({"written": report}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("run_manifest failed: %s" % exc, file=sys.stderr)
        raise
