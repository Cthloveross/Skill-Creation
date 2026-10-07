---
name: airport-pddl-planner
version: 2.0.0
description: Solve each current Airport PDDL manifest entry, replay-check its grounded plan, and atomically create every declared plan_output artifact.
---

# Airport PDDL planner

Use this Skill for a manifest-driven PDDL artifact task. The required deliverable is not a solver transcript: it is a replay-valid plan file at **every** `plan_output` path in the current `/app/problem.json`.

## Execute the full manifest

Run the batch entrypoint from this Skill directory. It resolves relative manifest paths relative to the manifest, validates any pre-existing plans, locates or bootstraps Fast Downward once, solves tasks incrementally, and writes each accepted plan before starting the next task.

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":590,"planner_setup_timeout_sec":330}
JSON
```

If a Fast Downward wrapper is already available, provide it; this avoids any installation/build delay.

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","fast_downward":"/path/to/fast-downward.py","timeout_sec":590}
JSON
```

The command emits a JSON report. Completion requires `ok: true`, `missing_outputs: []`, and a successful replay result for every row. If the shared execution deadline interrupts a batch, rerun the same command. Valid files are retained after independent replay validation, so completed artifacts are never discarded and the next run concentrates on unresolved entries.

## Method and safeguards

- Each plan uses the exact domain/problem pair named in its manifest row; no airport graph, action name, object name, or route is assumed in advance.
- Planner output is parsed and replayed before it is written. Replay checks action existence, argument count, objects and type hierarchy, preconditions, conditional/quantified effects, and the complete final goal.
- Files are written atomically only after validation. The scripts never create placeholder, empty, fabricated, or replay-failing plan files.
- Output uses one grounded primitive per line in `action(arg1, arg2, ...)` syntax. PDDL identifiers are preserved (lower-case PDDL is canonicalized by parsing).
- One bounded planning slice is used per unresolved row. A plan produced before planner timeout is still recovered, replayed, and saved.

## JSON script interfaces

All scripts consume exactly one JSON object on stdin and emit one JSON object on stdout.

`solve_pddl.py` accepts:

```json
{"domain":"/app/airport/domain01.pddl","problem":"/app/airport/task01.pddl","plan_output":"/app/task01.txt","fast_downward":"/path/to/fast-downward.py","timeout_sec":30}
```

It returns `ok`, `valid`, `actions`, `plan_output`, `method`, and diagnostics. To validate without writing, supply `validate_plan` instead of `plan_output`.

`solve_all.py` accepts `problem_json`, optional `fast_downward`, optional `timeout_sec`, and optional `planner_setup_timeout_sec`. Its result has one record for each manifest row plus `missing_outputs`.
