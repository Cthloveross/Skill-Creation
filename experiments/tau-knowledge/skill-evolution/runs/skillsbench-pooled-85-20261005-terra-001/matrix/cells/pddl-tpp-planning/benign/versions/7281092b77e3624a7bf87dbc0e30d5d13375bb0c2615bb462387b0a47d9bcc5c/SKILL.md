---
name: pddl-tpp-manifest-planner
description: Solve every typed classical travelling-purchase PDDL problem named by a problem.json manifest, validate the plans by replay, and create the manifest's required function-style plan files.
---

# PDDL TPP manifest planner

Use this Skill when the task supplies a `problem.json` array whose entries contain `id`, `domain`, `problem`, and `plan_output`. The required deliverables are the plan files at the exact `plan_output` paths, not a prose answer and not merely the solver's JSON report.

## Mandatory artifact-generation action

Before completing the task, execute the packaged solver in the task runtime. This is required even when only one or two manifest entries are present.

```bash
python3 /PATH/TO/THIS/SKILL/scripts/solve_tpp.py <<'JSON'
{"root":"/app","problem_json":"/app/problem.json","max_expansions":5000000,"weight":3}
JSON
```

Replace `/PATH/TO/THIS/SKILL` with the actual directory containing this Skill. The command reads all current PDDL inputs from `/app`, processes **every** manifest entry, and creates each declared output file (for example, `/app/task01.txt` and `/app/task02.txt` when those are declared by the current manifest).

The script receives one JSON object on stdin and emits one JSON object on stdout. Input fields are:

- `root`: base directory for relative manifest paths; defaults to `/app`.
- `problem_json`: manifest file; defaults to `<root>/problem.json`.
- `max_expansions`: positive per-task state-expansion limit; defaults to `5000000`.
- `weight`: positive weighted best-first heuristic multiplier; defaults to `3`.

A successful report has `"ok": true` and a successful result for every manifest entry. Do not consider a report with any failed result complete. If a task exhausts the limit, rerun the complete manifest with a larger `max_expansions` value. Do not handwrite guessed actions or reuse object names from another problem.

## What the solver guarantees

The solver parses the supplied domain and problem at runtime. It supports the typed classical STRIPS subset used by TPP: type hierarchies, constants, conjunctions, positive and negative predicates, equality tests, add/delete effects, and numeric bookkeeping effects such as `increase`. Numeric bookkeeping is ignored only because it does not affect propositional applicability; unsupported logical constructs fail explicitly rather than yielding an unsound plan.

For each entry it grounds only type-compatible actions, searches reachable propositional states, then independently replays the recovered plan. Replay checks action declaration, arity, object types, equality, positive and negative preconditions, add/delete effects, and all goal literals.

On success, the solver atomically writes only one grounded primitive per line at the exact manifest path:

```text
action_name(object1, object2)
```

Action and object names are taken from the current PDDL and arguments retain the domain parameter order. After execution, confirm that every reported `plan_output` exists. These files are the final task artifacts.
