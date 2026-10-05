---
name: airport-pddl-batch-planner
version: 12.0.0
description: Solve every manifest-listed Airport PDDL instance with Fast Downward, replay-validate each grounded result, and atomically write every declared plan_output file.
---

# Airport PDDL batch planner

Use this Skill for a manifest-driven collection of classical PDDL problems. It reads the current `/app/problem.json` and the exact domain/problem paths named by each row. The required artifact is a replay-valid plan file at **every** row's `plan_output` path; stdout, a temporary plan, or a plan in the package directory is not a deliverable.

Run this once from the package directory, allowing the full build budget:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":595,"planner_setup_timeout_sec":450,"per_task_timeout_sec":45}
JSON
```

`solve_all.py` first preserves only already-valid plans, locates or builds Fast Downward once, then solves manifest rows incrementally. Each candidate plan is parsed and independently replayed before it is atomically committed to the exact declared output path. Thus completed files remain present if a later planning attempt fails or times out.

The script receives one JSON object on stdin and emits one JSON report on stdout. Its accepted fields are:

- `problem_json`: manifest path (default `/app/problem.json`)
- `fast_downward`: optional path to an existing Fast Downward driver or executable
- `timeout_sec`: overall batch deadline
- `planner_setup_timeout_sec`: maximum time used to locate/build Fast Downward
- `per_task_timeout_sec`: cap for any one planner call
- `fallback_timeout_sec`: optional small internal-search attempt before external planning; default is disabled

Success requires `ok: true`, `solved == total`, and `missing_outputs: []`. If any row fails, use its report and rerun with more time or a valid `fast_downward` path. Do **not** create blank or synthetic files: a blank plan is valid only when replay establishes that the initial state already satisfies that row's complete goal.

Plans are written with one grounded primitive per line, for example `action_name(object1, object2)`. The validator checks action names, arity, subtype-compatible arguments, positive/negative and quantified formulae, conditional/quantified effects, and the complete final goal.
