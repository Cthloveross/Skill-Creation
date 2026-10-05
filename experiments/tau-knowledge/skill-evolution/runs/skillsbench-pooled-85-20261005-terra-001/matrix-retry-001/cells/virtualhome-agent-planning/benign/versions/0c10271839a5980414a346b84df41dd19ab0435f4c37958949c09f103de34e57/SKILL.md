---
name: airport-pddl-planner
version: 1.1.0
description: Generate and write validated grounded plans for every typed PDDL airport task declared in a problem.json manifest. Use for classical/ADL airport planning tasks with per-task plan_output files.
---

# Airport PDDL planner

Use this Skill to complete the artifact task, not merely to inspect or report on plans. The required result is a file at **every** `plan_output` declared by the current `/app/problem.json`.

## Required execution

1. Read the current manifest and retain each row's exact domain/problem pairing.
2. Ensure a capable ADL PDDL planner is available. Fast Downward is recommended for these IPC airport instances. If it is not already on `PATH`, install/build it through the execution environment's normal facilities and provide its `fast-downward.py` path.
3. Run the packaged batch entry point from the Skill directory. It invokes the planner, semantically replays every candidate plan against its paired PDDL files, and writes only plans that pass replay:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","fast_downward":"/path/to/fast-downward.py","timeout_sec":570}
JSON
```

`fast_downward` may be omitted only when `FAST_DOWNWARD`, `fast-downward.py`, or `fast-downward` resolves to a usable executable. The scripts emit a JSON report to stdout; `ok` must be true and `missing_outputs` must be empty before completion.

4. If any row fails, use the reported task id and reason to repair planner availability or increase the shared execution budget, then run the complete manifest again. Do not leave failed rows without output files and do not substitute blank files.

## Output and validation contract

- Each output has one grounded primitive per line in `action(object1, object2)` form. Action and object identifiers come from the current PDDL files.
- The bundled replayer checks action existence, arity, type hierarchy, ADL preconditions (`and`, `or`, `not`, `imply`, equality, quantifiers), conditional/quantified effects, and the complete final goal.
- Plan files are atomically replaced only after replay succeeds. Existing output files are not evidence of success; the batch entry point validates and regenerates all manifest rows.
- Relative paths in the manifest are resolved relative to the manifest directory. Absolute paths are preserved.

## Single-task interface

Scripts read one JSON object from stdin and emit one JSON object to stdout.

```bash
python3 scripts/solve_pddl.py <<'JSON'
{"domain":"/app/airport/domain01.pddl","problem":"/app/airport/task01.pddl","plan_output":"/app/task01.txt","fast_downward":"/path/to/fast-downward.py","timeout_sec":300}
JSON
```

To replay an existing candidate without changing it, pass `validate_plan` instead of `plan_output`. The response contains `ok`, `valid`, `actions`, and an error explaining the first replay failure when invalid.

The dependency-free fallback search is deliberately bounded and intended only for small STRIPS-like instances. It is not a replacement for Fast Downward on realistic Munich airport maps.
