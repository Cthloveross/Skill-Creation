#!/usr/bin/env python3
"""Solve a typed classical-PDDL manifest. JSON stdin -> JSON stdout.

The program has no instance-specific data: domain, problem, and output paths are
always obtained from the supplied manifest at execution time.
"""
import heapq
import itertools
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


class Error(Exception):
    pass


def parse(path):
    """Read one comment-stripped PDDL s-expression as nested Python lists."""
    text = Path(path).read_text(encoding="utf-8")
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    pos = 0

    def one():
        nonlocal pos
        if pos >= len(tokens):
            raise Error("unexpected end of PDDL")
        token = tokens[pos]
        pos += 1
        if token == "(":
            value = []
            while pos < len(tokens) and tokens[pos] != ")":
                value.append(one())
            if pos == len(tokens):
                raise Error("unclosed parenthesis")
            pos += 1
            return value
        if token == ")":
            raise Error("unexpected closing parenthesis")
        return token

    result = one()
    if pos != len(tokens) or not isinstance(result, list) or not result or result[0] != "define":
        raise Error("expected one PDDL define form")
    return result


def section(tree, key):
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] == key:
            return item[1:]
    return None


def typed(items):
    """Convert a PDDL typed-name sequence to ordered (name, type) pairs."""
    output, pending, i = [], [], 0
    while i < len(items):
        item = items[i]
        if not isinstance(item, str):
            raise Error("malformed typed list")
        if item == "-":
            if not pending or i + 1 >= len(items) or not isinstance(items[i + 1], str):
                raise Error("malformed typed list")
            output.extend((name, items[i + 1]) for name in pending)
            pending = []
            i += 2
        else:
            pending.append(item)
            i += 1
    output.extend((name, "object") for name in pending)
    return output


def atom(value):
    if (not isinstance(value, list) or not value or not isinstance(value[0], str)
            or any(isinstance(part, list) for part in value[1:])):
        raise Error("expected a propositional atom")
    return tuple(value)


def literals(value, where, effects=False):
    """Return (positive literals, negative literals) for conjunction-only PDDL."""
    if not isinstance(value, list) or not value:
        raise Error("malformed " + where)
    op = value[0]
    if op == "and":
        positive, negative = [], []
        for child in value[1:]:
            p, n = literals(child, where, effects)
            positive.extend(p)
            negative.extend(n)
        return positive, negative
    if effects and op in {"increase", "decrease", "assign", "scale-up", "scale-down"}:
        return [], []
    if op == "not":
        if len(value) != 2:
            raise Error("malformed negation in " + where)
        return [], [atom(value[1])]
    if op in {"or", "forall", "exists", "imply", "when", ">", "<", ">=", "<="}:
        raise Error("unsupported " + op + " in " + where)
    return [atom(value)], []


def read_domain(path):
    tree = parse(path)
    parents = {"object": None}
    parents.update(dict(typed(section(tree, ":types") or [])))
    schemas = []
    for item in tree[1:]:
        if not (isinstance(item, list) and len(item) >= 2 and item[0] == ":action"):
            continue
        fields, i = {}, 2
        while i < len(item):
            if (not isinstance(item[i], str) or not item[i].startswith(":")
                    or i + 1 >= len(item)):
                raise Error("malformed action " + item[1])
            fields[item[i]] = item[i + 1]
            i += 2
        params = typed(fields.get(":parameters", []))
        if any(not name.startswith("?") for name, _ in params):
            raise Error("invalid parameter in " + item[1])
        pre_pos, pre_neg = literals(fields.get(":precondition", ["and"]), "precondition")
        add, delete = literals(fields.get(":effect", ["and"]), "effect", effects=True)
        if any(literal[0] == "=" for literal in add + delete):
            raise Error("equality effects are unsupported")
        schemas.append((item[1], params, pre_pos, pre_neg, add, delete))
    if not schemas:
        raise Error("domain declares no actions")
    return parents, typed(section(tree, ":constants") or []), schemas


