---
name: airport-pddl-batch-planner
version: 9.0.0
description: Create and independently replay-validate a grounded PDDL plan at every path declared by a runtime planning manifest.
---

# Airport PDDL batch planner

Use this Skill for the supplied manifest-driven Airport PDDL tasks. The deliverable is a valid file at **every** `plan_output` in `/app/problem.json`; planner logs and successful command exit codes are not deliverables.

Run the batch entrypoint from the package directory before finishing:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":590,"planner_setup_timeout_sec":360,"per_task_timeout_sec":120}
JSON
```

The entrypoint reads current PDDL files and the manifest at runtime. It preserves only an existing plan which replays successfully, finds or builds Fast Downward once, solves rows in manifest order, replays each candidate against its paired domain/problem, and atomically writes each valid plan immediately. This ordering and immediate commit are intentional: a long later instance must not discard completed required artifacts.

Inspect its JSON report. Completion requires `ok: true`, `solved == total`, and `missing_outputs: []`. If a row fails, use its stated domain/problem pair and rerun; never create an empty placeholder. An empty plan is valid only if the exact initial state already satisfies the complete goal.

Plans are written one action per line as `action_name(object1, object2)`. Action and object names come only from the current paired PDDL files.

## JSON interfaces

`scripts/solve_all.py` reads one JSON object from stdin and emits one report object. Inputs are `problem_json` (default `/app/problem.json`), optional `fast_downward`, `timeout_sec`, `planner_setup_timeout_sec`, and `per_task_timeout_sec`.

`scripts/solve_pddl.py` solves one pair with `domain`, `problem`, and `plan_output`; it also supports replay-only requests using `validate_plan` instead of `plan_output`. Both scripts emit `ok`, `valid`, diagnostics, and action counts. The replayer checks action names, argument arity and types, logical preconditions, conditional/quantified effects, and the full final goal.
