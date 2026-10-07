---
name: pddl-tpp-manifest-planner
description: Generate, validate, and write one function-style grounded plan for every typed classical PDDL travelling-purchase task listed in a JSON manifest.
---

# PDDL TPP manifest planner

Use this Skill for a `problem.json` manifest whose entries contain `id`, `domain`, `problem`, and `plan_output`. The deliverable is the set of plan files, not a prose answer. Every manifest entry must have a file at its exact `plan_output` path.

## Execute the solver

Run the packaged solver in the task runtime before completion. It reads the live manifest and PDDL files, plans separately for every entry, independently replays each recovered plan, and writes the requested files only after replay succeeds.

```bash
python3 scripts/solve_tpp.py <<'JSON'
{"root":"/app","problem_json":"/app/problem.json","max_expansions":5000000,"weight":3}
JSON
```

When the Skill package is stored outside `/app`, invoke the same `scripts/solve_tpp.py` path from the package location while keeping `root` and `problem_json` pointed at `/app`.

The JSON stdin schema is:

- `root` (string, default `/app`): base for relative paths in the manifest.
- `problem_json` (string, default `<root>/problem.json`): manifest to process.
- `max_expansions` (positive integer, default `5000000`): per-task state-expansion limit.
- `weight` (positive number, default `3`): weighted missing-goal heuristic multiplier.

The script emits one JSON object: `{ "ok": boolean, "results": [...] }`. Each successful result includes its task ID, output path, action count, and expanded-state count. If `ok` is false, inspect every task error, fix the runtime issue or increase the expansion bound, and run it again. Do not finish after merely describing a command.

## Required completion checks

1. Confirm `ok` is true and that every manifest `plan_output` now exists.
2. Plans must contain only one grounded primitive per nonblank line in this format:

   ```text
   action_name(object1, object2, ...)
   ```

3. Do not reuse object names or routes across tasks. The solver obtains schemas, type hierarchy, constants, objects, initial facts, and goals from each entry's current PDDL.

The solver supports conjunctions of positive/negative propositional literals and equality, plus ignored numeric bookkeeping effects such as `increase`, matching ordinary TPP encodings. It grounds only type-compatible actions, searches the reachable propositional state space, and replays the selected action sequence to check action declaration, arity, types, equality, positive/negative preconditions, add/delete effects, and the complete final goal. Unsupported logical constructs fail explicitly rather than producing an unchecked plan.