def read_problem(path):
    tree = parse(path)
    raw_init = section(tree, ":init")
    if raw_init is None:
        raise Error("problem has no init")
    initial = set()
    for item in raw_init:
        # Numeric initial assignments are not propositional state facts.
        if isinstance(item, list) and item and item[0] == "=":
            continue
        positive, negative = literals(item, "initial state")
        if negative:
            raise Error("negative initial facts unsupported")
        initial.update(positive)
    raw_goal = section(tree, ":goal")
    if raw_goal is None or len(raw_goal) != 1:
        raise Error("problem has malformed goal")
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


def term(value, env):
    return env[value] if isinstance(value, str) and value.startswith("?") else value


def grounded(literal, env):
    return tuple(term(value, env) for value in literal)


def equal(literal, env):
    if len(literal) != 3:
        raise Error("equality must have two terms")
    return term(literal[1], env) == term(literal[2], env)


def holds(positive, negative, state, env):
    for literal in positive:
        present = equal(literal, env) if literal[0] == "=" else grounded(literal, env) in state
        if not present:
            return False
    for literal in negative:
        present = equal(literal, env) if literal[0] == "=" else grounded(literal, env) in state
        if present:
            return False
    return True


def successors(schema, state, object_types, parents):
    """Yield applicable grounded instances using positive preconditions as joins."""
    name, params, pre_pos, pre_neg, add, delete = schema
    index = defaultdict(list)
    for fact in state:
        index[fact[0]].append(fact)

    patterns = sorted((literal for literal in pre_pos if literal[0] != "="),
                      key=lambda literal: len(index[literal[0]]))
    environments = [{}]
    for pattern in patterns:
        next_environments = []
        for env in environments:
            for fact in index[pattern[0]]:
                if len(fact) != len(pattern):
                    continue
                candidate, compatible = dict(env), True
                for pattern_value, fact_value in zip(pattern[1:], fact[1:]):
                    if pattern_value.startswith("?"):
                        if pattern_value in candidate and candidate[pattern_value] != fact_value:
                            compatible = False
                            break
                        candidate[pattern_value] = fact_value
                    elif pattern_value != fact_value:
                        compatible = False
                        break
                if compatible:
                    next_environments.append(candidate)
        environments = next_environments
        if not environments:
            return

    choices = [
        (variable, [obj for obj, typ in object_types.items() if subtype(typ, needed, parents)])
        for variable, needed in params
    ]
    for env in environments:
        if any(variable in env and env[variable] not in values for variable, values in choices):
            continue
        missing = [(variable, values) for variable, values in choices if variable not in env]
        if any(not values for _, values in missing):
            continue
        products = itertools.product(*(values for _, values in missing)) if missing else [()]
        for values in products:
            binding = dict(env)
            binding.update(zip((variable for variable, _ in missing), values))
            if not holds(pre_pos, pre_neg, state, binding):
                continue
            next_state = frozenset(
                (set(state) - {grounded(literal, binding) for literal in delete})
                | {grounded(literal, binding) for literal in add}
            )
            yield name, tuple(binding[variable] for variable, _ in params), next_state


def replay(parents, schemas, initial, goal_pos, goal_neg, object_types, plan):
    """Independently validate a fully grounded plan before it is written."""
    table = {schema[0]: schema for schema in schemas}
    state = initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in table:
            raise Error("undeclared action at step %d" % step)
        _, params, pre_pos, pre_neg, add, delete = table[name]
        if len(args) != len(params):
            raise Error("wrong arity at step %d" % step)
        for argument, (_, required) in zip(args, params):
            if argument not in object_types or not subtype(object_types[argument], required, parents):
                raise Error("type error at step %d" % step)
        binding = dict(zip((variable for variable, _ in params), args))
        if not holds(pre_pos, pre_neg, state, binding):
            raise Error("precondition failure at step %d" % step)
        state = frozenset(
            (set(state) - {grounded(literal, binding) for literal in delete})
            | {grounded(literal, binding) for literal in add}
        )
    if not holds(goal_pos, goal_neg, state, {}):
        raise Error("final state does not satisfy goal")


