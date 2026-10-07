---
name: pddl-manifest-plan-producer
description: Generate and validate grounded plans for every typed classical-PDDL domain/problem pair declared in a runtime JSON manifest, then write each plan at its exact declared plan_output path. Use for IPC Airport and similar sequential planning tasks.
---

# PDDL manifest plan producer

The deliverable is one plan artifact for **every** manifest entry, not a prose response. Read `/app/problem.json`; each entry's own `domain`, `problem`, and `plan_output` fields are authoritative. Do not modify the supplied PDDL or manifest.

## Required first action

Invoke the packaged solver using the execution environment's `run_skill_script` tool. This invocation writes the required output files; merely reading its source or describing a plan does not create artifacts.

```json
{
  "relative_path": "scripts/solve_manifest.py",
  "input_json": {
    "manifest": "/app/problem.json",
    "time_limit_sec": 240
  }
}
```

The script reads all declared PDDL pairs, performs typed state-space search, replay-validates every proposed plan, and atomically writes each successful result to its declared `plan_output` path. A successful response has `ok: true` and `status: "solved"` for every task.

Immediately perform the required output check with a second actual tool invocation:

```json
{
  "relative_path": "scripts/solve_manifest.py",
  "input_json": {
    "mode": "validate-manifest",
    "manifest": "/app/problem.json"
  }
}
```

Do not finish until this returns `ok: true`. If the solver reports an error, timeout, or unsolved task, inspect its diagnostic and continue solving that task rather than omitting its file. Every path declared by the manifest is mandatory, including absolute paths such as `/app/task01.txt`.

## Output requirements

Each plan file contains only grounded action primitives, one action per nonblank line, using exact action and object identifiers from that task's PDDL. The writer uses the accepted form:

```text
action_name(object1,object2)
```

Do not add headings, comments, timestamps, plan lengths, solver logs, or explanatory text. An empty file is permitted only when the task's initial state already satisfies the complete goal.

Tasks are independent. Never reuse an Airport route, action arity, object name, graph edge, or resource assumption from another entry. A valid plan must be replayed from that entry's `:init`: every action must exist, be correctly typed and applicable at its step, and the final state must satisfy all goal conditions.

## Script interface

`scripts/solve_manifest.py` accepts one JSON object on stdin and emits one JSON object on stdout.

- Solve and write all artifacts: `{"manifest":"/app/problem.json","time_limit_sec":240}`.
- Replay-check all declared existing artifacts: `{"mode":"validate-manifest","manifest":"/app/problem.json"}`.

The manifest may be a list, or an object containing a `tasks` or `problems` list. Relative paths resolve from the manifest's directory. The solver supports typed classical PDDL with conjunction, disjunction, negation, equality, implication, quantifiers, and conditional effects. Numeric and durative constructs are reported as unsupported instead of emitting unchecked output.
