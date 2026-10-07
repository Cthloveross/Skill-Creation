---
name: airport-pddl-batch-planner
version: 5.0.0
description: Generate, replay-validate, and write a grounded PDDL plan at every plan_output path in a manifest of Airport planning instances.
---

# Airport PDDL batch planner

Use this Skill for the manifest-driven Airport PDDL task. The deliverable is **not** a solver log: it is a valid plan file at every `plan_output` location declared in `/app/problem.json` (including `/app/task01.txt` when declared).

From the Skill package directory, run this actual batch command before finishing:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":590,"planner_setup_timeout_sec":300}
JSON
```

The entrypoint reads the current manifest and PDDL files at runtime. It checks any pre-existing output by replay, then solves unresolved entries one at a time. A plan is independently replayed against its exact domain/problem and atomically written immediately after validation. Thus already completed artifacts survive a timeout or a later failure; rerunning the same command only works on missing or invalid outputs.

The script first uses an explicitly supplied or installed Fast Downward wrapper. If none is available, it clones and builds Fast Downward under `/app/.fast-downward` using the public network, then invokes its `release_no_lp` build. This requires the normal `git`, Python, CMake/compiler toolchain expected for Fast Downward. To select a known installation, pass its wrapper path:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","fast_downward":"/path/to/fast-downward.py","timeout_sec":590}
JSON
```

The JSON stdout report lists each output path and reports `ok: true` only when all manifest outputs exist and have passed replay validation. If it reports failure but some plans were completed, rerun it rather than overwriting completed plans.

## Output and validation guarantees

- Output is exactly one grounded `action(arg1, arg2, ...)` primitive per line.
- Action and object names are obtained from the supplied PDDL; none are instance-hardcoded.
- The replayer checks action schema existence, arity, type inheritance, positive/negative and quantified preconditions, conditional/quantified effects, and the full final goal.
- An empty output is accepted only when the initial state already satisfies the full goal.

## Single-instance interface

`scripts/solve_pddl.py` reads one JSON object from stdin and emits one JSON result. Required solve fields are `domain`, `problem`, and `plan_output`; optional fields are `fast_downward`, `fast_downward_build`, and `timeout_sec`.

For validation without solving, replace `plan_output` with `validate_plan`:

```json
{"domain":"/app/airport/domain01.pddl","problem":"/app/airport/task01.pddl","validate_plan":"/app/task01.txt"}
```

Its response has `ok`, `valid`, `actions`, and either a method or a diagnostic error.