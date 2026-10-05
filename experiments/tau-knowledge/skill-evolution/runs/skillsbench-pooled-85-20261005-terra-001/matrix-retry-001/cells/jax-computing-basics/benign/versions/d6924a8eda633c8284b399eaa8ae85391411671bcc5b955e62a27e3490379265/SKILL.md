---
name: execute-jax-manifest-tasks
description: Execute a runtime problem.json manifest of JAX numerical tasks, including reductions, logistic-loss gradients, batched two-layer MLP evaluation, and scan recurrences. Use when each manifest entry supplies an input array/archive, natural-language computation description, and exact output destination.
---

# Execute manifest-declared JAX tasks

This Skill performs the task only when its runner is invoked. Invoke the packaged script runtime **once** before claiming completion:

```json
{"problem":"/app/problem.json"}
```

using `scripts/solve_manifest.py`. Do not merely inspect the script or manifest.

The runner reads the live manifest, processes every entry independently, and writes a numerical result at every exact `output` path. It never writes to the manifest or to an input path. Its final JSON response is either:

```json
{"ok":true,"backend":"jax","outputs":[{"id":"...","output":"...","shape":[...],"dtype":"..."}]}
```

or a nonzero failure response. A successful `outputs` list must contain every manifest task. The normal implementation runs the calculations in an isolated, single-CPU JAX worker. Isolation prevents an accelerator/XLA abort from preventing output generation; only if that worker exits abnormally does the runner use mathematically equivalent NumPy array operations as a runtime-resilience fallback and report `"backend":"numpy-fallback"`.

## Runtime interface

`scripts/solve_manifest.py` reads one JSON object from stdin:

- `problem` — optional absolute or relative path to the manifest; defaults to `/app/problem.json`.

It emits one JSON object on stdout. It accepts `.npy` and `.npz` inputs with `allow_pickle=False`, examines archive keys at runtime, creates needed output parent directories, writes atomically, and reloads every output with `numpy.load(..., allow_pickle=False)`.

## Task interpretation

The runner selects the operation from each description rather than task ordering: reductions honor mentioned axes; gradient tasks compute the binary-logistic cross-entropy gradient with respect to weights; MLP tasks apply a per-example two-affine-layer network with `vmap`; and scan tasks return running sum or product states. Inputs must have keys and compatible shapes required by the described operation. An unsupported description or incompatible archive fails visibly rather than overwriting inputs or emitting a placeholder.

After the runner succeeds, retain its produced output files at the manifest-declared destinations. Do not rename them and do not modify `/app/problem.json` or files under `/app/data`.
