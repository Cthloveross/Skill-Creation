---
name: jax-task-bundle-executor
description: Execute a runtime JSON bundle of basic JAX numerical tasks, inspecting .npy/.npz schemas, using JAX transformations where requested, and saving every result at its manifest-specified NumPy output path. Use for row reductions, vectorized elementwise functions, logistic gradients, scan RNNs, and JIT two-layer MLPs described in problem.json.
---

# JAX task bundle executor

The runtime manifest and its descriptions determine the computation and output names. Inspect inputs before selecting operands or axes; never infer an archive schema solely from its filename.

## Execute the supplied standard-task entrypoint

For the common tasks named in this Skill, run the packaged entrypoint from the runtime root (use `python3` when `python` is not installed):

```sh
python3 /app/environment/skills/current/scripts/run_bundle.py <<'JSON'
{"problem":"/app/problem.json", "root":"/app"}
JSON
python3 /app/environment/skills/current/scripts/validate_outputs.py <<'JSON'
{"problem":"/app/problem.json", "root":"/app"}
JSON
```

`run_bundle.py` reads JSON on stdin with:

- `problem`: manifest path, absolute or relative to `root` (default `problem.json`);
- `root`: directory resolving relative manifest input/output paths (default current directory).

It emits one JSON report on stdout. On success, `written` reports every task id, exact output path, result shape, and dtype. It uses `jax.numpy`, `jax.vmap`, `jax.grad`, `jax.lax.scan`, and `jax.jit` as appropriate; it converts materialized device arrays to NumPy only at save time. A nonzero exit and `ok: false` mean that the manifest, description, keys, or shapes are unsupported rather than that a partial output is valid.

The entrypoint supports these precise description families and validates their required runtime schema:

- **Mean of each row**: rank-2 single array; `jnp.mean(x, axis=1)`.
- **Square using vectorization**: single array; scalar squaring mapped by `jax.vmap` over flattened elements and reshaped back.
- **Gradient of logistic loss**: archive `x` `(examples, features)`, `y` `(examples,)`, `w` `(features,)`; gradient with respect to `w` of the mean stable binary cross entropy for logits `x @ w`.
- **RNN forward pass using scan**: archive `seq`, `init`, `Wx`, `Wh`, `b`; post-update hidden states from `tanh(item @ Wx + hidden @ Wh + b)` via `jax.lax.scan`.
- **JIT 2-layer MLP**: archive `X`, `W1`, `b1`, `W2`, `b2`; `jax.jit` of `relu(X @ W1 + b1) @ W2 + b2`.

These conventions are the standard meanings implemented by the entrypoint. If a different task supplies an explicit formula, output form, activation, orientation, loss reduction, or requested dtype, write a small task-specific JAX solver following that formula instead of applying this entrypoint.

## Inspection and validation helpers

Before execution, inventory all distinct inputs:

```sh
python3 /app/environment/skills/current/scripts/inventory.py <<'JSON'
{"paths":["/app/data/input.npy", "/app/data/archive.npz"]}
JSON
```

`inventory.py` accepts `{"paths":[string,...]}` and emits JSON schemas (kind, keys, shapes, dtypes). `validate_outputs.py` accepts `{"problem": string, "root": string}` and emits a JSON report confirming each declared `.npy` or `.npz` result is present and loadable. It checks artifact schemas, not mathematical semantics.

For task-specific work, keep the computation in JAX, use a scalar-returning loss for `jax.grad`, match scan output timing (pre- versus post-update), and use `axis=-1` only when the description identifies the final axis. Call `block_until_ready()` before `np.asarray`/`np.save`, create output parent directories, and save exactly the manifest output paths. Do not modify runtime inputs or the manifest, silently substitute NumPy computation, or claim a result for an ambiguous/unsupported description.
