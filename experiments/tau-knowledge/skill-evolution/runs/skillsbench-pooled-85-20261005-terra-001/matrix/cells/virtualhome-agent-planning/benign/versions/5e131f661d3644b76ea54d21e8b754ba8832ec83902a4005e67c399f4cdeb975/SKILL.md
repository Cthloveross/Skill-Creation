---
name: pddl-manifest-artifact-solver
description: Create and validate every grounded plan artifact declared by a JSON manifest for typed classical PDDL tasks, including IPC Airport ground-traffic instances. Use when the required result is one plan file at each manifest plan_output path.
---

# PDDL manifest artifact solver

The deliverable is **not** a chat explanation. It is a valid plan file at every `plan_output` path declared by the runtime manifest. Read the current manifest and solve each entry independently using that entry's own domain and problem files. Do not modify input PDDL files or the manifest.

## Required execution

Before finishing, make this actual packaged-script call. It reads `/app/problem.json`, writes all declared artifacts (including absolute output paths), and replay-validates each plan before writing it.

```json
{
  "relative_path": "scripts/solve_manifest.py",
  "input_json": {
    "manifest": "/app/problem.json",
    "time_limit_sec": 500
  }
}
```

The response must have `"ok": true`. Then make the required independent artifact-presence and replay check:

```json
{
  "relative_path": "scripts/solve_manifest.py",
  "input_json": {
    "mode": "validate-manifest",
    "manifest": "/app/problem.json"
  }
}
```

Do not stop after inspecting PDDL, obtaining a plan in tool output, or describing actions: the first call must create every file. If a task times out, rerun solve mode with a larger `time_limit_sec`; do not submit missing, placeholder, or prose files.

## Output requirements

Each output has only grounded actions, one per nonblank line, in this form:

```text
action_name(object1,object2)
```

Names and argument order come exactly from the corresponding PDDL. The solver checks declared action arity, object typing, positive and negative preconditions, effects, and the entire goal by replaying the sequence from `:init`.

## Script JSON interface

`scripts/solve_manifest.py` accepts one JSON object on stdin and emits one JSON object on stdout.

- Solve and write: `{"manifest":"/app/problem.json","time_limit_sec":500}`
- Validate existing artifacts only: `{"mode":"validate-manifest","manifest":"/app/problem.json"}`

The manifest may be a list or an object with `tasks` or `problems`. Relative paths are resolved relative to the manifest location. The solver supports the typed classical/ADL constructs used by Airport instances: conjunction, disjunction, negation, equality, implication, quantified formulae, and conditional or quantified effects. Numeric and durative PDDL are rejected explicitly rather than producing an unchecked plan.
