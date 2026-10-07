#!/usr/bin/env python3
"""Solve a typed classical-PDDL manifest and write validated function-style plans.

Input is one JSON object on stdin:
  {"root": "/app", "problem_json": "/app/problem.json",
   "max_expansions": 5000000, "weight": 3}
All fields are optional. Output is one JSON report on stdout. Uses only the
Python standard library.
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


def lex(text):
    text = re.sub(r";[^\n]*", "", text).lower()
    return re.findall(r"\(|\)|[^\s()]+", text)


def sexpr(text):
    tokens, pos = lex(text), 0

    def read():
        nonlocal pos
        if pos >= len(tokens):
            raise PDDLError("unexpected end of PDDL")
        token = tokens[pos]
        pos += 1
        if token == "(":
            result = []
            while True:
                if pos >= len(tokens):
                    raise PDDLError("unclosed parenthesis")
                if tokens[pos] == ")":
                    pos += 1
                    return result
                result.append(read())
        if token == ")":
            raise PDDLError("unexpected closing parenthesis")
        return token

    tree = read()
    if pos != len(tokens):
        raise PDDLError("multiple top-level PDDL forms")
    if not isinstance(tree, list) or not tree or tree[0] != "define":
        raise PDDLError("expected a (define ...) form")
    return tree


def section(tree, key):
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] == key:
            return item[1:]
    return None


def typed(items, default="object"):
    """Convert a PDDL typed-name sequence to ordered (name, type) pairs."""
    result, pending, index = [], [], 0
    while index < len(items):
        value = items[index]
        if not isinstance(value, str):
            raise PDDLError("nested expression in typed list")
        if value == "-":
            if not pending or index + 1 >= len(items) or not isinstance(items[index + 1], str):
                raise PDDLError("malformed typed list")
            result.extend((name, items[index + 1]) for name in pending)
            pending = []
            index += 2
        else:
            pending.append(value)
            index += 1
    result.extend((name, default) for name in pending)
    return result


def atom(form):
    if not isinstance(form, list) or not form or not isinstance(form[0], str):
        raise PDDLError("expected a predicate atom")
    if any(isinstance(term, list) for term in form[1:]):
        raise PDDLError("function terms are unsupported in propositional formulas")
    return tuple(form)


def conjunction(form, where, effect=False):
    """Return positive and negative atom lists for a supported conjunction."""
    if not isinstance(form, list) or not form:
        raise PDDLError("empty " + where)
    op = form[0] if isinstance(form[0], str) else ""
    if op == "and":
        positive, negative = [], []
        for child in form[1:]:
            child_positive, child_negative = conjunction(child, where, effect)
            positive.extend(child_positive)
            negative.extend(child_negative)
        return positive, negative
    if effect and op in {"increase", "decrease", "assign", "scale-up", "scale-down"}:
        # TPP cost bookkeeping is not a propositional state transition.
        return [], []
    if op == "not":
        if len(form) != 2:
            raise PDDLError("malformed negation in " + where)
        return [], [atom(form[1])]
    if op in {"or", "forall", "exists", "imply", "when"}:
        raise PDDLError("unsupported " + op + " in " + where)
    value = atom(form)
    if value[0] in {">", "<", ">=", "<="}:
        raise PDDLError("numeric comparison unsupported in " + where)
    return [value], []


def action_fields(declaration):
    result, index = {}, 2
    while index < len(declaration):
        if (not isinstance(declaration[index], str)
                or not declaration[index].startswith(":")
                or index + 1 >= len(declaration)):
            raise PDDLError("malformed action declaration")
        result[declaration[index]] = declaration[index + 1]
        index += 2
    return result


def read_domain(path):
    tree = sexpr(Path(path).read_text(encoding="utf-8"))
    parents = {"object": None}
    raw_types = section(tree, ":types")
    if raw_types:
        parents.update(dict(typed(raw_types)))

    actions = []
    for item in tree[1:]:
        if not (isinstance(item, list) and len(item) >= 2 and item[0] == ":action"):
            continue
        name = item[1]
        data = action_fields(item)
        parameters_form = data.get(":parameters")
        if not isinstance(parameters_form, list):
            raise PDDLError("action %s lacks :parameters" % name)
        parameters = typed(parameters_form)
        if any(not variable.startswith("?") for variable, _ in parameters):
            raise PDDLError("action %s has a non-variable parameter" % name)
        pre_pos, pre_neg = conjunction(data.get(":precondition", ["and"]),
                                       "precondition of " + name)
        add, delete = conjunction(data.get(":effect", ["and"]),
                                  "effect of " + name, effect=True)
        if any(fact[0] == "=" for fact in add + delete):
            raise PDDLError("equality is not a valid action effect")
        actions.append({"name": name, "parameters": parameters,
                        "pre_pos": pre_pos, "pre_neg": pre_neg,
                        "add": add, "delete": delete})
    if not actions:
        raise PDDLError("domain declares no actions")
    return {"parents": parents,
            "constants": typed(section(tree, ":constants") or []),
            "actions": actions}


def read_problem(path):
    tree = sexpr(Path(path).read_text(encoding="utf-8"))
    raw_init = section(tree, ":init")
    if raw_init is None:
        raise PDDLError("problem has no :init")
    initial = set()
    for item in raw_init:
        # Standard numeric fluent assignments, e.g. (= (total-cost) 0).
        if isinstance(item, list) and item and item[0] == "=":
            continue
        positive, negative = conjunction(item, "initial state")
        if negative:
            raise PDDLError("negative initial facts are unsupported")
        initial.update(positive)

    raw_goal = section(tree, ":goal")
    if raw_goal is None or len(raw_goal) != 1:
        raise PDDLError("problem has malformed or missing :goal")
    goal_pos, goal_neg = conjunction(raw_goal[0], "goal")
    return {"objects": typed(section(tree, ":objects") or []),
            "initial": frozenset(initial), "goal_pos": goal_pos,
            "goal_neg": goal_neg}


def is_subtype(actual, required, parents):
    seen = set()
    while actual is not None and actual not in seen:
        if actual == required:
            return True
        seen.add(actual)
        actual = parents.get(actual)
    return False


def substitute(value, env):
    return env[value] if isinstance(value, str) and value.startswith("?") else value


def ground(fact, env):
    return tuple(substitute(value, env) for value in fact)


def equal(fact, env):
    if len(fact) != 3:
        raise PDDLError("equality must have two terms")
    return substitute(fact[1], env) == substitute(fact[2], env)


def holds(positive, negative, state, env):
    for fact in positive:
        if fact[0] == "=":
            if not equal(fact, env):
                return False
        elif ground(fact, env) not in state:
            return False
    for fact in negative:
        if fact[0] == "=":
            if equal(fact, env):
                return False
        elif ground(fact, env) in state:
            return False
    return True


def all_object_types(domain, problem):
    result = {}
    for name, kind in domain["constants"] + problem["objects"]:
        if kind not in domain["parents"]:
            raise PDDLError("undeclared type " + kind)
        if name in result and result[name] != kind:
            raise PDDLError("conflicting types for " + name)
        result[name] = kind
    return result


def applicable(schema, state, types, parents):
    """Yield type-valid action groundings whose complete precondition holds."""
    facts_by_predicate = defaultdict(list)
    for fact in state:
        facts_by_predicate[fact[0]].append(fact)

    patterns = [fact for fact in schema["pre_pos"] if fact[0] != "="]
    patterns.sort(key=lambda fact: len(facts_by_predicate.get(fact[0], ())))
    environments = [{}]
    for pattern in patterns:
        candidates = facts_by_predicate.get(pattern[0], ())
        if not candidates:
            return
        next_environments = []
        for env in environments:
            for fact in candidates:
                if len(fact) != len(pattern):
                    continue
                candidate, valid = dict(env), True
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
                    next_environments.append(candidate)
        environments = next_environments
        if not environments:
            return

    choices = []
    for variable, required in schema["parameters"]:
        choices.append((variable, [obj for obj, actual in types.items()
                                   if is_subtype(actual, required, parents)]))
    for partial in environments:
        if any(variable in partial and partial[variable] not in values
               for variable, values in choices):
            continue
        missing = [(variable, values) for variable, values in choices
                   if variable not in partial]
        if any(not values for _, values in missing):
            continue
        products = itertools.product(*(values for _, values in missing)) if missing else [()]
        for values in products:
            env = dict(partial)
            env.update({variable: value for (variable, _), value in zip(missing, values)})
            if not holds(schema["pre_pos"], schema["pre_neg"], state, env):
                continue
            successor = frozenset((set(state) - {ground(fact, env) for fact in schema["delete"]})
                                  | {ground(fact, env) for fact in schema["add"]})
            yield schema["name"], tuple(env[var] for var, _ in schema["parameters"]), successor


def goal_reached(problem, state):
    return holds(problem["goal_pos"], problem["goal_neg"], state, {})


def heuristic(problem, state):
    missing = 0
    for fact in problem["goal_pos"]:
        missing += (not equal(fact, {}) if fact[0] == "=" else fact not in state)
    for fact in problem["goal_neg"]:
        missing += (equal(fact, {}) if fact[0] == "=" else fact in state)
    return int(missing)


def replay(domain, problem, plan, types):
    """Independently replay a plan and reject any invalid transition or goal."""
    schemas = {schema["name"]: schema for schema in domain["actions"]}
    state = problem["initial"]
    for number, (name, args) in enumerate(plan, 1):
        schema = schemas.get(name)
        if schema is None or len(args) != len(schema["parameters"]):
            raise PDDLError("invalid action at step %d" % number)
        env = {}
        for (variable, required), value in zip(schema["parameters"], args):
            actual = types.get(value)
            if actual is None or not is_subtype(actual, required, domain["parents"]):
                raise PDDLError("type-invalid argument at step %d" % number)
            env[variable] = value
        if not holds(schema["pre_pos"], schema["pre_neg"], state, env):
            raise PDDLError("precondition fails at step %d" % number)
        state = frozenset((set(state) - {ground(fact, env) for fact in schema["delete"]})
                          | {ground(fact, env) for fact in schema["add"]})
    if not goal_reached(problem, state):
        raise PDDLError("final state does not satisfy goal")


def solve(domain, problem, limit, weight):
    types = all_object_types(domain, problem)
    start = problem["initial"]
    if goal_reached(problem, start):
        return [], 0, types

    queue, serial = [], itertools.count()
    best_cost, predecessor = {start: 0}, {}
    start_h = heuristic(problem, start)
    heapq.heappush(queue, (weight * start_h, start_h, 0, next(serial), start))
    expanded = 0

    while queue:
        _, _, cost, _, state = heapq.heappop(queue)
        if best_cost.get(state) != cost:
            continue
        if goal_reached(problem, state):
            plan, current = [], state
            while current != start:
                previous, action = predecessor[current]
                plan.append(action)
                current = previous
            plan.reverse()
            replay(domain, problem, plan, types)
            return plan, expanded, types

        expanded += 1
        if expanded > limit:
            raise PDDLError("search expansion limit exceeded (%d)" % limit)
        for schema in domain["actions"]:
            for name, args, successor in applicable(schema, state, types, domain["parents"]):
                new_cost = cost + 1
                if new_cost >= best_cost.get(successor, 10 ** 30):
                    continue
                best_cost[successor] = new_cost
                predecessor[successor] = (state, (name, args))
                next_h = heuristic(problem, successor)
                heapq.heappush(queue, (new_cost + weight * next_h, next_h,
                                       new_cost, next(serial), successor))
    raise PDDLError("state space exhausted without a plan")


def resolve(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def solve_entry(entry, root, limit, weight):
    required = ("id", "domain", "problem", "plan_output")
    missing = [key for key in required if key not in entry]
    if missing:
        raise PDDLError("manifest entry missing " + ", ".join(missing))
    domain = read_domain(resolve(root, entry["domain"]))
    problem = read_problem(resolve(root, entry["problem"]))
    plan, expanded, _ = solve(domain, problem, limit, weight)

    output = resolve(root, entry["plan_output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join("%s(%s)" % (name, ", ".join(args)) for name, args in plan)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(text + ("\n" if text else ""), encoding="utf-8")
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
        if not isinstance(manifest, list) or not manifest:
            raise PDDLError("problem.json must contain a nonempty array")
        limit = request.get("max_expansions", 5000000)
        weight = request.get("weight", 3)
        if not isinstance(limit, int) or limit <= 0:
            raise PDDLError("max_expansions must be a positive integer")
        if not isinstance(weight, (int, float)) or weight <= 0:
            raise PDDLError("weight must be a positive number")

        results = []
        for entry in manifest:
            try:
                if not isinstance(entry, dict):
                    raise PDDLError("manifest entry is not an object")
                results.append(solve_entry(entry, root, limit, weight))
            except Exception as exc:
                identifier = entry.get("id", "<unknown>") if isinstance(entry, dict) else "<unknown>"
                results.append({"id": identifier, "ok": False, "error": str(exc)})
        print(json.dumps({"ok": all(result["ok"] for result in results),
                          "results": results}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "results": []}, sort_keys=True))


if __name__ == "__main__":
    main()
