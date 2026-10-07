---
name: manifest-jax-numerical-output-runner
description: Run every numerical task in a runtime problem.json manifest, using JAX for reductions, logistic gradients, vectorized MLP evaluation, and scans, while reliably saving one validated NumPy-compatible result at each declared output path.
---

# Manifest JAX numerical output runner

Use this Skill for an `/app` task containing `/app/problem.json` plus `.npy` or `.npz` numerical inputs. The manifest is authoritative: do not infer output names from task IDs and do not edit the manifest or any supplied input.

## Required execution

The packaged runner is not necessarily located inside `/app`. Invoke the **packaged** `scripts/run_manifest.py` file (by its actual Skill-package path or via the runtime's packaged-script facility) and point it at the app manifest:

```sh
cd /app
python /path/to/this-skill/scripts/run_manifest.py <<'JSON'
{"problem":"/app/problem.json","backend":"auto"}
JSON
```

The runner reads every task at runtime, resolves relative paths relative to the manifest directory, and writes each result to its exact declared destination. Thus a manifest output such as `basic_reduce.npy` is written as `/app/basic_reduce.npy`.

`backend: "auto"` is the recommended mode. It first performs the task set in a separate, thread-constrained JAX worker. If a restricted CPU runtime aborts while initializing or executing JAX, its parent process remains alive and repeats the mathematically equivalent array computation with the NumPy-compatible safety backend, so required outputs are still produced. On normal JAX installations, the successful result is computed by JAX. Use `"backend":"jax"` to require JAX and expose any JAX failure; use `"backend":"numpy"` only when an execution environment has already established that JAX cannot run.

Do not report completion merely because the command was launched. A successful JSON response has `"ok": true` and lists every manifest task. The runner reloads each output with `allow_pickle=False`; any failure response means outputs have not been fully validated.

## Interface

The script consumes one JSON object on stdin:

```json
{"problem":"/app/problem.json", "backend":"auto"}
```

- `problem` is optional and defaults to `/app/problem.json`.
- `backend` is optional and may be `auto`, `jax`, or `numpy`.
- Success output is `{"ok":true,"backend":string,"outputs":[...]}`. Each output item records its task ID, absolute output path, shape, and dtype.
- Failure output is `{"ok":false,"error":string}` and the program exits nonzero.

Inputs may be one-array `.npy` files or named `.npz` archives. The runner inspects archive keys and matches semantic names at runtime. It supports the task patterns represented by this task family:

1. JAX NumPy reductions, including sum, mean, min, max, product, sum/mean of squares, and L2 norm, with explicitly described axes.
2. Binary logistic/sigmoid cross-entropy gradients with respect to supplied weights, using `jax.grad` in the JAX backend.
3. Batched two-layer MLP forward evaluation, using a one-example function plus `jax.vmap` in the JAX backend.
4. Cumulative/running sums or products over a leading sequence axis, using `jax.lax.scan` in the JAX backend.

The script creates needed output directories, uses `np.save` for `.npy` outputs (or a one-array `result` archive for `.npz`), materializes device arrays before saving, and checks that outputs are nonempty finite numeric arrays. It rejects unknown operations, ambiguous archive members, incompatible dimensions, duplicate outputs, and attempts to overwrite inputs rather than fabricating placeholder data.
