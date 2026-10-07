---
name: pddl-manifest-plan-producer
description: Produce required plan artifacts for every typed classical-PDDL task declared in a runtime manifest. Use for IPC/Airport planning tasks where each manifest entry supplies domain, problem, and plan_output paths.
---

# PDDL manifest plan producer

The deliverable is a set of files, not a chat answer. Read `/app/problem.json` at runtime and create a valid plan at **every** declared `plan_output` path. Do not modify supplied PDDL files or the manifest.

## Mandatory execution sequence

Immediately run the packaged solver with the execution agent's script tool:

```json
{
  "relative_path": "scripts/solve_manifest.py",
  "input_json": {
    "manifest": "/app/problem.json",
    "time_limit_sec": 260
  }
}
```

The script reads every manifest entry, solves each entry using its own domain/problem pair, replay-validates the plan, and writes it to the exact declared output path. A successful response has `ok: true` and `status: "solved"` for every result.

Then, as a separate mandatory step, run the artifact validator:

```json
{
  "relative_path": "scripts/solve_manifest.py",
  "input_json": {
    "mode": "validate-manifest",
    "manifest": "/app/problem.json"
  }
}
```

Do not finish merely because a plan was printed in tool output. Finish only after this second call returns `ok: true`, with `valid: true` for every manifest entry. In particular, confirm that every declared output file exists. If solving reports an error, timeout, or unsolved entry, use its diagnostic and continue resolving that entry; never intentionally omit a declared plan file.

## Output requirements

Each nonempty output file contains only one grounded action primitive per line, for example:

```text
action_name(object1,object2)
```

Use exact action and object identifiers from that task's PDDL. Do not write headers, comments, timestamps, plan lengths, solver logs, or prose. An empty output is permitted only when the corresponding initial state already satisfies the complete goal.

Tasks are independent. Airport topology, occupancy restrictions, safety constraints, and action signatures must be derived from each task's paired domain and problem, not inferred from another task.

## Script interface

`scripts/solve_manifest.py` reads one JSON object from stdin and emits one JSON object on stdout.

- Solve and create artifacts: `{"manifest":"/app/problem.json","time_limit_sec":260}`.
- Validate already-created artifacts: `{"mode":"validate-manifest","manifest":"/app/problem.json"}`.

`manifest` may be a list itself or an object with a `tasks` or `problems` list. Relative paths are resolved relative to the manifest directory. The solver supports typed classical PDDL with conjunction, disjunction, negation, implication, equality, quantifiers, and conditional/quantified effects. It rejects numeric and durative models rather than writing an unchecked plan.
