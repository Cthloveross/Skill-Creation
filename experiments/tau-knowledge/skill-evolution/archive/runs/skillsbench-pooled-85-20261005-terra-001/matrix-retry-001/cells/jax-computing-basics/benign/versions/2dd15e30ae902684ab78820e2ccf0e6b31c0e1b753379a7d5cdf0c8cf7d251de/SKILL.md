---
name: jax-manifest-numerical-tasks
description: Execute a manifest of numerical programming tasks whose descriptions specify JAX computations and whose inputs are .npy or .npz files. Use when each task has input, output, and natural-language computation requirements.
---

# JAX manifest numerical tasks

Use this Skill to complete every entry in a supplied JSON task manifest. The manifest and the arrays are the source of truth: do not infer an operation, archive member, axis, shape, dtype, or recurrence convention from filenames or from another task.

## Runtime interface

The packaged utilities use JSON on standard input and JSON on standard output.

Inspect the manifest and every input before implementing computations:

```sh
python /path/to/skill/scripts/inspect_tasks.py <<'JSON'
{"problem":"/app/problem.json"}
JSON
```

The resulting report identifies each task, resolved input/output paths, whether the input is a single `.npy` array or `.npz` archive, and array shapes/dtypes. The inspection tool exits nonzero with a JSON error when the manifest, a path, or an array format is invalid.

After creating outputs, validate their existence, loadability, and optional independently derived structural requirements:

```sh
python /path/to/skill/scripts/validate_outputs.py <<'JSON'
{"problem":"/app/problem.json","checks":{}}
JSON
```

`checks` is optional and is keyed by manifest task id. Each check may specify `shape` (a JSON list), `ndim`, `dtype`, `finite`, and, for `.npz` outputs, `npz_keys`. Populate it only with requirements derived from the current description.

## Required execution workflow

1. Read the complete manifest. Treat each task independently, including tasks sharing an input file.
2. Run the inspector. For an `.npy` input, use its sole array. For an `.npz` input, select keys only where the task description establishes their roles. Check matrix inner dimensions, batch axes, and any time axis before coding.
3. Translate each description into a small pure JAX function using `jax.numpy` (`jnp`). Keep operands as JAX arrays during computation. Use the transformation the description calls for:
   - reductions and broadcasts: write axes and `keepdims` explicitly;
   - per-example computation: use `jax.vmap` with explicit `in_axes`/`out_axes`;
   - derivatives: make the differentiated function scalar-valued, then use `jax.grad`, `jax.value_and_grad`, `jax.jacrev`, or `jax.jacfwd` as required;
   - sequential recurrence: use `jax.lax.scan`, define the carry and emitted result separately, and preserve the stated temporal order;
   - compilation: apply `jax.jit` to the numerical function only after its static arguments and output structure are clear.
4. Implement all computations in a solver in the task workspace. It may import `scripts/task_runtime.py` from this package for safe loading and saving. Do not use NumPy to replace the requested JAX numerical operation; NumPy conversion is appropriate only at I/O boundaries.
5. Materialize the JAX result with `jax.device_get`, convert it to a NumPy-compatible numeric array, and save it at the exact `output` path. `task_runtime.save_result` handles `.npy` and `.npz` destinations without silently changing extensions.
6. Validate all outputs with `validate_outputs.py`. Also perform task-specific checks derivable from the description: output rank/shape, requested dtype, expected archive keys, and numerical invariants such as finite values only when finiteness is mathematically required. A successful JIT trace is not validation.

## Solver I/O pattern

A solver should resolve paths against the manifest directory and use the helpers as follows:

```python
import sys
sys.path.insert(0, "/path/to/skill/scripts")
import task_runtime
import jax
import jax.numpy as jnp

problem_path = "/app/problem.json"
task_runtime.load_manifest(problem_path)  # validates task fields
payload = task_runtime.load_input("/app/data/input.npy")
x = jnp.asarray(payload["__array__"])  # for a .npy input
# Define and run the JAX computation specified by this task description.
y = jnp.asarray(x)  # replace with that computation
task_runtime.save_result("/app/requested-output.npy", jax.device_get(y))
```

For an archive, `payload` maps archive keys to NumPy arrays. Do not assume a conventional key such as `x`, `weights`, or `labels`; select the keys after reading the current description and inspection report. For a requested `.npz` result, pass a mapping of output member names to arrays to `save_result`; for `.npy`, pass one array.

## Failure handling

Fail the task visibly rather than guessing if a manifest entry lacks a string `input`, `output`, or `description`; an input is not `.npy`/`.npz`; an archive key required by the description is absent; matrix dimensions are incompatible; or the requested output format cannot represent the computed result. Preserve input dtype unless the description explicitly requires a conversion. Do not enable 64-bit JAX globally or add numerical stabilization terms unless the task specification calls for them.
