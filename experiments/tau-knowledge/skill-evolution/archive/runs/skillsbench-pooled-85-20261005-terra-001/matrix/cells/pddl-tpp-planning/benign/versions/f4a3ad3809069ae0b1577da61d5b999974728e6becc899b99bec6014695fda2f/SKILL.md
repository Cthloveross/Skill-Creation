---
name: pddl-tpp-manifest-planner
description: Solve every typed classical PDDL travelling-purchase problem listed in a JSON manifest and write a validated function-style plan at each declared output path.
---

# PDDL TPP manifest planner

Use this Skill for a task whose live `/app/problem.json` is a nonempty array of objects containing `id`, `domain`, `problem`, and `plan_output`.

## Mandatory execution step

This Skill does not itself create deliverables until its solver is **executed in the task sandbox**. Do not stop after reading this file, describing a plan, or reporting a command. Run the following packaged script before completing the task:

```bash
python3 scripts/solve_tpp.py <<'JSON'
{"root":"/app","problem_json":"/app/problem.json","max_expansions":30000000,"weight":3}
JSON
```

If the current working directory is not the Skill package directory, use the actual path to this package's `scripts/solve_tpp.py`. The script reads the current manifest and current PDDL files at runtime. It creates or replaces every file named by `plan_output`, including absolute paths such as `/app/task01.txt`.

The script receives one JSON object on standard input:

- `root` (optional string): base used for relative manifest paths; defaults to `/app`.
- `problem_json` (optional string): manifest path; defaults to `<root>/problem.json`.
- `max_expansions` (optional positive integer): per-problem search limit; defaults to `5000000`.
- `weight` (optional positive number): A* missing-goal heuristic weight; defaults to `3`.

It emits one JSON object on standard output:

```json
{"ok": true, "results": [{"id": "...", "ok": true, "plan_output": "/...", "steps": 0, "expanded": 0}]}
```

A false top-level `ok` means at least one configured task was not solved and written. Resolve that failure and rerun with a larger expansion bound when appropriate; do not finish with any manifest entry missing its output artifact.

## Completion requirements

1. Check the solver JSON result and require `ok: true` for every current manifest entry.
2. Check that every exact `plan_output` path from the live manifest is a regular file. Never assume a fixed task count, output filename, action signature, object name, or route.
3. Each nonblank output line must be exactly one grounded action in this form:

   ```text
   action_name(object1, object2, ...)
   ```

   Write no prose, numbering, cost, timestamp, parenthesized PDDL expression, or solver transcript into a plan file.
4. The packaged solver parses each domain and problem, grounds type-compatible actions, searches reachable propositional states, independently replays the recovered actions, and writes only a replay-validated plan. Replay checks action declaration, arity, types, equality, positive and negative preconditions, add/delete effects, and all final-goal literals.

The solver deliberately fails rather than writing an unvalidated plan for unsupported logical constructs. Use only the supplied domain/problem pair for each manifest entry.
