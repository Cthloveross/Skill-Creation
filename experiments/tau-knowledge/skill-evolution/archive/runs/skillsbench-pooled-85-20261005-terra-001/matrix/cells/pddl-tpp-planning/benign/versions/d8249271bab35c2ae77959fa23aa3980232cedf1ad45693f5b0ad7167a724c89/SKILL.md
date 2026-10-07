---
name: pddl-tpp-manifest-planner
description: Solve every typed classical travelling-purchase PDDL problem named by a JSON manifest, validate the plans by replay, and write function-style plan files at the manifest's exact output paths.
---

# PDDL TPP manifest planner

Use this Skill when `problem.json` contains tasks with `id`, `domain`, `problem`, and `plan_output`. The required deliverable is not a textual answer: it is a valid plan file at **every** live `plan_output` path in the manifest.

## Mandatory execution

Execute the packaged solver before finishing. It reads the current PDDL and manifest at runtime, generates plans, replays them, and creates the output artifacts itself.

```bash
python3 "$SKILL_DIR/scripts/solve_tpp.py" <<'JSON'
{"root":"/app","problem_json":"/app/problem.json","max_expansions":5000000,"weight":3}
JSON
```

If the script runner is used instead, invoke `scripts/solve_tpp.py` with the same JSON object on stdin. Do not merely report or describe this command. Inspect its JSON stdout: success requires top-level `ok` to be `true` and every element of `results` to have `ok: true`. If a task reaches its expansion limit, rerun with a larger positive `max_expansions`; if it reports a parse or unsupported-language error, resolve that error rather than inventing a plan.

The input JSON schema is:

- `root` (string, default `/app`): base directory for relative manifest paths.
- `problem_json` (string, default `<root>/problem.json`): manifest file.
- `max_expansions` (positive integer, default `5000000`): per-task search bound.
- `weight` (positive number, default `3`): weighted goal-count heuristic factor.

The stdout schema is `{ "ok": boolean, "results": [...] }`. A successful result supplies `id`, `plan_output`, `steps`, and `expanded`; a failed result supplies `id` and `error`.

## Completion checks

For every manifest entry, confirm that its exact `plan_output` exists after the successful solver run. Each nonblank line is written only as:

```text
action_name(object1, object2, ...)
```

The solver parses the current domain/problem, handles typed objects and type hierarchies, grounds only type-compatible actions, searches a propositional STRIPS state space, and replays the recovered plan from `:init`. Replay verifies action declaration, arity, types, positive and negative preconditions, equality, add/delete effects, and the complete goal before atomically replacing an output file. It preserves action parameter order and PDDL names. Numeric bookkeeping effects are ignored because they are not propositional facts in the requested plan validation; unsupported logical constructs fail explicitly.
