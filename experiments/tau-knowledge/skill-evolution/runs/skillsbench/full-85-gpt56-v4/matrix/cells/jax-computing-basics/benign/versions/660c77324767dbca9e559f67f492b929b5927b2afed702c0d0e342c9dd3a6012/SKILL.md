---
name: jax-task-bundle-executor
description: Complete a runtime bundle of numerical programming tasks described in problem.json by inspecting .npy/.npz inputs, implementing each stated computation with JAX, and writing verified NumPy-compatible output files. Use when task descriptions, archive schemas, output paths, and numerical operations are supplied at execution time.
---

# JAX task bundle executor

Use this Skill to solve every entry in the runtime `problem.json`; do not infer the intended computation from input filenames or this Skill. The manifest descriptions are authoritative.

## Runtime procedure

1. Read and parse `/app/problem.json` (or the supplied manifest path). Record every task's `id`, `description`, `input`, and `output`. Treat output paths as relative to the task work directory unless they are absolute.
2. Inspect every distinct input before coding:
   ```sh
   python /app/environment/skills/current/scripts/inventory.py <<'JSON'
   {"paths":["/app/data/example.npy","/app/data/example.npz"]}
   JSON
   ```
   For `.npz`, use the reported keys, shapes, and dtypes rather than guessing key names. Understand which axes are batch, feature, class, hidden-state, or time axes from the description and inspected shapes.
3. Create a task-specific `/app/solve.py` which imports `jax`, `jax.numpy as jnp`, and `numpy as np`. It must load each file once, perform the requested numerical computation through JAX array operations, and save one result for each manifest output. Do not use NumPy as the computational substitute for a requested JAX operation.
4. Choose the JAX construct that matches the wording:
   - Elementwise arithmetic, reductions, dot products, softmax, sigmoid, and indexing: `jax.numpy`.
   - A computation independently applied to each example: write a one-example function and use `jax.vmap` over precisely the described batch axes.
   - A derivative: make the differentiated function return a scalar loss; use `jax.grad`, with `argnums` only for requested differentiated arguments. For per-example gradients, combine the scalar one-example loss with `vmap(grad(...))`.
   - A time/state recurrence: express `(carry, item) -> (new_carry, output)` and use `jax.lax.scan`; pay close attention to whether outputs are pre-update or post-update states.
   - A requested compiled calculation: apply `jax.jit` around an array-only function. Do not use value-dependent Python branches inside a jitted function.
5. Convert device results with `np.asarray(result)` before saving. Ensure parent output directories exist. Use `np.save(path, array)` for a single required array; only use `np.savez` when the description explicitly requires named multiple outputs. Calling `block_until_ready()` before conversion is appropriate for a JAX result.
6. Run the solver from `/app` and validate each declared output with the packaged validator:
   ```sh
   cd /app && python solve.py
   python /app/environment/skills/current/scripts/validate_outputs.py <<'JSON'
   {"problem":"/app/problem.json","root":"/app"}
   JSON
   ```
   The validator checks that each output exists, is a loadable `.npy`/`.npz` artifact, and reports its schema. It cannot prove task semantics: manually compare output shape, dtype, and a small direct calculation against the exact description.

## Implementation requirements and common safeguards

- Preserve the requested output dtype where it is stated. Otherwise avoid accidental integer arithmetic and use the input floating dtype unless JAX configuration or the task requires otherwise.
- For classification operations, distinguish `axis=-1` (per example class dimension) from a batch reduction. For matrix products, assert expected inner dimensions before computing.
- Stable logistic/softmax calculations should use JAX primitives such as `jax.nn.sigmoid`, `jax.nn.log_sigmoid`, `jax.nn.softmax`, or `jax.scipy.special.logsumexp` when that matches the specified formula.
- A `.npz` object is a keyed archive, not an array. Load it in a context manager and explicitly extract only the keys required by the description.
- Do not overwrite one task's output with another task's result, skip a manifest entry, hardcode inspected values, or alter `problem.json` or inputs.
- If a description is mathematically ambiguous, first use its explicit formulas, axis wording, named archive fields, and requested output shape. If these still do not determine an operation, report the ambiguity rather than silently choosing an unrelated computation.

## Packaged script interfaces

`inventory.py` receives JSON on stdin: `{"paths": ["path", ...]}`. It emits JSON describing each readable `.npy` or `.npz` input, including archive keys and each member's shape/dtype.

`validate_outputs.py` receives JSON on stdin: `{"problem":"path/to/problem.json", "root":"base-directory"}`. It emits JSON with `ok`, any missing/unreadable outputs, and schemas for loadable outputs. A nonzero exit means required files are missing, unreadable, or an unsupported output extension was requested.
