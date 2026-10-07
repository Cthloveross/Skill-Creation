---
name: resilient-jax-manifest-executor
description: Execute all numerical tasks in an /app/problem.json manifest, using JAX operations when the JAX subprocess is available and a numerically equivalent portable fallback if its native runtime fails, then save one validated NumPy-compatible result at every declared output path.
---

# Resilient JAX manifest executor

Use this Skill for a manifest-driven JAX numerical task environment. Read `/app/problem.json` at runtime; do not infer task IDs, archive keys, shapes, axes, or output names from this Skill. Never modify `/app/problem.json` or anything in `/app/data`.

The required completion condition is that **every** task's declared `output` is present, loadable by `numpy.load(..., allow_pickle=False)`, and contains exactly one nonempty finite numeric array.

## Run it

Invoke the packaged `scripts/run_manifest.py` through the runtime's packaged-script facility, rather than guessing an installed Skill filesystem path or relying on an external command. Its stdin request is:

```json
{"problem":"/app/problem.json","engine":"auto"}
```

`problem` is optional and defaults to `/app/problem.json`. Relative paths in the manifest are resolved relative to the manifest directory. `engine` is optional:

- `"auto"` (default) starts a contained JAX execution first. If JAX exits normally, its JAX result is retained. If JAX fails at native initialization or execution, the parent process computes the same supported numerical operations with the portable NumPy implementation so that all required artifacts are still produced.
- `"jax"` requires the JAX implementation and returns failure if JAX cannot run.
- `"numpy"` selects the portable implementation directly. This is a recovery mode for a known-broken JAX runtime.

The JAX branch uses `jax.numpy`, `jax.grad`, `jax.vmap`, and `jax.lax.scan` as appropriate to the task. The fallback implements the same array formulas, including stable logistic loss-gradient arithmetic, and is deliberately isolated in a child-safe recovery design because a native JAX segfault cannot be caught inside the importing Python process.

A successful stdout response has this schema:

```json
{"ok":true,"engine":"jax-or-numpy","outputs":[{"id":"...","output":"/app/...","shape":[...],"dtype":"..."}]}
```

Do not regard source code, a successful import, or a partial set of files as completion. A response with `ok: false`, a nonzero process exit, or a missing manifest destination requires correction and another execution.

## Supported manifest task families

For each task independently, the script loads `.npy` input or inspects `.npz` keys and selects the operation from its description:

- scalar or axis-qualified reductions: sum, mean, minimum, maximum, product, squared sum/mean, and L2 norm;
- binary logistic cross-entropy gradient with respect to the supplied weight vector;
- batched two-layer MLP evaluation, with `vmap` in the JAX branch and ReLU by default (or an activation stated in the description);
- leading-axis cumulative/running/prefix sum or product with `lax.scan` in the JAX branch.

It recognizes conventional semantic archive members (`x`, `y`, `w`, optional `b`, `w1`, `b1`, `w2`, `b2`, and optional `initial`). Ambiguous or unsupported descriptions fail rather than silently writing an unrelated result.

Each output is written atomically at its exact manifest destination. `.npy` destinations receive `np.save`; `.npz` destinations receive a single `result` member. The script reloads every output before reporting success.
