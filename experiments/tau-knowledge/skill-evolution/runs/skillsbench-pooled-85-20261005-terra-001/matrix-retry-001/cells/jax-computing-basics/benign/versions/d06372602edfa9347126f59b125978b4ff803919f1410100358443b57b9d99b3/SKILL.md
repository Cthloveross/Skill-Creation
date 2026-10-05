---
name: jax-runtime-manifest-solver
description: Execute all numerical tasks declared by a runtime problem.json manifest using JAX, loading .npy/.npz inputs and writing one portable numeric result to every exact manifest output path.
---

# JAX runtime manifest solver

Use this Skill for a task environment containing `/app/problem.json` and manifest-declared numerical input/output files. The manifest is the sole source of truth: do not infer operations from task IDs, input filenames, or examples from another task.

This Skill must be **executed**, not merely read. From `/app`, immediately run the packaged entrypoint with the manifest path:

```sh
python /path/to/skill/scripts/run_manifest.py <<'JSON'
{"problem":"/app/problem.json"}
JSON
```

The script reads every task at runtime, loads each declared `.npy` or `.npz` input with `allow_pickle=False`, performs recognized reductions, logistic-loss gradients, vectorized MLP forwards, and scan computations with JAX, materializes the device result, and writes every result to its declared destination. Relative paths are resolved relative to `problem.json`; therefore an output such as `basic_reduce.npy` is written as `/app/basic_reduce.npy`.

The process exits nonzero for an unsupported or ambiguous computation rather than writing a guessed result. In that case, inspect the current manifest and archive keys, write the small task-specific computation exactly as described using JAX, and use the same output rules: save one nonempty finite numeric ndarray at each exact destination. Do not modify `/app/problem.json` or anything under `/app/data`.

## Entrypoint interface

`scripts/run_manifest.py` reads JSON from stdin and emits a JSON report on stdout.

- Input: `{"problem":"/app/problem.json"}`. `problem` is optional and defaults to `/app/problem.json`.
- Success output: `{"ok":true,"outputs":[{"id":...,"output":...,"shape":[...],"dtype":...}]}`.
- Failure output: `{"ok":false,"error":"..."}` and a nonzero exit status.

After it writes all tasks, the entrypoint reloads every output using NumPy with pickle disabled and verifies that it is exactly one nonempty, finite, portable numeric array. It creates necessary parent output directories but never writes to declared input paths.

## Computation rules

1. Inspect array names, shapes, and dtypes before selecting archive members. A `.npy` file supplies one array; `.npz` members are selected by semantically named keys required by the current description.
2. Implement the stated operation with `jax.numpy`, `jax.grad`, `jax.vmap`, or `jax.lax.scan`, as applicable. Conversion through `jax.device_get` is only for serialization.
3. Make reduction axes, loss normalization, activations, matrix orientation, and scan carry explicit. Reject incompatible dimensions and unknown key layouts.
4. Save `.npy` outputs with `numpy.save`; for a manifest `.npz` output, save an archive containing exactly one key, `result`.
5. Treat a failure report as incomplete work: no task is complete until every manifest-declared output exists and can be loaded by `numpy.load(..., allow_pickle=False)`.
