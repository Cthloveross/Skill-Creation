---
name: pddl-plan-artifact-generator
description: Solve every classical typed-PDDL task declared by a runtime JSON manifest and write a replay-validated grounded plan at each required output path. Use for IPC Airport-style planning tasks where the required deliverable is one plan file per manifest entry.
---

# PDDL plan artifact generator

## Required completion procedure

The required result is **not** a chat response or a displayed plan. It is a physical file at every `plan_output` declared in `/app/problem.json`.

Use the packaged script tool (not a shell command that assumes package scripts exist under `/app`) with:

```json
{"manifest":"/app/problem.json","time_limit_sec":260}
```

That call reads the manifest, loads each entry's own domain/problem pair, searches for a plan, independently replays it, and writes the plan to the exact `plan_output` path. Do not stop after merely inspecting the returned JSON. A successful response has `"ok": true` and all result statuses are `"solved"`.

Then use the same packaged script with:

```json
{"mode":"validate-manifest","manifest":"/app/problem.json"}
```

Finish only when this response has `"ok": true` and every result has `"valid": true`. In particular, check that every path named by the manifest now exists. If a task is unsolved, timed out, or invalid, use its diagnostic to continue solving; do not claim completion and do not omit its output artifact.

## Plan-file contract

The script writes exactly one grounded primitive per line, in this form:

```text
action_name(object1, object2)
```

Plan files contain no headings, comments, timestamps, costs, solver diagnostics, or prose. An empty file is permitted only when the complete goal already holds in the initial state.

Each manifest entry is independent: derive action names, arities, objects, routes, and resource constraints from that entry's own PDDL files. Airport movements can share occupancy and safety predicates, so action ordering must be planned over the joint state rather than inferred from location names.

## Script interface

`scripts/solve_manifest.py` consumes one JSON object on stdin and emits one JSON object on stdout.

- Generation input: `{"manifest": "/app/problem.json", "time_limit_sec": 260}`. `manifest` defaults to `problem.json`; the time limit is per task.
- Validation input: `{"mode": "validate-manifest", "manifest": "/app/problem.json"}`. This only replays existing output files.
- A manifest can be a list or an object containing a `tasks` or `problems` list. Every entry must provide nonempty `domain`, `problem`, and `plan_output` strings. Relative paths are resolved against the manifest directory.

The implementation supports typed classical STRIPS/ADL formulas including conjunction, disjunction, negation, equality, quantifiers, conditional effects, and quantified effects. Numeric and durative constructs are explicitly rejected rather than producing an unchecked plan. It grounds type-compatible actions with static-fact joins, performs forward A* search, and replays every emitted action for preconditions, effects, and complete-goal satisfaction before writing the artifact.
