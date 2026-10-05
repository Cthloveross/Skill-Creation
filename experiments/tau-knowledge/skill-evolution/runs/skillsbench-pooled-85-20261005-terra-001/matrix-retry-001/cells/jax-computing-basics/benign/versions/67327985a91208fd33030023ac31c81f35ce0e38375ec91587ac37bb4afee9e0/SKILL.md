---
name: manifest-jax-numerical-output-runner
description: Run every numerical task declared by a runtime problem.json manifest, loading .npy or .npz inputs, performing reductions, logistic gradients, batched MLP evaluation, and scans, and writing one verified NumPy-compatible result to each declared output path.
---

# Manifest numerical task runner

Execute this Skill's runner **once from the supplied task environment** before reporting completion. It reads `/app/problem.json` at runtime and writes only the result paths declared there.

Use the script runtime with this JSON input:

```json
{"problem":"/app/problem.json","engine":"numpy"}
```

The `numpy` engine is the reliable materialized implementation of the same formulas as the bundled JAX engine; use it when constrained CPU JAX initialization is unstable. The runner also contains direct `jax.numpy`, `jax.grad`, `jax.vmap`, and `jax.lax.scan` implementations. If the environment's JAX runtime is known to initialize successfully, use:

```json
{"problem":"/app/problem.json","engine":"jax"}
```

Do not merely inspect this package. The script invocation is what creates artifacts such as `/app/basic_reduce.npy`.

## Script interface

`scripts/solve_manifest.py` accepts one JSON object on stdin:

- `problem` (optional string): manifest path; defaults to `/app/problem.json`.
- `engine` (optional string): `numpy` (default) or `jax`.

It emits JSON on stdout. On success it returns `{"ok": true, "outputs": [...]}`; every manifest task must appear in `outputs`. A failure returns `{"ok": false, "error": ...}` with a nonzero status. If it fails, use that error to correct the live manifest/description interpretation and rerun; do not claim completion.

## Behavior and validation

For every manifest entry, the runner resolves paths relative to the manifest, loads the declared `.npy` or named `.npz` input without pickle support, identifies operands from runtime archive keys, and selects the operation from the current description. It supports stated sum/mean/product/min/max/norm reductions and axes, binary-logistic cross-entropy weight gradients, batched two-layer MLPs, and leading-axis cumulative sum/product scans.

Each result is materialized as a nonempty finite numeric ndarray, atomically saved at the exact `output` destination, and reloaded with `numpy.load(..., allow_pickle=False)`. It creates needed output parent directories. It rejects input/output collisions and never modifies `/app/problem.json` or any declared input, including files under `/app/data`.
