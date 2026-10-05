---
name: pddl-manifest-plan-producer
description: Solve every typed classical-PDDL task declared by a runtime manifest and write a replay-validated grounded plan to each declared plan_output path. Use for IPC and Airport planning tasks where files are the required deliverable.
---

# PDDL manifest plan producer

The required deliverables are files, not a textual answer. Read the runtime manifest and treat **every** entry's `plan_output` as mandatory. Do not modify the manifest, domain, or problem inputs.

## Required executor workflow

1. Use the execution tool `run_skill_script` to run `scripts/solve_manifest.py` with:

   ```json
   {"manifest":"/app/problem.json","time_limit_sec":270}
   ```

   This call parses each entry's own domain/problem pair, searches for a plan, validates it by replay, and writes the result to the exact declared output path.

2. Do not stop after receiving a script response. Inspect it: completion requires `ok: true` and `status: "solved"` for every result. If an entry reports an error, timeout, or unsolved result, use that diagnostic to resolve the task and rerun the script; never omit that entry's output file.

3. Run the mandatory artifact replay check with the same tool:

   ```json
   {"mode":"validate-manifest","manifest":"/app/problem.json"}
   ```

   Finish only when `ok` is true and every result reports `valid: true`. This confirms the declared files actually exist, not merely that a plan was displayed or held in memory.

## Artifact format

Each nonempty output file has exactly one grounded action primitive per line:

```text
action_name(object1, object2)
```

No prose, headers, comments, timestamps, action counts, or solver logs may be written. An empty file is valid only if the corresponding initial state already satisfies its complete goal.

The solver preserves normalized PDDL action and object names. Each task is independent: derive route topology, movement permissions, occupancy, and safety constraints from that task's supplied PDDL rather than reusing a route from another task.

## Script interface

`scripts/solve_manifest.py` reads one JSON object on stdin and writes one JSON object on stdout.

- Solve and write artifacts: `{"manifest":"/app/problem.json","time_limit_sec":270}`.
- Validate existing artifacts only: `{"mode":"validate-manifest","manifest":"/app/problem.json"}`.

`manifest` defaults to `problem.json`. It may be a list or an object containing `tasks` or `problems`. Relative domain, problem, and output paths are resolved relative to the manifest. The implementation supports ordinary typed classical PDDL plus conjunction, disjunction, negation, equality, quantifiers, and conditional/quantified effects. It rejects malformed or unsupported numeric/durative input rather than emitting an unchecked plan.
