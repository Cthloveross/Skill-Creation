---
name: pddl-tpp-manifest-planner
description: Generate and publish replay-validated function-style plans for every finite typed classical PDDL task listed in a runtime problem.json manifest.
---

# PDDL TPP manifest planner

Use this Skill when a task provides a `problem.json` array with `domain`, `problem`, and `plan_output` fields and requires one executable PDDL plan per entry.

## Required runtime action

The deliverable is the set of files named by the live manifest, not a plan shown in chat. **Run the packaged solver before completing the task.** Use the Skill-script execution capability on `scripts/solve_tpp.py` with this JSON input:

```json
{"root":"/app","problem_json":"/app/problem.json","max_expansions":30000000,"weight":2}
```

The script reads the current manifest and PDDL files at runtime, independently solves each entry, replays the plan, and writes directly to each exact `plan_output` path. This includes absolute paths such as `/app/task01.txt`; do not substitute package-relative output paths.

Its stdin schema is one JSON object:

- `root`: optional base directory for relative paths; defaults to `/app`.
- `problem_json`: optional manifest path; defaults to `<root>/problem.json`.
- `max_expansions`: optional positive integer search bound per task; defaults to `5000000`.
- `weight`: optional positive numeric weighted-A* heuristic multiplier; defaults to `2`.

The stdout schema is `{"ok": boolean, "results": [...]}`. Each successful result has `id`, `plan_output`, `steps`, and `expanded`. A failed result has `id` and `error`.

Do not finish after describing the invocation. Require `ok: true` and one successful result for every manifest entry. If a search bound is reached, rerun the same script with a larger positive `max_expansions`; do not emit a guessed plan.

## Output contract and checks

After the successful run, verify that every path in the current manifest exists as a regular file. Every nonblank line must be exactly one grounded primitive in this format:

```text
action_name(object1, object2, ...)
```

Do not add headings, comments, step numbers, costs, JSON, or whitespace-separated parenthesized PDDL syntax. The solver preserves PDDL identifiers and validates declared action names, arity, type hierarchy, equality, positive and negative preconditions, add/delete effects, and all goal literals before publishing each file.

The solver supports finite propositional classical PDDL formulas formed from conjunction, negation, and equality, which covers the supplied TPP-style planning representation. It fails explicitly rather than publishing an unvalidated result for unsupported logical constructs.
