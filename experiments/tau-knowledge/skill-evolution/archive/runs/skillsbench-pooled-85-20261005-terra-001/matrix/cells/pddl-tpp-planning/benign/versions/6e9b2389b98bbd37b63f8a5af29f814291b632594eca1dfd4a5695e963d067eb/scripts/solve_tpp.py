#!/usr/bin/env python3
"""Typed classical-PDDL batch planner.

Read one JSON request from stdin, solve every entry in its problem.json manifest,
write each requested plan file, and emit a JSON report on stdout.  Only the
Python standard library is required.
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


def tokens(text):
    """Tokenize case-insensitive PDDL, discarding semicolon comments."""
    text = re.sub(r";[^\n]*", "", text).lower()
    return re.findall(r"\(|\)|[^\s()]+", text)


def parse_sexpr(text):
    ts = tokens(text)
    at = 0

    def read_one():
        nonlocal at
        if at >= len(ts):
            raise PDDLError("unexpected end of PDDL")
        token = ts[at]
        at += 1
        if token == "(":
            result = []
            while True:
                if at >= len(ts):
                    raise PDDLError("unclosed parenthesis")
                if ts[at] == ")":
                    at += 1
                    return result
                result.append(read_one())
        if token == ")":
            raise PDDLError("unexpected closing parenthesis")
        return token

    tree = read_one()
    if at != len(ts):
        raise PDDLError("multiple top-level PDDL forms")
    if not isinstance(tree, list) or not tree or tree[0] != "define":
        raise PDDLError("expected a (define ...) PDDL form")
    return tree


def section(tree, label):
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] == label:
            return item[1:]
    return None


def typed(items, default="object"):
    """Parse PDDL grouped typed lists into ordered (name, type) pairs."""
    out, pending = [], []
    i = 0
    while i < len(items):
        item = items[i]
        if not isinstance(item, str):
            raise PDDLError("list where a typed name was expected")
        if item == "-":
            if not pending or i + 1 >= len(items) or not isinstance(items[i + 1], str):
                raise PDDLError("malformed typed list")
            out.extend((name, items[i + 1]) for name in pending)
            pending = []
            i += 2
        else:
            pending.append(item)
            i += 1
    out.extend((name, default) for name in pending)
    return out


def atom(form):
    if not isinstance(form, list) or not form or not isinstance(form[0], str):
        raise PDDLError("expected predicate atom")
    if any(isinstance(x, list) for x in form[1:]):
        raise PDDLError("function terms are unsupported")
    return tuple(form)


def formula(form, where, effect=False):
    """Flatten a conjunction to (positive atoms, negative atoms).

    Numeric effects are intentionally returned as no propositional effect.
    """
    if not isinstance(form, list) or not form:
        raise PDDLError("empty " + where)
    op = form[0] if isinstance(form[0], str) else ""
    if op == "and":
        pos, neg = [], []
        for child in form[1:]:
            cp, cn = formula(child, where, effect)
            pos.extend(cp)
            neg.extend(cn)
        return pos, neg
    if effect and op in {"increase", "decrease", "assign", "scale-up", "scale-down"}:
        return [], []
    if op == "not":
        if len(form) != 2:
            raise PDDLError("malformed negation in " + where)
        inside = atom(form[1])
        if inside[0] in {"and", "or", "not"}:
            raise PDDLError("non-atomic negation in " + where)
        return [], [inside]
    if op in {"or", "forall", "exists", "imply", "when"}:
        raise PDDLError("unsupported " + op + " in " + where)
    value = atom(form)
    if value[0] in {">", "<", ">=", "<="}:
        raise PDDLError("numeric comparison unsupported in " + where)
    return [value], []


def action_fields(item):
    fields = {}
    i = 2
    while i < len(item):
        if not isinstance(item[i], str) or not item[i].startswith(":") or i + 1 >= len(item):
            raise PDDLError("malformed action declaration")
        fields[item[i]] = item[i + 1]
        i += 2
    return fields


def read_domain(path):
    tree = parse_sexpr(Path(path).read_text(encoding="utf-8"))
    parents = {"object": None}
    raw_types = section(tree, ":types")
    if raw_types:
        parents.update(dict(typed(raw_types)))
    constants = typed(section(tree, ":constants") or [])
    actions = []
    for item in tree[1:]:
        if not (isinstance(item, list) and len(item) >= 2 and item[0] == ":action"):
            continue
        name = item[1]
        fields = action_fields(item)
        raw_parameters = fields.get(":parameters")
        if not isinstance(raw_parameters, list):
            raise PDDLError("action %s lacks a parameter list" % name)
        parameters = typed(raw_parameters)
        if any(not var.startswith("?") for var, _ in parameters):
            raise PDDLError("action %s has a non-variable parameter" % name)
        pre_pos, pre_neg = formula(fields.get(":precondition", ["and"]), "precondition of " + name)
        add, delete = formula(fields.get(":effect", ["and"]), "effect of " + name, effect=True)
        if any(item[0] == "=" for item in add + delete):
            raise PDDLError("equality is not a valid action effect")
        actions.append({"name": name, "parameters": parameters, "pre_pos": pre_pos,
                        "pre_neg": pre_neg, "add": add, "delete": delete})
    if not actions:
        raise PDDLError("domain declares no actions")
    return {"parents": parents, "constants": constants, "actions": actions}


def read_problem(path):
    tree = parse_sexpr(Path(path).read_text(encoding="utf-8"))
    objects = typed(section(tree, ":objects") or [])
    raw_init = section(tree, ":init")
    if raw_init is None:
        raise PDDLError("problem has no :init")
    initial = set()
    for item in raw_init:
        pos, neg = formula(item, "initial state")
        if neg:
            raise PDDLError("negative initial facts are unsupported")
        for fact in pos:
            if fact[0] == "=":
                # Equality is evaluated directly, never represented as a state fact.
                continue
            initial.add(fact)
    raw_goal = section(tree, ":goal")
    if raw_goal is None or len(raw_goal) != 1:
        raise PDDLError("problem has malformed or missing :goal")
    goal_pos, goal_neg = formula(raw_goal[0], "goal")
    return {"objects": objects, "initial": frozenset(initial),
            "goal_pos": goal_pos, "goal_neg": goal_neg}


def subtype(actual, required, parents):
    seen = set()
    while actual is not None and actual not in seen:
        if actual == required:
            return True
        seen.add(actual)
        actual = parents.get(actual)
    return False


def substitute(term, env):
    return env[term] if isinstance(term, str) and term.startswith("?") else term


def ground(fact, env):
    return tuple(substitute(term, env) for term in fact)


def equality(fact, env):
    if len(fact) != 3:
        raise PDDLError("equality must contain exactly two terms")
    return substitute(fact[1], env) == substitute(fact[2], env)


def holds(pos, neg, state, env):
    for fact in pos:
        if fact[0] == "=":
            if not equality(fact, env):
                return False
        elif ground(fact, env) not in state:
            return False
    for fact in neg:
        if fact[0] == "=":
            if equality(fact, env):
                return False
        elif ground(fact, env) in state:
            return False
    return True


def all_objects(domain, problem):
    result = {}
    for name, kind in domain["constants"] + problem["objects"]:
        previous = result.get(name)
        if previous is not None and previous != kind:
            raise PDDLError("conflicting types for object " + name)
        if kind not in domain["parents"]:
            raise PDDLError("undeclared type " + kind)
        result[name] = kind
    return result


def applicable(schema, state, object_types, parents):
    """Yield every type-valid applicable grounding of one action schema."""
    facts_by_predicate = defaultdict(list)
    for fact in state:
        facts_by_predicate[fact[0]].append(fact)
    patterns = [x for x in schema["pre_pos"] if x[0] != "="]
    patterns.sort(key=lambda x: len(facts_by_predicate.get(x[0], ())))
    environments = [{}]
    for pattern in patterns:
        matching = facts_by_predicate.get(pattern[0], ())
        if not matching:
            return
        next_envs = []
        for env in environments:
            for fact in matching:
                if len(fact) != len(pattern):
                    continue
                candidate = dict(env)
                valid = True
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
                    next_envs.append(candidate)
        environments = next_envs
        if not environments:
            return

    choices = []
    for variable, required_type in schema["parameters"]:
        values = [obj for obj, actual_type in object_types.items()
                  if subtype(actual_type, required_type, parents)]
        choices.append((variable, values))

    for partial in environments:
        # A fact match alone must not bypass declared parameter typing.
        if any(var in partial and partial[var] not in values for var, values in choices):
            continue
        missing = [(var, values) for var, values in choices if var not in partial]
        if any(not values for _, values in missing):
            continue
        combinations = itertools.product(*(values for _, values in missing)) if missing else [()]
        for values in combinations:
            env = dict(partial)
            env.update({var: value for (var, _), value in zip(missing, values)})
            if not holds(schema["pre_pos"], schema["pre_neg"], state, env):
                continue
            deleted = {ground(fact, env) for fact in schema["delete"]}
            added = {ground(fact, env) for fact in schema["add"]}
            successor = frozenset((set(state) - deleted) | added)
            args = tuple(env[var] for var, _ in schema["parameters"])
            yield schema["name"], args, successor


def goal_reached(problem, state):
    return holds(problem["goal_pos"], problem["goal_neg"], state, {})


def goal_distance(problem, state):
    missing = 0
    for fact in problem["goal_pos"]:
        if fact[0] == "=":
            missing += not equality(fact, {})
        else:
            missing += fact not in state
    for fact in problem["goal_neg"]:
        if fact[0] == "=":
            missing += equality(fact, {})
        else:
            missing += fact in state
    return int(missing)


def replay(domain, problem, plan, object_types):
    schemas = {schema["name"]: schema for schema in domain["actions"]}
    state = problem["initial"]
    for number, (name, args) in enumerate(plan, 1):
        schema = schemas.get(name)
        if schema is None:
            raise PDDLError("step %d uses unknown action %s" % (number, name))
        if len(args) != len(schema["parameters"]):
            raise PDDLError("step %d has wrong arity" % number)
        env = {}
        for (var, required), value in zip(schema["parameters"], args):
            actual = object_types.get(value)
            if actual is None or not subtype(actual, required, domain["parents"]):
                raise PDDLError("step %d has type-invalid argument %s" % (number, value))
            env[var] = value
        if not holds(schema["pre_pos"], schema["pre_neg"], state, env):
            raise PDDLError("precondition fails at step %d" % number)
        state = frozenset((set(state) - {ground(x, env) for x in schema["delete"]}) |
                          {ground(x, env) for x in schema["add"]})
    if not goal_reached(problem, state):
        raise PDDLError("final state does not satisfy goal")


def solve(domain, problem, limit, weight):
    object_types = all_objects(domain, problem)
    start = problem["initial"]
    if goal_reached(problem, start):
        return [], 0, object_types
    queue = []
    serial = itertools.count()
    best_cost = {start: 0}
    predecessor = {}
    initial_h = goal_distance(problem, start)
    heapq.heappush(queue, (weight * initial_h, initial_h, 0, next(serial), start))
    expanded = 0

    while queue:
        _, _, cost, _, state = heapq.heappop(queue)
        if cost != best_cost.get(state):
            continue
        if goal_reached(problem, state):
            plan = []
            current = state
            while current != start:
                previous, action = predecessor[current]
                plan.append(action)
                current = previous
            plan.reverse()
            replay(domain, problem, plan, object_types)
            return plan, expanded, object_types
        expanded += 1
        if expanded > limit:
            raise PDDLError("search expansion limit exceeded (%d)" % limit)
        for schema in domain["actions"]:
            for name, args, successor in applicable(schema, state, object_types, domain["parents"]):
                new_cost = cost + 1
                if new_cost >= best_cost.get(successor, 10 ** 30):
                    continue
                best_cost[successor] = new_cost
                predecessor[successor] = (state, (name, args))
                h = goal_distance(problem, successor)
                heapq.heappush(queue, (new_cost + weight * h, h, new_cost,
                                       next(serial), successor))
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
    output.write_text(text + ("\n" if text else ""), encoding="utf-8")
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
        limit = request.get("max_expansions", 2000000)
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
        print(json.dumps({"ok": all(item["ok"] for item in results), "results": results}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "results": []}, sort_keys=True))


if __name__ == "__main__":
    main()
