"""Keyword-driven handlers mapping a task description to a JAX computation.

Each handler receives (task, kind, data) and returns a result (a JAX/NumPy array
or a dict of arrays). Handlers must read shapes/keys/axes at runtime and must not
hardcode instance answers. If no handler matches, dispatch raises Unhandled so
solve.py can report it instead of writing a wrong file.

These are best-effort implementations for the common operations this task family
tests. After inspecting the real descriptions, correct any handler that does not
produce exactly the quantity requested.
"""
import re

import jax
import jax.numpy as jnp
import numpy as np


class Unhandled(Exception):
    pass


def _axis_from(desc):
    m = re.search(r"axis\s*=?\s*(-?\d+)", desc)
    if m:
        return int(m.group(1))
    if "each column" in desc or "over rows" in desc or "down the column" in desc:
        return 0
    if "each row" in desc or "over columns" in desc or "along the row" in desc:
        return 1
    if "last axis" in desc or "last dimension" in desc:
        return -1
    if "first axis" in desc or "first dimension" in desc:
        return 0
    return None


def _primary_array(kind, data):
    if kind == "npy":
        return data
    # prefer common input names, else first entry
    for key in ("x", "X", "input", "inputs", "a", "data"):
        if key in data:
            return data[key]
    return data[next(iter(data))]


def _reduction(desc, arr):
    axis = _axis_from(desc)
    arr = jnp.asarray(arr)
    if "mean" in desc or "average" in desc:
        return jnp.mean(arr, axis=axis)
    if "std" in desc or "standard deviation" in desc:
        return jnp.std(arr, axis=axis)
    if "var" in desc:
        return jnp.var(arr, axis=axis)
    if "prod" in desc or "product" in desc:
        return jnp.prod(arr, axis=axis)
    if "maximum" in desc or "max" in desc:
        return jnp.max(arr, axis=axis)
    if "minimum" in desc or "min" in desc:
        return jnp.min(arr, axis=axis)
    if "argmax" in desc:
        return jnp.argmax(arr, axis=axis)
    if "argmin" in desc:
        return jnp.argmin(arr, axis=axis)
    # default to sum
    return jnp.sum(arr, axis=axis)


def _cumulative(desc, arr):
    axis = _axis_from(desc)
    arr = jnp.asarray(arr)
    if "cumprod" in desc or "cumulative product" in desc:
        return jnp.cumprod(arr, axis=axis if axis is not None else 0)
    return jnp.cumsum(arr, axis=axis if axis is not None else 0)


def _sigmoid(arr):
    return jax.nn.sigmoid(jnp.asarray(arr))


def _relu(arr):
    return jax.nn.relu(jnp.asarray(arr))


def _softmax(desc, arr):
    axis = _axis_from(desc)
    return jax.nn.softmax(jnp.asarray(arr), axis=axis if axis is not None else -1)


def _get(data, *names):
    for n in names:
        if n in data:
            return data[n]
    return None


def _logistic_grad(desc, data):
    """Gradient of mean binary cross-entropy loss of logistic regression wrt w (and b)."""
    X = _get(data, "X", "x", "inputs", "features")
    y = _get(data, "y", "Y", "labels", "targets")
    w = _get(data, "w", "W", "weights", "theta")
    b = _get(data, "b", "bias")
    X = jnp.asarray(X)
    y = jnp.asarray(y)
    w = jnp.asarray(w)
    has_b = b is not None
    b0 = jnp.asarray(b) if has_b else jnp.asarray(0.0)

    def loss(w_, b_):
        logits = X @ w_ + b_
        p = jax.nn.sigmoid(logits)
        eps = 1e-7
        p = jnp.clip(p, eps, 1 - eps)
        return -jnp.mean(y * jnp.log(p) + (1 - y) * jnp.log(1 - p))

    if has_b:
        gw, gb = jax.grad(loss, argnums=(0, 1))(w, b0)
        return {"dw": gw, "db": gb}
    return jax.grad(loss)(w, b0)


