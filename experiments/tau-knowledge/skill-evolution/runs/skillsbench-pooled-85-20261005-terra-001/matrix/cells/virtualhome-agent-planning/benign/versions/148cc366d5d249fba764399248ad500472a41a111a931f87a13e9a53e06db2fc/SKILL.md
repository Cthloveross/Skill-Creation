---
name: pddl-manifest-plan-producer
description: Solve every typed classical-PDDL planning task listed in a runtime manifest and write a replay-validated grounded plan to each declared plan_output path. Use for IPC/Airport planning tasks supplied as domain/problem PDDL pairs.
---

# PDDL manifest plan producer

The task deliverable is the plan artifacts, not a textual answer. Read the runtime manifest and create a plan file at **every** `plan_output` it declares. Never modify the supplied domain PDDL, problem PDDL, or manifest.

## Required execution procedure

Use the packaged script tool to run the solver before doing anything else:

```json
{
  "relative_path": "scripts/solve_manifest.py",
  "input_json": {
    "manifest": "/app/problem.json",
    "time_limit_sec": 270
  }
}
```

This call is side-effecting: it reads each entry's own domain and problem PDDL, searches for a plan, replay-validates it, and writes the result to the exact `plan_output` path. A successful call has `ok: true` and `status: "solved"` for every entry.

Then run the mandatory independent artifact check:

```json
{
  "relative_path": "scripts/solve_manifest.py",
  "input_json": {
    "mode": "validate-manifest",
    "manifest": "/app/problem.json"
  }
}
```

Do not finish unless that second call returns `ok: true`. In particular, confirm that it reports `valid: true` for every entry and that all declared output paths exist. If a task is unsolved or times out, retain the diagnostic and continue working on that task; do not silently omit its artifact.

## Artifact format

Each nonblank line of a plan file must contain exactly one grounded action primitive, using the exact lower-case identifiers from that task's PDDL, for example:

```text
action_name(object1,object2)
```

There must be no headers, comments, timestamps, plan lengths, solver logs, or prose in an output file. An empty file is valid only if the corresponding initial state already satisfies the complete goal.

Tasks are independent: derive action names, graph links, resource constraints, object types, and action ordering from each entry's paired PDDL files. Do not transfer a route or action signature between Airport instances.

## Script interface

`scripts/solve_manifest.py` accepts one JSON object on stdin and emits one JSON object on stdout.

- Solve and write every declared artifact: `{"manifest":"/app/problem.json","time_limit_sec":270}`.
- Check all existing artifacts by replay: `{"mode":"validate-manifest","manifest":"/app/problem.json"}`.

The manifest can be a task list or an object containing `tasks` or `problems`. Relative paths are resolved against the manifest directory. The planner supports typed classical PDDL with conjunction, disjunction, negation, implication, equality, quantifiers, and conditional effects. Numeric and durative PDDL are explicitly rejected rather than producing an unchecked plan.
