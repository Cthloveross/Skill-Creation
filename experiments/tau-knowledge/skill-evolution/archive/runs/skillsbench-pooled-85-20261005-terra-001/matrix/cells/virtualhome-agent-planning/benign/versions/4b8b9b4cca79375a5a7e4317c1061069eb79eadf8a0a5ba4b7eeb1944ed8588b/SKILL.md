---
name: pddl-airport-plan-generation
description: Create and validate every grounded PDDL plan artifact declared in a runtime problem.json manifest, especially typed IPC Airport ground-traffic instances.
---

# PDDL Airport Plan Generation

## Required artifact-producing step

This Skill is not complete until its solver has been **executed**. From `/app`, run:

```bash
python3 scripts/solve_manifest.py <<'JSON'
{"manifest":"/app/problem.json","time_limit_sec":280}
JSON
```

The command reads every entry in the manifest and writes a plan to that entry's exact `plan_output` path. Treat every declared output as mandatory. In particular, do not stop after inspecting PDDL, printing a prospective plan, or solving only the first manifest entry.

Inspect the JSON response. Every result must have `"status":"solved"`. A `timeout`, `unsolved`, or `error` result means the required artifact has not been produced; resolve it before finishing. The solver always parses each entry's own domain and problem, so plans must not be reused across Airport instances.

Then validate the actual emitted files:

```bash
python3 scripts/solve_manifest.py <<'JSON'
{"mode":"validate-manifest","manifest":"/app/problem.json"}
JSON
```

Finish only when the result has `"ok": true` and every declared plan output is present and valid.

## Output contract

Each plan file contains only grounded action primitives, one action per line:

```text
action_name(object1, object2)
```

The action and object spelling comes from the current PDDL files. Do not put headings, comments, timestamps, planner logs, costs, prose, or blank explanatory material in a plan file. An empty file is valid only if that task's initial state already satisfies its complete goal.

## Entrypoint interface

`scripts/solve_manifest.py` consumes one JSON object on stdin and emits one JSON result object on stdout.

```json
{"manifest":"/app/problem.json","time_limit_sec":280}
```

- `manifest` defaults to `problem.json`. It can be a task list or an object with a `tasks` or `problems` list.
- Every task object requires string `domain`, `problem`, and `plan_output` fields.
- Relative paths are resolved relative to the manifest file, which makes outputs land under `/app` for the supplied `/app/problem.json`.
- `time_limit_sec` is a per-task search limit, defaulting to 240 seconds.
- Set `mode` to `validate-manifest` to replay already-written plan files rather than search.

The bundled solver supports typed classical PDDL with type hierarchies, STRIPS effects, conjunction, disjunction, negation, equality, quantifiers, conditional effects, and quantified effects. It rejects durative and numeric constructs rather than writing an unchecked plan. Before writing a file it independently replays the proposed actions, checking action names, arity, object types, preconditions, effects, and the full goal.
