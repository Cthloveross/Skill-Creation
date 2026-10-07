---
name: jax-manifest-numerical-solver
description: Execute a runtime JAX numerical manifest in /app and materialize one valid .npy result at every manifest-declared destination. Use for problem.json tasks with .npy or .npz data, including explicit reductions, logistic objectives/gradients, dense MLP evaluation, and scan/recurrent computations.
---

# JAX manifest numerical solver

This Skill must be **executed**, not merely inspected. Once the public files are present in `/app`, run the following command from `/app`:

```sh
printf '%s\n' '{"manifest_path":"/app/problem.json"}' | python scripts/run_manifest.py
```

Do not stop after reading `problem.json`, listing archive members, or drafting code. A successful run prints a JSON report and writes a materialized, single-array NumPy file at the exact `output` path of **every** task in the manifest. In particular, a task describing a row mean must load its declared array, compute `jnp.mean(x, axis=1)`, and save that returned array at its declared destination.

## Method

1. Read `/app/problem.json`; each item must have `id`, `description`, `input`, and `output`.
2. Resolve relative input and output paths relative to the manifest directory.
3. Load `.npy` inputs as one array and `.npz` inputs by inspecting their actual keys, shapes, and dtypes at runtime.
4. Dispatch from the current description, using JAX for the computation:
   - explicit array reductions and transforms such as row/column/global mean or sum, sum of squares, norm, cumsum, square, and vector softmax;
   - stable binary logistic loss or its gradient with respect to the named weights;
   - ordered dense MLP layers, with the activation stated in the description;
   - `jax.lax.scan` cumulative or affine recurrent sequences.
5. Convert only at the output boundary and save exactly one finite numeric array with `np.save` through an open destination handle. This preserves the precise manifest filename even if it has an unusual suffix.
6. The runner validates each saved result immediately. If it reports an unsupported description or incompatible archive schema, correct the implementation for that stated operation and rerun the complete command; never substitute a guessed constant or omit an output.

## Script interface

`scripts/run_manifest.py` receives one JSON object on stdin:

```json
{"manifest_path": "/app/problem.json"}
```

`manifest_path` is optional and defaults to `/app/problem.json`. It emits JSON on stdout:

```json
{"written": [{"id": "...", "path": "...", "shape": ["..."], "dtype": "..."}]}
```

A nonzero exit and stderr diagnostic mean outputs are not yet complete. `scripts/validate_outputs.py` receives the same stdin schema and reports metadata for all declared results; run it after the producer when an independent format check is useful:

```sh
printf '%s\n' '{"manifest_path":"/app/problem.json"}' | python scripts/validate_outputs.py
```
