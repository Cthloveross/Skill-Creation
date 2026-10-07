---
name: jax-computing-basics-solver
description: >-
  Solve a batch of small JAX programming tasks declared in a problem.json
  manifest. Each task names an input array file (.npy or .npz), a natural-language
  description of a computation (reductions, broadcasting, vmap batching, grad,
  scan/recurrence, jit, matrix ops, logistic/MLP forward passes, etc.), and an
  exact output path. Use this Skill when a task hands you a problem.json plus data
  files and asks you to compute and save each result in a NumPy-compatible format.
  The Skill inspects every task and data file at runtime, implements the described
  computation with JAX, materializes device arrays, and writes each output to the
  exact path from the manifest.
---

# JAX computing-basics solver

## When to use

The public task supplies `problem.json` (a JSON list of task objects) and one or
more data files. Every task object has:

- `id`: unique problem id
- `description`: natural-language description of the computation
- `input`: input data path (e.g. `data/x.npy` or `data/mlp.npz`)
- `output`: destination path for the result (e.g. `basic_reduce.npy`)

Your job: for each task, load `input`, perform exactly the computation described,
and save the result to `output` in a format `numpy.load` can read.

**The exact descriptions, archive keys, shapes, and expected operations are NOT
known in advance.** They must be discovered at runtime. Do not assume the
meaning of a file from its name alone — always inspect it.

## Workflow

1. **Inspect first.** Run `scripts/inspect.py` to dump every task's full
   description and the structure (keys, shapes, dtypes, small previews) of each
   referenced input file. Read the descriptions carefully before writing or
   trusting any computation.

   ```bash
   cd /app
   echo '{"problem": "/app/problem.json", "root": "/app"}' | python3 /app/environment/skills/current/scripts/inspect.py
   ```

2. **Map each description to a JAX computation.** Use the methodology in
   `references/jax_patterns.md`. The transform to use (array reduction,
   broadcasting, `vmap`, `grad`, `lax.scan`, `jit`, matmul) follows from the
   description, not from the filename.

3. **Run the solver.** `scripts/solve.py` reads the manifest, loads each input,
   dispatches to a handler, materializes the JAX result to a NumPy array, and
   writes it to the task's `output` (`.npy` via `np.save`, `.npz` via
   `np.savez`). Output paths are resolved relative to `root` (the workdir).

   ```bash
   cd /app
   echo '{"problem": "/app/problem.json", "root": "/app"}' | python3 /app/environment/skills/current/scripts/solve.py
   ```

   `solve.py` prints a JSON report of each task: id, resolved paths, output
   shape/dtype, and the handler decision (or an explicit `error`/`unhandled`
   note). A task is only correct when its handler matches the description — the
   report is where you confirm that.

4. **Verify.** After running, re-load each produced file with `numpy.load`,
   confirm shape and dtype are sensible for the description, and where practical
   cross-check a small case against a plain-NumPy formulation (see
   `scripts/verify.py`). Compilation or a saved file alone does not prove the
   axes, archive members, or recurrence semantics are right.

## Important: dispatch is heuristic — adjust it per the real descriptions

`scripts/handlers.py` contains keyword-driven handlers for the common
computations this task family tests (reductions with an axis, elementwise /
broadcasting ops, sigmoid/logistic, binary-cross-entropy gradients via
`jax.grad`, batched forward passes via `vmap`, sequential recurrences via
`lax.scan`, matmul, cumulative ops). These are best-effort starting points.

When `inspect.py` reveals the actual wording, confirm each handler produces the
specific quantity the description asks for (which operation, which axis, which
array key, whether to return predictions vs. a gradient vs. a loss, output dtype).
If a description is not matched or is matched wrongly, edit `handlers.py` so the
computation is correct, then rerun `solve.py` and `verify.py`. Keep handlers
generic (read keys/axes/shapes at runtime); do not hardcode an instance's
numeric answers.

## Failure handling

- Missing input file or manifest: `solve.py` reports a per-task `error` and
  continues with the other tasks.
- `.npz` with unexpected keys: the handler inspects `.files` at runtime; if the
  needed role (e.g. inputs vs. weights) is ambiguous, the inspection output and
  description must disambiguate it before editing the handler.
- Unrecognized description: the task is reported as `unhandled` rather than
  silently producing a wrong file. Implement the computation and rerun.
- Always `np.asarray(...)` (materialize) JAX results before saving so the
  process does not exit with unevaluated device arrays.
