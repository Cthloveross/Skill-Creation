#!/usr/bin/env python3
"""Typed classical PDDL manifest planner. JSON stdin -> JSON stdout.

Instance data is never embedded: this program reads the manifest, domains, and
problems at execution time and writes only their declared output paths.
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


def parse_pddl(path):
    text = Path(path).read_text(encoding="utf-8")
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    at = 0

    def read_one():
        nonlocal at
        if at >= len(tokens):
            raise PDDLError("unexpected end of PDDL")
        token = tokens[at]
        at += 1
        if token == "(":
            out = []
            while at < len(tokens) and tokens[at] != ")":
                out.append(read_one())
            if at >= len(tokens):
                raise PDDLError("unclosed PDDL parenthesis")
            at += 1
            return out
        if token == ")":
            raise PDDLError("unexpected closing PDDL parenthesis")
        return token

    tree = read_one()
    if at != len(tokens) or not isinstance(tree, list) or not tree or tree[0] != "define":
        raise PDDLError("expected one PDDL define form")
    return tree


def section(tree, name):
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] == name:
            return item[1:]
    return None


def typed_names(items):
    result, waiting, index = [], [], 0
    while index < len(items):
        value = items[index]
        if not isinstance(value, str):
            raise PDDLError("malformed typed-name list")
        if value == "-":
            if not waiting or index + 1 >= len(items) or not isinstance(items[index + 1], str):
                raise PDDLError("malformed typed-name list")
            result.extend((name, items[index + 1]) for name in waiting)
            waiting = []
            index += 2
        else:
            waiting.append(value)
            index += 1
    result.extend((name, "object") for name in waiting)
    return result


def atom(expr):
    if (not isinstance(expr, list) or not expr or not isinstance(expr[0], str)
            or any(isinstance(x, list) for x in expr[1:])):
        raise PDDLError("expected a propositional atom")
    return tuple(expr)


def conjunction(expr, where, effect=False):
    """Return positive and negative literal lists for conjunction-only formulas."""
    if not isinstance(expr, list) or not expr:
        raise PDDLError("malformed " + where)
    operator = expr[0]
    if operator == "and":
        pos, neg = [], []
        for child in expr[1:]:
            child_pos, child_neg = conjunction(child, where, effect)
            pos.extend(child_pos)
            neg.extend(child_neg)
        return pos, neg
    if effect and operator in {"increase", "decrease", "assign", "scale-up", "scale-down"}:
        return [], []
    if operator == "not":
        if len(expr) != 2:
            raise PDDLError("malformed negation in " + where)
        return [], [atom(expr[1])]
    if operator in {"or", "imply", "when", "forall", "exists", ">", "<", ">=", "<="}:
        raise PDDLError("unsupported " + operator + " in " + where)
    return [atom(expr)], []


def read_domain(path):
    tree = parse_pddl(path)
    parents = {"object": None}
    parents.update(dict(typed_names(section(tree, ":types") or [])))
    constants = typed_names(section(tree, ":constants") or [])
    schemas = []
    for item in tree[1:]:
        if not (isinstance(item, list) and len(item) >= 2 and item[0] == ":action"):
            continue
        name, fields, index = item[1], {}, 2
        while index < len(item):
            if (not isinstance(item[index], str) or not item[index].startswith(":")
                    or index + 1 >= len(item)):
                raise PDDLError("malformed action " + str(name))
            fields[item[index]] = item[index + 1]
            index += 2
        parameters = typed_names(fields.get(":parameters", []))
        if any(not variable.startswith("?") for variable, _ in parameters):
            raise PDDLError("invalid parameter in " + name)
        pre_pos, pre_neg = conjunction(fields.get(":precondition", ["and"]), "precondition")
        add, delete = conjunction(fields.get(":effect", ["and"]), "effect", effect=True)
        if any(literal[0] == "=" for literal in add + delete):
            raise PDDLError("equality effects are unsupported")
        schemas.append((name, parameters, pre_pos, pre_neg, add, delete))
    if not schemas:
        raise PDDLError("domain declares no actions")
    return parents, constants, schemas


def read_problem(path):
    tree = parse_pddl(path)
    raw_initial = section(tree, ":init")
    if raw_initial is None:
        raise PDDLError("problem has no init section")
    initial = set()
    for item in raw_initial:
        # Numeric initial values are bookkeeping, not Boolean state atoms.
        if isinstance(item, list) and item and item[0] == "=":
            continue
        positive, negative = conjunction(item, "initial state")
        if negative:
            raise PDDLError("negative initial facts are unsupported")
        initial.update(positive)
    raw_goal = section(tree, ":goal")
    if raw_goal is None or len(raw_goal) != 1:
        raise PDDLError("problem has malformed goal")
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


def substitute(value, binding):
    return binding[value] if isinstance(value, str) and value.startswith("?") else value


def ground(literal, binding):
    return tuple(substitute(value, binding) for value in literal)


def equal(literal, binding):
    if len(literal) != 3:
        raise PDDLError("equality must have exactly two terms")
    return substitute(literal[1], binding) == substitute(literal[2], binding)


def holds(positive, negative, state, binding):
    for literal in positive:
        present = equal(literal, binding) if literal[0] == "=" else ground(literal, binding) in state
        if not present:
            return False
    for literal in negative:
        present = equal(literal, binding) if literal[0] == "=" else ground(literal, binding) in state
        if present:
            return False
    return True


def apply_effect(state, add, delete, binding):
    return frozenset((set(state) - {ground(x, binding) for x in delete}) |
                     {ground(x, binding) for x in add})


def successors(schema, state, object_types, parents):
    """Yield applicable schema instances, joining positive facts before grounding."""
    name, parameters, pre_pos, pre_neg, add, delete = schema
    facts_by_predicate = defaultdict(list)
    for fact in state:
        facts_by_predicate[fact[0]].append(fact)

    patterns = sorted((x for x in pre_pos if x[0] != "="),
                      key=lambda x: len(facts_by_predicate[x[0]]))
    environments = [{}]
    for pattern in patterns:
        next_environments = []
        for binding in environments:
            for fact in facts_by_predicate[pattern[0]]:
                if len(fact) != len(pattern):
                    continue
                candidate, valid = dict(binding), True
                for pattern_term, fact_term in zip(pattern[1:], fact[1:]):
                    if pattern_term.startswith("?"):
                        old = candidate.get(pattern_term)
                        if old is not None and old != fact_term:
                            valid = False
                            break
                        candidate[pattern_term] = fact_term
                    elif pattern_term != fact_term:
                        valid = False
                        break
                if valid:
                    next_environments.append(candidate)
        environments = next_environments
        if not environments:
            return

    choices = [(variable, [obj for obj, typ in object_types.items()
                           if is_subtype(typ, required, parents)])
               for variable, required in parameters]
    if any(not objects for _, objects in choices):
        return
    for partial in environments:
        if any(variable in partial and partial[variable] not in objects
               for variable, objects in choices):
            continue
        missing = [(variable, objects) for variable, objects in choices if variable not in partial]
        products = itertools.product(*(objects for _, objects in missing)) if missing else [()]
        for selected in products:
            binding = dict(partial)
            binding.update(zip((variable for variable, _ in missing), selected))
            if not holds(pre_pos, pre_neg, state, binding):
                continue
            yield name, tuple(binding[variable] for variable, _ in parameters), apply_effect(state, add, delete, binding)


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
            if value not in object_types or not is_subtype(object_types[value], required, parents):
                raise PDDLError("type error at step %d" % step)
        binding = dict(zip((variable for variable, _ in parameters), args))
        if not holds(pre_pos, pre_neg, state, binding):
            raise PDDLError("precondition failure at step %d" % step)
        state = apply_effect(state, add, delete, binding)
    if not holds(goal_pos, goal_neg, state, {}):
        raise PDDLError("final state does not satisfy goal")


def solve(parents, constants, schemas, objects, initial, goal_pos, goal_neg, limit, weight):
    object_types = dict(constants)
    object_types.update(dict(objects))
    if any(type_name not in parents for type_name in object_types.values()):
        raise PDDLError("object uses an undeclared type")
    if holds(goal_pos, goal_neg, initial, {}):
        return [], 0, object_types

    def heuristic(state):
        missing = sum(not (equal(item, {}) if item[0] == "=" else item in state) for item in goal_pos)
        bad_negative = sum(equal(item, {}) if item[0] == "=" else item in state for item in goal_neg)
        return missing + bad_negative

    serial = itertools.count()
    frontier = [(weight * heuristic(initial), 0, next(serial), initial)]
    best_cost, predecessor, expanded = {initial: 0}, {}, 0
    while frontier:
        _, cost, _, state = heapq.heappop(frontier)
        if best_cost.get(state) != cost:
            continue
        if holds(goal_pos, goal_neg, state, {}):
            plan, current = [], state
            while current != initial:
                current, action = predecessor[current]
                plan.append(action)
            plan.reverse()
            replay(parents, schemas, initial, goal_pos, goal_neg, object_types, plan)
            return plan, expanded, object_types
        expanded += 1
        if expanded > limit:
            raise PDDLError("search expansion limit exceeded (%d)" % limit)
        for schema in schemas:
            for name, args, next_state in successors(schema, state, object_types, parents):
                next_cost = cost + 1
                if next_cost >= best_cost.get(next_state, 10 ** 30):
                    continue
                best_cost[next_state] = next_cost
                predecessor[next_state] = (state, (name, args))
                heapq.heappush(frontier, (next_cost + weight * heuristic(next_state),
                                          next_cost, next(serial), next_state))
    raise PDDLError("state space exhausted without a plan")


def resolve(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def process(entry, root, limit, weight):
    for key in ("id", "domain", "problem", "plan_output"):
        if key not in entry:
            raise PDDLError("manifest entry lacks " + key)
    parents, constants, schemas = read_domain(resolve(root, entry["domain"]))
    objects, initial, goal_pos, goal_neg = read_problem(resolve(root, entry["problem"]))
    plan, expanded, _ = solve(parents, constants, schemas, objects, initial,
                              goal_pos, goal_neg, limit, weight)
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
        limit, weight = request.get("max_expansions", 5000000), request.get("weight", 3)
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
