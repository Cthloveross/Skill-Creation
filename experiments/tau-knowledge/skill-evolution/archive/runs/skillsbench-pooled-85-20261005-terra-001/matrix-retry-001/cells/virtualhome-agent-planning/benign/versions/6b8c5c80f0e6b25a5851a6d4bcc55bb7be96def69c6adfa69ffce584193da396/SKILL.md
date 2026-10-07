---
name: airport-pddl-batch-planner
version: 10.0.0
description: Solve every domain/problem pair in a runtime PDDL manifest and atomically write independently replay-validated grounded plans at each declared output path.
---

# Airport PDDL batch planner

Use this Skill for manifest-driven classical PDDL planning tasks, especially the supplied Airport suite. The required deliverables are files at **every** `plan_output` path in the current manifest. A planner log, a successful command exit, or an uncommitted temporary plan is not a deliverable.

From this package directory, execute the batch entrypoint before completion:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":595,"planner_setup_timeout_sec":520,"per_task_timeout_sec":120}
JSON
```

Do not stop after building a planner or after solving only one row. Inspect the JSON result and require all of:

- `ok` is `true`;
- `solved` equals `total`; and
- `missing_outputs` is empty.

The entrypoint reads the current manifest and PDDL files at runtime. It first independently validates any already-existing output and retains it only when it is a valid solution for the paired current inputs. It then locates or builds Fast Downward once, solves remaining rows in manifest order, validates every candidate by replaying it, and atomically commits each valid plan immediately. Thus, completed early plans survive a timeout or failure on a later task.

Plans use one grounded primitive per line in the requested syntax:

```text
action_name(object1, object2)
```

Action and object identifiers are taken only from the paired domain and problem files. Never create empty placeholders: an empty output is accepted only when the exact initial state satisfies the complete goal.

## Runtime interfaces

`scripts/solve_all.py` reads one JSON object on stdin and writes one JSON report on stdout. Inputs are:

- `problem_json`: manifest path, default `/app/problem.json`;
- `fast_downward`: optional Fast Downward driver path;
- `timeout_sec`: total batch wall-clock budget, default `595`;
- `planner_setup_timeout_sec`: build/installation budget, default `520`;
- `per_task_timeout_sec`: maximum solve time for one remaining row, default `120`.

`scripts/solve_pddl.py` accepts `domain`, `problem`, and `plan_output` to solve one task. Supplying `validate_plan` instead of `plan_output` performs replay validation only. Both scripts emit JSON including `ok`, `valid`, diagnostics, and action counts.

The packaged replayer checks declared action names, argument arity and types, positive/negative logical preconditions, conditional and quantified effects, and complete final-goal satisfaction. A candidate is written only after that validation succeeds.
