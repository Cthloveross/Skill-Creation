---
name: airport-pddl-planner
version: 1.0.0
description: Solve classical typed PDDL airport-ground-traffic tasks specified by a problem.json manifest, validate every returned grounded plan by replay, and write one action(args) primitive per output line. Use when each task supplies PDDL domain/problem paths and an output path.
---

# Airport PDDL planning

Use this Skill for the supplied airport planning tasks. It reads the current domain and problem files at execution time; it never assumes airport topology, action names, aircraft names, or a plan from another instance.

## Method

1. Read `/app/problem.json` (or the supplied manifest path). Each entry must contain `domain`, `problem`, and `plan_output`.
2. Prefer a capable installed Fast Downward executable for realistic airport instances. Set `FAST_DOWNWARD=/path/to/fast-downward.py`, or pass `fast_downward` in the JSON input. The solver is invoked with its documented `seq-sat-lama-2011` alias and a temporary plan file.
3. The packaged parser/replayer reads typed PDDL, grounds each returned action against the actual schema, checks types, positive and negative preconditions, applies add/delete effects, and checks every final goal literal. Invalid external output is never written.
4. If Fast Downward is unavailable or fails, the dependency-free fallback performs bounded greedy best-first state-space search over applicable, type-compatible grounded actions. It is useful for small instances but is intentionally not a replacement for a competitive planner on the largest Munich maps.
5. Write only validated plan lines in the required form, e.g. `move_aircraft(plane1, seg_a, seg_b)`. Do not add comments, costs, timestamps, explanations, or parentheses-only PDDL output to a task's plan file.

The parser supports the classical typed STRIPS fragment used by this task: conjunctions of positive/negative literals and add/delete effects. It rejects quantified, conditional, numeric, or disjunctive constructs instead of silently treating them as valid classical plans.

## Run all manifest tasks

The scripts receive JSON on stdin and emit one JSON report on stdout. From the Skill directory, run:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","fast_downward":"/path/to/fast-downward.py","timeout_sec":540}
JSON
```

`fast_downward` is optional when `FAST_DOWNWARD` is set or `fast-downward.py`/`fast-downward` is on `PATH`. The report has `ok`, `solved`, and one result per manifest task. Stop and diagnose if any result has `ok: false`; do not submit a missing or failed plan as though it solved the task.

## Run or validate one task

```bash
python3 scripts/solve_pddl.py <<'JSON'
{"domain":"/app/airport/domain01.pddl","problem":"/app/airport/task01.pddl","plan_output":"/app/out/plan.txt","fast_downward":"/path/to/fast-downward.py","timeout_sec":300}
JSON
```

For validation of a pre-existing plan without solving, use:

```bash
python3 scripts/solve_pddl.py <<'JSON'
{"domain":"DOMAIN","problem":"PROBLEM","validate_plan":"PLAN_FILE"}
JSON
```

The single-task result includes `valid`, action count, and, on failure, the first failed action/precondition or unsatisfied goal. A successful write is performed only after semantic replay succeeds.

## Operational notes

- Paths in `problem.json` may be absolute or relative to the manifest's directory.
- If Fast Downward is not installed, an execution agent may install/build it using its normal runtime facilities before invoking this Skill; this package does not claim that any solver is preinstalled.
- Keep the domain/problem pairing from each manifest row. Domain maps and constraints can differ between rows.
- Search limits (`max_states`, default 250000) affect only the fallback. Increase them only if memory/time permits.
