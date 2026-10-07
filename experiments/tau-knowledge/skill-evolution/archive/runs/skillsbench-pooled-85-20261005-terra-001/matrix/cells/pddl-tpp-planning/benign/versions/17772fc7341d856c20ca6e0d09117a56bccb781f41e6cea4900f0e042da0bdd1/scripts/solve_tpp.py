#!/usr/bin/env python3
"""Solve and publish plans for a manifest of finite classical typed PDDL tasks.

Input on stdin is a JSON object with optional root, problem_json,
max_expansions, and weight fields. Output on stdout is a JSON status object.
For every solved entry the validated plan is written to its plan_output path.
"""
import heapq
import itertools
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


class PDDLError(Exception):
    pass


def parse_sexpr(path):
    text = Path(path).read_text(encoding="utf-8")
    text = re.sub(r";[^\n]*", "", text).lower()
    tokens = re.findall(r"\(|\)|[^\s()]+", text)
    index = 0

    def read_one():
        nonlocal index
        if index >= len(tokens):
            raise PDDLError("unexpected end of PDDL")
        token = tokens[index]
        index += 1
        if token == "(":
            value = []
            while index < len(tokens) and tokens[index] != ")":
                value.append(read_one())
            if index >= len(tokens):
                raise PDDLError("unclosed parenthesis")
            index += 1
            return value
        if token == ")":
            raise PDDLError("unexpected closing parenthesis")
        return token

    tree = read_one()
    if index != len(tokens) or not isinstance(tree, list) or not tree or tree[0] != "define":
        raise PDDLError("expected one PDDL define expression")
    return tree


def section(tree, key):
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] == key:
            return item[1:]
    return None


def typed_names(items):
    """Return ordered (name, type) pairs from a PDDL typed-name sequence."""
    output, pending, index = [], [], 0
    while index < len(items):
        value = items[index]
        if not isinstance(value, str):
            raise PDDLError("malformed typed-name list")
        if value == "-":
            if not pending or index + 1 >= len(items) or not isinstance(items[index + 1], str):
                raise PDDLError("malformed typed-name list")
            output.extend((name, items[index + 1]) for name in pending)
            pending = []
            index += 2
        else:
            pending.append(value)
            index += 1
    output.extend((name, "object") for name in pending)
    return output


def atom(expr, context):
    if (not isinstance(expr, list) or not expr or not isinstance(expr[0], str)
            or any(isinstance(x, list) for x in expr[1:])):
        raise PDDLError("expected predicate atom in " + context)
    return tuple(expr)


def conjunction(expr, context, effects=False):
    """Convert an and/not classical formula to positive and negative atoms."""
    if not isinstance(expr, list) or not expr:
        raise PDDLError("malformed " + context)
    op = expr[0]
    if op == "and":
        positive, negative = [], []
        for child in expr[1:]:
            child_positive, child_negative = conjunction(child, context, effects)
            positive.extend(child_positive)
            negative.extend(child_negative)
        return positive, negative
    if op == "not":
        if len(expr) != 2:
            raise PDDLError("malformed negation in " + context)
        return [], [atom(expr[1], context)]
    if effects and op in {"increase", "decrease", "assign", "scale-up", "scale-down"}:
        # The public replay semantics treat numeric bookkeeping separately.
        return [], []
    if op in {"or", "imply", "when", "forall", "exists", "oneof", ">", "<", ">=", "<="}:
        raise PDDLError("unsupported construct " + op + " in " + context)
    return [atom(expr, context)], []


def read_domain(path):
    tree = parse_sexpr(path)
    parents = {"object": None}
    parents.update(dict(typed_names(section(tree, ":types") or [])))
    constants = typed_names(section(tree, ":constants") or [])
    schemas = []
    for item in tree[1:]:
        if not isinstance(item, list) or len(item) < 2 or item[0] != ":action":
            continue
        name = item[1]
        if not isinstance(name, str):
            raise PDDLError("invalid action name")
        fields, index = {}, 2
        while index < len(item):
            if (not isinstance(item[index], str) or not item[index].startswith(":")
                    or index + 1 >= len(item)):
                raise PDDLError("malformed action " + name)
            fields[item[index]] = item[index + 1]
            index += 2
        parameters = typed_names(fields.get(":parameters", []))
        if any(not variable.startswith("?") for variable, _ in parameters):
            raise PDDLError("action parameter is not a variable")
        positive, negative = conjunction(fields.get(":precondition", ["and"]), "precondition")
        add, delete = conjunction(fields.get(":effect", ["and"]), "effect", True)
        if any(pred[0] == "=" for pred in add + delete):
            raise PDDLError("equality effects are unsupported")
        schemas.append((name, parameters, positive, negative, add, delete))
    if not schemas:
        raise PDDLError("domain declares no actions")
    return parents, constants, schemas


