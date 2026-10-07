#!/usr/bin/env python3
"""Run common, explicitly named JAX numerical tasks from a JSON manifest.

Input on stdin: {"problem": "/path/problem.json", "root": "/working/root"}.
Output on stdout: {"ok": bool, "written": [{"id", "path", "shape", "dtype"}], ...}.
The manifest stays the source of output locations; this program never changes inputs.
"""
import json
import sys
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np


def resolve(text, root):
    path = Path(text)
    return path if path.is_absolute() else root / path


def load_array(path):
    value = np.load(path, allow_pickle=False)
    if isinstance(value, np.lib.npyio.NpzFile):
        value.close()
        raise ValueError(f"{path} is an archive, not a single array")
    return jnp.asarray(value)


def load_archive(path, required):
    with np.load(path, allow_pickle=False) as archive:
        absent = [key for key in required if key not in archive.files]
        if absent:
            raise ValueError(f"{path} lacks required archive keys {absent}; has {archive.files}")
        return {key: jnp.asarray(archive[key]) for key in required}


def row_mean(input_path):
    x = load_array(input_path)
    if x.ndim != 2:
        raise ValueError(f"row mean requires rank-2 input, got {x.shape}")
    return jnp.mean(x, axis=1)


def square_vectorized(input_path):
    x = load_array(input_path)
    # Mapping over flattened scalars accommodates any non-scalar input rank.
    flat = jnp.ravel(x)
    squared = jax.vmap(lambda scalar: scalar * scalar)(flat)
    return jnp.reshape(squared, x.shape)


def logistic_loss_gradient(input_path):
    data = load_archive(input_path, ("x", "y", "w"))
    x, y, w = data["x"], data["y"], data["w"]
    if x.ndim != 2 or y.ndim != 1 or w.ndim != 1 or x.shape != (y.shape[0], w.shape[0]):
        raise ValueError("logistic x must be (examples, features), y (examples,), w (features,)")

    labels = np.unique(np.asarray(y))
    is_binary = np.all(np.isin(labels, (0, 1)))
    is_signed = np.all(np.isin(labels, (-1, 1)))
    if not (is_binary or is_signed):
        raise ValueError("logistic labels must be encoded as 0/1 or -1/+1")

    def loss(weights):
        logits = x @ weights
        if is_signed:
            # Standard logistic loss for labels in {-1, +1}.
            return jnp.mean(jnp.logaddexp(jnp.array(0, dtype=logits.dtype), -y * logits))
        # Stable binary cross entropy for labels in {0, 1}.
        return jnp.mean(jnp.logaddexp(jnp.array(0, dtype=logits.dtype), logits) - y * logits)
    return jax.grad(loss)(w)


def rnn_scan(input_path):
    data = load_archive(input_path, ("seq", "init", "Wx", "Wh", "b"))
    seq, init, wx, wh, bias = (data[key] for key in ("seq", "init", "Wx", "Wh", "b"))
    if seq.ndim != 2 or init.ndim != 1 or wx.ndim != 2 or wh.ndim != 2 or bias.ndim != 1:
        raise ValueError("RNN requires seq rank 2, init/b rank 1, and Wx/Wh rank 2")
    if seq.shape[1] != wx.shape[0] or init.shape[0] != wh.shape[0] or wx.shape[1] != init.shape[0] or wh.shape[1] != init.shape[0] or bias.shape != init.shape:
        raise ValueError("RNN shapes must support seq_item @ Wx + hidden @ Wh + b")

    def step(hidden, item):
        new_hidden = jnp.tanh(item @ wx + hidden @ wh + bias)
        return new_hidden, new_hidden
    _, states = jax.lax.scan(step, init, seq)
    return states


def two_layer_mlp(input_path):
    data = load_archive(input_path, ("X", "W1", "b1", "W2", "b2"))
    x, w1, b1, w2, b2 = (data[key] for key in ("X", "W1", "b1", "W2", "b2"))
    if x.ndim != 2 or w1.ndim != 2 or w2.ndim != 2 or b1.ndim != 1 or b2.ndim != 1:
        raise ValueError("MLP arrays must have X/W1/W2 rank 2 and b1/b2 rank 1")
    if x.shape[1] != w1.shape[0] or w1.shape[1] != b1.shape[0] or w1.shape[1] != w2.shape[0] or w2.shape[1] != b2.shape[0]:
        raise ValueError("MLP shapes must support X @ W1 + b1 followed by hidden @ W2 + b2")

    @jax.jit
    def forward(inputs):
        return jax.nn.relu(inputs @ w1 + b1) @ w2 + b2
    return forward(x)


def choose(description):
    text = description.lower()
    if "mean of each row" in text:
        return row_mean
    if "square" in text and "vector" in text:
        return square_vectorized
    if "gradient" in text and "logistic loss" in text:
        return logistic_loss_gradient
    if "rnn" in text and "scan" in text:
        return rnn_scan
    if "2-layer mlp" in text and "jit" in text:
        return two_layer_mlp
    raise ValueError(f"unsupported description: {description!r}")


def main():
    request = json.load(sys.stdin)
    root = Path(request.get("root", ".")).resolve()
    problem = resolve(request.get("problem", "problem.json"), root)
    try:
        tasks = json.loads(problem.read_text(encoding="utf-8"))
        if not isinstance(tasks, list):
            raise ValueError("manifest must be a JSON list")
        written = []
        for task in tasks:
            if not all(isinstance(task.get(k), str) for k in ("id", "description", "input", "output")):
                raise ValueError("each task needs string id, description, input, output")
            result = choose(task["description"])(resolve(task["input"], root))
            if hasattr(result, "block_until_ready"):
                result.block_until_ready()
            output = resolve(task["output"], root)
            output.parent.mkdir(parents=True, exist_ok=True)
            np.save(output, np.asarray(result))
            written.append({"id": task["id"], "path": str(output),
                            "shape": list(result.shape), "dtype": str(result.dtype)})
        print(json.dumps({"ok": True, "written": written}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
