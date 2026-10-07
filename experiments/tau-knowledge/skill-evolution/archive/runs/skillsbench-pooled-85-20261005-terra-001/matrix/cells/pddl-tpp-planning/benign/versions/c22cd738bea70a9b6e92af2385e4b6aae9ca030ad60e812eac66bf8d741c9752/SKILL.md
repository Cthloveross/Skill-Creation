---
name: pddl-tpp-manifest-planner
description: Generate, validate, and write function-style grounded plans for every typed classical PDDL travelling-purchase problem listed in a JSON manifest.
---

# PDDL TPP manifest planner

Use this Skill when `/app/problem.json` lists tasks with `id`, `domain`, `problem`, and `plan_output`. The task is incomplete until a plan artifact exists at **every exact `plan_output` path** in the live manifest. Do not merely explain a plan or report that a solver is available.

## Required execution

Immediately invoke the packaged solver in the task runtime. From the Skill package directory, use:

```bash
python3 scripts/solve_tpp.py <<'JSON'
{"root":"/app","problem_json":"/app/problem.json","max_expansions":20000000,"weight":3}
JSON
```

If the package directory differs from the current directory, invoke the package's `scripts/solve_tpp.py` by its actual package-relative location. Keep `/app/problem.json` and `/app` as the runtime inputs. This command is an execution step: it reads the current manifest and PDDL files, then creates the declared output files, including absolute output paths.

The script accepts one JSON object on stdin:

- `root` (optional string): base directory for relative manifest paths; default `/app`.
- `problem_json` (optional string): manifest path; default `<root>/problem.json`.
- `max_expansions` (optional positive integer): per-task search bound; default `5000000`.
- `weight` (optional positive number): missing-goal heuristic weight; default `3`.

It emits JSON on stdout: `{ "ok": boolean, "results": [...] }`. Each successful result includes `id`, `plan_output`, `steps`, and `expanded`. If a task reports an expansion-limit error, rerun with a higher `max_expansions`; do not finish while any manifest entry has `ok: false`.

## Required completion checks

1. Read the solver result and ensure top-level `ok` is true.
2. Ensure every current manifest entry has a regular file at its declared `plan_output`. Never assume a fixed number of entries or fixed output names.
3. Plan files contain only one grounded primitive on each nonblank line:

   ```text
   action_name(object1, object2, ...)
   ```

   Do not include prose, timestamps, costs, PDDL parenthesized syntax, or a solver transcript.
4. Do not reuse routes, actions, or object names from another problem. The solver parses each supplied domain/problem pair at runtime, grounds only type-compatible actions, searches reachable states, then replays the recovered plan before writing it.

The solver rejects unsupported logical constructs rather than emitting an unvalidated plan. Replay validates declared action names, argument count and types, equality, positive and negative preconditions, add/delete effects, and the complete final goal.
