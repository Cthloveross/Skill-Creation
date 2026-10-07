#!/usr/bin/env python3
"""Manifest-driven solver for typed classical propositional PDDL.

Read a JSON object from stdin and emit JSON to stdout.  For every entry in the
manifest, write its validated plan to plan_output as action(arg, arg) lines.
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


def read_sexpr(filename):
    text = Path(filename).read_text(encoding="utf-8")
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    pos = 0

    def parse_one():
        nonlocal pos
        if pos >= len(tokens):
            raise PDDLError("unexpected end of PDDL")
        token = tokens[pos]
        pos += 1
        if token == "(":
            result = []
            while pos < len(tokens) and tokens[pos] != ")":
                result.append(parse_one())
            if pos == len(tokens):
                raise PDDLError("unclosed PDDL parenthesis")
            pos += 1
            return result
        if token == ")":
            raise PDDLError("unexpected closing parenthesis")
        return token

    tree = parse_one()
    if pos != len(tokens) or not isinstance(tree, list) or not tree or tree[0] != "define":
        raise PDDLError("expected exactly one PDDL define form")
    return tree


def section(tree, key):
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] == key:
            return item[1:]
    return None


def typed_names(items):
    result, pending = [], []
    index = 0
    while index < len(items):
        value = items[index]
        if not isinstance(value, str):
            raise PDDLError("malformed typed-name list")
        if value == "-":
            if not pending or index + 1 >= len(items) or not isinstance(items[index + 1], str):
                raise PDDLError("malformed typed-name list")
            result.extend((name, items[index + 1]) for name in pending)
            pending = []
            index += 2
        else:
            pending.append(value)
            index += 1
    result.extend((name, "object") for name in pending)
    return result


def atom(formula, context):
    if (not isinstance(formula, list) or not formula or not isinstance(formula[0], str)
            or any(isinstance(x, list) for x in formula[1:])):
        raise PDDLError("expected atom in " + context)
    return tuple(formula)


def literal_sets(formula, context, effect=False):
    """Return positive and negative atoms for an and/not-only PDDL formula."""
    if not isinstance(formula, list) or not formula:
        raise PDDLError("malformed " + context)
    operator = formula[0]
    if operator == "and":
        positive, negative = [], []
        for child in formula[1:]:
            cp, cn = literal_sets(child, context, effect)
            positive.extend(cp)
            negative.extend(cn)
        return positive, negative
    if effect and operator in {"increase", "decrease", "assign", "scale-up", "scale-down"}:
        # The public task evaluator treats these bookkeeping effects as non-facts.
        return [], []
    if operator == "not":
        if len(formula) != 2:
            raise PDDLError("malformed negation in " + context)
        return [], [atom(formula[1], context)]
    if operator in {"or", "imply", "when", "forall", "exists", "oneof", ">", "<", ">=", "<="}:
        raise PDDLError("unsupported logical construct " + operator + " in " + context)
    return [atom(formula, context)], []


def parse_domain(filename):
    tree = read_sexpr(filename)
    parents = {"object": None}
    parents.update(dict(typed_names(section(tree, ":types") or [])))
    constants = typed_names(section(tree, ":constants") or [])
    schemas = []
    for item in tree[1:]:
        if not (isinstance(item, list) and len(item) >= 2 and item[0] == ":action"):
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
            raise PDDLError("action parameter is not a variable: " + name)
        pre_pos, pre_neg = literal_sets(fields.get(":precondition", ["and"]), "precondition")
        add, delete = literal_sets(fields.get(":effect", ["and"]), "effect", True)
        if any(item[0] == "=" for item in add + delete):
            raise PDDLError("equality effects are unsupported")
        schemas.append((name, parameters, pre_pos, pre_neg, add, delete))
    if not schemas:
        raise PDDLError("domain declares no actions")
    return parents, constants, schemas


def parse_problem(filename):
    tree = read_sexpr(filename)
    initial = section(tree, ":init")
    goal = section(tree, ":goal")
    if initial is None or goal is None or len(goal) != 1:
        raise PDDLError("problem requires :init and exactly one :goal formula")
    state = set()
    for formula in initial:
        # Numeric initial assignments and explicit negative initial formulas do
        # not belong to the finite positive-fact state used by the public replay.
        if isinstance(formula, list) and formula and formula[0] in {"=", "not"}:
            continue
        positive, _ = literal_sets(formula, "initial state")
        state.update(positive)
    goal_pos, goal_neg = literal_sets(goal[0], "goal")
    return typed_names(section(tree, ":objects") or []), frozenset(state), goal_pos, goal_neg


def is_subtype(actual, required, parents):
    visited = set()
    while actual is not None and actual not in visited:
        if actual == required:
            return True
        visited.add(actual)
        actual = parents.get(actual)
    return False


def substitute(term, binding):
    return binding[term] if term.startswith("?") else term


def ground(predicate, binding):
    return tuple(substitute(term, binding) for term in predicate)


def formula_holds(positive, negative, state, binding):
    def contains(predicate):
        if predicate[0] == "=":
            if len(predicate) != 3:
                raise PDDLError("equality requires two terms")
            return substitute(predicate[1], binding) == substitute(predicate[2], binding)
        return ground(predicate, binding) in state
    return all(contains(p) for p in positive) and all(not contains(p) for p in negative)


def apply_effect(state, add, delete, binding):
    return frozenset((set(state) - {ground(p, binding) for p in delete}) |
                     {ground(p, binding) for p in add})


def applicable_instances(schema, state, objects, parents):
    name, parameters, pre_pos, pre_neg, add, delete = schema
    facts_by_predicate = defaultdict(list)
    for fact in state:
        facts_by_predicate[fact[0]].append(fact)
    patterns = sorted((p for p in pre_pos if p[0] != "="),
                      key=lambda p: len(facts_by_predicate[p[0]]))
    partial_bindings = [{}]
    for pattern in patterns:
        next_bindings = []
        for binding in partial_bindings:
            for fact in facts_by_predicate[pattern[0]]:
                if len(fact) != len(pattern):
                    continue
                candidate, valid = dict(binding), True
                for term, value in zip(pattern[1:], fact[1:]):
                    if term.startswith("?"):
                        if term in candidate and candidate[term] != value:
                            valid = False
                            break
                        candidate[term] = value
                    elif term != value:
                        valid = False
                        break
                if valid:
                    next_bindings.append(candidate)
        partial_bindings = next_bindings
        if not partial_bindings:
            return
    choices = []
    for variable, required_type in parameters:
        values = [obj for obj, actual_type in objects.items()
                  if is_subtype(actual_type, required_type, parents)]
        if not values:
            return
        choices.append((variable, values))
    for partial in partial_bindings:
        if any(variable in partial and partial[variable] not in values
               for variable, values in choices):
            continue
        missing = [(variable, values) for variable, values in choices if variable not in partial]
        products = itertools.product(*(values for _, values in missing)) if missing else [()]
        for picked in products:
            binding = dict(partial)
            binding.update(zip((variable for variable, _ in missing), picked))
            if formula_holds(pre_pos, pre_neg, state, binding):
                yield name, tuple(binding[v] for v, _ in parameters), apply_effect(state, add, delete, binding)


def replay(parents, schemas, objects, initial, goal_pos, goal_neg, plan):
    schema_by_name = {schema[0]: schema for schema in schemas}
    state = initial
    for step, (name, arguments) in enumerate(plan, 1):
        if name not in schema_by_name:
            raise PDDLError("undeclared action at step %d" % step)
        _, parameters, pre_pos, pre_neg, add, delete = schema_by_name[name]
        if len(parameters) != len(arguments):
            raise PDDLError("wrong action arity at step %d" % step)
        for argument, (_, required_type) in zip(arguments, parameters):
            if argument not in objects or not is_subtype(objects[argument], required_type, parents):
                raise PDDLError("type error at step %d" % step)
        binding = dict(zip((variable for variable, _ in parameters), arguments))
        if not formula_holds(pre_pos, pre_neg, state, binding):
            raise PDDLError("precondition failure at step %d" % step)
        state = apply_effect(state, add, delete, binding)
    if not formula_holds(goal_pos, goal_neg, state, {}):
        raise PDDLError("final state does not satisfy goal")


def solve(parents, constants, schemas, declared, initial, goal_pos, goal_neg, limit, weight):
    objects = dict(constants)
    objects.update(dict(declared))
    if any(type_name not in parents for type_name in objects.values()):
        raise PDDLError("object has undeclared type")
    if formula_holds(goal_pos, goal_neg, initial, {}):
        return [], 0, objects

    def heuristic(state):
        missing_positive = sum(not formula_holds([p], [], state, {}) for p in goal_pos)
        present_negative = sum(formula_holds([p], [], state, {}) for p in goal_neg)
        return missing_positive + present_negative

    counter = itertools.count()
    frontier = [(weight * heuristic(initial), 0, next(counter), initial)]
    distance, predecessor, expanded = {initial: 0}, {}, 0
    while frontier:
        _, cost, _, state = heapq.heappop(frontier)
        if distance.get(state) != cost:
            continue
        if formula_holds(goal_pos, goal_neg, state, {}):
            plan, current = [], state
            while current != initial:
                current, action = predecessor[current]
                plan.append(action)
            plan.reverse()
            replay(parents, schemas, objects, initial, goal_pos, goal_neg, plan)
            return plan, expanded, objects
        expanded += 1
        if expanded > limit:
            raise PDDLError("search expansion limit exceeded (%d)" % limit)
        for schema in schemas:
            for name, arguments, successor in applicable_instances(schema, state, objects, parents):
                new_cost = cost + 1
                if new_cost >= distance.get(successor, 10 ** 30):
                    continue
                distance[successor] = new_cost
                predecessor[successor] = (state, (name, arguments))
                heapq.heappush(frontier, (new_cost + weight * heuristic(successor),
                                          new_cost, next(counter), successor))
    raise PDDLError("state space exhausted without a plan")


def resolve(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def solve_entry(item, root, limit, weight):
    if not isinstance(item, dict):
        raise PDDLError("manifest entry is not an object")
    for key in ("id", "domain", "problem", "plan_output"):
        if not isinstance(item.get(key), str):
            raise PDDLError("manifest entry lacks string " + key)
    parents, constants, schemas = parse_domain(resolve(root, item["domain"]))
    declared, initial, goal_pos, goal_neg = parse_problem(resolve(root, item["problem"]))
    plan, expanded, objects = solve(parents, constants, schemas, declared, initial,
                                    goal_pos, goal_neg, limit, weight)
    replay(parents, schemas, objects, initial, goal_pos, goal_neg, plan)
    output = resolve(root, item["plan_output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text("".join("%s(%s)\n" % (name, ", ".join(args))
                                 for name, args in plan), encoding="utf-8")
    temporary.replace(output)
    return {"id": item["id"], "ok": True, "plan_output": str(output),
            "steps": len(plan), "expanded": expanded}


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise PDDLError("request must be a JSON object")
        root = Path(request.get("root", "/app"))
        manifest_name = request.get("problem_json", str(root / "problem.json"))
        limit = request.get("max_expansions", 5000000)
        weight = request.get("weight", 2)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise PDDLError("max_expansions must be a positive integer")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0:
            raise PDDLError("weight must be positive")
        manifest = json.loads(resolve(root, manifest_name).read_text(encoding="utf-8"))
        if not isinstance(manifest, list) or not manifest:
            raise PDDLError("problem.json must be a nonempty array")
        results = []
        for item in manifest:
            try:
                results.append(solve_entry(item, root, limit, weight))
            except Exception as exc:
                ident = item.get("id", "<unknown>") if isinstance(item, dict) else "<unknown>"
                results.append({"id": ident, "ok": False, "error": str(exc)})
        print(json.dumps({"ok": all(result["ok"] for result in results), "results": results},
                         sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "results": []}, sort_keys=True))


if __name__ == "__main__":
    main()
