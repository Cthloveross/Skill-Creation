---
name: runtime-pddl-airport-planner
description: Generate and validate grounded classical PDDL plans for a problem manifest containing domain, problem, and plan_output paths. Use for IPC-style airport/ground-traffic tasks where plans must be written one action per line.
---

# Runtime PDDL Airport Planner

Use this Skill when supplied PDDL domain/problem files and a JSON manifest whose entries contain `domain`, `problem`, and `plan_output` paths. The planner derives action names, object names, types, preconditions, and effects from the supplied files; it does not use airport naming conventions or precomputed routes.

## Entry point

Run from the directory containing this Skill:

```sh
python3 scripts/plan_pddl.py --manifest /app/problem.json --timeout 560
```

The script writes every successful plan at that entry's `plan_output` path, creating parent directories if needed. It emits a JSON status object on stdout. It returns a nonzero status and does not write a purported solution for an unsolved, unsupported, or timed-out instance.

The command-line interface is also available through JSON stdin for orchestration:

```sh
printf '%s\n' '{"manifest":"/app/problem.json","timeout":560}' | python3 scripts/plan_pddl.py
```

Input JSON schema: `{"manifest": string, "timeout"?: number, "max_expansions"?: integer}`. `timeout` is a shared wall-clock budget in seconds. Output JSON has `ok` plus one result per manifest entry; each result reports its paths, action count on success, or a diagnostic error.

## Method

1. Parse comments-free PDDL S-expressions at runtime. The implementation supports typed objects and hierarchy, `:action` schemas, conjunction/disjunction and negation in conditions, equality, ordinary add/delete effects, and conditional (`when`) effects.
2. Identify predicates changed by any effect. Unchanged predicates are static and are used to ground each schema efficiently before search; remaining parameter combinations are constrained by declared types.
3. Search the joint dynamic state space using duplicate detection, predecessor reconstruction, and a goal-missing best-first ordering. Applicability is checked against all positive and negative preconditions, including static facts and equality. This naturally retains aircraft occupancy/safety interactions in the same state rather than independently routing aircraft.
4. Replay the reconstructed plan before writing it. Replay checks the grounded action signature, every precondition, all effects (including applicable conditional effects), and the complete final goal.
5. Serialize each primitive exactly as `action(object1, object2, ...)`, one primitive per line, using symbols parsed from the current domain/problem.

The included parser is intentionally a classical propositional/STRIPS-style planner. It rejects durative actions, quantified conditions/effects, derived predicates, and numeric fluents instead of silently emitting an invalid plan. If this happens, inspect the reported construct and use a PDDL engine that explicitly supports that feature, then independently validate and serialize the resulting plan in the required line format.

## Validation

Successful planning already performs an independent replay. To validate existing files without planning again, provide the same manifest and use:

```sh
python3 scripts/plan_pddl.py --manifest /app/problem.json --validate-only
```

Each referenced plan must contain one `name(args)` action per nonblank line (the validator also accepts parenthesized whitespace PDDL actions). A validation result of `ok: true` means every action was applicable from the declared initial state and a goal alternative was true at the end.
