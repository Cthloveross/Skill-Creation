---
name: pddl-airport-plan-generation
description: Generate, write, and replay-validate a grounded classical-PDDL plan for every task declared in a runtime problem.json manifest. Use for IPC Airport and other typed STRIPS/ADL-style planning tasks with required plan artifacts.
---

# PDDL plan artifact generation

## Completion gate

This Skill is not complete merely because a plan was printed or a domain was inspected. The execution agent must create a physical plan file for **every** `plan_output` declared by `/app/problem.json`.

From `/app`, run the packaged solver before finishing:

```bash
python3 scripts/solve_manifest.py <<'JSON'
{"manifest":"/app/problem.json","time_limit_sec":280}
JSON
```

The command reads every manifest item, independently loads its paired `domain` and `problem`, and atomically writes its plan to the exact declared output path. In the current episode this includes `/app/task01.txt` and `/app/task02.txt`; do not finish until both files exist.

A successful response has `"ok": true` and every result has `"status": "solved"`. Then run the required independent replay of the files actually written:

```bash
python3 scripts/solve_manifest.py <<'JSON'
{"mode":"validate-manifest","manifest":"/app/problem.json"}
JSON
```

Finish only when that response has `"ok": true` and every result has `"valid": true`. If either command reports `error`, `timeout`, or `unsolved`, retain the diagnostic and continue planning rather than claiming completion.

## Output contract

Each plan output contains only grounded action primitives, one per line:

```text
action_name(object1, object2)
```

Use exact action and object names from the task's own PDDL. Do not put headings, comments, timestamps, costs, prose, or solver logs in plan files. An empty output is valid only if the complete goal is already true in the initial state.

Do not transfer routes, object names, action signatures, or airport topology between manifest entries. Ground traffic actions can interact through occupancy and safety facts, so plans are searched and replayed as ordered transitions in each task's joint state.

## Entrypoint interface

`scripts/solve_manifest.py` reads one JSON object from stdin and emits one JSON object on stdout.

```json
{"manifest":"/app/problem.json","time_limit_sec":280}
```

- `manifest` defaults to `problem.json`. It may be a list or an object containing `tasks` or `problems`.
- Every entry requires nonempty `domain`, `problem`, and `plan_output` strings. Relative paths are resolved from the manifest directory.
- `time_limit_sec` is a per-task forward-search limit and defaults to 240 seconds.
- `{"mode":"validate-manifest","manifest":"/app/problem.json"}` only parses and replays existing outputs.

The solver parses typed objects and type hierarchies, initial facts, action schemas, logical preconditions, conditional/quantified effects, and complete goals. It grounds only type-compatible actions, searches forward over applicable transitions, and validates every candidate sequentially before writing it. Numeric and durative PDDL are reported as unsupported instead of producing an unchecked artifact.
