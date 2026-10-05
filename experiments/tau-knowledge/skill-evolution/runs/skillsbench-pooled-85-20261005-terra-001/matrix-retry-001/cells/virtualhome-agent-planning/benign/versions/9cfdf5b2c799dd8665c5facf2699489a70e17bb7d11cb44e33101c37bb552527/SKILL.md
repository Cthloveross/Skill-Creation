---
name: airport-pddl-batch-planner
version: 13.0.0
description: Generate, replay-validate, and write a grounded plan at every output path in a manifest of Airport PDDL tasks.
---

# Airport PDDL batch planner

Use this Skill for the supplied manifest-driven PDDL planning task. It reads the current `/app/problem.json`, not hardcoded task names, and writes a plan to **every** declared `plan_output` path. A plan printed to stdout, left in a temporary directory, or written beside this Skill is not a deliverable.

Run the batch entrypoint from the package directory:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":595,"planner_setup_timeout_sec":240,"per_task_timeout_sec":20,"fallback_timeout_sec":1}
JSON
```

The script first replay-validates any pre-existing output, then tries a bounded internal search for small instances before locating or building Fast Downward once for remaining instances. Every planner candidate is independently replayed with typed arguments, ADL formulae, conditional/quantified effects, and the full goal before it is atomically written at its exact manifest path. Completed valid outputs are therefore retained when a later task fails.

`solve_all.py` consumes one JSON object on stdin and emits one JSON report on stdout. Fields are:

- `problem_json` — manifest location; defaults to `/app/problem.json`.
- `timeout_sec` — total batch budget; defaults to 595.
- `planner_setup_timeout_sec` — budget to find/build Fast Downward; defaults to 240 so planning time remains.
- `per_task_timeout_sec` — upper bound for one external planning call; defaults to 20.
- `fast_downward` — optional Fast Downward driver path, avoiding discovery/build.
- `fallback_timeout_sec` and `fallback_max_expansions` — bounded internal BFS for small instances.

A successful report has `ok: true`, `solved == total`, and an empty `missing_outputs` list. Do not create blank placeholder files: an empty plan is committed only after replay establishes that the initial state already satisfies the complete goal. Output uses one `action(object, ...)` primitive per line with names from the paired PDDL files.
