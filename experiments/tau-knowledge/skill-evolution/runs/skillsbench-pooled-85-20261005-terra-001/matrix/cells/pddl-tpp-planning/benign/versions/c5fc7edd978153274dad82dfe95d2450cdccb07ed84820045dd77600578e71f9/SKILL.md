---
name: pddl-tpp-manifest-planner
description: Solve every typed classical PDDL task named by a problem.json manifest and publish replay-validated function-style plans at the manifest's exact output paths.
---

# PDDL TPP manifest planner

Use this Skill for travelling-purchase and other finite, typed, classical PDDL tasks. The runtime manifest is a nonempty JSON array whose entries contain `id`, `domain`, `problem`, and `plan_output`.

## Mandatory execution step

The required deliverables are runtime files, not a textual plan description. **Before completing the task, execute the solver in the task sandbox.** From the Skill package directory, use the execution agent's terminal tool to run:

```bash
printf '%s\n' '{"root":"/app","problem_json":"/app/problem.json","max_expansions":30000000,"weight":2}' | python3 scripts/solve_tpp.py
```

Do not merely report or quote this command. It reads the current `/app/problem.json`, solves every entry independently, validates each plan by replay, and creates each entry's exact `plan_output` file. Absolute output paths, including paths such as `/app/task01.txt`, are written directly.

The script consumes one JSON object from stdin:

- `root` (optional string; default `/app`): base for relative manifest paths.
- `problem_json` (optional string; default `<root>/problem.json`): manifest path.
- `max_expansions` (optional positive integer; default `5000000`): limit per task.
- `weight` (optional positive number; default `2`): weighted-A* heuristic multiplier.

It emits one JSON status object on stdout. A successful run has `ok: true` and one successful result for every manifest entry. If any result has `ok: false`, do not complete the task: read its error, correct the available invocation/input issue or increase the search limit, then execute the solver again.

## Completion checks

After a successful solver run, confirm that every live manifest `plan_output` is a regular file. Do not assume a fixed number of tasks, filenames, objects, locations, or routes.

Each plan file contains only one grounded primitive per nonblank line in exactly this form:

```text
action_name(object1, object2, ...)
```

Do not add comments, headings, numbering, timestamps, costs, JSON, or parenthesized whitespace-PDDL syntax. The solver preserves identifiers from the supplied PDDL and checks action arity, object types, equality, positive and negative preconditions, add/delete effects, and complete final goals before it publishes a file.

The packaged solver intentionally supports finite propositional PDDL formulas composed of conjunction, negation, and equality. It rejects unsupported logical constructs rather than emitting a plan that has not been validated.
