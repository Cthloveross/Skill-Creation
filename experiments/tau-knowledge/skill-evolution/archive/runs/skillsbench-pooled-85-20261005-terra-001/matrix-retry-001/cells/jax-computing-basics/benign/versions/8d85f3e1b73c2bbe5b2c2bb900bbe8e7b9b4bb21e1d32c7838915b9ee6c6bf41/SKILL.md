---
name: run-jax-problem-manifest
description: Run a problem.json manifest of JAX numerical-array tasks and save every result at its declared path. Use for task bundles with .npy/.npz inputs, descriptions covering reductions, logistic gradients, batched MLPs, and scan recurrences.
---

# Run all manifest tasks

This Skill is executable: **run `scripts/solve_manifest.py` once** from `/app` before completing the task. Code inspection alone does not produce task artifacts.

Use the script runtime with this JSON stdin:

```json
{"problem":"/app/problem.json"}
```

Equivalently, invoke Python from `/app` with JSON on standard input. The script reads the live manifest, rather than assuming task order or paths. It returns JSON on stdout:

```json
{"ok":true,"backend":"jax","outputs":[{"id":"...","output":"...","shape":[...],"dtype":"..."}]}
```

A successful result must list every manifest task. The runner creates each exact `output` destination (including absolute destinations when declared), creates output parent directories, and checks that every result reloads through `numpy.load(..., allow_pickle=False)` as a nonempty numeric finite array.

## Safety and computation

- Treat `/app/problem.json` and every declared input, especially `/app/data/*`, as read-only.
- Inputs may be `.npy` single arrays or `.npz` named archives. The runner loads them with `allow_pickle=False` and chooses archive members by their runtime keys.
- Normal computation occurs in an isolated CPU JAX worker using `jax.numpy`, `jax.grad`, `jax.vmap`, and `jax.lax.scan` where indicated. Isolation keeps a native JAX/XLA initialization failure from losing all required files; a mathematically equivalent NumPy fallback is used only if the JAX worker terminates abnormally.
- Operation selection comes from each task description: reductions honor stated axes; logistic tasks differentiate stable binary cross-entropy with respect to weights; MLP tasks apply two affine layers per example; and scan tasks return the sequence of updated carries.
- If the script reports `ok: false`, do not claim outputs were produced. Surface its error instead of writing placeholders or modifying inputs.

After a successful invocation, leave all generated files at their manifest-declared destinations.
