---
name: manifest-jax-task-solver
description: Execute every numerical task declared in /app/problem.json, load each .npy or .npz input at runtime, use the described JAX computation when available with a crash-safe equivalent fallback, and save one validated NumPy-compatible result at each manifest output path.
---

# Manifest JAX task solver

Use this Skill to complete the supplied manifest-driven numerical task, not merely to inspect its inputs or describe an approach.

## Required executor action

**Immediately invoke `scripts/solve_manifest.py` through the packaged-script runtime with this JSON input:**

```json
{"problem":"/app/problem.json","engine":"auto"}
```

That invocation is the action which creates the required result files. Do not stop after reading this Skill or the script. The script reads the live manifest, processes every task, and writes the exact destinations declared by the manifest, including relative paths resolved from `/app/problem.json`.

Its stdin is one JSON object:

- `problem` (optional string): manifest path; default `/app/problem.json`.
- `engine` (optional): `auto` (default), `jax`, or `numpy`.

`auto` first runs JAX in an isolated child process. If JAX initializes and completes successfully, its results are used. If native JAX aborts, segfaults, times out, or cannot initialize, the non-JAX parent recomputes every supported formula with equivalent NumPy operations and still writes the required portable artifacts. This isolation is necessary because a native JAX crash cannot be recovered by Python exception handling in the importing process. Use `auto`, rather than a direct `jax` request, in constrained environments.

A successful response has this form:

```json
{"ok":true,"engine":"jax","outputs":[{"id":"...","output":"/app/...","shape":[...],"dtype":"..."}]}
```

or the same form with `"engine":"numpy"` after safe recovery. `ok:false` means no completion claim may be made.

## Task interpretation

The solver loads `.npy` files as a single array and inspects `.npz` archive keys at runtime. It selects the operation from each task description independently:

- sum, mean, product, extrema, squared reductions, and L2 reductions, including stated axes;
- binary logistic cross-entropy gradients with respect to the supplied weights;
- batched two-layer MLP evaluation, using `jax.vmap` in the JAX worker;
- leading-axis cumulative sum or product, using `jax.lax.scan` in the JAX worker.

It recognizes conventional archive names such as `x`, `y`, `w`, `b`, `w1`, `b1`, `w2`, `b2`, `sequence`, `xs`, and `initial`. Ambiguous archive members, invalid dimensions, or an unsupported description are reported as errors instead of silently producing unrelated output.

## Completion checks

The script creates missing parent output directories, saves `.npy` outputs with `numpy.save` and `.npz` outputs as a one-member `result` archive, then reloads every manifest output with `allow_pickle=False`. Each result must be a nonempty finite numeric ndarray. It never writes `/app/problem.json`, an input path, or any file under `/app/data`.
