---
name: pddl-airport-plan-generation
description: Solve every typed classical-PDDL task declared by a runtime problem.json manifest, write each required grounded plan artifact, and replay-validate each plan. Applies especially to IPC Airport ground-traffic planning tasks.
---

# PDDL Airport Plan Generation

## Mandatory completion procedure

This Skill produces required files only when its entrypoint is run. From `/app`, execute this command before completing the task:

```bash
python3 scripts/solve_manifest.py <<'JSON'
{"manifest":"/app/problem.json","time_limit_sec":280}
JSON
```

The command reads **every** manifest entry and writes a plan at that entry's exact `plan_output` path. Do not stop after inspecting PDDL, printing a proposed plan, or solving only the first entry. In the supplied environment, outputs declared as `/app/task01.txt` and `/app/task02.txt` must physically exist before completion.

Read the JSON response. Every entry must report `"status":"solved"`. If an entry reports `timeout`, `unsolved`, or `error`, it has not produced a valid required artifact and must not be treated as complete.

Then replay the files actually written:

```bash
python3 scripts/solve_manifest.py <<'JSON'
{"mode":"validate-manifest","manifest":"/app/problem.json"}
JSON
```

Finish only if the response has `"ok":true` and every declared output has `"valid":true`.

## Output contract

Each output file contains only one grounded action primitive per nonempty line, in this form:

```text
action_name(object1, object2)
```

Action and object spellings are obtained from the current task's PDDL files. Do not put headers, comments, timestamps, costs, prose, blank explanatory content, or solver logs into a plan file. An empty plan is written only when the complete goal already holds in the initial state.

Solve each manifest entry independently with its paired domain and problem; Airport movement names, connectivity, occupancy rules, and valid object names cannot be inferred from another instance.

## Entrypoint JSON interface

`scripts/solve_manifest.py` reads one JSON object from stdin and emits one JSON object on stdout.

```json
{"manifest":"/app/problem.json","time_limit_sec":280}
```

- `manifest` defaults to `problem.json`; it may be a list or an object containing a `tasks` or `problems` list.
- Each entry requires nonempty string `domain`, `problem`, and `plan_output` fields.
- Relative paths resolve relative to the manifest directory.
- `time_limit_sec` is a per-task search limit and defaults to 240 seconds.
- Use `{"mode":"validate-manifest","manifest":"/app/problem.json"}` to replay existing plans without searching.

The bundled solver parses typed PDDL type hierarchies, objects, initial facts, action schemas, conjunction/disjunction/negation/equality/quantifiers, conditional effects, and quantified effects. It uses sound forward state-space search over type-compatible ground actions. Before replacing any plan output, it replays the candidate plan and checks action declaration, arity, object types, sequential preconditions/effects, and the complete goal. Numeric and durative constructs are rejected rather than serialized as an unchecked plan.
