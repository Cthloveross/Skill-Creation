---
name: pddl-airport-plan-generator
description: >-
  Solve a batch of PDDL ground-traffic (airport) planning tasks listed in a
  problem.json manifest. For each entry it loads the referenced PDDL domain and
  problem, invokes an available classical planner to produce a grounded plan,
  then writes the plan to the entry's plan_output path in the required
  one-action-per-line "name(arg1, arg2, ...)" format. Use whenever a task gives
  a problem.json whose items contain id/domain/problem/plan_output keys and asks
  for a valid PDDL plan file per item.
---

# PDDL airport plan generator

## When to use
The public task supplies `/app/problem.json` (path may differ) that is a JSON
**list** of objects, each with keys:

```json
{ "id": "...", "domain": ".../x.pddl", "problem": ".../y.pddl", "plan_output": "dir/id.txt" }
```

For every item you must: load the domain + problem PDDL, generate a plan that
solves the problem, and write it to `plan_output`, one grounded action per line.

## Required output format (critical)
The grader expects the exact style shown in the task opening, e.g.

```
drive(truck1, depot1, market1)
load(goods1, truck1, market1, level0, level1, level0, level1)
```

That is: lowercase/exact action name, then `(`, then the object arguments
separated by `, ` (comma + space), then `)`. A zero-argument action is written
`name()`. One action per line, no blank lines, no comments, no step numbers.
`scripts/solve_all.py` converts planner output (`(drive truck1 depot1 market1)`)
into this format automatically — do not hand-edit unless a check fails.

Action and object names must match those in the domain/problem exactly. The
converter preserves the tokens emitted by the planner (which come from the
parsed PDDL), so names stay consistent.

## Method
1. Read the manifest and resolve each `domain`, `problem`, and `plan_output`
   path. Relative paths are resolved against the directory that contains the
   manifest (normally `/app`).
2. For each task, run a classical planner subprocess with a per-task time
   limit, capture its grounded action sequence, convert to the required
   format, and write the file (creating parent directories).
3. Backends, tried in order (`backend: "auto"`):
   - **Fast Downward** if a `fast-downward.py` binary (or `$FAST_DOWNWARD`) is
     on PATH — handles ADL (quantifiers / conditional effects) that airport
     domains may use. Uses the `lama-first` satisficing alias.
   - **pyperplan** (pure Python, pip-installable, no build) with greedy
     best-first + FF heuristic — handles STRIPS / typed / negative-precondition
     encodings. The grounded (large) airport domains are often propositional
     STRIPS, which pyperplan can parse.
   The script auto-installs pyperplan via pip when internet is allowed and it is
   not already importable.
4. If a task cannot be solved within its timeout or the planner rejects the
   domain, the script still **creates** the `plan_output` file (empty) so the
   deliverable path exists, and records the failure in its JSON summary. Prefer
   raising the per-task timeout or supplying Fast Downward for ADL domains
   rather than fabricating actions.

The airport domain is a ground-traffic graph: legal movement depends on
direction, occupancy, and safety-separation predicates derived from action
preconditions/effects, not mere adjacency. Do **not** write routes by hand from
segment names — let the planner respect those preconditions.

## Running the entrypoint
Scripts read a JSON object on stdin and print a JSON object on stdout; plan
files are written as a side effect.

```bash
echo '{"problem_json": "/app/problem.json", "per_task_timeout": 120, "backend": "auto"}' \
  | python3 /app/environment/skills/current/scripts/solve_all.py
```

Input fields (all optional):
- `problem_json` (default `/app/problem.json`)
- `base_dir` (default: directory of the manifest) — base for relative paths
- `per_task_timeout` seconds (default `120`)
- `backend` one of `auto` (default), `fd`, `pyperplan`

Output JSON:
```json
{"results":[{"id":"...","plan_output":"...","status":"solved|empty|error",
              "num_actions":N,"backend":"fd|pyperplan|none","detail":"..."}],
 "summary":{"total":N,"solved":N,"empty":N,"error":N}}
```

`status`:
- `solved` — a non-empty plan was written.
- `empty`  — no plan found; an empty file was created at `plan_output`.
- `error`  — manifest/path problem; see `detail`.

## Local verification (not grading)
After running, confirm every expected file exists and is syntactically shaped:

```bash
echo '{"problem_json": "/app/problem.json"}' \
  | python3 /app/environment/skills/current/scripts/check_outputs.py
```

This checks each `plan_output` exists and every non-blank line matches
`name(arg, ...)`. It reports counts of empty / malformed files so you can raise
timeouts or install Fast Downward before resubmitting. It does not perform full
semantic PDDL validation; if a VAL/Fast-Downward validator is available you may
replay plans, but syntactic shape plus the planner's own validity is the
baseline guarantee here.

## Assumptions and limits
- Needs `python3`. pyperplan is installed on demand when internet is allowed.
- Very large (Munich-scale) grounded instances may exceed memory/time on a
  single CPU with 2 GB; those tasks fall back to `empty`. Partial coverage of
  the solvable (smaller) instances is still produced.
- Do not hardcode any instance's actions, ids, or expected plans; always read
  the manifest and the current PDDL files at runtime.
