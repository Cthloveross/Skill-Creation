---
name: pddl-tpp-manifest-planner
description: Create and validate function-style grounded plans for every typed classical PDDL travelling-purchase problem listed in a JSON manifest.
---

# PDDL TPP manifest planner

Use this Skill when `/app/problem.json` lists entries with `id`, `domain`, `problem`, and `plan_output`. The required deliverable is a plan file at **every exact `plan_output` path** in that live manifest. Do not return a prose plan and do not stop after inspecting the PDDL.

## Mandatory execution step

From the Skill-package directory, run the packaged solver against the task runtime before finishing the task:

```bash
python3 scripts/solve_tpp.py <<'JSON'
{"root":"/app","problem_json":"/app/problem.json","max_expansions":20000000,"weight":3}
JSON
```

If the package directory is not the current directory, invoke its `scripts/solve_tpp.py` by its package-relative location, but keep the input paths rooted at `/app`. The script reads the current manifest and current PDDL files at runtime; it writes each requested plan directly to the manifest's declared path, including absolute paths such as `/app/task01.txt`.

Its JSON stdin is an object with:

- `root`: string base directory for relative manifest paths; defaults to `/app`.
- `problem_json`: string manifest path; defaults to `<root>/problem.json`.
- `max_expansions`: positive integer per-task state-search limit; defaults to `5000000`.
- `weight`: positive numeric missing-goal heuristic weight; defaults to `3`.

Its JSON stdout is `{ "ok": boolean, "results": [...] }`. A successful result reports `id`, `plan_output`, `steps`, and `expanded`. On any `ok: false`, read the reported task error, correct a runtime/path issue or raise the expansion bound, then execute the solver again. A command description is not completion: the command must actually be run so the output artifacts exist.

## Completion requirements

1. Confirm the solver reports `ok: true` and every entry in `/app/problem.json` now has a regular file at its declared `plan_output` path. Do not assume the manifest contains only a particular pair of tasks.
2. Each nonblank line of a plan must be precisely one grounded primitive:

   ```text
   action_name(object1, object2, ...)
   ```

   Use commas between arguments and no explanatory lines, costs, timestamps, or parenthesized PDDL syntax.
3. Never transfer action names, objects, or routes between problem files. The solver derives all types, constants, objects, action schemas, initial facts, and goals from each task's supplied domain/problem pair.

The solver grounds only type-compatible actions, searches the reachable propositional state space, and independently replays the recovered sequence before writing it. Replay checks declaration, arity, object types, equality, positive and negative preconditions, add/delete effects, and the complete goal. It explicitly rejects unsupported logical constructs rather than emitting an unvalidated plan.
