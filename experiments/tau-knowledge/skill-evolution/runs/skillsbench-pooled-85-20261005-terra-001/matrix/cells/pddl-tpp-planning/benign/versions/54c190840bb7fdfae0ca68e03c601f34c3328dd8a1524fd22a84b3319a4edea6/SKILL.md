---
name: pddl-tpp-batch-planner
description: Generate, replay-validate, and write function-style plans for every typed classical travelling-purchase PDDL task listed in a problem.json manifest.
---

# PDDL TPP batch planner

Use this Skill for a task with a `problem.json` array of entries containing `id`, `domain`, `problem`, and `plan_output` fields. The solver reads the current domain and problem files at runtime. It never reuses object names, routes, or plans from another task.

## Required execution step

**Run the packaged solver before returning the task result.** The plan files are not part of the Skill package and are created only when this command executes in the task runtime. Do not merely inspect or describe the script.

From the directory containing this `SKILL.md`, execute:

```bash
python3 scripts/solve_tpp.py <<'JSON'
{"root":"/app","problem_json":"/app/problem.json","max_expansions":5000000,"weight":3}
JSON
```

If the package directory differs from the current directory, invoke `scripts/solve_tpp.py` through its absolute package path. Do not select only some manifest entries: the script must process every entry in `/app/problem.json`.

The script consumes one JSON object from stdin and writes one JSON report to stdout. Its request fields are:

- `root` (string, default `/app`): base for relative manifest paths.
- `problem_json` (string, default `<root>/problem.json`): manifest path.
- `max_expansions` (positive integer, default `5000000`): per-task search limit.
- `weight` (positive number, default `3`): weighted best-first goal-count heuristic multiplier.

Its report has the form:

```json
{"ok":true,"results":[{"id":"task01","ok":true,"plan_output":"/app/task01.txt","steps":5,"expanded":18}]}
```

A `false` task result is not a completed deliverable. Read its error, correct a supported-runtime invocation issue or raise the search limit when appropriate, and run the complete manifest again. Before returning, require overall `ok: true` and ensure every reported `plan_output` exists at the exact path declared by the manifest.

## Solver behavior and validation

The supplied Python implementation supports the typed classical STRIPS PDDL subset used by TPP: typed objects and constants, conjunctions, positive and negative literals, equality tests, add/delete effects, and numeric bookkeeping `increase`, `decrease`, and `assign` effects. Numeric assignments and metrics are ignored because they do not change propositional action applicability in this TPP representation. Unsupported disjunction, quantification, implication, conditional effects, derived predicates, and numeric comparisons cause a reported failure rather than an unsound output.

For each task it parses the domain and problem, grounds only type-compatible actions, searches reachable propositional states, and independently replays the reconstructed plan. Replay verifies declared actions, argument arity and type, equality, positive and negative preconditions, add/delete effects, and every final goal literal.

For every successful entry, it creates the parent directory of the exact declared `plan_output` and atomically writes only grounded action primitives, one action per line:

```text
action_name(object1, object2)
```

The action and object names are preserved from the PDDL (lower-cased according to PDDL token parsing), and arguments follow the action parameter order. These output artifacts, rather than the JSON report, are the required deliverables.
