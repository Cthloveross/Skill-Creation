#!/usr/bin/env python3
"""Solve or validate a manifest of typed classical PDDL tasks.
Reads one JSON object on stdin and writes one JSON object on stdout.
"""
import collections
import heapq
import itertools
import json
import os
import re
import sys
import time

CONTROL = {"and", "or", "not", "when", "forall", "exists", "imply", "=",
           "increase", "decrease", "assign", "scale-up", "scale-down"}
NUMERIC = {"increase", "decrease", "assign", "scale-up", "scale-down"}


def sexpr(text):
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    root, stack = [], [[]]
    root = stack[0]
    for token in tokens:
        if token == "(":
            node = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ")":
            if len(stack) == 1:
                raise ValueError("unexpected closing parenthesis")
            stack.pop()
        else:
            stack[-1].append(token)
    if len(stack) != 1 or len(root) != 1 or not isinstance(root[0], list):
        raise ValueError("malformed PDDL expression")
    return root[0]


def typed(items, default="object"):
    result, waiting, i = [], [], 0
    while i < len(items):
        item = items[i]
        if item == "-":
            if i + 1 >= len(items) or isinstance(items[i + 1], list):
                raise ValueError("malformed typed list")
            result.extend((name, items[i + 1]) for name in waiting)
            waiting = []
            i += 2
        else:
            if isinstance(item, list):
                raise ValueError("unexpected expression in typed list")
            waiting.append(item)
            i += 1
    result.extend((name, default) for name in waiting)
    return result


def action_fields(item):
    result, i = {}, 2
    while i + 1 < len(item):
        if isinstance(item[i], str) and item[i].startswith(":"):
            result[item[i]] = item[i + 1]
            i += 2
        else:
            i += 1
    return result


