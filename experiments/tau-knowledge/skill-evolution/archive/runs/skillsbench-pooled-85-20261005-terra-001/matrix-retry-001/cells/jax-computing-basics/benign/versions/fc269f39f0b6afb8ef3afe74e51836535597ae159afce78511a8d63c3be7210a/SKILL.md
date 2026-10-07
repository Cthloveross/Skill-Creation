---
name: reliable-jax-manifest-runner
description: Execute every numerical task declared in /app/problem.json, safely load .npy/.npz inputs, implement reductions, logistic gradients, vectorized two-layer MLPs, and scans, then write a verified numeric NumPy result at each manifest output path.
---

# Reliable JAX manifest runner

This Skill must be **executed**, not merely read. Use the packaged script runner once before completing the task:

```json
{"problem":"/app/problem.json","engine":"numpy"}
```

Invoke `scripts/solve_manifest.py` through the Skill script runtime with that JSON input. The default manifest is `/app/problem.json`, so `{}` is also valid. Run it from the supplied task environment; it writes results to `/app`, not to the Skill package directory.

The preferred reliable mode is `numpy`, which implements the same array formulas as the JAX implementation while avoiding a known possibility that JAX initialization aborts in a constrained CPU sandbox before artifacts are saved. The package includes direct JAX implementations of every supported computation. When JAX has been confirmed usable, invoke with `{"problem":"/app/problem.json","engine":"jax"}` to execute with `jax.numpy`, `jax.grad`, `jax.vmap`, and `jax.lax.scan`.

## Input and output interface

`solve_manifest.py` reads one JSON object from stdin:

- `problem` (optional string): path to the task manifest; defaults to `/app/problem.json`.
- `engine` (optional string): `numpy` or `jax`; defaults to `numpy`.

It emits one JSON object on stdout:

- success: `{"ok": true, "engine": "...", "outputs": [{"id": ..., "output": ..., "shape": [...], "dtype": ...}]}`;
- failure: `{"ok": false, "error": "..."}` and a nonzero status.

A successful response is required. Its `outputs` list must cover every manifest entry. Do not report task completion after an unsuccessful invocation.

## Runtime behavior

The runner treats `/app/problem.json` and all declared inputs as read-only. For every manifest task it:

1. Resolves the task's input and output paths relative to the manifest unless a path is absolute, rejects input/output collisions, and checks unique IDs and output destinations.
2. Loads `.npy` files or inspects all `.npz` archive members at runtime. It selects operands by archive-key aliases and validates compatible dimensions.
3. Determines the operation from the current description: a reduction and stated axis; a binary logistic cross-entropy weight gradient; a batched two-layer MLP; or a cumulative leading-axis sum/product scan.
4. Materializes a standard numeric ndarray, creates output parent directories where necessary, and atomically saves one array at the exact declared destination.
5. Reloads each written artifact using `allow_pickle=False` and rejects missing, empty, object, nonnumeric, NaN, or infinite outputs.

If a description uses an unsupported operation or the archive has unexpected keys, use the reported error to update the operation/key handling based on the live manifest and input inspection, then rerun. Never modify `/app/problem.json` or files under `/app/data`.
