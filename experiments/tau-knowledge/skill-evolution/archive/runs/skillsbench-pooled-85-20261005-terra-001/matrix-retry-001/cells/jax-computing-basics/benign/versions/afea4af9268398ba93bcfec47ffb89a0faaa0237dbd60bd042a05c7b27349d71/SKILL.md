---
name: execute-jax-manifest-numerical-tasks
description: Executes every task declared in a runtime problem.json manifest with JAX, loads .npy or .npz inputs safely, and saves one validated numeric NumPy-compatible result at each declared output path. Use for manifest-driven JAX reductions, gradients, batched MLPs, and scans.
---

# JAX manifest task executor

This Skill must be **executed**, not merely read. From the task environment, invoke `scripts/solve_manifest.py` through the script runtime with exactly:

```json
{"problem":"/app/problem.json"}
```

The invocation reads the live `/app/problem.json`, computes every listed task with JAX, and creates every manifest-declared output, including paths such as `/app/basic_reduce.npy`. Do this once before reporting task completion.

## Script interface

`scripts/solve_manifest.py` receives one JSON object on stdin:

- `problem` (optional string): absolute or relative manifest path. Defaults to `/app/problem.json`.

It emits JSON on stdout:

- Success: `{"ok": true, "outputs": [{"id": ..., "output": ..., "shape": [...], "dtype": ...}]}`.
- Failure: `{"ok": false, "error": "..."}` and exits nonzero.

A successful response must list one output for every manifest entry. The runner resolves relative input/output paths relative to the manifest, never edits the manifest or inputs, creates output parent directories, writes results atomically, and reloads each result with `numpy.load(..., allow_pickle=False)`.

## Supported task interpretation

The runner inspects `.npy` versus `.npz` inputs, archive keys, shapes, and dtypes at runtime. It recognizes reduction operations and requested axes; binary-logistic cross-entropy gradients via `jax.grad`; batched two-layer networks via `jax.vmap`; and cumulative sum/product recurrences via `jax.lax.scan`. Operations are performed with JAX arrays and materialized only for portable result-file writing.

If the script reports an interpretation or shape error, preserve the supplied files and correct the runtime task interpretation; do not substitute placeholder outputs or write to files under `/app/data`.
