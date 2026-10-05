#!/usr/bin/env python3
"""Execute supported JAX numerical tasks in a runtime JSON manifest.

The program deliberately uses descriptions and runtime archive metadata rather than task IDs.
It writes one ordinary, materialized NumPy array at each exact manifest output path.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Mapping

import numpy as np
from jax import config
config.update("jax_enable_x64", True)
import jax
import jax.numpy as jnp


def resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def natural_key(text: str):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", text)]


def description_text(task: Mapping) -> str:
    return " ".join(str(task["description"]).lower().split())


def load_arrays(path: Path) -> dict[str, jax.Array]:
    loaded = np.load(path, allow_pickle=False)
    if isinstance(loaded, np.lib.npyio.NpzFile):
        try:
            return {key: jnp.asarray(loaded[key]) for key in loaded.files}
        finally:
            loaded.close()
    return {"input": jnp.asarray(loaded)}


def named(arrays, names, *, required=True):
    """Find a member by an exact normalized alias, then by an informative substring."""
    aliases = [normalized(n) for n in names]
    items = list(arrays.items())
    for alias in aliases:
        for key, value in items:
            if normalized(key) == alias:
                return key, value
    for alias in aliases:
        for key, value in items:
            key_norm = normalized(key)
            if len(alias) > 1 and (alias in key_norm or key_norm in alias):
                return key, value
    if required:
        raise KeyError(f"could not find any of {names}; available keys are {list(arrays)}")
    return None, None


def first_data_array(arrays):
    preferred = ("input", "x", "features", "feature", "data", "values", "array")
    key, value = named(arrays, preferred, required=False)
    if value is not None:
        return key, value
    excluded = ("label", "target", "weight", "bias", "theta", "param", "init", "state")
    candidates = [(k, v) for k, v in arrays.items()
                  if not any(token in normalized(k) for token in excluded)]
    if not candidates:
        candidates = list(arrays.items())
    return max(candidates, key=lambda kv: (kv[1].ndim, kv[1].size))


def activation(text: str, x):
    if "sigmoid" in text:
        return jax.nn.sigmoid(x)
    if "tanh" in text:
        return jnp.tanh(x)
    if "relu" in text:
        return jax.nn.relu(x)
    return x


def elementary(text: str, arrays):
    _, x = first_data_array(arrays)
    # Scope wording is tested before broad operation wording.
    if "cumulative sum" in text or "cumsum" in text:
        return jnp.cumsum(x)
    if "softmax" in text:
        axis = -1
        return jax.nn.softmax(x, axis=axis)
    if "sum of squares" in text or re.search(r"sum\s*\(\s*x\s*\*\s*x\s*\)", text):
        return jnp.sum(jnp.square(x))
    if "l2 norm" in text or "euclidean norm" in text:
        return jnp.sqrt(jnp.sum(jnp.square(x)))
    if "elementwise square" in text or "square each" in text or "x ** 2" in text:
        return jnp.square(x)
    if "mean" in text:
        if "row" in text:
            return jnp.mean(x, axis=1)
        if "column" in text:
            return jnp.mean(x, axis=0)
        return jnp.mean(x)
    if "sum" in text:
        if "row" in text:
            return jnp.sum(x, axis=1)
        if "column" in text:
            return jnp.sum(x, axis=0)
        return jnp.sum(x)
    raise ValueError("description is not a recognized elementary array computation")


def logistic(text: str, arrays):
    _, x = named(arrays, ("x", "features", "feature", "inputs", "data"))
    _, labels = named(arrays, ("labels", "label", "targets", "target", "y"))
    weight_key, weights = named(arrays, ("weights", "weight", "theta", "w", "beta", "params"))
    _, bias = named(arrays, ("bias", "b", "intercept"), required=False)
    if x.ndim != 2:
        raise ValueError("binary logistic feature array must be rank 2")
    if weights.ndim not in (1, 2):
        raise ValueError("logistic weights must be a vector or a column matrix")
    if x.shape[-1] == weights.shape[0]:
        logits = lambda w: jnp.matmul(x, w)
    elif weights.ndim == 2 and x.shape[-1] == weights.shape[1]:
        logits = lambda w: jnp.matmul(x, w.T)
    else:
        raise ValueError(f"features {x.shape} and weights {weights.shape} are incompatible")
    def loss(w):
        z = logits(w)
        if bias is not None:
            z = z + bias
        # softplus(z) - y*z is stable binary cross entropy from logits.
        return jnp.mean(jax.nn.softplus(z) - labels * z)
    if "gradient" in text or re.search(r"\bgrad\b", text):
        return jax.grad(loss)(weights)
    return loss(weights)


def dense_apply(x, weight, bias):
    if x.shape[-1] == weight.shape[0]:
        out = jnp.matmul(x, weight)
    elif x.shape[-1] == weight.shape[1]:
        out = jnp.matmul(x, weight.T)
    else:
        raise ValueError(f"cannot apply dense weight {weight.shape} to activation {x.shape}")
    if bias is not None:
        if bias.ndim != 1 or bias.shape[0] != out.shape[-1]:
            raise ValueError(f"bias {bias.shape} incompatible with dense output {out.shape}")
        out = out + bias
    return out


def mlp(text: str, arrays):
    _, x = named(arrays, ("x", "input", "inputs", "features", "data"))
    matrices = [(k, v) for k, v in arrays.items()
                if v.ndim == 2 and any(token in normalized(k)
                                       for token in ("w", "weight", "kernel", "matrix"))]
    matrices.sort(key=lambda kv: natural_key(kv[0]))
    if not matrices:
        raise ValueError("MLP task needs named rank-2 weight matrices")
    biases = [(k, v) for k, v in arrays.items()
              if v.ndim == 1 and any(token in normalized(k)
                                     for token in ("b", "bias"))]
    biases.sort(key=lambda kv: natural_key(kv[0]))
    value = x
    for index, (_, weight) in enumerate(matrices):
        bias = biases[index][1] if index < len(biases) else None
        value = dense_apply(value, weight, bias)
        # Conventionally the final layer is linear unless wording explicitly says all layers.
        final = index == len(matrices) - 1
        if not final or "each layer" in text or "every layer" in text or "output activation" in text:
            value = activation(text, value)
    return value


def scan_task(text: str, arrays):
    _, xs = named(arrays, ("xs", "sequence", "sequences", "inputs", "input", "x", "values"))
    _, init = named(arrays, ("h0", "initialstate", "init", "initial", "carry", "state"), required=False)
    if init is None:
        init = jnp.zeros(xs.shape[1:] if xs.ndim > 1 else (), dtype=xs.dtype)
    matrices = [(k, v) for k, v in arrays.items() if v.ndim == 2]
    _, bias = named(arrays, ("bias", "b"), required=False)

    if ("cumulative" in text or "cumsum" in text) and not matrices:
        def body(carry, item):
            carry = carry + item
            return carry, carry
    elif not matrices:
        # A stated scan without learned matrices is the standard additive carry recurrence.
        def body(carry, item):
            carry = carry + item
            return carry, carry
    else:
        hdim = init.shape[-1] if init.ndim else 1
        xdim = xs.shape[-1] if xs.ndim > 1 else 1
        recurrent = next((v for _, v in matrices if hdim in v.shape and v.shape[0] == v.shape[1]), None)
        incoming = next((v for _, v in matrices if v is not recurrent and xdim in v.shape), None)
        if recurrent is None or incoming is None:
            raise ValueError("could not identify recurrent and input matrices from scan shapes")
        def project(value, matrix):
            if value.shape[-1] == matrix.shape[0]:
                return value @ matrix
            if value.shape[-1] == matrix.shape[1]:
                return value @ matrix.T
            raise ValueError("scan projection has incompatible shape")
        def body(carry, item):
            next_carry = project(carry, recurrent) + project(item, incoming)
            if bias is not None:
                next_carry = next_carry + bias
            next_carry = activation(text if any(a in text for a in ("tanh", "relu", "sigmoid")) else "tanh", next_carry)
            return next_carry, next_carry
    final, outputs = jax.lax.scan(body, init, xs)
    if "final" in text and not any(word in text for word in ("all states", "all outputs", "sequence of", "outputs")):
        return final
    return outputs


def compute(task, arrays):
    text = description_text(task)
    if "scan" in text or "recurrent" in text or "recurrence" in text:
        return scan_task(text, arrays)
    if "mlp" in text or "multi-layer perceptron" in text or "dense layer" in text:
        return mlp(text, arrays)
    if "logistic" in text or "binary cross entropy" in text or "binary cross-entropy" in text:
        return logistic(text, arrays)
    return elementary(text, arrays)


def save_exact(path: Path, result):
    value = np.asarray(result)
    if value.dtype == object or value.size == 0:
        raise ValueError(f"refusing invalid result for {path}: shape={value.shape}, dtype={value.dtype}")
    if not (np.issubdtype(value.dtype, np.number) or np.issubdtype(value.dtype, np.bool_)):
        raise ValueError(f"refusing nonnumeric result dtype {value.dtype}")
    if np.issubdtype(value.dtype, np.inexact) and not np.isfinite(value).all():
        raise ValueError(f"refusing nonfinite result for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Passing an open handle prevents np.save from altering the manifest destination.
    with path.open("wb") as handle:
        np.save(handle, value, allow_pickle=False)
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="/app/problem.json")
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("problem.json must be a nonempty list")
    required = {"id", "description", "input", "output"}
    if any(not isinstance(task, dict) or not required <= set(task) for task in manifest):
        raise ValueError("every manifest item requires id, description, input, and output")
    ids = [task["id"] for task in manifest]
    if len(set(ids)) != len(ids):
        raise ValueError("manifest task ids must be unique")
    outputs = [resolve(manifest_path.parent, task["output"]) for task in manifest]
    if len(set(outputs)) != len(outputs):
        raise ValueError("manifest output paths must be unique")
    report = []
    for task, output_path in zip(manifest, outputs):
        arrays = load_arrays(resolve(manifest_path.parent, task["input"]))
        result = save_exact(output_path, compute(task, arrays))
        report.append({"id": task["id"], "path": str(output_path),
                       "shape": list(result.shape), "dtype": str(result.dtype)})
    print(json.dumps({"written": report}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"run_manifest failed: {exc}", file=sys.stderr)
        raise
