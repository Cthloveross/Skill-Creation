# Implementation notes

## Output format contract
The task opening shows plans as `name(arg1, arg2, ...)`, one action per line.
This differs from the native PDDL plan syntax `(name arg1 arg2)` emitted by
most planners. `solve_all.py` parses planner output tokens and re-serializes
them into the required comma-separated, parenthesized-after-name style. Names
are preserved exactly as the planner (and therefore the parsed PDDL) produced
them, satisfying "action and object names must match the domain/problem".

Zero-argument actions become `name()`.

## Planner backends
- Fast Downward (`fast-downward.py`, or `$FAST_DOWNWARD`): preferred when
  present because it supports ADL (quantified preconditions, conditional
  effects) that the airport ground-traffic domain can use. Invoked with the
  satisficing `lama-first` alias; the anytime plan files `plan`, `plan.1`, ...
  are read and the last (best) one is used.
- pyperplan: pure-Python, installed via pip on demand. Supports STRIPS /
  typed / negative-precondition encodings. Many large (Munich-scale) airport
  domains in these suites are grounded/propositional, which pyperplan can
  parse. Run with greedy best-first search + FF heuristic (`-s gbf -H hff`),
  which finds satisficing plans quickly; it writes `<problem>.soln`.

The harness tries backends in order and keeps the first non-empty plan.

## Failure handling
- A task that cannot be solved within `per_task_timeout` yields an **empty**
  plan_output file (still created) and `status:"empty"`. This guarantees the
  deliverable path exists while making unsolved cases visible in the summary.
- Missing domain/problem files -> `status:"error"`, empty file still created.

## Tuning for coverage
- Raise `per_task_timeout` for the larger instances if time allows.
- Provide Fast Downward on PATH (or `$FAST_DOWNWARD`) to handle ADL encodings
  that pyperplan rejects.
- Smaller instances should solve under pyperplan alone; the single-CPU / 2 GB
  limit means the largest instances may remain `empty`.

## Do not hardcode
Always read the current `problem.json` and the referenced PDDL at runtime.
Never embed instance ids, object names, or precomputed action sequences into
the skill.
