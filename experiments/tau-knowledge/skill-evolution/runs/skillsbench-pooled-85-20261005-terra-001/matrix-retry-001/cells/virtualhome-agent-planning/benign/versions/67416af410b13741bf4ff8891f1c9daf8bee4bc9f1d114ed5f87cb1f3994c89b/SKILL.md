---
name: airport-pddl-batch-planner
version: 11.0.0
description: Generate, replay-validate, and write one grounded PDDL plan for every domain/problem row in a runtime manifest, with an internal search fallback and Fast Downward acceleration.
---

# Airport PDDL batch planner

Use this Skill for the supplied manifest-driven Airport PDDL tasks. The required result is a plan file at **every** current `plan_output` path in `/app/problem.json`; printing plans or leaving plans in temporary files does not satisfy the task.

Run the batch entrypoint from this package directory:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":595,"fallback_timeout_sec":3,"planner_setup_timeout_sec":300,"per_task_timeout_sec":20}
JSON
```

The script reads the manifest and paired PDDL files at runtime. It first replays existing outputs and retains only valid ones. It then makes a short internal grounded-search attempt for every unresolved task, committing each replay-valid result immediately. Remaining tasks are passed to Fast Downward, which is located or built once. Each candidate is independently replayed before its file is atomically committed, so a timeout on a later task cannot remove earlier deliverables.

Require the final JSON report to have `ok: true`, `solved == total`, and an empty `missing_outputs` list. If it does not, use the reported failing row and rerun with an available planner path via `fast_downward`; do not create empty or synthetic placeholder files.

Plans are serialized as one primitive per line:

```text
action_name(object1, object2)
```

The scripts accept JSON on stdin and emit JSON on stdout. `solve_all.py` accepts `problem_json`, optional `fast_downward`, total/setup/per-task timeouts, and `fallback_timeout_sec`. `solve_pddl.py` accepts `domain`, `problem`, `plan_output`, optional planner settings, or `validate_plan` to replay an existing plan only.

Validation checks action existence, arity, object types, positive/negative and quantified preconditions, conditional/quantified effects, and the complete final goal. An empty file is written only if the exact initial state already satisfies the goal.