def solve(parents, constants, schemas, objects, initial, goal_pos, goal_neg, limit, weight):
    object_types = dict(constants)
    object_types.update(dict(objects))
    if any(typ not in parents for typ in object_types.values()):
        raise Error("undeclared object type")
    if holds(goal_pos, goal_neg, initial, {}):
        return [], 0

    def heuristic(state):
        missing_positive = sum(
            not (equal(literal, {}) if literal[0] == "=" else literal in state)
            for literal in goal_pos
        )
        violated_negative = sum(
            equal(literal, {}) if literal[0] == "=" else literal in state
            for literal in goal_neg
        )
        return missing_positive + violated_negative

    queue, serial = [], itertools.count()
    best_cost = {initial: 0}
    previous = {}
    heapq.heappush(queue, (weight * heuristic(initial), 0, next(serial), initial))
    expanded = 0

    while queue:
        _, cost, _, state = heapq.heappop(queue)
        if best_cost.get(state) != cost:
            continue
        if holds(goal_pos, goal_neg, state, {}):
            plan, current = [], state
            while current != initial:
                current, action = previous[current]
                plan.append(action)
            plan.reverse()
            replay(parents, schemas, initial, goal_pos, goal_neg, object_types, plan)
            return plan, expanded
        expanded += 1
        if expanded > limit:
            raise Error("search expansion limit exceeded (%d)" % limit)
        for schema in schemas:
            for name, args, next_state in successors(schema, state, object_types, parents):
                next_cost = cost + 1
                if next_cost >= best_cost.get(next_state, 10 ** 30):
                    continue
                best_cost[next_state] = next_cost
                previous[next_state] = (state, (name, args))
                heapq.heappush(
                    queue,
                    (next_cost + weight * heuristic(next_state), next_cost, next(serial), next_state),
                )
    raise Error("state space exhausted without a plan")


def resolve(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def process(entry, root, limit, weight):
    for key in ("id", "domain", "problem", "plan_output"):
        if key not in entry:
            raise Error("manifest entry lacks " + key)
    parents, constants, schemas = read_domain(resolve(root, entry["domain"]))
    objects, initial, goal_pos, goal_neg = read_problem(resolve(root, entry["problem"]))
    plan, expanded = solve(
        parents, constants, schemas, objects, initial, goal_pos, goal_neg, limit, weight
    )

    output = resolve(root, entry["plan_output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(
        "".join("%s(%s)\n" % (name, ", ".join(args)) for name, args in plan),
        encoding="utf-8",
    )
    temporary.replace(output)
    return {
        "id": entry["id"],
        "ok": True,
        "plan_output": str(output),
        "steps": len(plan),
        "expanded": expanded,
    }


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise Error("request must be a JSON object")
        root = Path(request.get("root", "/app"))
        manifest_path = resolve(root, request.get("problem_json", str(root / "problem.json")))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        limit = request.get("max_expansions", 5000000)
        weight = request.get("weight", 3)
        if not isinstance(manifest, list) or not manifest:
            raise Error("problem.json must be a nonempty array")
        if (not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0
                or not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0):
            raise Error("invalid search settings")

        results = []
        for entry in manifest:
            try:
                if not isinstance(entry, dict):
                    raise Error("manifest entry is not an object")
                results.append(process(entry, root, limit, weight))
            except Exception as exc:
                task_id = entry.get("id", "<unknown>") if isinstance(entry, dict) else "<unknown>"
                results.append({"id": task_id, "ok": False, "error": str(exc)})
        print(json.dumps({"ok": all(item["ok"] for item in results), "results": results}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "results": []}, sort_keys=True))


if __name__ == "__main__":
    main()
