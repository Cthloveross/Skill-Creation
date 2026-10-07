---
name: pddl-manifest-plan-writer
description: Solve every classical typed-PDDL task declared by a JSON manifest and create replay-validated grounded plan files at the manifest's exact plan_output paths. Use for IPC-style planning tasks, including Airport ground-traffic instances.
---

# PDDL manifest plan writer

The required deliverable is the plan artifact for **every** manifest entry, not a prose answer. Read the current manifest and solve each task using its own domain/problem pair. Never modify supplied PDDL inputs or the manifest.

## Execute the solver

Use the `run_skill_script` tool (not a prose-only response) with these exact tool arguments:

- `relative_path`: `scripts/solve_manifest.py`
- `input_json`: `{"manifest":"/app/problem.json","time_limit_sec":240}`

The script reads all manifest entries, searches each typed classical PDDL state space, replays every proposed plan, and writes the declared `plan_output` artifact. It prints a JSON report. Do not finish unless its top-level `ok` is true and each task has `status` `solved`.

If a task reports `timeout`, call the same script again with a larger `time_limit_sec` within the available task budget. If it reports `error` or `unsolved`, inspect the stated PDDL issue rather than creating a placeholder plan.

## Mandatory post-write check

After a successful solve call, invoke `run_skill_script` again with:

- `relative_path`: `scripts/solve_manifest.py`
- `input_json`: `{"mode":"validate-manifest","manifest":"/app/problem.json"}`

Finish only when this validation response has `ok: true`. Validation checks that every declared output path exists, each action has valid syntax/arity/types, every action is applicable sequentially, and the final state satisfies the complete goal. An initially solved task still requires its declared output file (it may be empty only when the initial state satisfies its goal).

## Plan-file format

The solver writes one action primitive per line in the public comma-separated form:

```text
action_name(object1,object2)
```

No headers, comments, timestamps, solver logs, or explanatory text are written. Action names, argument order, and objects are taken from the current PDDL files at runtime. Relative manifest paths are resolved against the manifest directory. The manifest can be a list or an object containing `tasks` or `problems`.

## Script interface

`scripts/solve_manifest.py` receives a single JSON object on stdin and emits a single JSON object on stdout.

- Solve, replay, and write every entry: `{"manifest":"/app/problem.json","time_limit_sec":240}`
- Validate all existing declared artifacts only: `{"mode":"validate-manifest","manifest":"/app/problem.json"}`

It supports ordinary typed classical PDDL, including conjunction/disjunction, negation, equality, implication, quantifiers, conditional effects, and quantified effects. It explicitly rejects numeric and durative PDDL rather than emitting an unchecked plan.
