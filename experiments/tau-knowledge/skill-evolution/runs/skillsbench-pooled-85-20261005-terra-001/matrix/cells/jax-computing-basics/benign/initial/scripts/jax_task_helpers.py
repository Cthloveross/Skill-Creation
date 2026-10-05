"""Reusable JAX expression evaluation helpers for manifest numerical tasks.

Expression leaves are JSON numbers/lists or {"ref": "archive_key"}. Each operation is a
mapping with an "op" field. Operations intentionally use JAX arrays exclusively after loading.
"""
from __future__ import annotations

from typing import Any, Mapping
from jax import config
config.update("jax_enable_x64", True)
import jax
import jax.numpy as jnp
import jax.scipy as jsp


def _axis(value):
    return tuple(value) if isinstance(value, list) else value


def _activation(name: str, x):
    table = {
        "identity": lambda z: z,
        "relu": jax.nn.relu,
        "sigmoid": jax.nn.sigmoid,
        "tanh": jnp.tanh,
        "softplus": jax.nn.softplus,
        "gelu": jax.nn.gelu,
    }
    if name not in table:
        raise ValueError(f"unsupported activation {name!r}")
    return table[name](x)


def evaluate(node: Any, env: Mapping[str, Any]):
    """Evaluate one static JSON expression against JAX-array environment ``env``."""
    if isinstance(node, (int, float, bool)) or node is None:
        return jnp.asarray(node)
    if isinstance(node, list):
        return jnp.asarray(node)
    if not isinstance(node, dict):
        raise TypeError(f"expression must be JSON scalar/list/object, got {type(node).__name__}")
    if "ref" in node:
        key = node["ref"]
        if key not in env:
            raise KeyError(f"unknown array reference {key!r}; available: {sorted(env)}")
        return env[key]
    op = node.get("op")
    if not op:
        raise ValueError("expression object needs ref or op")
    args = [evaluate(a, env) for a in node.get("args", [])]
    unary = {"neg": jnp.negative, "abs": jnp.abs, "exp": jnp.exp, "log": jnp.log,
             "sqrt": jnp.sqrt, "square": jnp.square, "tanh": jnp.tanh,
             "sigmoid": jax.nn.sigmoid, "relu": jax.nn.relu, "softplus": jax.nn.softplus}
    binary = {"add": jnp.add, "sub": jnp.subtract, "mul": jnp.multiply, "div": jnp.divide,
              "pow": jnp.power, "maximum": jnp.maximum, "minimum": jnp.minimum,
              "equal": jnp.equal, "greater": jnp.greater, "less": jnp.less,
              "matmul": jnp.matmul, "dot": jnp.dot}
    if op in unary:
        return unary[op](args[0])
    if op in binary:
        return binary[op](args[0], args[1])
    if op in ("sum", "mean", "max", "min", "prod"):
        return getattr(jnp, op)(args[0], axis=_axis(node.get("axis")), keepdims=node.get("keepdims", False))
    if op == "sum_squares":
        return jnp.sum(jnp.square(args[0]), axis=_axis(node.get("axis")), keepdims=node.get("keepdims", False))
    if op == "norm":
        return jnp.linalg.norm(args[0], ord=node.get("ord"), axis=_axis(node.get("axis")), keepdims=node.get("keepdims", False))
    if op == "transpose":
        return jnp.transpose(args[0], axes=_axis(node.get("axes")))
    if op == "reshape":
        return jnp.reshape(args[0], tuple(node["shape"]))
    if op == "astype":
        return args[0].astype(node["dtype"])
    if op == "getitem":
        return args[0][node["index"]]
    if op == "take":
        return jnp.take(args[0], args[1], axis=node.get("axis"))
    if op == "concatenate":
        return jnp.concatenate(args, axis=node.get("axis", 0))
    if op == "stack":
        return jnp.stack(args, axis=node.get("axis", 0))
    if op == "where":
        return jnp.where(args[0], args[1], args[2])
    if op == "softmax":
        return jax.nn.softmax(args[0], axis=node.get("axis", -1))
    if op == "logsumexp":
        return jsp.special.logsumexp(args[0], axis=_axis(node.get("axis")), keepdims=node.get("keepdims", False))
    if op == "binary_logistic_loss":
        logits, labels = args
        loss = jax.nn.softplus(logits) - labels * logits
        reduction = node.get("reduction", "mean")
        if reduction == "none": return loss
        if reduction == "sum": return jnp.sum(loss)
        if reduction == "mean": return jnp.mean(loss)
        raise ValueError("binary_logistic_loss reduction must be none, sum, or mean")
    if op in ("grad", "value_and_grad"):
        variable = node["variable"]
        value = evaluate(node["value"], env)
        def fn(v):
            local = dict(env)
            local[variable] = v
            return evaluate(node["loss"], local)
        transform = jax.grad if op == "grad" else jax.value_and_grad
        return transform(fn)(value)
    if op == "vmap":
        variable = node["variable"]
        value = evaluate(node["value"], env)
        def fn(v):
            local = dict(env)
            local[variable] = v
            return evaluate(node["body"], local)
        return jax.vmap(fn, in_axes=node.get("in_axes", 0), out_axes=node.get("out_axes", 0))(value)
    if op == "jit":
        variable = node["variable"]
        value = evaluate(node["value"], env)
        def fn(v):
            local = dict(env)
            local[variable] = v
            return evaluate(node["body"], local)
        return jax.jit(fn)(value)
    if op == "scan":
        carry_name, x_name = node.get("carry_var", "carry"), node.get("x_var", "x")
        init, xs = evaluate(node["init"], env), evaluate(node["xs"], env)
        def body(carry, x):
            local = dict(env)
            local[carry_name], local[x_name] = carry, x
            next_carry = evaluate(node["carry_expr"], local)
            local[carry_name] = next_carry
            y = evaluate(node.get("y_expr", {"ref": carry_name}), local)
            return next_carry, y
        carry, ys = jax.lax.scan(body, init, xs)
        return carry if node.get("result", "outputs") == "carry" else ys
    if op == "mlp":
        x = evaluate(node["x"], env)
        for layer in node["layers"]:
            w, b = evaluate(layer["weight"], env), evaluate(layer["bias"], env)
            if layer.get("transpose_weight", False):
                w = w.T
            x = _activation(layer.get("activation", "identity"), jnp.matmul(x, w) + b)
        return x
    raise ValueError(f"unsupported expression op {op!r}")
