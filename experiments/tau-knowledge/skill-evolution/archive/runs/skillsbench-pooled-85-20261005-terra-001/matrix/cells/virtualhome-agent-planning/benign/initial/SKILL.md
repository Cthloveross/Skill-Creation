---
name: pddl-airport-plan-generation
description: Solve classical typed PDDL planning tasks, especially IPC Airport ground-traffic instances, from a runtime manifest containing domain, problem, and plan-output paths. Use when valid one-action-per-line plans must be produced and semantically replayed before writing them.
---

# PDDL Airport Plan Generation

Use `scripts/solve_pddl.py` to load every task in a manifest, parse its actual PDDL domain and problem, obtain a plan, replay the plan against the parsed semantics, and write the requested plan files. The solver does not infer airport connectivity or action signatures from names: all objects, types, preconditions, effects, and goals are read from the current files.

The implementation supports the classical typed PDDL constructs normally used by Airport instances: STRIPS add/delete effects, negative preconditions, equality, conjunction/disjunction, quantifiers, implications, and conditional effects. It first attempts an installed Fast Downward driver when requested or available, then uses a built-in type- and static-fact-filtered grounded forward search. Every candidate, including an external planner's candidate, is replayed independently before it is written.

## Runtime inputs and outputs

The script reads one JSON object from stdin and emits one JSON report on stdout.

```json
{
  "manifest": "/app/problem.json",
  "time_limit_sec": 540,
  "planner": "auto"
}
```

- `manifest` is a JSON array of task objects with `domain`, `problem`, and `plan_output` fields. Paths may be absolute or relative to the current working directory (existing relative input paths are also tried relative to the manifest directory).
- Alternatively, provide `tasks` as that array directly.
- `time_limit_sec` is an optional per-task limit for built-in search. It defaults to 300 seconds.
- `planner` is `auto` (default), `fast-downward`, or `internal`. `auto` uses `fast-downward.py` or `downward` if either is installed; otherwise it uses the built-in solver. The built-in solver uses only Python's standard library.

For each solved task the program creates the exact `plan_output` path. Each line has the required interchange form `action(arg1, arg2, ...)`, using names parsed from the supplied PDDL. The JSON report has a `results` entry per task with `status`, path, plan length, and validation information. A non-`solved` status means no output should be treated as a valid plan.

Example execution by the task executor:

```bash
python3 scripts/solve_pddl.py <<'JSON'
{"manifest":"/app/problem.json","time_limit_sec":540,"planner":"auto"}
JSON
```

## Validation and failure handling

Use the same script to validate an already written plan without searching:

```bash
python3 scripts/solve_pddl.py <<'JSON'
{"mode":"validate","domain":"/app/airport/domain01.pddl","problem":"/app/airport/task01.pddl","plan":"/app/output.txt"}
JSON
```

Validation checks action existence, arity, argument types, positive and negative preconditions at every step, effects (including conditional effects), and the final complete goal. The result includes the first failing action and reason, or `valid: true`.

If parsing encounters unsupported numeric/durative constructs, if no planner finds a solution before the limit, or if replay fails, the script returns an explicit error/unsolved result rather than emitting an unchecked plan. For large instances, make an ordinary compatible planner such as Fast Downward available to the execution environment and select `auto` or `fast-downward`; do not substitute a guessed route or reuse another task's actions.
