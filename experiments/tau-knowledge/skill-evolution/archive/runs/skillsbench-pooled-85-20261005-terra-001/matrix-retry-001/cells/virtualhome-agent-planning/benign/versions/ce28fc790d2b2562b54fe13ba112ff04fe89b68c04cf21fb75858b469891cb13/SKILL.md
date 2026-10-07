---
name: airport-pddl-batch-planner
version: 7.0.0
description: Generate, replay-validate, and write a grounded plan at every plan_output declared by a PDDL Airport task manifest.
---

# Airport PDDL batch planner

Use this Skill for the manifest-driven Airport planning task. A successful planner process is not sufficient: the deliverables are valid plan files at **every** `plan_output` path in `/app/problem.json`.

Run the batch entrypoint from the Skill package directory before finishing:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":590,"planner_setup_timeout_sec":360,"per_task_timeout_sec":100}
JSON
```

The entrypoint loads the current runtime manifest and its paired PDDL files. It first retains only existing plans that independently replay successfully. It then locates or bootstraps Fast Downward once, solves remaining rows incrementally, replay-validates every candidate against the exact domain/problem pair, and atomically writes each validated plan immediately. Thus a completed `/app/task01.txt` is preserved even if a later task fails.

An already-installed Fast Downward driver can be supplied explicitly:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","fast_downward":"/path/to/fast-downward.py","timeout_sec":590}
JSON
```

When no driver is supplied, bootstrap uses the public runtime network to clone and build Fast Downward under `/app/.fast-downward`. It requires normal `git`, CMake, C++ compiler, and Python facilities. If bootstrap or planning fails, the JSON report says so; it must never be treated as evidence that artifacts exist.

## Output and validation requirements

- Every manifest row must produce its exact `plan_output` file.
- Each nonblank line is one grounded primitive rendered as `action(arg1, arg2, ...)`.
- Names are taken exclusively from that row's supplied PDDL domain and problem.
- The bundled replayer checks action existence, parameter arity and type inheritance, ADL preconditions, conditional and quantified effects, and every final goal conjunct.
- An empty file is written only when the problem's initial state already satisfies its complete goal.
- The batch result has `ok: true` only if every declared artifact exists and has passed replay validation.

## JSON interfaces

`scripts/solve_all.py` reads one JSON object on stdin and emits one JSON report on stdout. Supported input fields are `problem_json` (default `/app/problem.json`), optional `fast_downward`, `timeout_sec`, `planner_setup_timeout_sec`, and `per_task_timeout_sec`.

`scripts/solve_pddl.py` handles one row. Solve mode requires `domain`, `problem`, and `plan_output`; optional fields are `fast_downward`, `fast_downward_build`, and `timeout_sec`. Replay-only mode replaces `plan_output` with `validate_plan`, for example:

```json
{"domain":"/app/airport/domain01.pddl","problem":"/app/airport/task01.pddl","validate_plan":"/app/task01.txt"}
```

It returns JSON containing `ok`, `valid`, action count where applicable, and a diagnostic on failure.
