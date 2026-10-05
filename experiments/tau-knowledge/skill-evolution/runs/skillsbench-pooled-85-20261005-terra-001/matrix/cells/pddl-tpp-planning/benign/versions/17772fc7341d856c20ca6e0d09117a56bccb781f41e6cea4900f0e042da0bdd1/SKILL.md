---
name: pddl-tpp-plan-publisher
description: Solve every finite typed classical PDDL task in a runtime problem.json manifest and publish replay-validated plans to each exact plan_output path.
---

# PDDL TPP plan publisher

Use this Skill for tasks that provide a JSON array of PDDL planning entries with `domain`, `problem`, and `plan_output` fields. The required deliverable is the files named by the live manifest, not a plan displayed in a response.

## Mandatory execution step

Before completing the task, invoke the packaged script through the Skill-script runtime:

```json
{"root":"/app","problem_json":"/app/problem.json","max_expansions":30000000,"weight":2}
```

Use `scripts/solve_tpp.py` as the script path. This invocation reads the current PDDL inputs, searches each task independently, replays each resulting plan, and writes the files directly to the corresponding manifest `plan_output` paths. In particular, absolute output paths such as `/app/task01.txt` must be created as files in `/app`; do not write package-relative substitutes.

The script accepts one JSON object on stdin:

- `root` (optional string): base for relative manifest and PDDL paths; default `/app`.
- `problem_json` (optional string): manifest path; default `<root>/problem.json`.
- `max_expansions` (optional positive integer): per-task search bound; default `5000000`.
- `weight` (optional positive number): weighted-A* heuristic multiplier; default `2`.

It emits `{"ok": boolean, "results": [...]}` on stdout. A successful result reports `id`, `plan_output`, `steps`, and `expanded`; a failed result reports `id` and `error`.

Do not stop after explaining this invocation. Require `ok` to be true and require one successful result for every manifest entry. If a task reaches the search bound, invoke the same script again with a larger `max_expansions`. Never publish a guessed action sequence.

## Completion checks

After a successful invocation, confirm that every exact path in the runtime manifest is a regular file. The script publishes only after independently replaying the plan from the task's `:init` state and checking parameter arity, type hierarchy, equality, positive and negative preconditions, add/delete effects, and all goal literals.

Each nonblank output line has exactly this required serialization:

```text
action_name(object1, object2, ...)
```

Do not add headings, comments, action numbers, costs, JSON, or parenthesized whitespace-separated PDDL actions. The script uses only the action and object identifiers parsed from the current domain/problem files. It explicitly fails unsupported non-classical formulas rather than creating an unvalidated output.
