---
name: pddl-tpp-plan-writer
description: Solve a batch of classical STRIPS-style PDDL planning problems, especially travelling-purchase/logistics tasks with discrete resource-level objects, and write one validated action-per-line plan for every entry in problem.json.
---

# PDDL TPP plan writer

Use this Skill when `problem.json` lists PDDL domain/problem pairs and required plan-output paths. It reads the current files at runtime; it does not rely on object names, action signatures, routes, or plans from a previous instance.

## Procedure

1. Run the packaged entrypoint from the task work directory. It accepts a JSON object on stdin and emits a JSON summary on stdout:

   ```sh
   python3 /app/environment/skills/current/scripts/solve_batch.py <<'JSON'
   {"problem_json": "/app/problem.json", "seconds_per_problem": 90, "solver": "auto"}
   JSON
   ```

   `problem_json` is a JSON array whose entries have `domain`, `problem`, and `plan_output` fields. Relative paths are interpreted relative to the directory containing that JSON file. `solver` may be `auto` (first use Fast Downward if it is installed, then use the built-in planner), `builtin`, or `fast-downward`.

2. Inspect the JSON summary. A successful entry has `status: "solved"` and the script has created its requested `plan_output`. If an entry failed, do **not** treat a missing or partial plan as a solution. Increase `seconds_per_problem` or use an installed PDDL planner, then rerun only after diagnosing the reported unsupported construct, timeout, or unsolvability result.

3. Deliver the files at the exact `plan_output` locations. Each nonempty line is serialized as `action(arg1, arg2, ...)`, preserving parsed action and object names. Empty plans are written only when the initial state already satisfies the goal.

## Built-in planner and validation

The built-in fallback parses S-expressions, typed objects and type hierarchies, STRIPS positive/negative preconditions and add/delete effects. It grounds only bindings supported by positive state facts, performs greedy best-first forward search using a delete-relaxed planning-graph heuristic, retains predecessors, and reconstructs a grounded plan. It is intended for classical PDDL, including TPP encodings that represent quantities as objects and predicates.

Before any plan is written, the script independently replays every action from the initial state. Replay checks the action name, arity, object existence, parameter type compatibility, positive and negative preconditions, effects, and every final goal literal. Thus an external planner result is also rejected if it cannot be replayed by the supplied domain/problem parser.

Unsupported features such as numeric expressions, disjunction, quantifiers, conditional effects, or durative actions are reported explicitly rather than silently misinterpreted. The executor should then use a planner that supports the domain's declared PDDL features and still validate the resulting plan against the domain semantics.
