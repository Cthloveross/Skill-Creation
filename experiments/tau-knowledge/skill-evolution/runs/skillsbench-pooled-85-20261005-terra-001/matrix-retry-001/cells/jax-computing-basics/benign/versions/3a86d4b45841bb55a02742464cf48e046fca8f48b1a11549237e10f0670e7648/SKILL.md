---
name: execute-jax-manifest-tasks
description: Execute every numerical-array task declared by a live problem.json manifest, using JAX for reductions, logistic-loss gradients, batched two-layer MLP evaluation, and scan-style prefix recurrences, then write each result to its exact declared output path.
---

# Execute the manifest

This Skill produces task artifacts only when its runner is executed. Invoke the packaged script through the script runtime **once**, with JSON stdin:

```json
{"problem":"/app/problem.json"}
```

The `problem` field is optional and defaults to `/app/problem.json`. The runner emits one JSON object on stdout:

```json
{"ok":true,"backend":"jax","outputs":[{"id":"...","output":"...","shape":[...],"dtype":"..."}]}
```

A successful response must contain one entry for every manifest task. Do not stop after the first task.

## Method

1. Read the live manifest at runtime. Treat its `input`, `output`, and `description` fields as the source of truth; do not assume task order or paths.
2. Load `.npy` inputs as one array and `.npz` inputs as named arrays with `allow_pickle=False`. Archive keys, shapes, and dtypes are inspected at runtime.
3. Select the operation indicated by each description. The runner supports numerical reductions, stable binary-logistic-loss gradients with respect to weights, vectorized two-layer MLP evaluation, and additive or multiplicative scans.
4. The runner first executes a CPU JAX worker using `jax.numpy`, `jax.grad`, `jax.vmap`, and `jax.lax.scan` as appropriate. If native JAX initialization aborts, it reruns the same supported numerical formulas with NumPy so the required portable artifacts are still produced.
5. Each result is materialized as a nonempty finite numeric NumPy ndarray, atomically saved to the exact manifest `output` path, and reloaded with `numpy.load(..., allow_pickle=False)`.

The script creates required parent directories. It never modifies `/app/problem.json` or declared input files, including files under `/app/data`.

If stdout reports `ok: false`, report the error rather than claiming results were written. Unsupported descriptions or ambiguous archive keys are deliberate errors: resolve them from the task description and input rather than writing placeholder data.
