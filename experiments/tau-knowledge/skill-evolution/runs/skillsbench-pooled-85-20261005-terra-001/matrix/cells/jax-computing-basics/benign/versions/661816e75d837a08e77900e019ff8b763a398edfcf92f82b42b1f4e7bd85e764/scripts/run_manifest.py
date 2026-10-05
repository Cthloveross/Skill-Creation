#!/usr/bin/env python3
"""Compute and save all JAX tasks declared by a runtime JSON manifest.

stdin:  {"manifest_path": "/app/problem.json"} (path optional)
stdout: {"written": [{"id", "path", "shape", "dtype"}, ...]}

The implementation reads archive names and shapes at runtime.  It deliberately does not use
manifest task IDs as computation selectors.
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


def resolve(base, name):
    path = Path(name)
    return path if path.is_absolute() else base / path


def norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def text_of(task):
    return " ".join(str(task["description"]).lower().split())


def order_key(name):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", str(name).lower())]


def load_input(path):
    loaded = np.load(path, allow_pickle=False)
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            return {key: jnp.asarray(loaded[key]) for key in loaded.files}
        finally:
            loaded.close()
    return {"input": jnp.asarray(loaded)}


def find(arrays, aliases, required=True):
    """Find named data with exact normalized aliases before controlled substrings."""
    aliases = tuple(norm(a) for a in aliases)
    items = list(arrays.items())
    for alias in aliases:
        for key, value in items:
            if norm(key) == alias:
                return key, value
    # Do not use single-character aliases for substring matching: e.g. b in labels.
    for alias in aliases:
        if len(alias) < 2:
            continue
        for key, value in items:
            keyname = norm(key)
            if alias in keyname or keyname in alias:
                return key, value
    if required:
        raise KeyError("missing one of %s; archive keys are %s" % (aliases, list(arrays)))
    return None, None


def primary(arrays):
    key, value = find(arrays, ("input", "x", "features", "data", "values", "array"), False)
    if value is not None:
        return key, value
    excluded = ("label", "target", "weight", "bias", "theta", "state", "init")
    candidates = [(k, v) for k, v in arrays.items()
                  if not any(word in norm(k) for word in excluded)]
    if not candidates:
        candidates = list(arrays.items())
    return max(candidates, key=lambda item: (item[1].ndim, item[1].size))


def activate(description, value):
    if "relu" in description:
        return jax.nn.relu(value)
    if "sigmoid" in description:
        return jax.nn.sigmoid(value)
    if "tanh" in description:
        return jnp.tanh(value)
    return value


def elementary(description, arrays):
    _, x = primary(arrays)
    if "cumulative sum" in description or "cumsum" in description:
        return jnp.cumsum(x)
    if "softmax" in description:
        return jax.nn.softmax(x, axis=-1)
    if ("sum of squares" in description or
            re.search(r"sum\s*\(\s*x\s*\*\s*x\s*\)", description) or
            re.search(r"sum\s*\(\s*x\s*\*\*\s*2\s*\)", description)):
        return jnp.sum(jnp.square(x))
    if "l2 norm" in description or "euclidean norm" in description:
        return jnp.sqrt(jnp.sum(jnp.square(x)))
    if ("elementwise square" in description or "square each element" in description or
            re.search(r"x\s*\*\*\s*2", description)):
        return jnp.square(x)
    if "mean" in description:
        if "row" in description:
            if x.ndim < 2:
                raise ValueError("a row mean requires a rank-2-or-higher input")
            return jnp.mean(x, axis=1)
        if "column" in description:
            if x.ndim < 2:
                raise ValueError("a column mean requires a rank-2-or-higher input")
            return jnp.mean(x, axis=0)
        return jnp.mean(x)
    if "sum" in description:
        if "row" in description:
            if x.ndim < 2:
                raise ValueError("a row sum requires a rank-2-or-higher input")
            return jnp.sum(x, axis=1)
        if "column" in description:
            if x.ndim < 2:
                raise ValueError("a column sum requires a rank-2-or-higher input")
            return jnp.sum(x, axis=0)
        return jnp.sum(x)
    raise ValueError("unsupported elementary computation: %r" % description)


def logistic(description, arrays):
    _, x = find(arrays, ("x", "features", "inputs", "data"))
    _, y = find(arrays, ("labels", "label", "targets", "target", "y"))
    _, w = find(arrays, ("weights", "weight", "theta", "beta", "params", "w"))
    _, bias = find(arrays, ("bias", "intercept", "b"), False)
    if x.ndim != 2 or w.ndim not in (1, 2):
        raise ValueError("logistic inputs must be rank-2 features and rank-1/2 weights")

    def logits(weight):
        if x.shape[-1] == weight.shape[0]:
            value = x @ weight
        elif weight.ndim == 2 and x.shape[-1] == weight.shape[1]:
            value = x @ weight.T
        else:
            raise ValueError("feature shape %s incompatible with weights %s" % (x.shape, weight.shape))
        return value if bias is None else value + bias

    def loss(weight):
        z = logits(weight)
        # Stable BCE from logits: log(1 + exp(z)) - y*z.
        return jnp.mean(jax.nn.softplus(z) - y * z)

    if "gradient" in description or re.search(r"\bgrad\b", description):
        return jax.grad(loss)(w)
    return loss(w)


def dense(value, weight, bias):
    if value.shape[-1] == weight.shape[0]:
        output = value @ weight
    elif value.shape[-1] == weight.shape[1]:
        output = value @ weight.T
    else:
        raise ValueError("dense input %s incompatible with weight %s" % (value.shape, weight.shape))
    if bias is not None:
        if bias.ndim != 1 or bias.shape[0] != output.shape[-1]:
            raise ValueError("dense bias %s incompatible with output %s" % (bias.shape, output.shape))
        output = output + bias
    return output


def mlp(description, arrays):
    _, value = find(arrays, ("x", "input", "inputs", "features", "data"))
    weights = [(k, v) for k, v in arrays.items()
               if v.ndim == 2 and any(word in norm(k)
                                      for word in ("weight", "kernel", "matrix", "w"))]
    weights.sort(key=lambda item: order_key(item[0]))
    biases = [(k, v) for k, v in arrays.items()
              if v.ndim == 1 and ("bias" in norm(k) or norm(k).startswith("b"))]
    biases.sort(key=lambda item: order_key(item[0]))
    if not weights:
        raise ValueError("MLP archive has no named rank-2 dense weights")
    for index, (_, weight) in enumerate(weights):
        bias = biases[index][1] if index < len(biases) else None
        value = dense(value, weight, bias)
        is_last = index == len(weights) - 1
        # Standard wording applies hidden activation only; explicit all-layer wording includes output.
        if not is_last or any(phrase in description for phrase in
                              ("each layer", "every layer", "output activation", "final activation")):
            value = activate(description, value)
    return value


def project(value, matrix):
    if value.shape[-1] == matrix.shape[0]:
        return value @ matrix
    if value.shape[-1] == matrix.shape[1]:
        return value @ matrix.T
    raise ValueError("cannot project %s through %s" % (value.shape, matrix.shape))


def scan_task(description, arrays):
    _, xs = find(arrays, ("xs", "sequence", "sequences", "inputs", "input", "x", "values"))
    _, initial = find(arrays, ("h0", "initialstate", "initial", "init", "carry", "state"), False)
    if initial is None:
        initial = jnp.zeros(xs.shape[1:] if xs.ndim > 1 else (), dtype=xs.dtype)
    matrices = [(k, v) for k, v in arrays.items() if v.ndim == 2]
    _, bias = find(arrays, ("bias", "b"), False)

    if not matrices:
        def body(carry, item):
            next_carry = carry + item
            return next_carry, next_carry
    else:
        hidden_size = initial.shape[-1] if initial.ndim else 1
        input_size = xs.shape[-1] if xs.ndim > 1 else 1
        recurrent = next((v for _, v in matrices
                          if v.shape[0] == v.shape[1] and hidden_size in v.shape), None)
        incoming = next((v for _, v in matrices
                         if v is not recurrent and input_size in v.shape), None)
        if recurrent is None or incoming is None:
            raise ValueError("could not identify recurrent and input matrices by runtime shape")

        def body(carry, item):
            next_carry = project(carry, recurrent) + project(item, incoming)
            if bias is not None:
                next_carry = next_carry + bias
            # Affine RNN descriptions conventionally use tanh unless another activation is stated.
            next_carry = activate(description if any(a in description for a in
                                                     ("relu", "sigmoid", "tanh")) else "tanh", next_carry)
            return next_carry, next_carry

    final, outputs = jax.lax.scan(body, initial, xs)
    if "final" in description and not any(word in description for word in
                                            ("all states", "all outputs", "sequence of", "outputs")):
        return final
    return outputs


def compute(task, arrays):
    description = text_of(task)
    if any(word in description for word in ("scan", "recurrent", "recurrence")):
        return scan_task(description, arrays)
    if any(word in description for word in ("mlp", "multi-layer perceptron", "dense layer")):
        return mlp(description, arrays)
    if any(word in description for word in ("logistic", "binary cross entropy", "binary cross-entropy")):
        return logistic(description, arrays)
    return elementary(description, arrays)


def save_and_check(path, result):
    value = np.asarray(result)
    if value.dtype == object or value.size == 0:
        raise ValueError("invalid result shape/dtype for %s: %s %s" % (path, value.shape, value.dtype))
    if not (np.issubdtype(value.dtype, np.number) or np.issubdtype(value.dtype, np.bool_)):
        raise ValueError("non-numeric result dtype for %s: %s" % (path, value.dtype))
    if np.issubdtype(value.dtype, np.inexact) and not np.isfinite(value).all():
        raise ValueError("non-finite result for %s" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
    reread = np.load(path, allow_pickle=False)
    if not isinstance(reread, np.ndarray) or reread.dtype == object or reread.size == 0:
        raise ValueError("saved output is not a valid single numeric array: %s" % path)
    return value


def main():
    request = json.load(sys.stdin)
    if not isinstance(request, dict):
        raise ValueError("stdin must be a JSON object")
    manifest_path = Path(request.get("manifest_path", "/app/problem.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"id", "description", "input", "output"}
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("manifest must be a nonempty JSON list")
    if any(not isinstance(task, dict) or not required <= set(task) for task in manifest):
        raise ValueError("each manifest task requires id, description, input, output")
    outputs = [resolve(manifest_path.parent, task["output"]) for task in manifest]
    if len(set(outputs)) != len(outputs):
        raise ValueError("manifest output paths must be unique")

    report = []
    # Save immediately per task so a later diagnostic never erases already materialized work.
    for task, output in zip(manifest, outputs):
        arrays = load_input(resolve(manifest_path.parent, task["input"]))
        result = save_and_check(output, compute(task, arrays))
        report.append({"id": task["id"], "path": str(output),
                       "shape": list(result.shape), "dtype": str(result.dtype)})
    print(json.dumps({"written": report}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("run_manifest failed: %s" % exc, file=sys.stderr)
        raise
