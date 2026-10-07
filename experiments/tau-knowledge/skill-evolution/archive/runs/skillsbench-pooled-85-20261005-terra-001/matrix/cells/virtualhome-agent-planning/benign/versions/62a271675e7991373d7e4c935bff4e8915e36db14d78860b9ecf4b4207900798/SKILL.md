---
name: pddl-airport-plan-generation
description: Generate and validate required plan files for every typed classical-PDDL task declared in a runtime manifest, particularly IPC Airport ground-traffic tasks. Use when the executor must create one grounded action per line at each task's exact plan_output path.
---

# PDDL Airport Plan Generation

**This Skill produces artifacts only when its entrypoint is executed.** Before finishing the task, the executor must run the command below from `/app`, inspect its JSON result, and ensure that every manifest entry reports `"status":"solved"`. Do not merely describe a plan or stop after reading the PDDL.

```bash
python3 scripts/solve_manifest.py <<'JSON'
{"manifest":"/app/problem.json","time_limit_sec":500}
JSON
```

The entrypoint reads every task declared in `problem.json`; each task must supply `domain`, `problem`, and `plan_output`. It parses each task's own files, searches its typed state space, independently replays the candidate, and writes the validated sequence to the exact declared `plan_output` path. Thus, if the manifest declares `/app/task01.txt` and `/app/task02.txt`, both files are mandatory artifacts.

## Output contract

Each output file contains only action primitives, one action per line, in this form:

```text
action_name(object1, object2)
```

Action and object names are read from the current PDDL and are never copied from another task. No headers, timestamps, solver logs, comments, or explanatory text may be written into a plan file.

The bundled solver supports the ordinary typed classical PDDL used by Airport: type hierarchies, STRIPS add/delete effects, conjunction, disjunction, negation, equality, quantified formulas, conditional effects, and quantified effects. It grounds only type-compatible actions and uses static predicates from the actual domain to reduce grounding. It rejects numeric and durative constructs instead of emitting an unchecked plan.

## JSON interface

`solve_manifest.py` reads one JSON object on stdin and writes one JSON object on stdout:

```json
{
  "manifest": "/app/problem.json",
  "time_limit_sec": 500
}
```

- `manifest` defaults to `problem.json`. It may be a JSON list or an object containing `tasks` or `problems`.
- `time_limit_sec` is a per-task search limit and defaults to 240.
- Relative domain/problem paths are resolved against the manifest directory when present; relative output paths are resolved against the executor's current directory, matching the task contract.

A successful result has one `results` element per manifest task, each with `status: "solved"`, its output path, plan length, and replay verdict. `timeout`, `unsolved`, and `error` are failures: do not finish the task while any occurs. Increase the limit or use an available ordinary PDDL planner to obtain a candidate, but always replay it with the supplied domain and problem before writing it.

## Final artifact check

After the solve command returns, run the built-in manifest validation mode. It verifies presence and semantic replay of every declared output, including empty plans only when the initial state already reaches the goal.

```bash
python3 scripts/solve_manifest.py <<'JSON'
{"mode":"validate-manifest","manifest":"/app/problem.json"}
JSON
```

Finish only if its `ok` field is true. This check verifies action names, arity, object types, sequential positive/negative preconditions, effects, and complete goals for every declared task.
