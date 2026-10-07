---
name: jax-manifest-task-executor
description: Execute every numerical task declared in an /app/problem.json manifest with JAX, loading .npy or .npz inputs and saving one validated numeric NumPy-compatible result at each exact declared output path.
---

# JAX manifest task executor

Use this Skill for the supplied `/app` numerical-task environment. The mandatory completion condition is that **every** `output` path in `/app/problem.json` exists as a readable NumPy array after execution. Do not edit `/app/problem.json` or files in `/app/data`.

## Execute

Run the packaged script from `/app` and provide its JSON request on standard input. The script path must be the actual installed path of this Skill package.

```sh
cd /app
python /path/to/skill/scripts/run_manifest.py <<'JSON'
{"problem":"/app/problem.json"}
JSON
```

If the runtime offers packaged-script execution, invoke `scripts/run_manifest.py` with:

```json
{"problem":"/app/problem.json"}
```

Do not stop after inspecting the manifest or writing JAX source. Run the script. Its successful stdout is a JSON object with `"ok": true` and one entry in `outputs` for every manifest task. A nonzero exit or `"ok": false` means the task has not been completed and must be corrected before reporting completion.

## Script interface

`run_manifest.py` consumes exactly one JSON object from stdin:

```json
{"problem":"/app/problem.json"}
```

`problem` is optional and defaults to `/app/problem.json`. Relative input and output paths are resolved relative to that manifest's directory. The script:

1. validates the manifest and prevents an output from replacing a declared input;
2. inspects `.npy` arrays and `.npz` archive members at runtime;
3. selects the JAX operation indicated independently by each task description;
4. materializes each JAX result, writes it to the exact declared path, and reloads it with `allow_pickle=False`;
5. rejects empty, object-typed, non-numeric, non-finite floating, missing, or ambiguous results.

Supported task-family operations are reductions (including axis-qualified sum, mean, extrema, product, squared reductions, and L2 norm), logistic binary-cross-entropy gradients with respect to weights, batched two-layer MLP evaluation through `jax.vmap`, and leading-axis cumulative sum/product through `jax.lax.scan`. Archive members are selected by semantic names such as `x`, `y`, `w`, `w1`, `b1`, `w2`, and `b2`; their shapes are checked before computation.

The program sets conservative CPU/JAX thread environment defaults before importing JAX, disables JIT compilation for reliability in constrained single-CPU containers, but still performs the numerical operations using JAX APIs. Results are saved as `.npy` when the declared path ends in `.npy`; a declared `.npz` output receives an unambiguous single member named `result`.
