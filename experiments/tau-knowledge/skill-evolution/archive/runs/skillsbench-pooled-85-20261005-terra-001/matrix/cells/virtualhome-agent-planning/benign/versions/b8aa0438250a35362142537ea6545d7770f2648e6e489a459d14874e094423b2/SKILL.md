---
name: pddl-manifest-plan-writer
description: Solve every typed classical PDDL task declared by a JSON manifest and write a replay-validated grounded plan at each required plan_output path. Use for IPC-style planning tasks, including Airport ground-traffic problems.
---

# PDDL manifest plan writer

The required deliverable is a plan artifact, not an explanation in chat. Read the current manifest, solve **every** entry independently against its own domain and problem, and create the exact `plan_output` file declared by that entry. Never modify supplied PDDL inputs or the manifest.

## Mandatory execution procedure

1. Invoke the packaged script with the runtime script tool. This is the step that actually writes the required artifacts:

```json
{"relative_path":"scripts/solve_manifest.py","input_json":{"manifest":"/app/problem.json","time_limit_sec":240}}
```

2. Inspect the JSON result. It is successful only when `ok` is `true` and every task has `status: "solved"`. A plan appearing in tool output does not count unless the script reports the declared file was written.

3. Invoke the independent replay and artifact check before finishing:

```json
{"relative_path":"scripts/solve_manifest.py","input_json":{"mode":"validate-manifest","manifest":"/app/problem.json"}}
```

Finish only when that result has `ok: true`. If search reports a timeout, rerun solve mode with an appropriate larger limit while retaining enough time to run the validation call. Do not submit missing files, placeholder files, headers, solver logs, or prose.

For the current runtime, `problem.json` is authoritative: each declared `plan_output` is mandatory, including absolute paths such as `/app/task01.txt`. Paths are resolved relative to the manifest when they are not absolute.

## Plan artifact format

The writer emits exactly one grounded action primitive per line:

```text
action_name(object1,object2)
```

Action names, object names, and argument order are taken from the paired PDDL files. The script parses typed objects, action schemas, logical preconditions, effects, initial facts, and goals; grounds only type-compatible actions; searches the reachable state space; then replays the plan before atomically writing it. Its validator checks action existence, arity, typing, positive and negative conditions, effects, and the complete goal.

## Script interface

`scripts/solve_manifest.py` receives one JSON object on stdin and emits one JSON object on stdout.

- Solve and write all outputs: `{"manifest":"/app/problem.json","time_limit_sec":240}`
- Validate existing declared outputs only: `{"mode":"validate-manifest","manifest":"/app/problem.json"}`

The manifest can be a list, or an object containing a `tasks` or `problems` list. The supported subset is typed classical/ADL PDDL with conjunction, disjunction, negation, equality, implication, quantifiers, and conditional or quantified effects. Numeric and durative domains are explicitly rejected rather than producing an unchecked result.
