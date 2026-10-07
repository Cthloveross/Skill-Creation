# Mapping task descriptions to JAX computations

Discover the computation from the task's `description` and the runtime structure
of its input file. Never infer semantics from the filename alone.

## Inspection checklist (run before trusting any handler)
- Print the full `description` for every task.
- For `.npy`: shape and dtype of the single array.
- For `.npz`: the member keys (`obj.files`) and each member's shape/dtype.
- Decide which member is the operand(s) vs. parameters vs. labels.

## Common operation families
- **Reductions**: sum / mean / prod / max / min / std / var / argmax / argmin.
  Determine the axis from the wording ("along axis 0", "per row", "per column",
  "over the last dimension", or whole-array if none). A reduction removes the
  named axis.
- **Broadcasting / elementwise**: sigmoid, relu, softmax, scaling, normalization.
  Softmax needs the correct axis.
- **Vectorized mapping (`jax.vmap`)**: apply a per-example function across a batch
  axis, e.g. an MLP forward pass over N input rows. Compose linear layers
  (`x @ W + b`) with ReLU between hidden layers.
- **Automatic differentiation (`jax.grad`)**: `grad` needs a scalar output. For a
  logistic-regression loss, build mean binary cross-entropy of
  `sigmoid(X @ w + b)` against labels `y`, then differentiate w.r.t. the
  parameters requested (w, and b if present). Confirm whether the task wants the
  gradient, the loss value, or the predictions.
- **Structured scan (`jax.lax.scan`)**: a recurrence with an explicit carry and a
  stacked per-step output. Identify the time axis (often axis 0, time-major), the
  initial carry, and the exact update rule from the description.
- **JIT (`jax.jit`)**: compile a function for the observed shapes/dtypes. Produces
  the same numerical result; use it when speed is requested.
- **Matrix multiply**: inner dimensions must agree; check shapes at runtime.

## Correctness notes
- JAX arrays are immutable; use functional updates and array ops, not in-place
  mutation or value-dependent Python control flow inside traced/scanned/vmapped
  functions.
- Materialize results with `np.asarray(...)` before saving so no unevaluated
  device array remains.
- Save to the EXACT `output` path. Use `np.save` for a single array and
  `np.savez` only when the description/output explicitly expects multiple named
  arrays.
- Validate output shape/dtype against what the description implies, and compare a
  small case to a plain-NumPy formula when feasible. Successful compilation or a
  written file is not proof of correct axes, keys, or recurrence semantics.

## When a description is not matched
The solver reports such a task as `unhandled` instead of writing a wrong file.
Implement the computation in `scripts/handlers.py` (keeping it generic: read
keys/axes/shapes at runtime, no hardcoded instance answers), then rerun the
solver and the verifier.
