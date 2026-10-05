---
name: jax-manifest-output-producer
description: Produce every NumPy-array output declared by a runtime problem.json manifest using JAX. Use for numerical manifests with .npy or .npz inputs and descriptions covering elementary reductions, logistic-loss gradients, MLP forward evaluation, or scan-based sequence recurrences.
---

# JAX manifest output producer

This Skill is designed to **materialize all declared outputs**, rather than only inspect a manifest or prepare a plan. Inputs, archive member names, dimensions, dtypes, descriptions, and destinations are runtime facts and must not be assumed from filenames.

## Required execution

From `/app`, run the complete producer after the public files have been copied:

```sh
python scripts/run_manifest.py --manifest /app/problem.json
```

The script reads every manifest item, loads its declared `.npy` or `.npz` input, performs its JAX computation, and writes a single materialized numeric NumPy array to the item's exact `output` path. It validates that every declared destination exists, is a readable single-array file, is nonempty, numeric, and finite. Do not stop after metadata inspection or an exploratory command: the producer must finish successfully before the task is complete.

For a machine-readable inventory before execution, use:

```sh
echo '{"problem_path":"/app/problem.json"}' | python scripts/inspect_inputs.py
```

## Computations recognized by the producer

The dispatcher uses each task description, not its task id, and discovers archive roles from member names and compatible shapes.

- Plain `.npy` tasks: row/column/global `mean`, `sum`, sum of squares, Euclidean norm, elementwise square, cumulative sum, and one-dimensional softmax.
- Logistic tasks: stable binary cross-entropy and its JAX gradient with respect to the described weight parameter. Features, labels, weights, and an optional bias are found from archive names and dimensions.
- MLP tasks: ordered dense layers with compatible matrix orientations, biases, and stated ReLU/tanh/sigmoid activations.
- Sequence tasks: `jax.lax.scan` for cumulative sums and standard affine recurrent cells, returning final carry when requested and scan outputs otherwise.

Descriptions outside these supported forms cause a loud failure rather than a fabricated result. In that case, inspect the reported manifest description and archive schema, add a small JAX implementation in `scripts/run_manifest.py`, and rerun the complete producer. Preserve the exact output-writing and validation behavior.

## Script interfaces

- `scripts/run_manifest.py [--manifest PATH]` reads the manifest from the argument (default `/app/problem.json`) and emits one JSON report on stdout. It has no stdin schema.
- `scripts/inspect_inputs.py` reads `{"problem_path":"/app/problem.json"}` from stdin and writes JSON metadata to stdout.
- `scripts/validate_outputs.py` reads `{"manifest_path":"/app/problem.json"}` from stdin and writes JSON metadata for all manifest outputs to stdout.

All result arrays are computed through JAX, converted only at the save boundary, and saved through an already-open file at the precise manifest path. This also ensures that a nonstandard suffix cannot cause NumPy to silently append `.npy` to the declared filename.