class Model:
    def __init__(self, domain_path, problem_path):
        domain = sexpr(open(domain_path, encoding="utf-8").read())
        problem = sexpr(open(problem_path, encoding="utf-8").read())
        if not domain or domain[0] != "define" or not problem or problem[0] != "define":
            raise ValueError("domain and problem must be PDDL define forms")
        self.types = {"object": None}
        self.objects = []
        self.schemas = []
        init = set()
        self.goal = ["and"]

        for item in domain[1:]:
            if not isinstance(item, list) or not item:
                continue
            if item[0] == ":types":
                self.types.update(dict(typed(item[1:])))
            elif item[0] == ":constants":
                self.objects.extend(typed(item[1:]))
            elif item[0] == ":durative-action":
                raise ValueError("durative actions are unsupported")
            elif item[0] == ":action":
                fields = action_fields(item)
                required = (":parameters", ":precondition", ":effect")
                if len(item) < 2 or any(key not in fields for key in required):
                    raise ValueError("malformed action schema")
                self.schemas.append({
                    "name": item[1], "params": typed(fields[":parameters"]),
                    "pre": fields[":precondition"], "effect": fields[":effect"]
                })

        for item in problem[1:]:
            if not isinstance(item, list) or not item:
                continue
            if item[0] == ":objects":
                self.objects.extend(typed(item[1:]))
            elif item[0] == ":init":
                for fact in item[1:]:
                    if not isinstance(fact, list) or not fact:
                        continue
                    if fact[0] in NUMERIC:
                        raise ValueError("numeric initial facts are unsupported")
                    # Classical negative init facts are represented by absence,
                    # matching the closed-world validator used for these tasks.
                    if fact[0] not in ("not", "="):
                        init.add(tuple(fact))
            elif item[0] == ":goal":
                if len(item) != 2:
                    raise ValueError("malformed goal")
                self.goal = item[1]

        self.objtype = dict(self.objects)
        self.bytype = collections.defaultdict(list)
        for obj, typ in self.objects:
            for ancestor in self.ancestors(typ):
                self.bytype[ancestor].append(obj)

        self.changed = set()
        for schema in self.schemas:
            self.mark_changed(schema["effect"])
        self.static_predicates = {fact[0] for fact in init if fact[0] not in self.changed}
        self.static = frozenset(fact for fact in init if fact[0] in self.static_predicates)
        self.start = frozenset(fact for fact in init if fact[0] not in self.static_predicates)

    def ancestors(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ)
            yield typ
            typ = self.types.get(typ)

    def mark_changed(self, expression):
        if not isinstance(expression, list) or not expression:
            return
        op = expression[0]
        if op == "and":
            for child in expression[1:]:
                self.mark_changed(child)
        elif op == "not":
            if len(expression) == 2 and isinstance(expression[1], list) and expression[1]:
                self.changed.add(expression[1][0])
        elif op in ("when", "forall"):
            if len(expression) == 3:
                self.mark_changed(expression[2])
        elif op in NUMERIC:
            raise ValueError("numeric effects are unsupported")
        elif op not in CONTROL:
            self.changed.add(op)

    def formula(self, expression, state, env=None):
        env = {} if env is None else env
        if not isinstance(expression, list) or not expression:
            raise ValueError("malformed logical formula")
        op = expression[0]
        if op == "and":
            return all(self.formula(x, state, env) for x in expression[1:])
        if op == "or":
            return any(self.formula(x, state, env) for x in expression[1:])
        if op == "not":
            return len(expression) == 2 and not self.formula(expression[1], state, env)
        if op == "imply":
            return len(expression) == 3 and (not self.formula(expression[1], state, env) or self.formula(expression[2], state, env))
        if op == "=":
            return len(expression) == 3 and env.get(expression[1], expression[1]) == env.get(expression[2], expression[2])
        if op in ("forall", "exists"):
            if len(expression) != 3:
                raise ValueError("malformed quantified formula")
            variables = typed(expression[1])
            values = []
            domains = [self.bytype[typ] for _, typ in variables]
            for assignment in itertools.product(*domains):
                extended = dict(env)
                extended.update(dict(zip((var for var, _ in variables), assignment)))
                values.append(self.formula(expression[2], state, extended))
            return all(values) if op == "forall" else any(values)
        return tuple(env.get(term, term) for term in expression) in state

    def apply(self, effect, dynamic, env):
        full = set(self.static | dynamic)

        def walk(expression, local_env):
            if not isinstance(expression, list) or not expression:
                raise ValueError("malformed effect")
            op = expression[0]
            if op == "and":
                for child in expression[1:]:
                    walk(child, local_env)
            elif op == "not":
                if len(expression) != 2 or not isinstance(expression[1], list):
                    raise ValueError("malformed delete effect")
                full.discard(tuple(local_env.get(term, term) for term in expression[1]))
            elif op == "when":
                if len(expression) != 3:
                    raise ValueError("malformed conditional effect")
                if self.formula(expression[1], full, local_env):
                    walk(expression[2], local_env)
            elif op == "forall":
                if len(expression) != 3:
                    raise ValueError("malformed quantified effect")
                variables = typed(expression[1])
                domains = [self.bytype[typ] for _, typ in variables]
                for assignment in itertools.product(*domains):
                    extended = dict(local_env)
                    extended.update(dict(zip((var for var, _ in variables), assignment)))
                    walk(expression[2], extended)
            elif op in NUMERIC:
                raise ValueError("numeric effects are unsupported")
            else:
                full.add(tuple(local_env.get(term, term) for term in expression))

        walk(effect, env)
        return frozenset(fact for fact in full if fact[0] not in self.static_predicates)

    def static_atoms(self, expression):
        answer = []

        def visit(node):
            if not isinstance(node, list) or not node:
                return
            if node[0] == "and":
                for child in node[1:]:
                    visit(child)
            elif node[0] not in CONTROL and node[0] in self.static_predicates:
                answer.append(node)

        visit(expression)
        return answer

    def positive_dynamic_atoms(self, expression, env):
        answer = []

        def visit(node):
            if not isinstance(node, list) or not node:
                return
            if node[0] == "and":
                for child in node[1:]:
                    visit(child)
            elif node[0] not in CONTROL and node[0] not in self.static_predicates:
                answer.append(tuple(env.get(term, term) for term in node))

        visit(expression)
        return tuple(answer)

    def ground(self):
        static_by_predicate = collections.defaultdict(list)
        for fact in self.static:
            static_by_predicate[fact[0]].append(fact)
        actions, seen = [], set()

        for schema in self.schemas:
            variables = [var for var, _ in schema["params"]]
            domains = {var: self.bytype[typ] for var, typ in schema["params"]}

            def bind(env, constraints):
                if constraints:
                    atom = min(constraints, key=lambda x: len(static_by_predicate[x[0]]))
                    rest = list(constraints)
                    rest.remove(atom)
                    for fact in static_by_predicate[atom[0]]:
                        if len(fact) != len(atom):
                            continue
                        extended, ok = dict(env), True
                        for term, value in zip(atom[1:], fact[1:]):
                            if term.startswith("?"):
                                if term in extended and extended[term] != value:
                                    ok = False
                                    break
                                if value not in domains.get(term, ()):
                                    ok = False
                                    break
                                extended[term] = value
                            elif term != value:
                                ok = False
                                break
                        if ok:
                            bind(extended, rest)
                    return

                missing = [var for var in variables if var not in env]
                if missing:
                    var = min(missing, key=lambda x: len(domains[x]))
                    for value in domains[var]:
                        extended = dict(env)
                        extended[var] = value
                        bind(extended, ())
                    return

                key = (schema["name"], tuple(env[var] for var in variables))
                if key in seen:
                    return
                seen.add(key)
                actions.append({
                    "name": schema["name"], "args": key[1], "env": dict(env),
                    "pre": schema["pre"], "effect": schema["effect"],
                    "positive": self.positive_dynamic_atoms(schema["pre"], env)
                })

            bind({}, self.static_atoms(schema["pre"]))
        return actions