def read_problem(path):
    tree = parse_sexpr(path)
    init = section(tree, ":init")
    goal = section(tree, ":goal")
    if init is None or goal is None or len(goal) != 1:
        raise PDDLError("problem requires :init and exactly one :goal formula")
    state = set()
    for fact in init:
        # Match the supplied evaluator's treatment of equality and explicit negation in init.
        if isinstance(fact, list) and fact and fact[0] in {"=", "not"}:
            continue
        positive, _ = conjunction(fact, "initial state")
        state.update(positive)
    goal_positive, goal_negative = conjunction(goal[0], "goal")
    return typed_names(section(tree, ":objects") or []), frozenset(state), goal_positive, goal_negative


def is_subtype(actual, required, parents):
    visited = set()
    while actual is not None and actual not in visited:
        if actual == required:
            return True
        visited.add(actual)
        actual = parents.get(actual)
    return False


def substitute(value, binding):
    return binding[value] if value.startswith("?") else value


def ground(predicate, binding):
    return tuple(substitute(value, binding) for value in predicate)


def holds(positive, negative, state, binding):
    def present(predicate):
        if predicate[0] == "=":
            if len(predicate) != 3:
                raise PDDLError("equality requires two terms")
            return substitute(predicate[1], binding) == substitute(predicate[2], binding)
        return ground(predicate, binding) in state
    return all(present(predicate) for predicate in positive) and all(
        not present(predicate) for predicate in negative
    )


def apply_effect(state, add, delete, binding):
    remove = {ground(predicate, binding) for predicate in delete}
    insert = {ground(predicate, binding) for predicate in add}
    return frozenset((set(state) - remove) | insert)


def applicable_instances(schema, state, objects, parents):
    """Yield applicable ground instances, using positive facts to bind variables first."""
    name, parameters, positive, negative, add, delete = schema
    fact_index = defaultdict(list)
    for fact in state:
        fact_index[fact[0]].append(fact)
    patterns = sorted((p for p in positive if p[0] != "="), key=lambda p: len(fact_index[p[0]]))
    partials = [{}]
    for pattern in patterns:
        next_partials = []
        for binding in partials:
            for fact in fact_index[pattern[0]]:
                if len(fact) != len(pattern):
                    continue
                candidate, matches = dict(binding), True
                for term, value in zip(pattern[1:], fact[1:]):
                    if term.startswith("?"):
                        if term in candidate and candidate[term] != value:
                            matches = False
                            break
                        candidate[term] = value
                    elif term != value:
                        matches = False
                        break
                if matches:
                    next_partials.append(candidate)
        partials = next_partials
        if not partials:
            return

    choices = []
    for variable, required_type in parameters:
        values = [obj for obj, actual_type in objects.items()
                  if is_subtype(actual_type, required_type, parents)]
        if not values:
            return
        choices.append((variable, values))

    for partial in partials:
        if any(variable in partial and partial[variable] not in values for variable, values in choices):
            continue
        missing = [(variable, values) for variable, values in choices if variable not in partial]
        combinations = itertools.product(*(values for _, values in missing)) if missing else [()]
        for selected in combinations:
            binding = dict(partial)
            binding.update(zip((variable for variable, _ in missing), selected))
            if holds(positive, negative, state, binding):
                args = tuple(binding[variable] for variable, _ in parameters)
                yield name, args, apply_effect(state, add, delete, binding)


