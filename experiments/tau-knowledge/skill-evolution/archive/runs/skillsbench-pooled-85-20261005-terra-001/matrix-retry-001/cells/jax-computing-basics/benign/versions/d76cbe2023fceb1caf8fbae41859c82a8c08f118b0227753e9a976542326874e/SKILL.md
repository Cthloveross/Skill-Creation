---
name: jax-manifest-numerical-tasks
description: Complete a runtime JSON manifest of JAX numerical tasks with .npy or .npz inputs and manifest-declared NumPy output paths. Use when task descriptions call for reductions, gradients, vectorized neural computations, scans, or related JAX array operations.
---

# JAX manifest numerical tasks

The runtime `/app/problem.json` is the source of truth. Read every entry and create **every** declared output; do not use task IDs, filenames, or another task's arrays to infer an operation. Never modify `/app/problem.json` or files under `/app/data`.

## Required execution

Run from `/app`. First inspect the current manifest and its input arrays:

```sh
python /path/to/skill/scripts/inspect_tasks.py <<'JSON'
{"problem":"/app/problem.json"}
JSON
```

Implement the operation stated by each current `description` with JAX (`jax.numpy`, `jax.grad`, `jax.vmap`, `jax.lax.scan`, or `jax.jit` as appropriate). The packaged `solve_manifest.py` is an executable driver for common explicitly described reductions, logistic-loss gradients, MLP forwards, and cumulative scans. It reads the manifest at runtime and writes every result at its exact declared path:

```sh
python /path/to/skill/scripts/solve_manifest.py <<'JSON'
{"problem":"/app/problem.json"}
JSON
```

The driver intentionally rejects an ambiguous description rather than fabricating a result. If that happens, write a small task-specific JAX solver after using the inspection report, then use `task_runtime.save_result` for each output. Do not replace a requested JAX computation with NumPy; conversion to NumPy is only for saving.

For each task:

1. Resolve `input` and `output` relative to the manifest directory (unless absolute).
2. For `.npy`, use the sole array. For `.npz`, inspect keys, shapes, and dtypes and choose members only as established by the task description.
3. Express axes, broadcasting, activation, reduction normalization, parameter order, and recurrence carry explicitly. Check matrix inner dimensions and time/batch axes before running.
4. Materialize the JAX result using `jax.device_get`, save one numeric non-object array at the exact output path, and preserve the requested file extension.
5. Validate all manifest entries after writing:

```sh
python /path/to/skill/scripts/validate_outputs.py <<'JSON'
{"problem":"/app/problem.json","checks":{}}
JSON
```

`validate_outputs.py` takes JSON on stdin and emits JSON on stdout. `checks` is optional and keyed by task ID; checks can include `shape`, `ndim`, `dtype`, `finite`, and `npz_keys`. Supply only constraints independently implied by the present description.

## Packaged script interfaces

- `inspect_tasks.py`: stdin `{"problem": "path"}`; prints task descriptions, resolved paths, archive keys, shapes, and dtypes.
- `solve_manifest.py`: stdin `{"problem": "path"}`; performs only unambiguously recognized JAX computations and prints `{"ok", "outputs"}`. It exits nonzero without writing a guessed output for unsupported wording.
- `validate_outputs.py`: stdin `{"problem": "path", "checks": {...}}`; verifies existence and NumPy loadability of each manifest output.

A solver may import `task_runtime` from `scripts/`. `load_input` returns `{"__array__": array}` for `.npy`, or a key-to-array mapping for `.npz`; `save_result(path, value)` saves a single `.npy` result or a named mapping for `.npz`.

Do not globally enable JAX x64, alter input files, silently add numerical stabilization, or guess missing archive keys. Fail visibly for malformed manifests, incompatible dimensions, unsupported formats, or computation requirements that cannot be determined from the description.
