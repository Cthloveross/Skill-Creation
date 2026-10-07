---
name: pddl-tpp-manifest-planner
description: Generate and publish validated function-style plans for every typed classical PDDL task listed in a problem.json manifest.
---

# PDDL TPP manifest planner

Use this Skill for travelling-purchase or other classical propositional PDDL tasks where `/app/problem.json` is a nonempty JSON array and each entry has `id`, `domain`, `problem`, and `plan_output`.

## Required executor action

**Execute the packaged solver in the task sandbox before declaring the task complete.** The output plan files are runtime artifacts; reading this Skill or describing the command does not create them.

From the Skill package directory, run:

```bash
python3 scripts/solve_tpp.py <<'JSON'
{"root":"/app","problem_json":"/app/problem.json","max_expansions":30000000,"weight":2}
JSON
```

The solver reads the current manifest and PDDL files, solves each manifest entry independently, replays the recovered plan, and writes every declared `plan_output`. Absolute output paths such as `/app/task01.txt` are supported.

The script accepts one JSON object on stdin:

- `root` (optional string, default `/app`): base directory for relative paths.
- `problem_json` (optional string, default `<root>/problem.json`): manifest location.
- `max_expansions` (optional positive integer, default `5000000`): per-task search limit.
- `weight` (optional positive number, default `2`): weighted-A* goal-count heuristic factor.

It prints JSON on stdout:

```json
{"ok":true,"results":[{"id":"...","ok":true,"plan_output":"/...","steps":4,"expanded":12}]}
```

If `ok` is false, do not finish: inspect the per-entry error, correct the invocation or use a larger `max_expansions`, then execute it again. A task is complete only when every current manifest entry has a successful result and a regular file at its exact `plan_output` path.

## Output and validation contract

Each published plan contains only grounded actions, one per nonblank line:

```text
action_name(object1, object2, ...)
```

Do not put comments, headings, parenthesized whitespace-PDDL actions, costs, timestamps, numbering, or solver JSON in plan files. Action and object identifiers come only from the particular task's supplied PDDL.

The solver parses typed objects, domain constants, type hierarchy, action schemas, conjunctions, negation, equality, initial state, and goal. It grounds only type-compatible actions, searches reachable propositional states, and independently replays the selected actions to check arity, types, equality, all positive/negative preconditions, effects, and every goal literal immediately before publication. It refuses unsupported logical constructs rather than writing an unvalidated plan.

After execution, verify the JSON status and verify each live manifest `plan_output` exists. Do not assume two tasks, fixed filenames, shared objects, or a reusable route.