def _logistic_predict(desc, data):
    X = _get(data, "X", "x", "inputs", "features")
    w = _get(data, "w", "W", "weights", "theta")
    b = _get(data, "b", "bias")
    logits = jnp.asarray(X) @ jnp.asarray(w)
    if b is not None:
        logits = logits + jnp.asarray(b)
    return jax.nn.sigmoid(logits)


def _mlp_forward(desc, data):
    """Batched MLP forward pass via vmap over the batch axis.
    Expects weight/bias keys like W1,b1,W2,b2,... and inputs X/x.
    ReLU between layers; final layer left linear unless a nonlinearity is named.
    """
    X = _get(data, "X", "x", "inputs")
    layers = []
    i = 1
    while True:
        W = _get(data, f"W{i}", f"w{i}")
        b = _get(data, f"b{i}")
        if W is None:
            break
        layers.append((jnp.asarray(W), None if b is None else jnp.asarray(b)))
        i += 1
    if not layers:
        raise Unhandled("no weight layers Wi found for mlp forward")

    def single(x):
        h = x
        for idx, (W, b) in enumerate(layers):
            h = h @ W
            if b is not None:
                h = h + b
            if idx < len(layers) - 1:
                h = jax.nn.relu(h)
        return h

    return jax.vmap(single)(jnp.asarray(X))


def _scan_recurrence(desc, data):
    """Simple linear recurrence / cumulative state via lax.scan.
    Interprets a sequence array (time-major by default) and optional weights.
    Default: running cumulative sum of the sequence along the time axis.
    Adjust once the description's recurrence is known.
    """
    seq = _get(data, "x", "X", "seq", "sequence", "inputs")
    if seq is None:
        seq = data[next(iter(data))] if isinstance(data, dict) else data
    seq = jnp.asarray(seq)

    def step(carry, xt):
        new = carry + xt
        return new, new

    init = jnp.zeros(seq.shape[1:], dtype=seq.dtype)
    _, ys = jax.lax.scan(step, init, seq)
    return ys


def _matmul(desc, kind, data):
    if kind == "npz":
        a = _get(data, "a", "A", "x", "X")
        b = _get(data, "b", "B", "y", "Y", "w", "W")
        if a is not None and b is not None:
            return jnp.asarray(a) @ jnp.asarray(b)
    raise Unhandled("matmul needs two arrays")


def dispatch(task, kind, data):
    desc = (task.get("description") or "").lower()

    # Order matters: more specific intents first.
    if ("gradient" in desc or "grad" in desc or "derivative" in desc) and (
        "loss" in desc or "logistic" in desc or "cross entropy" in desc
        or "cross-entropy" in desc or "bce" in desc):
        return _logistic_grad(desc, data)
    if "logistic" in desc and ("predict" in desc or "probab" in desc or "forward" in desc):
        return _logistic_predict(desc, data)
    if ("mlp" in desc or "multilayer" in desc or "multi-layer" in desc
            or "neural" in desc or ("forward" in desc and "layer" in desc)):
        return _mlp_forward(desc, data)
    if "scan" in desc or "recurren" in desc or "rnn" in desc or "sequential" in desc:
        return _scan_recurrence(desc, data)
    if "cumulative" in desc or "cumsum" in desc or "cumprod" in desc:
        return _cumulative(desc, _primary_array(kind, data))
    if "softmax" in desc:
        return _softmax(desc, _primary_array(kind, data))
    if "sigmoid" in desc:
        return _sigmoid(_primary_array(kind, data))
    if "relu" in desc:
        return _relu(_primary_array(kind, data))
    if "matmul" in desc or "matrix multipl" in desc or "dot product" in desc or "@" in desc:
        return _matmul(desc, kind, data)
    if any(k in desc for k in ("sum", "mean", "average", "reduce", "reduction",
                               "max", "min", "prod", "product", "std", "var",
                               "argmax", "argmin")):
        return _reduction(desc, _primary_array(kind, data))

    raise Unhandled(f"no handler matched description: {task.get('description')!r}")
