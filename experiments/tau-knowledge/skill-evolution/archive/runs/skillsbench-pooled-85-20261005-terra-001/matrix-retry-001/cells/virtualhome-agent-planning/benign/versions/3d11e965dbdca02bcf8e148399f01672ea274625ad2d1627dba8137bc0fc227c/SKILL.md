---
name: airport-pddl-planner
version: 4.0.0
description: Solve every manifest-declared Airport PDDL instance, replay-validate each grounded plan, and write it to its required plan_output path.
---

# Airport PDDL planner

Use this Skill for the supplied manifest-driven Airport planning task. The required deliverables are the files named by **every** `plan_output` entry in `/app/problem.json`; a planner log alone is not a deliverable.

Run the batch entrypoint from the Skill package directory:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":590,"planner_setup_timeout_sec":260}
JSON
```

The script receives one JSON object on stdin and emits one JSON report on stdout. It reads the current manifest, domains, and problems at runtime. It first preserves any already replay-valid plans, then solves remaining rows one at a time. Each valid plan is replayed independently and atomically written before the next row is attempted, so rerunning the command retains completed required artifacts.

## Solver setup

The script locates an installed Fast Downward wrapper if available. Otherwise it clones and builds Fast Downward locally under `/app/.fast-downward`. The bootstrapper builds `release_no_lp` and explicitly selects that build when invoking the wrapper. This is important: Fast Downward wrappers otherwise commonly default to `release`, which does not exist after a no-LP-only build.

To use an existing wrapper explicitly:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","fast_downward":"/path/to/fast-downward.py","timeout_sec":590}
JSON
```

A success report has `ok: true`, `missing_outputs: []`, and a replay-valid result for every manifest row. If the report is not successful, rerun it with the remaining available build time; do not replace valid plans with placeholders.

## Guarantees and output format

- Plans use one `action(arg1, arg2, ...)` primitive per line, using exact action and object identifiers from the current PDDL files.
- The replayer checks action existence, parameter count, object typing and type inheritance, preconditions, conditional/quantified effects, and the complete final goal.
- Empty output is committed only if the initial state already satisfies the complete goal.
- No route, object identifier, action schema, or expected answer is hardcoded.

## Single-instance interface

`scripts/solve_pddl.py` accepts JSON such as:

```json
{"domain":"/app/airport/domain01.pddl","problem":"/app/airport/task01.pddl","plan_output":"/app/task01.txt","fast_downward":"/path/to/fast-downward.py","timeout_sec":30}
```

For validation only, provide `validate_plan` instead of `plan_output`. Its JSON response contains `ok`, `valid`, `actions`, and diagnostics.
