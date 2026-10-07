---
name: airport-pddl-batch-planner
version: 8.0.0
description: Solve every PDDL Airport problem declared by a runtime manifest, replay-check each grounded plan, and atomically write each required plan_output artifact.
---

# Airport PDDL batch planner

Use this Skill for manifest-driven PDDL planning tasks. The required deliverable is not a planner log: it is a replay-valid plan file at **every** `plan_output` path in the current `/app/problem.json`.

From the package directory, actually run the batch entrypoint before finishing:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":585,"planner_setup_timeout_sec":240,"per_task_timeout_sec":300}
JSON
```

The script reads the manifest at runtime, resolves relative paths relative to that manifest, and first preserves any existing plan only if it independently replays successfully. It then locates Fast Downward or clones/builds it once under `/app/.fast-downward`, solves each remaining domain/problem pair, validates the emitted grounded actions against the exact pair, and atomically commits each validated file immediately. Do not treat an exit status, a planner message, or a partial batch report as proof that required artifacts exist.

An already installed Fast Downward driver may be supplied to avoid setup:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","fast_downward":"/path/to/fast-downward.py","timeout_sec":585}
JSON
```

## Required result checks

Inspect the JSON result. Completion requires `ok: true`, `solved == total`, an empty `missing_outputs` array, and one replay-valid file at each manifest `plan_output`. If the report identifies a failed row, resolve that row using its exact PDDL files and rerun; do not create empty or placeholder files for unsolved goals.

Plans are serialized with one grounded action per line as:

```text
action_name(object1, object2)
```

Only action and object identifiers parsed from the paired current domain/problem are used. Empty output is valid only when replay confirms that the initial state already satisfies the full goal.

## Script JSON interfaces

`scripts/solve_all.py` reads one JSON object on stdin and writes one JSON report on stdout. Inputs: `problem_json` (default `/app/problem.json`), optional `fast_downward`, `timeout_sec` (default 585), `planner_setup_timeout_sec` (default 240), and `per_task_timeout_sec` (default 300).

`scripts/solve_pddl.py` handles one domain/problem pair. Solve mode requires `domain`, `problem`, and `plan_output`; optional inputs are `fast_downward`, `fast_downward_build`, and `timeout_sec`. Replay-only mode uses `validate_plan` instead of `plan_output`, for example:

```json
{"domain":"/app/airport/domain01.pddl","problem":"/app/airport/task01.pddl","validate_plan":"/app/task01.txt"}
```

Both scripts return `ok`, `valid`, action counts where applicable, and diagnostics on failure. The bundled validator checks action names, arity, inherited types, ADL logical preconditions, conditional and quantified effects, and the complete final goal.
