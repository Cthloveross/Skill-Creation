---
name: pddl-tpp-manifest-planner
description: Generate, validate, and write function-style plans for every typed classical travelling-purchase PDDL task listed in a problem.json manifest.
---

# PDDL TPP manifest planner

Use this Skill for a task with a JSON manifest containing `id`, `domain`, `problem`, and `plan_output` fields. The deliverables are files at **every exact** `plan_output` path in the current manifest. A solver report alone is not a deliverable.

## Required execution step

Before finishing, execute `scripts/solve_tpp.py` using the execution agent's packaged-script runner with this JSON input:

```json
{"root":"/app","problem_json":"/app/problem.json","max_expansions":5000000,"weight":3}
```

Equivalently, when the package directory is available as `SKILL_DIR`, run:

```bash
python3 "$SKILL_DIR/scripts/solve_tpp.py" <<'JSON'
{"root":"/app","problem_json":"/app/problem.json","max_expansions":5000000,"weight":3}
JSON
```

The script reads the live manifest and PDDL files, solves **every** manifest entry, replays every recovered plan, and writes the required files itself. Do not stop after describing this command, and do not substitute guessed or handwritten plans.

The script receives one JSON object on stdin and emits one JSON object on stdout. `root` is the base for relative paths, `problem_json` selects the manifest, `max_expansions` is a positive per-task search limit, and `weight` is a positive heuristic weight. Inspect the emitted report: it must have `ok: true` and every result must have `ok: true`. If search reaches the limit, rerun with a larger positive `max_expansions` value.

## Output and validation contract

On success, each declared file contains only one grounded action per nonblank line:

```text
action_name(object1, object2)
```

The solver preserves the parsed action parameter order and uses names from the current PDDL. It supports typed STRIPS PDDL with type hierarchies, constants, conjunction, positive/negative literals, equality, add/delete effects, and ignored numeric bookkeeping effects. Unsupported logical constructs fail explicitly.

For each task the solver parses the supplied domain and problem at runtime, grounds only type-compatible actions, searches state space, and independently replays the selected sequence. Replay verifies declared actions, arity, types, positive and negative preconditions, equality, effects, and the complete final goal before the output is atomically written. After a successful run, confirm each reported `plan_output` exists at its manifest path.
