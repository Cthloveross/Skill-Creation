#!/usr/bin/env python3
"""Execute JAX numerical tasks listed in a JSON manifest.

stdin:  {"manifest_path": "/app/problem.json"}  (path optional)
stdout: {"written": [{"id", "path", "shape", "dtype"}, ...]}

Each manifest task must provide id, description, input, and output. Relative input and output
paths are relative to the manifest's directory.
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
    path = Path(str(name))
    return path if path.is_absolute() else base / path


def normalized(text: object) -> str:
    return " ".join(str(text).lower().split())


def key_name(name: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def natural_key(name: str):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", name.lower())]


def load_input(path: Path) -> dict[str, jax.Array]:
    loaded = np.load(path, allow_pickle=False)
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            return {name: jnp.asarray(loaded[name]) for name in loaded.files}
        finally:
            loaded.close()
    if not isinstance(loaded, np.ndarray):
        raise ValueError("input is not an ndarray or NPZ archive: %s" % path)
    return {"input": jnp.asarray(loaded)}


def available(arrays: dict[str, jax.Array]) -> str:
    return ", ".join("%s:%s" % (k, tuple(v.shape)) for k, v in arrays.items())


def find_array(arrays: dict[str, jax.Array], aliases, required=True):
    """Return a semantically named archive member; exact normalized matches win."""
    aliases = [key_name(alias) for alias in aliases]
    for alias in aliases:
        for key, value in arrays.items():
            if key_name(key) == alias:
                return key, value
    # Longer aliases can safely match conventional variants such as feature_matrix.
    for alias in aliases:
        if len(alias) < 2:
            continue
        for key, value in arrays.items():
            actual = key_name(key)
            if alias in actual or actual in alias:
                return key, value
    if required:
        raise KeyError("expected one of %s; found %s" % (aliases, available(arrays)))
    return None, None


def main_array(arrays: dict[str, jax.Array]):
    _, value = find_array(arrays, ("input", "x", "features", "data", "values", "array"), False)
    if value is not None:
        return value
    candidates = list(arrays.items())
    if not candidates:
        raise ValueError("input archive has no arrays")
    return max(candidates, key=lambda item: (item[1].ndim, item[1].size))[1]


def apply_activation(text: str, value):
    if "relu" in text:
        return jax.nn.relu(value)
    if "sigmoid" in text or "logistic activation" in text:
        return jax.nn.sigmoid(value)
    if "gelu" in text:
        return jax.nn.gelu(value)
    if "tanh" in text:
        return jnp.tanh(value)
    return value


def elementary(text: str, arrays):
    x = main_array(arrays)
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
                raise ValueError("row-wise mean requires rank at least two")
            return jnp.mean(x, axis=1)
        if "column" in text or "col-wise" in text:
            if x.ndim < 2:
                raise ValueError("column-wise mean requires rank at least two")
            return jnp.mean(x, axis=0)
        return jnp.mean(x)
    if "sum" in text:
        if "row" in text:
            if x.ndim < 2:
                raise ValueError("row-wise sum requires rank at least two")
            return jnp.sum(x, axis=1)
        if "column" in text or "col-wise" in text:
            if x.ndim < 2:
                raise ValueError("column-wise sum requires rank at least two")
            return jnp.sum(x, axis=0)
        return jnp.sum(x)
    raise ValueError("unsupported elementary description: %r" % text)


def affine(value, matrix, bias=None):
    if matrix.ndim != 2:
        raise ValueError("weight matrix must be rank 2, got %s" % (matrix.shape,))
    if value.shape[-1] == matrix.shape[0]:
        output = value @ matrix
    elif value.shape[-1] == matrix.shape[1]:
        output = value @ matrix.T
    else:
        raise ValueError("cannot apply matrix %s to value %s" % (matrix.shape, value.shape))
    if bias is not None:
        if bias.ndim != 1 or bias.shape[0] != output.shape[-1]:
            raise ValueError("bias %s incompatible with output %s" % (bias.shape, output.shape))
        output = output + bias
    return output


def logistic(text: str, arrays):
    _, x = find_array(arrays, ("x", "features", "inputs", "data"))
    _, y = find_array(arrays, ("labels", "label", "targets", "target", "y"))
    _, weights = find_array(arrays, ("weights", "weight", "theta", "beta", "params", "w"))
    _, bias = find_array(arrays, ("bias", "intercept", "b"), False)

    def loss(w):
        logits = affine(x, w, bias)
        # softplus(z) - y*z is stable binary cross entropy with logits.
        return jnp.mean(jax.nn.softplus(logits) - y * logits)

    if "gradient" in text or re.search(r"\bgrad\b", text):
        return jax.grad(loss)(weights)
    if "probabilit" in text or "prediction" in text:
        return jax.nn.sigmoid(affine(x, weights, bias))
    return loss(weights)


def mlp(text: str, arrays):
    _, value = find_array(arrays, ("x", "input", "inputs", "features", "data"))
    weights, biases = [], []
    for key, candidate in arrays.items():
        name = key_name(key)
        if candidate.ndim == 2 and ("weight" in name or "kernel" in name or re.fullmatch(r"w\d*", name)):
            weights.append((key, candidate))
        elif candidate.ndim == 1 and ("bias" in name or re.fullmatch(r"b\d*", name)):
            biases.append((key, candidate))
    weights.sort(key=lambda item: natural_key(item[0]))
    biases.sort(key=lambda item: natural_key(item[0]))
    if not weights:
        raise ValueError("no MLP weight matrices found; archive contains %s" % available(arrays))

    for index, (_, weight) in enumerate(weights):
        bias = biases[index][1] if index < len(biases) else None
        value = affine(value, weight, bias)
        last = index == len(weights) - 1
        # Standard MLP descriptions activate hidden layers; wording can explicitly activate final.
        if not last or any(term in text for term in ("final activation", "output activation", "each layer", "every layer")):
            value = apply_activation(text, value)
    return value


def mat_project(value, matrix):
    return affine(value, matrix)


def scan_task(text: str, arrays):
    sequence_key, xs = find_array(arrays, ("xs", "sequence", "sequences", "inputs", "input", "x", "values"))
    _, initial = find_array(arrays, ("h0", "initialstate", "initial", "init", "carry", "state"), False)
    if initial is None:
        initial = jnp.zeros(xs.shape[1:] if xs.ndim > 1 else (), dtype=xs.dtype)
    _, bias = find_array(arrays, ("bias", "b"), False)

    # Prefer semantic recurrent/input names, then use dimensions for archives with generic names.
    _, recurrent = find_array(arrays, ("wh", "wrec", "recurrentweight", "hiddenweight", "transition"), False)
    _, incoming = find_array(arrays, ("wx", "win", "inputweight", "inputkernel"), False)
    matrices = [(k, v) for k, v in arrays.items() if v.ndim == 2 and k != sequence_key]
    hidden_size = initial.shape[-1] if initial.ndim else 1
    input_size = xs.shape[-1] if xs.ndim > 1 else 1
    if recurrent is None:
        recurrent = next((v for _, v in matrices if v.shape[0] == v.shape[1] and hidden_size in v.shape), None)
    if incoming is None:
        incoming = next((v for _, v in matrices if v is not recurrent and input_size in v.shape), None)

    if recurrent is None and incoming is None:
        def body(carry, item):
            next_carry = carry + item
            return next_carry, next_carry
    elif recurrent is not None and incoming is not None:
        activation_text = text if any(a in text for a in ("relu", "sigmoid", "gelu", "tanh")) else "tanh"
        def body(carry, item):
            next_carry = mat_project(carry, recurrent) + mat_project(item, incoming)
            if bias is not None:
                next_carry = next_carry + bias
            next_carry = apply_activation(activation_text, next_carry)
            return next_carry, next_carry
    else:
        raise ValueError("could not identify both recurrence matrices; archive contains %s" % available(arrays))

    final, states = jax.lax.scan(body, initial, xs)
    if "final" in text and not any(term in text for term in ("all states", "all outputs", "sequence of", "return states")):
        return final
    return states


def compute(task, arrays):
    text = normalized(task["description"])
    if any(word in text for word in ("scan", "recurrent", "recurrence", "rnn")):
        return scan_task(text, arrays)
    if any(word in text for word in ("mlp", "multi-layer perceptron", "multilayer perceptron", "dense layer")):
        return mlp(text, arrays)
    if any(word in text for word in ("logistic", "binary cross entropy", "binary cross-entropy")):
        return logistic(text, arrays)
    return elementary(text, arrays)


def save_result(path: Path, result):
    value = np.asarray(jax.device_get(result))
    if value.dtype == object or value.size == 0:
        raise ValueError("result is empty or object dtype for %s" % path)
    if not (np.issubdtype(value.dtype, np.number) or np.issubdtype(value.dtype, np.bool_)):
        raise ValueError("result is nonnumeric (%s) for %s" % (value.dtype, path))
    if np.issubdtype(value.dtype, np.inexact) and not np.isfinite(value).all():
        raise ValueError("result contains NaN or infinity for %s" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
    # Confirm a standard single-array file was actually materialized before proceeding.
    reread = np.load(path, allow_pickle=False)
    if not isinstance(reread, np.ndarray) or reread.dtype == object or reread.size == 0:
        raise ValueError("failed to save a valid single-array NPY file: %s" % path)
    return value


def main():
    request = json.load(sys.stdin)
    if not isinstance(request, dict):
        raise ValueError("stdin must be a JSON object")
    manifest_path = Path(request.get("manifest_path", "/app/problem.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"id", "description", "input", "output"}
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("manifest must be a nonempty list")
    if any(not isinstance(task, dict) or not required.issubset(task) for task in manifest):
        raise ValueError("each manifest task needs id, description, input, and output")

    outputs = [resolve(manifest_path.parent, task["output"]) for task in manifest]
    if len(set(outputs)) != len(outputs):
        raise ValueError("manifest declares duplicate output paths")

    written = []
    for task, output in zip(manifest, outputs):
        arrays = load_input(resolve(manifest_path.parent, task["input"]))
        result = save_result(output, compute(task, arrays))
        written.append({"id": task["id"], "path": str(output),
                        "shape": list(result.shape), "dtype": str(result.dtype)})
    print(json.dumps({"written": written}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("run_manifest failed: %s" % exc, file=sys.stderr)
        raise
