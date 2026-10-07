---
name: pddl-tpp-batch-planner
description: Solve every typed classical travelling-purchase PDDL task in a problem.json manifest, validate each grounded plan by replay, and write function-style plan artifacts at the declared paths.
---

# PDDL TPP batch planner

Use this Skill when a task provides a `problem.json` array whose entries contain `id`, `domain`, `problem`, and `plan_output`. It reads the current PDDL files at runtime; it does not reuse routes, objects, or plans from another instance.

The packaged solver supports the typed classical STRIPS subset used by TPP: conjunctions, positive and negative literals, equality tests, add/delete effects, and numeric bookkeeping `increase`/`decrease`/`assign` effects that do not affect propositional applicability. Numeric initial assignments and metrics are ignored. It explicitly reports unsupported disjunction, quantification, conditional effects, derived predicates, or numeric comparisons instead of silently producing an unsound plan.

## Mandatory artifact-generation step

The executor must run the packaged script **before returning the task result**. Running this command is what creates the required plan artifacts; inspecting its JSON report alone is insufficient.

From the Skill package directory (the directory containing this `SKILL.md`), run:

```bash
python3 scripts/solve_tpp.py <<'JSON'
{"root":"/app","problem_json":"/app/problem.json","max_expansions":2000000,"weight":3}
JSON
```

If the package is invoked from another directory, use the absolute path to its `scripts/solve_tpp.py` instead. Do not filter entries: process every entry in the manifest. The script receives exactly one JSON object on stdin and emits one JSON object on stdout:

```json
{"ok":true,"results":[{"id":"task01","ok":true,"plan_output":"/app/task01.txt","steps":5,"expanded":18}]}
```

A result with `ok: false` means that task has no trustworthy output from this run. Resolve its reported PDDL construct or increase the justified search limit, then rerun the entire manifest. In particular, confirm that every `plan_output` reported by `problem.json` exists after a successful run.

## Output and validation

For every solved entry the script creates the parent directory for the exact declared `plan_output` path and writes only one grounded action per line:

```text
action_name(object1, object2)
```

Action argument order is the parameter order in the supplied domain. Before atomically writing the file, the script replays the candidate plan from the problem initial state and checks action existence, arity, object declarations and types, equality, positive and negative preconditions, add/delete effects, and all goal literals. Therefore a generated plan is semantically validated as well as serialized in the requested function-style syntax.
