#!/usr/bin/env python3
"""Runtime PDDL manifest planner.

Input: JSON object on stdin with root, problem_json, max_expansions, and weight.
Output: JSON status object on stdout.  For each solved manifest entry, a plan is
written at the entry's plan_output path in action(arg, arg) syntax.
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


def read_sexpr(path):
    text = Path(path).read_text(encoding="utf-8")
    text = re.sub(r";[^\n]*", "", text)
    tokens = re.findall(r"\(|\)|[^\s()]+", text.lower())
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
            raise PDDLError("unexpected closing PDDL parenthesis")
        return token

    value = parse_one()
    if pos != len(tokens) or not isinstance(value, list) or not value or value[0] != "define":
        raise PDDLError("expected one PDDL define form")
    return value


def section(tree, key):
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] == key:
            return item[1:]
    return None


def typed_names(items):
    result, pending = [], []
    i = 0
    while i < len(items):
        item = items[i]
        if not isinstance(item, str):
            raise PDDLError("malformed typed name list")
        if item == "-":
            if not pending or i + 1 >= len(items) or not isinstance(items[i + 1], str):
                raise PDDLError("malformed typed name list")
            result.extend((name, items[i + 1]) for name in pending)
            pending = []
            i += 2
        else:
            pending.append(item)
            i += 1
    result.extend((name, "object") for name in pending)
    return result


def atomic(expr, where):
    if (not isinstance(expr, list) or not expr or not isinstance(expr[0], str)
            or any(isinstance(x, list) for x in expr[1:])):
        raise PDDLError("expected atom in " + where)
    return tuple(expr)


def conjunction(expr, where, effect=False):
    """Return positive and negative atoms from a conjunction-only expression."""
    if not isinstance(expr, list) or not expr:
        raise PDDLError("malformed " + where)
    op = expr[0]
    if op == "and":
        positive, negative = [], []
        for child in expr[1:]:
            p, n = conjunction(child, where, effect)
            positive.extend(p)
            negative.extend(n)
        return positive, negative
    # Numeric bookkeeping is intentionally ignored, matching propositional plan
    # execution; numeric conditions are not silently accepted.
    if effect and op in {"increase", "decrease", "assign", "scale-up", "scale-down"}:
        return [], []
    if op == "not":
        if len(expr) != 2:
            raise PDDLError("malformed negation in " + where)
        return [], [atomic(expr[1], where)]
    if op in {"or", "imply", "when", "forall", "exists", ">", "<", ">=", "<=", "oneof"}:
        raise PDDLError("unsupported " + op + " in " + where)
    return [atomic(expr, where)], []


def load_domain(path):
    tree = read_sexpr(path)
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
        fields, i = {}, 2
        while i < len(item):
            if (not isinstance(item[i], str) or not item[i].startswith(":")
                    or i + 1 >= len(item)):
                raise PDDLError("malformed action " + name)
            fields[item[i]] = item[i + 1]
            i += 2
        parameters = typed_names(fields.get(":parameters", []))
        if any(not var.startswith("?") for var, _ in parameters):
            raise PDDLError("action parameter is not a variable in " + name)
        pre_pos, pre_neg = conjunction(fields.get(":precondition", ["and"]), "precondition")
        add, delete = conjunction(fields.get(":effect", ["and"]), "effect", True)
        if any(x[0] == "=" for x in add + delete):
            raise PDDLError("equality effects are unsupported")
        schemas.append((name, parameters, pre_pos, pre_neg, add, delete))
    if not schemas:
        raise PDDLError("domain declares no actions")
    return parents, constants, schemas


def load_problem(path):
    tree = read_sexpr(path)
    raw_init = section(tree, ":init")
    raw_goal = section(tree, ":goal")
    if raw_init is None:
        raise PDDLError("problem has no init")
    if raw_goal is None or len(raw_goal) != 1:
        raise PDDLError("problem has malformed goal")
    initial = set()
    for fact in raw_init:
        if isinstance(fact, list) and fact and fact[0] == "=":
            continue
        pos, neg = conjunction(fact, "initial state")
        if neg:
            raise PDDLError("negative initial facts are unsupported")
        initial.update(pos)
    goal_pos, goal_neg = conjunction(raw_goal[0], "goal")
    return typed_names(section(tree, ":objects") or []), frozenset(initial), goal_pos, goal_neg


def is_subtype(actual, required, parents):
    seen = set()
    while actual is not None and actual not in seen:
        if actual == required:
            return True
        seen.add(actual)
        actual = parents.get(actual)
    return False


def term(value, binding):
    return binding[value] if isinstance(value, str) and value.startswith("?") else value


def grounded(atom, binding):
    return tuple(term(x, binding) for x in atom)


def equal(atom, binding):
    if len(atom) != 3:
        raise PDDLError("equality must have two operands")
    return term(atom[1], binding) == term(atom[2], binding)


def satisfied(positive, negative, state, binding):
    for literal in positive:
        holds = equal(literal, binding) if literal[0] == "=" else grounded(literal, binding) in state
        if not holds:
            return False
    for literal in negative:
        holds = equal(literal, binding) if literal[0] == "=" else grounded(literal, binding) in state
        if holds:
            return False
    return True


def apply_effect(state, add, delete, binding):
    return frozenset((set(state) - {grounded(x, binding) for x in delete}) |
                     {grounded(x, binding) for x in add})


def applicable(schema, state, objects, parents):
    name, parameters, pre_pos, pre_neg, add, delete = schema
    facts_by_predicate = defaultdict(list)
    for fact in state:
        facts_by_predicate[fact[0]].append(fact)
    patterns = sorted((x for x in pre_pos if x[0] != "="),
                      key=lambda x: len(facts_by_predicate[x[0]]))
    partial = [{}]
    for pattern in patterns:
        next_partial = []
        for binding in partial:
            for fact in facts_by_predicate[pattern[0]]:
                if len(fact) != len(pattern):
                    continue
                candidate = dict(binding)
                valid = True
                for symbol, value in zip(pattern[1:], fact[1:]):
                    if symbol.startswith("?"):
                        if symbol in candidate and candidate[symbol] != value:
                            valid = False
                            break
                        candidate[symbol] = value
                    elif symbol != value:
                        valid = False
                        break
                if valid:
                    next_partial.append(candidate)
        partial = next_partial
        if not partial:
            return
    choices = []
    for variable, required in parameters:
        values = [obj for obj, typ in objects.items() if is_subtype(typ, required, parents)]
        if not values:
            return
        choices.append((variable, values))
    for binding in partial:
        if any(var in binding and binding[var] not in values for var, values in choices):
            continue
        remaining = [(var, values) for var, values in choices if var not in binding]
        products = itertools.product(*(values for _, values in remaining)) if remaining else [()]
        for values in products:
            candidate = dict(binding)
            candidate.update(zip((var for var, _ in remaining), values))
            if satisfied(pre_pos, pre_neg, state, candidate):
                args = tuple(candidate[var] for var, _ in parameters)
                yield name, args, apply_effect(state, add, delete, candidate)


def replay(parents, schemas, initial, goal_pos, goal_neg, objects, plan):
    table = {schema[0]: schema for schema in schemas}
    state = initial
    for number, (name, args) in enumerate(plan, 1):
        if name not in table:
            raise PDDLError("undeclared action at step %d" % number)
        _, parameters, pre_pos, pre_neg, add, delete = table[name]
        if len(args) != len(parameters):
            raise PDDLError("incorrect arity at step %d" % number)
        for arg, (_, required) in zip(args, parameters):
            if arg not in objects or not is_subtype(objects[arg], required, parents):
                raise PDDLError("type error at step %d" % number)
        binding = dict(zip((var for var, _ in parameters), args))
        if not satisfied(pre_pos, pre_neg, state, binding):
            raise PDDLError("precondition failure at step %d" % number)
        state = apply_effect(state, add, delete, binding)
    if not satisfied(goal_pos, goal_neg, state, {}):
        raise PDDLError("final state does not satisfy goal")


def search(parents, constants, schemas, declared_objects, initial, goal_pos, goal_neg, limit, weight):
    objects = dict(constants)
    objects.update(dict(declared_objects))
    if any(typ not in parents for typ in objects.values()):
        raise PDDLError("object has undeclared type")
    if satisfied(goal_pos, goal_neg, initial, {}):
        return [], 0, objects

    def heuristic(state):
        missing = sum(not (equal(x, {}) if x[0] == "=" else x in state) for x in goal_pos)
        present_negative = sum(equal(x, {}) if x[0] == "=" else x in state for x in goal_neg)
        return missing + present_negative

    sequence = itertools.count()
    frontier = [(weight * heuristic(initial), 0, next(sequence), initial)]
    distance, predecessor = {initial: 0}, {}
    expanded = 0
    while frontier:
        _, cost, _, state = heapq.heappop(frontier)
        if distance.get(state) != cost:
            continue
        if satisfied(goal_pos, goal_neg, state, {}):
            plan, current = [], state
            while current != initial:
                prior, action = predecessor[current]
                plan.append(action)
                current = prior
            plan.reverse()
            replay(parents, schemas, initial, goal_pos, goal_neg, objects, plan)
            return plan, expanded, objects
        expanded += 1
        if expanded > limit:
            raise PDDLError("search expansion limit exceeded (%d)" % limit)
        for schema in schemas:
            for name, args, successor in applicable(schema, state, objects, parents):
                next_cost = cost + 1
                if next_cost >= distance.get(successor, 10 ** 30):
                    continue
                distance[successor] = next_cost
                predecessor[successor] = (state, (name, args))
                heapq.heappush(frontier, (next_cost + weight * heuristic(successor), next_cost,
                                          next(sequence), successor))
    raise PDDLError("state space exhausted without a plan")


def resolve(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def solve_entry(entry, root, limit, weight):
    for key in ("id", "domain", "problem", "plan_output"):
        if key not in entry or not isinstance(entry[key], str):
            raise PDDLError("manifest entry lacks string " + key)
    parents, constants, schemas = load_domain(resolve(root, entry["domain"]))
    declared, initial, goal_pos, goal_neg = load_problem(resolve(root, entry["problem"]))
    plan, expanded, objects = search(parents, constants, schemas, declared, initial,
                                     goal_pos, goal_neg, limit, weight)
    # Validate once more immediately before publication.
    replay(parents, schemas, initial, goal_pos, goal_neg, objects, plan)
    output = resolve(root, entry["plan_output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text("".join("%s(%s)\n" % (name, ", ".join(args))
                                 for name, args in plan), encoding="utf-8")
    temporary.replace(output)
    return {"id": entry["id"], "ok": True, "plan_output": str(output),
            "steps": len(plan), "expanded": expanded}


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
                results.append(solve_entry(entry, root, limit, weight))
            except Exception as exc:
                task_id = entry.get("id", "<unknown>") if isinstance(entry, dict) else "<unknown>"
                results.append({"id": task_id, "ok": False, "error": str(exc)})
        print(json.dumps({"ok": all(x["ok"] for x in results), "results": results}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "results": []}, sort_keys=True))


if __name__ == "__main__":
    main()
