---
name: validated-pddl-plan-writer
description: Generate and write a semantically replay-validated grounded PDDL plan for every task declared in a runtime problem.json manifest. Use for IPC-style classical typed PDDL, including Airport ground-traffic tasks, where plan files—not a chat answer—are the required artifacts.
---

# Validated PDDL plan writer

## Mandatory execution procedure

The deliverable is a plan file at **every** `plan_output` path declared by the runtime manifest. Never substitute displayed actions, a status report, or a plan for one task for these files.

1. Invoke the packaged script through the executor's `run_skill_script` capability:

   ```json
   {"manifest":"/app/problem.json","time_limit_sec":280}
   ```

   Use `scripts/solve_manifest.py` as the script path. The script reads each entry's own domain and problem files, searches its state space, replays the resulting plan, and writes it to the exact declared `plan_output` location.

2. Inspect the returned JSON. Completion requires `"ok": true` and every entry status equal to `"solved"`. A timeout, error, or unsolved entry is not completion: use its per-entry diagnostic and continue resolving that task rather than omitting its artifact.

3. Invoke the same script again to replay the files actually written:

   ```json
   {"mode":"validate-manifest","manifest":"/app/problem.json"}
   ```

   Finish only when it returns `"ok": true` and every result has `"valid": true`. This final check also confirms that every declared output path exists.

Do not modify the supplied PDDL files or `problem.json`. Only create or replace the paths named by `plan_output`.

## Output contract

Each nonempty plan file contains exactly one grounded action primitive on each line:

```text
action_name(object1, object2)
```

No headers, comments, timestamps, action counts, solver output, or prose are permitted. The script preserves domain action/object names (normalized as PDDL identifiers). An empty plan is written only when the complete goal holds in the initial state.

Each manifest entry is independent. In particular, Airport movement permissions, occupancy, safety constraints, and objects must be obtained from that entry's domain/problem pair; routes from another instance must not be reused.

## Script interface

`scripts/solve_manifest.py` reads one JSON object from stdin and emits one JSON object on stdout.

- Solve: `{"manifest":"/app/problem.json","time_limit_sec":280}`. `manifest` defaults to `problem.json`; the limit is per entry.
- Validate existing artifacts only: `{"mode":"validate-manifest","manifest":"/app/problem.json"}`.

The manifest may be a list or an object containing `tasks` or `problems`. Each entry must contain nonempty string `domain`, `problem`, and `plan_output` fields. Relative paths are resolved relative to the manifest file.

The implementation handles typed classical PDDL with conjunction, disjunction, negation, equality, quantifiers, conditional effects, and quantified effects. Numeric and durative planning are reported as unsupported instead of generating unchecked output. It uses static-precondition joins and forward A* over grounded actions, then independently checks types, preconditions, effects, and the whole goal before atomically writing each artifact.
