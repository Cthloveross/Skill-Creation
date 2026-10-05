---
name: pddl-tpp-batch-planner
description: Generate, replay-validate, and write function-style plans for every typed classical PDDL travelling-purchase task listed in a problem.json manifest.
---

# PDDL TPP batch planner

Use this Skill for a manifest containing `id`, `domain`, `problem`, and `plan_output` fields. The solver reads the current PDDL files at runtime, rather than assuming any instance-specific action, object, route, or plan.

It supports the classical typed STRIPS subset used by the supplied TPP tasks: conjunctions, positive and negative literals, equality tests, and add/delete effects. Numeric bookkeeping effects such as `increase` are ignored, matching propositional plan replay; numeric preconditions, conditional effects, quantifiers, disjunction, derived predicates, and durative actions are rejected rather than being solved unsoundly.

## Required execution

The executor **must run the batch command below from the task runtime before returning the task result**. This creates a plan at every exact `plan_output` path declared in `/app/problem.json`; merely producing or inspecting the JSON report is not sufficient.

```bash
python3 /path/to/skill/scripts/solve_tpp.py <<'JSON'
{"root":"/app","problem_json":"/app/problem.json","max_expansions":2000000,"weight":3}
JSON
```

The script receives one JSON object on stdin and emits one JSON report on stdout.

Input fields:

- `root` optional base directory, default `/app`.
- `problem_json` optional manifest path, default `<root>/problem.json`.
- `max_expansions` optional positive integer per task, default `2000000`.
- `weight` optional positive number for weighted A* goal-literal guidance, default `3`.

Example report:

```json
{"ok":true,"results":[{"id":"task01","ok":true,"plan_output":"/app/task01.txt","steps":5,"expanded":18}]}
```

Do not use an ID filter for the final run: every manifest entry needs an output artifact. If any result has `ok: false`, do not claim completion. Resolve the reported unsupported construct or increase a justified search limit, then rerun the complete manifest.

## Output guarantee and validation

For each successfully solved entry, the script creates the parent directory of `plan_output` and writes only grounded actions, one per line, as:

```text
action_name(object1, object2)
```

It retains the PDDL action parameter order and names from the supplied domain/problem. Before writing a file it independently replays the plan from the problem initial state, checking action existence, arity, declared object types, equality, positive/negative preconditions, add/delete effects, and all goal literals. Thus the emitted plan is semantically validated, not merely formatted.
