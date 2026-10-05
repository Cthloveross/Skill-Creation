#!/usr/bin/env python3
"""Solve typed, conjunction-only classical PDDL tasks from a JSON manifest.

JSON stdin -> JSON stdout.  The program reads instance files at runtime and
writes each plan to the corresponding manifest plan_output path.
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


def parse(path):
    text = Path(path).read_text(encoding="utf-8")
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    index = 0

    def one():
        nonlocal index
        if index >= len(tokens):
            raise PDDLError("unexpected end of PDDL")
        token = tokens[index]
        index += 1
        if token == "(":
            out = []
            while index < len(tokens) and tokens[index] != ")":
                out.append(one())
            if index >= len(tokens):
                raise PDDLError("unclosed PDDL parenthesis")
            index += 1
            return out
        if token == ")":
            raise PDDLError("unexpected closing PDDL parenthesis")
        return token

    tree = one()
    if index != len(tokens) or not isinstance(tree, list) or not tree or tree[0] != "define":
        raise PDDLError("expected one PDDL define form")
    return tree


def section(tree, name):
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] == name:
            return item[1:]
    return None


def typed(items):
    result, pending, i = [], [], 0
    while i < len(items):
        item = items[i]
        if not isinstance(item, str):
            raise PDDLError("malformed typed-name list")
        if item == "-":
            if not pending or i + 1 >= len(items) or not isinstance(items[i + 1], str):
                raise PDDLError("malformed typed-name list")
            result.extend((name, items[i + 1]) for name in pending)
            pending = []
            i += 2
        else:
            pending.append(item)
            i += 1
    result.extend((name, "object") for name in pending)
    return result


def atom(expr):
    if (not isinstance(expr, list) or not expr or not isinstance(expr[0], str)
            or any(isinstance(item, list) for item in expr[1:])):
        raise PDDLError("expected a propositional atom")
    return tuple(expr)


def literals(expr, where, effect=False):
    """Return (positive, negative) literals for a conjunction-only formula."""
    if not isinstance(expr, list) or not expr:
        raise PDDLError("malformed " + where)
    op = expr[0]
    if op == "and":
        positive, negative = [], []
        for child in expr[1:]:
            p, n = literals(child, where, effect)
            positive.extend(p)
            negative.extend(n)
        return positive, negative
    if effect and op in {"increase", "decrease", "assign", "scale-up", "scale-down"}:
        return [], []
    if op == "not":
        if len(expr) != 2:
            raise PDDLError("malformed negation in " + where)
        return [], [atom(expr[1])]
    if op in {"or", "imply", "when", "forall", "exists", ">", "<", ">=", "<="}:
        raise PDDLError("unsupported " + op + " in " + where)
    return [atom(expr)], []


def domain(path):
    tree = parse(path)
    parents = {"object": None}
    parents.update(dict(typed(section(tree, ":types") or [])))
    constants = typed(section(tree, ":constants") or [])
    schemas = []
    for item in tree[1:]:
        if not (isinstance(item, list) and len(item) >= 2 and item[0] == ":action"):
            continue
        name, fields, i = item[1], {}, 2
        while i < len(item):
            if (not isinstance(item[i], str) or not item[i].startswith(":")
                    or i + 1 >= len(item)):
                raise PDDLError("malformed action " + str(name))
            fields[item[i]] = item[i + 1]
            i += 2
        parameters = typed(fields.get(":parameters", []))
        if any(not variable.startswith("?") for variable, _ in parameters):
            raise PDDLError("invalid action parameter in " + name)
        pre_pos, pre_neg = literals(fields.get(":precondition", ["and"]), "precondition")
        add, delete = literals(fields.get(":effect", ["and"]), "effect", True)
        if any(item[0] == "=" for item in add + delete):
            raise PDDLError("equality effects are unsupported")
        schemas.append((name, parameters, pre_pos, pre_neg, add, delete))
    if not schemas:
        raise PDDLError("domain declares no actions")
    return parents, constants, schemas


def problem(path):
    tree = parse(path)
    raw_init = section(tree, ":init")
    raw_goal = section(tree, ":goal")
    if raw_init is None:
        raise PDDLError("problem has no init section")
    if raw_goal is None or len(raw_goal) != 1:
        raise PDDLError("problem has malformed goal")
    initial = set()
    for item in raw_init:
        if isinstance(item, list) and item and item[0] == "=":
            continue
        positive, negative = literals(item, "initial state")
        if negative:
            raise PDDLError("negative initial facts are unsupported")
        initial.update(positive)
    goal_pos, goal_neg = literals(raw_goal[0], "goal")
    return typed(section(tree, ":objects") or []), frozenset(initial), goal_pos, goal_neg


def subtype(actual, required, parents):
    seen = set()
    while actual is not None and actual not in seen:
        if actual == required:
            return True
        seen.add(actual)
        actual = parents.get(actual)
    return False


def subst(term, binding):
    return binding[term] if isinstance(term, str) and term.startswith("?") else term


def ground(literal, binding):
    return tuple(subst(term, binding) for term in literal)


def equality(literal, binding):
    if len(literal) != 3:
        raise PDDLError("equality must have exactly two terms")
    return subst(literal[1], binding) == subst(literal[2], binding)


def holds(positive, negative, state, binding):
    for literal in positive:
        present = equality(literal, binding) if literal[0] == "=" else ground(literal, binding) in state
        if not present:
            return False
    for literal in negative:
        present = equality(literal, binding) if literal[0] == "=" else ground(literal, binding) in state
        if present:
            return False
    return True


def transition(state, add, delete, binding):
    return frozenset((set(state) - {ground(item, binding) for item in delete}) |
                     {ground(item, binding) for item in add})


def successors(schema, state, object_types, parents):
    name, parameters, pre_pos, pre_neg, add, delete = schema
    by_predicate = defaultdict(list)
    for fact in state:
        by_predicate[fact[0]].append(fact)

    patterns = sorted((item for item in pre_pos if item[0] != "="),
                      key=lambda item: len(by_predicate[item[0]]))
    bindings = [{}]
    for pattern in patterns:
        next_bindings = []
        for binding in bindings:
            for fact in by_predicate[pattern[0]]:
                if len(fact) != len(pattern):
                    continue
                candidate, valid = dict(binding), True
                for term, value in zip(pattern[1:], fact[1:]):
                    if term.startswith("?"):
                        previous = candidate.get(term)
                        if previous is not None and previous != value:
                            valid = False
                            break
                        candidate[term] = value
                    elif term != value:
                        valid = False
                        break
                if valid:
                    next_bindings.append(candidate)
        bindings = next_bindings
        if not bindings:
            return

    choices = [(variable, [obj for obj, type_name in object_types.items()
                           if subtype(type_name, required, parents)])
               for variable, required in parameters]
    if any(not values for _, values in choices):
        return
    for binding in bindings:
        if any(variable in binding and binding[variable] not in values
               for variable, values in choices):
            continue
        missing = [(variable, values) for variable, values in choices if variable not in binding]
        products = itertools.product(*(values for _, values in missing)) if missing else [()]
        for values in products:
            candidate = dict(binding)
            candidate.update(zip((variable for variable, _ in missing), values))
            if holds(pre_pos, pre_neg, state, candidate):
                yield name, tuple(candidate[variable] for variable, _ in parameters), transition(state, add, delete, candidate)


def replay(parents, schemas, initial, goal_pos, goal_neg, object_types, plan):
    table = {schema[0]: schema for schema in schemas}
    state = initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in table:
            raise PDDLError("undeclared action at step %d" % step)
        _, parameters, pre_pos, pre_neg, add, delete = table[name]
        if len(args) != len(parameters):
            raise PDDLError("wrong action arity at step %d" % step)
        for value, (_, required) in zip(args, parameters):
            if value not in object_types or not subtype(object_types[value], required, parents):
                raise PDDLError("type error at step %d" % step)
        binding = dict(zip((variable for variable, _ in parameters), args))
        if not holds(pre_pos, pre_neg, state, binding):
            raise PDDLError("precondition failure at step %d" % step)
        state = transition(state, add, delete, binding)
    if not holds(goal_pos, goal_neg, state, {}):
        raise PDDLError("final state does not satisfy goal")


def solve(parents, constants, schemas, objects, initial, goal_pos, goal_neg, limit, weight):
    object_types = dict(constants)
    object_types.update(dict(objects))
    if any(type_name not in parents for type_name in object_types.values()):
        raise PDDLError("object uses an undeclared type")
    if holds(goal_pos, goal_neg, initial, {}):
        return [], 0

    def heuristic(state):
        missing = sum(not (equality(item, {}) if item[0] == "=" else item in state) for item in goal_pos)
        forbidden = sum(equality(item, {}) if item[0] == "=" else item in state for item in goal_neg)
        return missing + forbidden

    serial = itertools.count()
    frontier = [(weight * heuristic(initial), 0, next(serial), initial)]
    best, predecessor, expanded = {initial: 0}, {}, 0
    while frontier:
        _, cost, _, state = heapq.heappop(frontier)
        if best.get(state) != cost:
            continue
        if holds(goal_pos, goal_neg, state, {}):
            plan, current = [], state
            while current != initial:
                current, action = predecessor[current]
                plan.append(action)
            plan.reverse()
            replay(parents, schemas, initial, goal_pos, goal_neg, object_types, plan)
            return plan, expanded
        expanded += 1
        if expanded > limit:
            raise PDDLError("search expansion limit exceeded (%d)" % limit)
        for schema in schemas:
            for name, args, next_state in successors(schema, state, object_types, parents):
                next_cost = cost + 1
                if next_cost >= best.get(next_state, 10 ** 30):
                    continue
                best[next_state] = next_cost
                predecessor[next_state] = (state, (name, args))
                heapq.heappush(frontier, (next_cost + weight * heuristic(next_state), next_cost,
                                          next(serial), next_state))
    raise PDDLError("state space exhausted without a plan")


def resolve(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def process(entry, root, limit, weight):
    for key in ("id", "domain", "problem", "plan_output"):
        if key not in entry:
            raise PDDLError("manifest entry lacks " + key)
    parents, constants, schemas = domain(resolve(root, entry["domain"]))
    objects, initial, goal_pos, goal_neg = problem(resolve(root, entry["problem"]))
    plan, expanded = solve(parents, constants, schemas, objects, initial, goal_pos, goal_neg, limit, weight)
    output = resolve(root, entry["plan_output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text("".join("%s(%s)\n" % (name, ", ".join(args)) for name, args in plan), encoding="utf-8")
    temporary.replace(output)
    return {"id": entry["id"], "ok": True, "plan_output": str(output), "steps": len(plan), "expanded": expanded}


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise PDDLError("request must be a JSON object")
        root = Path(request.get("root", "/app"))
        manifest_path = resolve(root, request.get("problem_json", str(root / "problem.json")))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        limit = request.get("max_expansions", 5000000)
        weight = request.get("weight", 3)
        if not isinstance(manifest, list) or not manifest:
            raise PDDLError("problem.json must be a nonempty array")
        if (not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0 or
                not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0):
            raise PDDLError("invalid search settings")
        results = []
        for entry in manifest:
            try:
                if not isinstance(entry, dict):
                    raise PDDLError("manifest entry is not an object")
                results.append(process(entry, root, limit, weight))
            except Exception as exc:
                task_id = entry.get("id", "<unknown>") if isinstance(entry, dict) else "<unknown>"
                results.append({"id": task_id, "ok": False, "error": str(exc)})
        print(json.dumps({"ok": all(result["ok"] for result in results), "results": results}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "results": []}, sort_keys=True))


if __name__ == "__main__":
    main()
