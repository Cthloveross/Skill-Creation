---
name: airport-pddl-planner
version: 3.0.0
description: Generate, replay-validate, and write a grounded Airport PDDL plan at every output path declared by the current manifest.
---

# Airport PDDL planner

Use this Skill for the manifest-driven Airport planning task. The deliverable is a plan file at **every** `plan_output` location in `/app/problem.json`; a planner transcript is not a deliverable.

From this Skill directory, run the manifest entrypoint once with the complete available build window:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","timeout_sec":590,"planner_setup_timeout_sec":250}
JSON
```

If Fast Downward is already installed, passing its wrapper avoids build time:

```bash
python3 scripts/solve_all.py <<'JSON'
{"problem_json":"/app/problem.json","fast_downward":"/path/to/fast-downward.py","timeout_sec":590}
JSON
```

The script consumes one JSON object on stdin and emits one JSON report on stdout. A successful result has `ok: true`, `missing_outputs: []`, and one replay-valid result per manifest row. It processes every row incrementally: existing plans are first replayed, and each new plan is validated and atomically committed before work begins on another row. Therefore rerunning the same command preserves already-completed valid artifacts.

## Planning and validation guarantees

- The script reads the domain, problem, and manifest at execution time. It does not assume airport routes, action schemas, object names, or goals.
- A Fast Downward plan is accepted only after independent replay from the supplied initial state. Replay checks action names, arity, declared object types and subtypes, preconditions, conditional and quantified effects, and the complete final goal.
- Plans are serialized as one `action(arg1, arg2, ...)` grounded primitive per line, using identifiers from the supplied PDDL.
- No placeholder, empty non-solution, or replay-failing file is written. An empty plan is accepted only when the initial state satisfies the complete goal.
- The bootstrapper prefers Fast Downward's `release_no_lp` configuration because these classical airport instances do not require LP support, and falls back to a normal release only when time remains.

## Individual interface

`solve_pddl.py` also accepts one instance:

```json
{"domain":"/app/airport/domain01.pddl","problem":"/app/airport/task01.pddl","plan_output":"/app/task01.txt","fast_downward":"/path/to/fast-downward.py","timeout_sec":30}
```

For validation without writing, replace `plan_output` with `validate_plan`. The response includes `ok`, `valid`, `actions`, and diagnostic information.
