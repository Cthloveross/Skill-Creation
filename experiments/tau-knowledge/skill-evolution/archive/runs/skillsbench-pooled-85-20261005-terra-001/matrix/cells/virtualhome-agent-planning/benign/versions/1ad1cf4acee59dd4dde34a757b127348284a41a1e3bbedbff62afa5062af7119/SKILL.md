---
name: pddl-manifest-plan-writer
description: Generate and write replay-validated grounded plans for every typed classical PDDL task declared in a JSON manifest. Use for IPC-style PDDL tasks, including Airport ground-traffic domains.
---

# PDDL manifest plan writer

The deliverable is the plan files, not a chat explanation. Read the current `problem.json`, solve **every** declared entry against its own paired PDDL files, and create every exact `plan_output` path. Do not modify the supplied domain, problem, or manifest files.

## Required execution

Immediately invoke the packaged script tool below. This invocation performs the search, independently replays each plan, and writes the required artifacts (including absolute paths such as `/app/task01.txt`). Merely reading the files or reporting a candidate plan does not satisfy the task.

```json
{"relative_path":"scripts/solve_manifest.py","input_json":{"manifest":"/app/problem.json","time_limit_sec":240}}
```

Inspect its JSON output. Do not finish unless `ok` is `true` and every result has `status: "solved"`. If a task times out, invoke the same script again with a larger `time_limit_sec`, subject to the runtime budget.

Then invoke the required artifact and semantic check:

```json
{"relative_path":"scripts/solve_manifest.py","input_json":{"mode":"validate-manifest","manifest":"/app/problem.json"}}
```

Finish only if this call reports `ok: true`. If it reports an error, use the reported task, PDDL pair, and failed replay step to correct the planning process, then rerun solve and validation. Never submit absent files, placeholders, solver logs, headers, timestamps, or prose in a plan file.

## Output format and guarantees

Each nonempty line written by the script is exactly one grounded action:

```text
action_name(object1,object2)
```

The script obtains action names, parameter order, object names, types, initial state, action preconditions/effects, and the complete goal from the current files at runtime. It grounds only type-compatible actions, searches the reachable state space, replays the selected sequence from `:init`, and atomically writes each declared output only after replay succeeds.

Relative manifest paths are resolved relative to the manifest file. The manifest may be a list or an object with a `tasks` or `problems` list. The supported PDDL subset is typed classical PDDL with `and`, `or`, `not`, implication, equality, quantifiers, and conditional/quantified effects. Numeric and durative PDDL are rejected explicitly rather than generating unchecked output.

## Script interface

`scripts/solve_manifest.py` receives one JSON object on stdin and emits one JSON object on stdout.

- Solve, replay, and write all declared outputs: `{"manifest":"/app/problem.json","time_limit_sec":240}`
- Replay and check already-written outputs only: `{"mode":"validate-manifest","manifest":"/app/problem.json"}`

Successful solve results list each actual `plan_output` and plan length. Successful validation results confirm that each declared path exists, every action has valid syntax/arity/types and sequentially satisfied preconditions, and its final state satisfies the entire goal.
