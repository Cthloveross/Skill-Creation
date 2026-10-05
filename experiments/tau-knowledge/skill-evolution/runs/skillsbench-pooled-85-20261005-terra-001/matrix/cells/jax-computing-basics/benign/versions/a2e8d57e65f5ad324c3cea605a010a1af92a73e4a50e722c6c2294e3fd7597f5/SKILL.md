---
name: jax-manifest-task-executor
description: Materialize every output required by a runtime problem.json manifest using JAX. Use for /app task bundles whose inputs are NumPy .npy or .npz files and whose descriptions request reductions, logistic objectives or gradients, dense MLP evaluation, or JAX scan recurrences.
---

# JAX manifest task executor

This Skill is not complete when its source files have merely been written or inspected. The
executor must **run the packaged producer** so it writes every manifest-declared result into
`/app` before reporting completion.

## Mandatory execution

Use the Skill runtime's packaged-script execution facility to invoke:

- `scripts/run_manifest.py` with JSON input `{"manifest_path":"/app/problem.json"}`
- then `scripts/validate_outputs.py` with the same JSON input.

For example, when the runtime provides `run_skill_script`, call it with
`relative_path="scripts/run_manifest.py"` and the input object above. This is preferred to
copying the script or guessing the Skill package's filesystem location. The producer resolves
all relative paths against `/app/problem.json`, so it writes paths such as
`/app/basic_reduce.npy` directly.

If only a shell is available, execute the packaged `scripts/run_manifest.py` by its actual
package path while the working directory is `/app`; do not leave `<skill-root>` as a literal
placeholder. Give the JSON request on stdin. Run the validator after the producer returns.

Do not finish until the validator reports one output per manifest entry. In particular, a task
described as computing the mean of each row is evaluated with `jnp.mean(x, axis=1)` and saved at
its exact manifest `output` location.

## Producer contract

`run_manifest.py` reads one JSON object from stdin:

```json
{"manifest_path": "/app/problem.json"}
```

`manifest_path` is optional and defaults to `/app/problem.json`. The script reads the live
manifest and live input data at execution time; it never assumes task IDs, archive keys, shapes,
or task count. Its successful stdout is:

```json
{"written":[{"id":"...","path":"/app/...","shape":[...],"dtype":"..."}]}
```

For each task it loads the declared `.npy` or every member of the declared `.npz`, selects
operands by their semantic key names and compatible dimensions, performs the computation with
JAX, materializes the device value, and saves a single standard numeric `.npy` array at the
exact declared destination. Parent directories are created if necessary. Completed tasks remain
saved even if a later task reports an unsupported description or incompatible archive schema.

The supported description families are explicit elementary reductions/transforms, binary
logistic loss or its parameter gradient, dense multilayer perceptrons, and scan/recurrent state
updates. For an unsupported or ambiguous task, the producer fails with the description, keys,
and shapes rather than creating a placeholder result. Correct the computation based on the
manifest wording and archive schema, then execute the whole producer again.

`validate_outputs.py` has the same input schema and emits `{"outputs":[...]}`. It verifies that
each manifest destination exists and is a readable, nonempty, finite, numeric, non-object,
single-array `.npy` file. It is format validation, not a substitute for following each task
description.
