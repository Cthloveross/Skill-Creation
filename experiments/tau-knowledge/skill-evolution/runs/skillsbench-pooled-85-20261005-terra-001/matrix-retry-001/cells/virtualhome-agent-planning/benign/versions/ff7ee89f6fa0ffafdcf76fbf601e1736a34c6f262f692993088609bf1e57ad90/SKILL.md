---
name: airport-pddl-batch-planner
version: 6.0.0
description: Solve every PDDL Airport instance named by a manifest, replay-validate each grounded plan, and atomically write every required plan_output artifact.
---

# Airport PDDL batch planner

Use this Skill for the manifest-driven Airport planning task. The required deliverables are plan files at **every** `plan_output` path in `/app/problem.json`; a planner log or a successful solver process alone is not a deliverable.

From the Skill package directory, run the batch entrypoint before finishing:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":590,"planner_setup_timeout_sec":180,"per_task_timeout_sec":45}
JSON
```

The entrypoint reads the current manifest, domains, and problems at runtime. It first replay-validates any pre-existing output, then obtains Fast Downward once, solves unresolved manifest rows in order, independently replays every proposed plan, and atomically commits each validated plan immediately. Consequently, completed outputs remain available if a later instance times out. Do not replace an already replay-valid plan with an unvalidated result.

Fast Downward may be supplied explicitly when it is already installed:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","fast_downward":"/path/to/fast-downward.py","timeout_sec":590,"per_task_timeout_sec":45}
JSON
```

Otherwise the script locates a normal installation or clones and builds Fast Downward once under `/app/.fast-downward`. It uses the public runtime network and requires the ordinary `git`, CMake, C++ compiler, and Python prerequisites. A failed bootstrap is reported as a failure; it must not be mistaken for a generated plan.

## Required output properties

- Each nonblank output line is one grounded action, serialized as `action(arg1, arg2, ...)`.
- Action and object identifiers are taken only from the paired runtime PDDL files.
- The bundled replayer checks action existence, arity, type inheritance, ADL preconditions, conditional/quantified effects, and the complete final goal.
- Empty plans are accepted only if the exact initial state satisfies the complete goal.
- The JSON batch report has `ok: true` only when every declared output exists and has passed replay validation.

## Script interfaces

`scripts/solve_all.py` reads one JSON object from stdin and emits a JSON batch report to stdout. Input fields are `problem_json` (default `/app/problem.json`), optional `fast_downward`, `timeout_sec`, `planner_setup_timeout_sec`, and `per_task_timeout_sec`.

`scripts/solve_pddl.py` handles one instance. Its solve input requires `domain`, `problem`, and `plan_output`; optional fields are `fast_downward`, `fast_downward_build`, and `timeout_sec`. For replay-only validation, use `validate_plan` instead of `plan_output`, for example:

```json
{"domain":"/app/airport/domain01.pddl","problem":"/app/airport/task01.pddl","validate_plan":"/app/task01.txt"}
```

Its JSON response includes `ok`, `valid`, action count when available, and a diagnostic on failure.
