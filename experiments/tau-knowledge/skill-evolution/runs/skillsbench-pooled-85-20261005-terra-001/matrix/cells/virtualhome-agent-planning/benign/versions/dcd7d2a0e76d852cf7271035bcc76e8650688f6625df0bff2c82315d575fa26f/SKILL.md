---
name: manifest-pddl-plan-writer
description: Solve every typed classical-PDDL task declared in a JSON manifest and create the required grounded-plan files. Use for IPC Airport or other manifest-driven sequential PDDL planning tasks where plan_output artifacts, rather than a chat response, are required.
---

# Manifest PDDL plan writer

The required deliverable is a plan file at **every** `plan_output` path in the runtime manifest. Do not only explain a plan, inspect PDDL manually without writing files, or modify the supplied manifest/domain/problem inputs.

## Mandatory execution

Use `run_skill_script` to execute the packaged writer before finishing. This is an actual artifact-producing tool call, not a suggested command:

```json
{
  "relative_path": "scripts/solve_manifest.py",
  "input_json": {
    "manifest": "/app/problem.json",
    "time_limit_sec": 250
  }
}
```

The script reads each entry's own `domain`, `problem`, and `plan_output`, searches for a typed grounded plan, replay-validates it, and writes it atomically to the declared path. Paths in the manifest are authoritative, including absolute paths. Tasks must be solved independently; do not transfer routes, action signatures, or object names between entries.

Then make this second, actual validation call:

```json
{
  "relative_path": "scripts/solve_manifest.py",
  "input_json": {
    "mode": "validate-manifest",
    "manifest": "/app/problem.json"
  }
}
```

Finish only after the validation response has `"ok": true`. If solve mode reports a timeout or an unsolved task, rerun it with a larger `time_limit_sec` rather than submitting with a missing output. Never replace an unsolved plan with prose or an empty file unless the validator confirms that the initial state already satisfies that task's complete goal.

## Artifact format and semantics

Each output file contains no headers, comments, timestamps, solver output, or prose. Each nonblank line is exactly one grounded primitive in this format:

```text
action_name(object1,object2)
```

The exact lower-case action and object identifiers must come from that task's PDDL. The emitted sequence must be executable from `:init`: every action has the declared arity and compatible object types, all positive/negative preconditions hold when used, effects are applied in order, and the complete `:goal` holds after the final action.

## Script interface

`scripts/solve_manifest.py` receives one JSON object on stdin and emits one JSON object on stdout.

- Solve and write artifacts: `{"manifest":"/app/problem.json","time_limit_sec":250}`.
- Validate existing artifacts only: `{"mode":"validate-manifest","manifest":"/app/problem.json"}`.

A manifest can be a list or an object containing `tasks` or `problems`. Relative domain, problem, and output paths are resolved relative to the manifest file. The solver supports the typed, classical propositional/ADL subset used by these Airport instances, including conjunction, disjunction, negation, equality, implication, quantifiers, and conditional effects. Numeric and durative PDDL are explicitly reported as unsupported rather than producing unchecked artifacts.
