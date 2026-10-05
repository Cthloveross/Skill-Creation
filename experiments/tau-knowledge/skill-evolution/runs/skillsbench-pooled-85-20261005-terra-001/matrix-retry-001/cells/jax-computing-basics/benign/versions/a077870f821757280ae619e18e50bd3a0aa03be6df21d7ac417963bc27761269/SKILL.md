---
name: robust-jax-manifest-numerical-solver
description: Execute every numerical task declared by a runtime problem.json manifest, using JAX reductions, gradients, vmaps, and scans where described, and save one validated NumPy-compatible result at every declared output path.
---

# Robust JAX manifest numerical solver

Use this Skill in an environment containing `/app/problem.json` and numerical `.npy` or `.npz` input files. It is an executable Skill: the executor must run `scripts/run_manifest.py` before considering the task complete. The runtime manifest, not task IDs or example names, is the source of truth for input paths, output paths, and requested computations.

Run the entrypoint from `/app` (or give its absolute packaged path) with:

```sh
python scripts/run_manifest.py <<'JSON'
{"problem":"/app/problem.json"}
JSON
```

The entrypoint sets conservative CPU/thread configuration **before importing JAX**. This avoids common constrained-runtime failures from excessive XLA, BLAS, or OpenMP worker creation. It then processes every manifest entry independently. Relative input and output paths are resolved relative to the manifest; for example, `basic_reduce.npy` resolves to `/app/basic_reduce.npy`.

Never modify `/app/problem.json`, an input path, or files under `/app/data`. A failure JSON report means execution is incomplete. Correct the manifest-description handling or input-key mapping and rerun; do not replace a computation with an arbitrary placeholder.

## Entrypoint interface

`scripts/run_manifest.py` consumes one JSON object on standard input and emits one JSON object on standard output.

- Input schema: `{"problem": "/app/problem.json"}`. `problem` is optional and defaults to `/app/problem.json`.
- Successful output schema: `{"ok": true, "outputs": [{"id": string, "output": string, "shape": [int, ...], "dtype": string}, ...]}`.
- Failure schema: `{"ok": false, "error": string}` with nonzero exit status.

For each task the script loads `.npy` or `.npz` with `allow_pickle=False`, derives archive members from their semantic names, performs the operation described by that entry, materializes the JAX result, and saves exactly one array. `.npy` destinations use `numpy.save`; `.npz` destinations contain exactly one array named `result`. Parent output directories are created when necessary.

## Supported computation patterns

The reusable solver recognizes the numerical patterns used by this task family:

1. JAX NumPy reductions: sum, mean, minimum, maximum, product, sums/means of squares, and L2 norm, including an explicitly stated axis or axes.
2. A binary logistic/sigmoid cross-entropy gradient with respect to the supplied weights, computed with `jax.grad`.
3. A batched two-layer MLP forward computation, implemented by a single-example function and `jax.vmap`, with ReLU, tanh, sigmoid, or identity activation chosen from the description.
4. Cumulative/running sum or product recurrences, implemented with `jax.lax.scan` over the leading sequence axis.

The script validates dimensions before computation and rejects unsupported/ambiguous descriptions instead of silently guessing. Archive keys are inspected at runtime and matched case-insensitively against conventional semantic aliases (`x`, `y`, `w`, `w1`, `b1`, etc.).

After all results are written, the script reloads every declared output with pickle disabled and checks that it is one nonempty finite portable numeric ndarray. Thus a success report is evidence that every manifest output, including `/app/basic_reduce.npy` when declared, exists at its exact destination.
