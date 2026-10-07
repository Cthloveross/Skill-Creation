---
name: manifest-jax-numerical-output-runner
description: Execute all numerical tasks declared by an /app/problem.json manifest, loading .npy or .npz inputs and writing one verified NumPy-compatible result to every declared output path. Use for JAX reductions, gradients, vectorized MLPs, and scans.
---

# Manifest numerical output runner

**Execute this Skill before considering the task complete.** From the task working directory, run `scripts/solve_manifest.py` once through the script runtime with:

```json
{"problem":"/app/problem.json","engine":"numpy"}
```

The script's default is also this request when invoked without stdin. It must return JSON with `"ok": true`. Its `outputs` list must contain one entry for every manifest task. Do not merely inspect the script or manifest: the required `.npy`/`.npz` artifacts are created only when the script runs.

`numpy` is the reliable execution mode for constrained CPU sandboxes in which importing JAX can abort the process before files are written. The computations implement the same immutable array formulas as the accompanying JAX implementations. When JAX is known to initialize safely, use `{"problem":"/app/problem.json","engine":"jax"}` instead; that mode uses `jax.numpy`, `jax.grad`, `jax.vmap`, and `jax.lax.scan` as appropriate.

## Interface

The program reads one optional JSON object from standard input:

- `problem` — manifest path, default `/app/problem.json`.
- `engine` — `numpy` (default) or `jax`.

It writes exactly one JSON object to standard output:

- success: `{"ok": true, "engine": "...", "outputs": [...]}`;
- failure: `{"ok": false, "error": "..."}` and a nonzero exit status.

## What it does

For every live manifest entry, the runner:

1. Resolves its input and output relative to the manifest, rejects output/input collisions, and leaves `/app/problem.json` and all input files unchanged.
2. Loads `.npy` input or inspects `.npz` member names at runtime.
3. Chooses the operation from the current task description: reductions (including stated axes), binary-logistic cross-entropy weight gradients, batched two-layer MLP evaluation, or leading-axis prefix/scan operations.
4. Materializes a numeric ndarray, creates required parent directories, and atomically saves it at the exact manifest `output` path.
5. Reloads every output with `allow_pickle=False` and rejects empty, object, nonnumeric, NaN, or infinite results.

If the JSON response is not successful, do not claim outputs exist. Correct the reported missing archive key, incompatible shape, or unsupported description and rerun. After a successful invocation, every manifest-declared output, including a root-level relative path such as `/app/basic_reduce.npy`, has been created at its declared destination.
