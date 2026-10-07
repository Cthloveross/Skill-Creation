---
name: jax-manifest-output-producer
description: Execute manifest-defined JAX numerical tasks in /app and materialize a valid single-array .npy output for every problem.json entry. Use for task bundles containing .npy/.npz inputs and descriptions of reductions, logistic regression, dense MLPs, or scan/recurrent computations.
---

# JAX manifest output producer

This Skill is complete only after its producer has actually run and every declared output
exists in `/app`. Do not merely inspect the manifest or create source code.

## Required execution

From `/app`, execute the packaged runner (with the Skill package root substituted for
`<skill-root>` if scripts are not copied into `/app/scripts`):

```sh
cd /app
printf '%s\n' '{"manifest_path":"/app/problem.json"}' | python <skill-root>/scripts/run_manifest.py
printf '%s\n' '{"manifest_path":"/app/problem.json"}' | python <skill-root>/scripts/validate_outputs.py
```

If the packaged scripts are available relative to the current directory, the first command is
instead:

```sh
printf '%s\n' '{"manifest_path":"/app/problem.json"}' | python scripts/run_manifest.py
```

A completion response must not be given until the first command has returned successfully and
the validation report lists one output for every manifest task. In particular, the task
`Given array x, compute mean of each row.` is computed as `jnp.mean(x, axis=1)` and saved at
its manifest-declared output path (normally `/app/basic_reduce.npy`).

## What the runner does

1. Reads the current `problem.json`, rather than assuming task count, paths, archive keys, or
   shapes.
2. Loads `.npy` as one array and inspects every `.npz` member at runtime.
3. Uses JAX operations for explicit reductions, logistic loss/gradients, dense MLP evaluation,
   and `jax.lax.scan` sequence computations.
4. Resolves relative input/output names relative to the manifest location, creates output
   parent directories, materializes results, and writes each as exactly one numeric NumPy array
   using `np.save`.
5. Rejects object, empty, nonnumeric, NaN, and infinite outputs immediately.

The runner receives one JSON object on stdin:

```json
{"manifest_path": "/app/problem.json"}
```

`manifest_path` is optional and defaults to `/app/problem.json`. It emits a JSON object with a
`written` list containing the task id, exact destination, shape, and dtype. A nonzero exit is a
real incomplete-task condition: read its diagnostic, correct the manifest-description dispatch
or schema handling as needed, rerun the *whole* manifest, and then rerun validation. Never
write placeholder constants merely to satisfy a destination.

`validate_outputs.py` uses the same stdin schema and reports `outputs`. It checks that every
manifest destination is a readable, nonempty, finite numeric single-array file (not an NPZ
archive or object array).