def goal_atoms(expression):
    result = []

    def visit(node):
        if not isinstance(node, list) or not node:
            return
        if node[0] == "and":
            for child in node[1:]:
                visit(child)
        elif node[0] not in CONTROL:
            result.append(tuple(node))

    visit(expression)
    return result


def solve(model, time_limit):
    if model.formula(model.goal, model.static | model.start):
        return []
    actions = model.ground()
    if not actions:
        return None

    indexed, always = collections.defaultdict(set), set()
    for number, action in enumerate(actions):
        if action["positive"]:
            for fact in action["positive"]:
                indexed[fact].add(number)
        else:
            always.add(number)

    goals = goal_atoms(model.goal)

    def heuristic(state):
        return sum(fact not in state and fact not in model.static for fact in goals)

    deadline = time.monotonic() + time_limit
    serial = 0
    frontier = [(2 * heuristic(model.start), 0, serial, model.start)]
    best = {model.start: 0}
    parent = {model.start: (None, None)}

    while frontier:
        if time.monotonic() > deadline:
            raise TimeoutError("search time limit reached")
        _, cost, _, state = heapq.heappop(frontier)
        if best.get(state) != cost:
            continue

        candidates = set(always)
        for fact in state:
            candidates.update(indexed.get(fact, ()))
        for number in candidates:
            action = actions[number]
            if not model.formula(action["pre"], state | model.static, action["env"]):
                continue
            successor = model.apply(action["effect"], state, action["env"])
            if successor == state or cost + 1 >= best.get(successor, 10 ** 18):
                continue
            best[successor] = cost + 1
            parent[successor] = (state, action)
            if model.formula(model.goal, successor | model.static):
                plan, cursor = [], successor
                while parent[cursor][0] is not None:
                    previous, used = parent[cursor]
                    plan.append((used["name"], used["args"]))
                    cursor = previous
                return list(reversed(plan))
            serial += 1
            heapq.heappush(frontier, (cost + 1 + 2 * heuristic(successor), cost + 1, serial, successor))
    return None


