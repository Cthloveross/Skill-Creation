---
name: pddl-tpp-plan-publisher
description: Generate, validate, and publish one grounded function-style plan for every typed classical PDDL task listed in a runtime problem.json manifest.
---

# PDDL TPP plan publisher

Use this Skill when `/app/problem.json` is a JSON array whose entries contain `id`, `domain`, `problem`, and `plan_output`. The deliverable is **not** a chat response: it is a plan file at every exact `plan_output` path in the live manifest.

## Required execution

Call the packaged script with the Skill-script tool; it writes directly into the task sandbox:

```json
{"root":"/app","problem_json":"/app/problem.json","max_expansions":30000000,"weight":2}
```

Use `scripts/solve_tpp.py` as `relative_path`. Do this before declaring the task complete. The script reads the current PDDL files, solves every manifest entry independently, replays each plan, and atomically writes it to that entry's exact `plan_output` path. Absolute paths such as `/app/task01.txt` must remain absolute; never substitute package-relative output paths.

The script accepts one JSON object on stdin:

- `root` (optional string, default `/app`): base for relative paths.
- `problem_json` (optional string, default `<root>/problem.json`): manifest path.
- `max_expansions` (optional positive integer, default `5000000`): per-task search bound.
- `weight` (optional positive number, default `2`): weighted-A* heuristic multiplier.

It emits `{"ok":true,"results":[...]}` only when every manifest entry was solved, replayed, and published. Each success result includes `id`, `plan_output`, `steps`, and `expanded`. If `ok` is false because an expansion bound was reached, rerun with a larger bound. Do not replace a failure with a guessed plan.

## Required completion checks

After a successful script call, inspect the live manifest and confirm every listed `plan_output` is a regular file at precisely that path. Do not stop merely because the script returned without a tool error: require its JSON `ok` field to be true and require a successful result for every manifest entry.

The published files contain only one grounded action per nonblank line:

```text
action_name(object1, object2, ...)
```

No headings, comments, numbering, costs, JSON, or parenthesized whitespace-separated PDDL actions are permitted. The solver preserves identifiers from the current PDDL and validates arity, type hierarchy, equality, positive/negative preconditions, add/delete effects, and the complete goal by replay before publication.
