---
name: reliable-manifest-jax-numerics
description: Produce every result required by an /app/problem.json numerical-task manifest. Use this for JAX array, reduction, gradient, batched MLP, and scan tasks whose inputs are .npy or .npz files and whose exact output destinations are declared in the manifest.
---

# Reliable manifest numerical solver

This Skill must be **executed**, not only read. Invoke the packaged script runtime once with:

```json
{"problem":"/app/problem.json","engine":"numpy"}
```

using `scripts/solve_manifest.py`. The successful JSON response has `"ok": true` and lists every written result. `numpy` is the safe default because some constrained runtimes abort during native JAX initialization; it computes the same array formulas as the JAX implementation without risking loss of all output artifacts. The script also contains JAX implementations and accepts `"engine":"jax"` where JAX execution is known to be stable.

## Runtime interface

The script reads one JSON object from stdin:

- `problem`: optional manifest path, default `/app/problem.json`.
- `engine`: optional `numpy` (default) or `jax`.

It emits one JSON object on stdout:

- success: `{"ok":true,"engine":"...","outputs":[...]}`;
- failure: `{"ok":false,"error":"..."}`.

## Method

The solver loads the live manifest and processes **every** entry independently. It resolves relative paths against the manifest directory, loads `.npy` files or inspects `.npz` archive members at runtime, and selects the computation from the task description:

- reductions including sum, mean, product, extrema, squared sums, and L2 norms, with stated axes;
- binary logistic cross-entropy gradients with respect to weights;
- batched two-layer MLP evaluation with the described activation;
- cumulative/prefix sum and product scans along the leading axis.

Each result is materialized as a numeric NumPy ndarray and saved to the exact output path. The script creates parent directories, uses atomic replacement, reloads every output with `allow_pickle=False`, and rejects empty, object, nonnumeric, NaN, or infinite outputs. It never writes the manifest or any declared input file.

After invocation, require `ok:true`. If it is false, use the reported missing key, shape mismatch, or unsupported wording to correct the task interpretation; do not claim completion and do not substitute guessed output paths.