def validate(model, plan):
    schemas = {schema["name"]: schema for schema in model.schemas}
    state = model.start
    for step, (name, args) in enumerate(plan, 1):
        schema = schemas.get(name)
        if schema is None:
            return {"valid": False, "step": step, "reason": "undeclared action " + name}
        if len(args) != len(schema["params"]):
            return {"valid": False, "step": step, "reason": "wrong action arity"}
        env = dict(zip((var for var, _ in schema["params"]), args))
        for variable, needed_type in schema["params"]:
            obj = env[variable]
            if obj not in model.objtype or needed_type not in set(model.ancestors(model.objtype[obj])):
                return {"valid": False, "step": step, "reason": "unknown or ill-typed object " + obj}
        if not model.formula(schema["pre"], state | model.static, env):
            return {"valid": False, "step": step, "reason": "unsatisfied precondition"}
        state = model.apply(schema["effect"], state, env)
    if not model.formula(model.goal, state | model.static):
        return {"valid": False, "step": len(plan), "reason": "goal not satisfied"}
    return {"valid": True, "steps": len(plan)}


def read_plan(path):
    plan = []
    with open(path, encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            line = raw.split(";", 1)[0].strip().lower()
            if not line:
                continue
            match = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
            if not match:
                raise ValueError("line %d is not a grounded action primitive" % line_number)
            args = tuple(x.strip() for x in match.group(2).split(",") if x.strip())
            if any(not re.fullmatch(r"[a-z0-9_-]+", x) for x in args):
                raise ValueError("line %d has malformed argument" % line_number)
            plan.append((match.group(1), args))
    return plan


def entries(manifest_path):
    with open(manifest_path, encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("tasks", "problems"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError("manifest must be a list or contain tasks/problems")


def resolve(path, base):
    return path if os.path.isabs(path) else os.path.join(base, path)


def valid_entry(entry):
    return isinstance(entry, dict) and all(isinstance(entry.get(key), str) and entry[key]
                                           for key in ("domain", "problem", "plan_output"))


def solve_one(entry, base, time_limit):
    label = entry.get("id") if isinstance(entry, dict) else None
    try:
        if not valid_entry(entry):
            raise ValueError("entry requires domain, problem, and plan_output")
        model = Model(resolve(entry["domain"], base), resolve(entry["problem"], base))
        plan = solve(model, time_limit)
        if plan is None:
            return {"id": label, "status": "unsolved"}
        verdict = validate(model, plan)
        if not verdict["valid"]:
            return {"id": label, "status": "error", "reason": "internal replay failed", "validation": verdict}
        output = resolve(entry["plan_output"], base)
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        temporary = output + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            for name, args in plan:
                handle.write("%s(%s)\n" % (name, ", ".join(args)))
        os.replace(temporary, output)
        return {"id": label, "status": "solved", "plan_output": output,
                "plan_length": len(plan), "validation": verdict}
    except TimeoutError as exc:
        return {"id": label, "status": "timeout", "reason": str(exc)}
    except Exception as exc:
        return {"id": label, "status": "error", "reason": str(exc)}


def validate_manifest(manifest_path):
    base, results = os.path.dirname(os.path.abspath(manifest_path)), []
    for entry in entries(manifest_path):
        label = entry.get("id") if isinstance(entry, dict) else None
        try:
            if not valid_entry(entry):
                raise ValueError("entry requires domain, problem, and plan_output")
            output = resolve(entry["plan_output"], base)
            if not os.path.isfile(output):
                raise ValueError("required plan output is missing: " + output)
            model = Model(resolve(entry["domain"], base), resolve(entry["problem"], base))
            results.append({"id": label, "plan_output": output, **validate(model, read_plan(output))})
        except Exception as exc:
            results.append({"id": label, "valid": False, "reason": str(exc)})
    return {"ok": all(result.get("valid") for result in results), "results": results}


def main(request):
    manifest = os.path.abspath(request.get("manifest", "problem.json"))
    if request.get("mode") == "validate-manifest":
        return validate_manifest(manifest)
    base = os.path.dirname(manifest)
    time_limit = float(request.get("time_limit_sec", 240))
    results = [solve_one(entry, base, time_limit) for entry in entries(manifest)]
    return {"ok": all(result.get("status") == "solved" for result in results), "results": results}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "error", "reason": str(exc)}))
        sys.exit(2)
