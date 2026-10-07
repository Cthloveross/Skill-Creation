---
name: pddl-tpp-batch-planner
description: Solve batches of typed STRIPS-style PDDL travelling-purchase planning tasks listed in problem.json, validate each plan by replay, and write one function-style grounded-action plan file per task.
---

# PDDL TPP batch planner

Use this Skill when a task provides a PDDL domain, PDDL problem files, and a JSON manifest whose entries contain `id`, `domain`, `problem`, and `plan_output` paths. It is designed for the typed, classical STRIPS subset used by TPP: conjunctions, positive/negative literals, add/delete effects, and optional equality tests.

The packaged solver parses the supplied files at runtime; it does not assume object names, routes, action schemas, or plans from another instance. It uses forward weighted A* search, grounds only objects compatible with declared parameter types, and replays the chosen plan before writing it.

## Run

From the task work directory, invoke the script with JSON on standard input:

```bash
python3 /path/to/skill/scripts/solve_tpp.py <<'JSON'
{"root":"/app","problem_json":"/app/problem.json","max_expansions":1000000,"weight":3}
JSON
```

Input schema:

- `root` (optional, default `/app`): base directory for relative manifest paths.
- `problem_json` (optional, default `<root>/problem.json`): manifest path.
- `ids` (optional array of strings): solve only entries with these IDs.
- `max_expansions` (optional positive integer, default `1000000`): per-problem search cap.
- `weight` (optional positive number, default `3`): weighted-A* goal-count heuristic weight. This affects speed and plan length, not replay validity.

The script emits a JSON report on stdout:

```json
{"ok":true,"results":[{"id":"...","ok":true,"plan_output":"...","steps":12,"expanded":34}]}
```

A failed parse, unsupported PDDL construct, exhausted/capped search, or failed replay is reported with `ok: false` for that task. The solver does not write a plan file for a failed task. Inspect this report and correct the task or increase a justified search limit rather than treating syntax alone as a solution.

## Output and validation

For every successful manifest entry the script creates the parent directory of `plan_output` if necessary and writes only one action per line, in the required form:

```text
action_name(object1, object2)
```

Names are taken from the runtime domain/problem tokens and arguments retain the declared action-parameter order. Before the file is written, validation checks action existence, arity, object type compatibility, every positive and negative precondition, all add/delete effects, and all final goal literals. An empty file is valid only if the initial state already satisfies the goal.

The parser intentionally rejects constructs outside its declared classical subset (including numeric fluents/effects, conditional effects, disjunction, quantifiers, derived predicates, and action costs) instead of silently producing an unsound plan. Use a PDDL engine supporting those requirements if they occur.
