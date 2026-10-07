---
name: jax-manifest-task-runner
description: Execute a runtime JSON manifest of numerical tasks using JAX. Use when each task names an input .npy/.npz file, describes a numerical computation, and names an output path that must receive a NumPy-compatible result.
---

# JAX manifest task runner

Use this Skill to complete every task in the supplied manifest, not merely the first one. The manifest and input archives are runtime data: inspect their descriptions, archive keys, shapes, and dtypes before deciding which operation is required.

## Workflow

1. Inspect the actual manifest and input metadata. This is a runnable, read-only call:

   ```sh
   echo '{"problem_path":"/app/problem.json"}' | python scripts/inspect_inputs.py
   ```

   Its JSON output includes every task's id, description, input path, output path, and input array metadata. Do not infer keys or dimensions from filenames.
2. Translate each description exactly into a declarative expression in the schema documented in `scripts/execute_plan.py`. Use JAX operations for numerical computation. In particular, use `grad`/`value_and_grad` for derivatives, `vmap` for independently mapped examples, `scan` for stated recurrences, and `jit` only when it preserves the stated semantics.
3. Put one plan entry per manifest task in a JSON plan and run `execute_plan.py`. It loads the manifest-selected data, evaluates expressions with JAX, materializes results, and writes each result to that task's exact manifest output path. It rejects omitted, duplicate, or unknown task ids rather than silently producing partial output.
4. Validate all output files after execution. Supply required shape and/or dtype only when those are stated by the task; otherwise validation still checks existence, NumPy readability, and finite floating values.

   ```sh
   echo '{"path":"/app/result.npy"}' | python scripts/validate_output.py
   ```

## Important semantic checks

- Preserve the described reduction axes and whether reductions are sums, means, or totals. Convert JSON axis lists to tuples; scalar reductions intentionally have shape `[]`.
- Keep the input dtype unless the description explicitly requests a cast. The executor enables JAX x64 before importing `jax.numpy`, avoiding unintended float64 truncation on CPU.
- For `.npz` inputs, references in expressions are the archive keys reported by the inspector. For a single `.npy` input, use `input` (and its filename stem alias) as the reference.
- A matrix layer is normally `x @ W + b`; transpose an operand only if the runtime description and inspected shapes require it. Check inner dimensions before executing.
- For logistic losses, use numerically stable `softplus(logits) - labels * logits` rather than `log(sigmoid(logits))` when equivalent. Gradients must be taken with respect to exactly the parameter named in the description.
- A scan body must return the next carry and the per-step output separately. Confirm whether the requested result is the final carry, all scan outputs, or both.
- JAX arrays are immutable. Do not implement a recurrence with mutation or value-dependent Python control flow.

If a description requires an operation absent from the declarative evaluator, write a small JAX-only extension in `jax_task_helpers.py` (with explicit inputs and shape checks), then invoke it from the plan evaluator. Do not substitute NumPy computation for JAX or guess an unsupported operation. Outputs must be standard `.npy` or `.npz` files at the exact paths specified by the manifest.

## Executor interfaces

- `inspect_inputs.py` stdin: `{"problem_path": "/app/problem.json"}`; stdout: task and array metadata JSON.
- `execute_plan.py` stdin: `{"manifest_path": "/app/problem.json", "plan": [...]}`; stdout: JSON report of written outputs. A plan entry is `{"id": <manifest id>, "expr": <expression>, "expected_shape": [...], "expected_dtype": "...", "archive_key": "result"}`. The two expected fields and `archive_key` are optional.
- `validate_output.py` stdin: `{"path": "...", "expected_shape": [...], "expected_dtype": "...", "require_finite": true}`; stdout: JSON metadata or an error.

All scripts receive JSON on stdin and emit JSON on stdout. They fail loudly on malformed manifests, missing files/keys, invalid dimensions, unsupported operations, or validation failures.
