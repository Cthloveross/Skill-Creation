---
name: airport-pddl-planner
version: 1.3.0
description: Generate, replay-validate, and write a grounded PDDL plan at every plan_output path in a current Airport planning manifest.
---

# Airport PDDL planner

Use this Skill for the supplied Airport PDDL artifact task. A run is complete only when **every** row in `/app/problem.json` has a nonempty, replay-valid plan at its declared `plan_output` path.

## Run once for the full manifest

From the Skill directory, run the batch entrypoint. It resolves manifest-relative paths from the manifest directory, reuses already valid output files, bootstraps Fast Downward only when it is not already available, and writes each validated result immediately before proceeding to the next task.

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":590}
JSON
```

If Fast Downward is already installed, provide its wrapper to avoid setup time:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","fast_downward":"/path/to/fast-downward.py","timeout_sec":590}
JSON
```

Read the JSON report after the command. Success requires `ok: true`, `missing_outputs: []`, and `valid: true` for every result. If the overall runtime ends before all rows are complete, rerun the same command: previously written plans are independently validated and retained, so the next run spends its time only on unresolved rows.

## Guarantees and validation

- The solver uses the exact domain and problem file paired by each manifest row; it does not infer airport topology or reuse object identifiers across tasks.
- Only a plan accepted by the packaged replayer is written. Replay checks action name, arity, object existence, type hierarchy, Boolean and quantified preconditions, conditional and quantified effects, and the complete final goal.
- Plans are serialized as one `action(arg1, arg2, ...)` primitive per line using the PDDL identifiers.
- Planner processes have a bounded per-instance slice so one hard task cannot prevent all later required files from being generated. A planner plan produced before its timeout is still recovered, validated, and written.
- The scripts never create empty, fabricated, or validation-failing plan files. Existing output files are counted only after replay succeeds.

## Script JSON interfaces

All scripts read one JSON object from stdin and write one JSON object to stdout.

`solve_pddl.py` accepts:

```json
{"domain":"/app/airport/domain01.pddl","problem":"/app/airport/task01.pddl","plan_output":"/app/task01.txt","timeout_sec":30}
```

It returns `ok`, `valid`, `actions`, `plan_output`, `method`, and diagnostics. To replay an existing plan without writing a file, pass `validate_plan` instead of `plan_output`.

`solve_all.py` accepts `problem_json`, optional `fast_downward`, optional `timeout_sec`, and optional `planner_setup_timeout_sec`. Its report contains one result per manifest row and a list of any still-missing outputs.
