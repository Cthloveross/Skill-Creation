---
name: airport-pddl-planner
version: 1.2.0
description: Solve every typed IPC Airport PDDL task declared by a manifest, validate each grounded plan by replay, and write the required per-task plan_output artifacts.
---

# Airport PDDL planner

Use this Skill to complete the artifact task. The required result is a valid, nonempty plan file at **every** `plan_output` path declared in the current manifest, not merely a solver report.

## Execute the batch entry point

Run the following from the Skill directory. The entry point reads the current runtime files, finds Fast Downward if already installed, or (when necessary) clones and builds it once under `/app/.fast-downward`. It then solves rows incrementally: every successful task is replay-validated and atomically written before the next task begins.

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":590}
JSON
```

To use a preinstalled planner explicitly, provide its wrapper path:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","fast_downward":"/path/to/fast-downward.py","timeout_sec":590}
JSON
```

The script emits one JSON report. Completion is successful only if `ok` is `true`, `missing_outputs` is empty, and every result has `valid: true`. Do not treat a successful process exit, planner log, or a blank file as a solution.

## Method and safeguards

- Manifest-relative paths are resolved against the manifest directory; absolute paths are retained.
- A Fast Downward plan is parsed into grounded actions, then replayed against the exact paired domain and problem before it is written.
- Replay checks action names, arity, type hierarchy, ADL boolean formulae, equality, quantifiers, conditional/quantified effects, all preconditions, and the complete final goal.
- The batch runner gives each remaining task a bounded share of the remaining wall-clock budget. It continues after an individual failure, so completed artifacts remain available rather than being lost to a later timeout.
- The previous bounded Python fallback is intentionally not run automatically: exhaustive grounding can consume the entire batch budget on realistic airport maps. Set `"allow_fallback": true` only for a known small STRIPS instance.

## Interfaces

All scripts receive one JSON object on stdin and emit one JSON object on stdout.

`solve_pddl.py` accepts:

```json
{"domain":"/app/airport/domain01.pddl","problem":"/app/airport/task01.pddl","plan_output":"/app/task01.txt","timeout_sec":60}
```

It returns `ok`, `valid`, `actions`, `method`, `plan_output`, and diagnostics. To validate an existing file without changing it, use `validate_plan` instead of `plan_output`.

`solve_all.py` accepts `problem_json`, optional `fast_downward`, `timeout_sec`, `planner_build_timeout_sec`, and optional `allow_fallback`. It returns an entry for every manifest row plus `missing_outputs`.

If Fast Downward cannot be found or built, the report identifies the setup error and no invalid output is written. Repair planner availability and rerun the batch; never substitute fabricated or empty plans.