def replay(parents, schemas, objects, initial, goal_positive, goal_negative, plan):
    indexed = {schema[0]: schema for schema in schemas}
    state = initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in indexed:
            raise PDDLError("undeclared action at step %d" % step)
        _, parameters, positive, negative, add, delete = indexed[name]
        if len(args) != len(parameters):
            raise PDDLError("wrong arity at step %d" % step)
        for argument, (_, required_type) in zip(args, parameters):
            if argument not in objects or not is_subtype(objects[argument], required_type, parents):
                raise PDDLError("type error at step %d" % step)
        binding = dict(zip((variable for variable, _ in parameters), args))
        if not holds(positive, negative, state, binding):
            raise PDDLError("precondition failure at step %d" % step)
        state = apply_effect(state, add, delete, binding)
    if not holds(goal_positive, goal_negative, state, {}):
        raise PDDLError("final state does not satisfy goal")


def solve(parents, constants, schemas, declared, initial, goal_positive, goal_negative, limit, weight):
    objects = dict(constants)
    objects.update(dict(declared))
    if any(type_name not in parents for type_name in objects.values()):
        raise PDDLError("object has undeclared type")
    if holds(goal_positive, goal_negative, initial, {}):
        return [], 0, objects

    def heuristic(state):
        missing_positive = sum(not holds([predicate], [], state, {}) for predicate in goal_positive)
        violated_negative = sum(holds([predicate], [], state, {}) for predicate in goal_negative)
        return missing_positive + violated_negative

    serial = itertools.count()
    frontier = [(weight * heuristic(initial), 0, next(serial), initial)]
    distance, previous = {initial: 0}, {}
    expanded = 0
    while frontier:
        _, cost, _, state = heapq.heappop(frontier)
        if distance.get(state) != cost:
            continue
        if holds(goal_positive, goal_negative, state, {}):
            plan, cursor = [], state
            while cursor != initial:
                cursor, action = previous[cursor]
                plan.append(action)
            plan.reverse()
            replay(parents, schemas, objects, initial, goal_positive, goal_negative, plan)
            return plan, expanded, objects
        expanded += 1
        if expanded > limit:
            raise PDDLError("search expansion limit exceeded (%d)" % limit)
        for schema in schemas:
            for name, args, successor in applicable_instances(schema, state, objects, parents):
                new_cost = cost + 1
                if new_cost >= distance.get(successor, 10 ** 30):
                    continue
                distance[successor] = new_cost
                previous[successor] = (state, (name, args))
                priority = new_cost + weight * heuristic(successor)
                heapq.heappush(frontier, (priority, new_cost, next(serial), successor))
    raise PDDLError("state space exhausted without a plan")


def resolve(root, value):
    candidate = Path(value)
    return candidate if candidate.is_absolute() else root / candidate


def solve_entry(item, root, limit, weight):
    if not isinstance(item, dict):
        raise PDDLError("manifest entry is not an object")
    for key in ("id", "domain", "problem", "plan_output"):
        if not isinstance(item.get(key), str):
            raise PDDLError("manifest entry lacks string " + key)
    parents, constants, schemas = read_domain(resolve(root, item["domain"]))
    declared, initial, goal_positive, goal_negative = read_problem(resolve(root, item["problem"]))
    plan, expanded, objects = solve(
        parents, constants, schemas, declared, initial, goal_positive, goal_negative, limit, weight
    )
    replay(parents, schemas, objects, initial, goal_positive, goal_negative, plan)

    output = resolve(root, item["plan_output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(
        "".join("%s(%s)\n" % (name, ", ".join(args)) for name, args in plan),
        encoding="utf-8",
    )
    temporary.replace(output)
    return {
        "id": item["id"], "ok": True, "plan_output": str(output),
        "steps": len(plan), "expanded": expanded,
    }


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise PDDLError("request must be a JSON object")
        root = Path(request.get("root", "/app"))
        manifest_path = resolve(root, request.get("problem_json", str(root / "problem.json")))
        limit = request.get("max_expansions", 5000000)
        weight = request.get("weight", 2)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise PDDLError("max_expansions must be a positive integer")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0:
            raise PDDLError("weight must be a positive number")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, list) or not manifest:
            raise PDDLError("problem.json must be a nonempty array")
        results = []
        for item in manifest:
            try:
                results.append(solve_entry(item, root, limit, weight))
            except Exception as exc:
                ident = item.get("id", "<unknown>") if isinstance(item, dict) else "<unknown>"
                results.append({"id": ident, "ok": False, "error": str(exc)})
        print(json.dumps({"ok": all(result["ok"] for result in results), "results": results}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "results": []}, sort_keys=True))


if __name__ == "__main__":
    main()
