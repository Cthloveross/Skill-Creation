#!/usr/bin/env python3
"""Manifest-driven typed classical PDDL planner. JSON on stdin/stdout."""
import collections
import heapq
import itertools
import json
import os
import re
import sys
import time

NUMERIC = {"increase", "decrease", "assign", "scale-up", "scale-down"}
LOGICAL = {"and", "or", "not", "imply", "=", "forall", "exists", "when"}


def parse_sexpr(text):
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    root, stack = [], []
    stack.append(root)
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
        raise ValueError("malformed PDDL")
    return root[0]


def typed(items, default="object"):
    result, waiting = [], []
    i = 0
    while i < len(items):
        if items[i] == "-":
            if i + 1 == len(items) or isinstance(items[i + 1], list):
                raise ValueError("malformed typed list")
            result.extend((name, items[i + 1]) for name in waiting)
            waiting = []
            i += 2
        else:
            if isinstance(items[i], list):
                raise ValueError("unexpected expression in typed list")
            waiting.append(items[i])
            i += 1
    result.extend((name, default) for name in waiting)
    return result


def action_fields(form):
    fields = {}
    i = 2
    while i + 1 < len(form):
        if isinstance(form[i], str) and form[i].startswith(":"):
            fields[form[i]] = form[i + 1]
            i += 2
        else:
            i += 1
    return fields


class Model:
    def __init__(self, domain_path, problem_path):
        domain = parse_sexpr(open(domain_path, encoding="utf-8").read())
        problem = parse_sexpr(open(problem_path, encoding="utf-8").read())
        if not domain or not problem or domain[0] != "define" or problem[0] != "define":
            raise ValueError("domain and problem must be PDDL define forms")

        self.types = {"object": None}
        self.actions = []
        changed = set()
        for form in domain[1:]:
            if not isinstance(form, list) or not form:
                continue
            if form[0] == ":types":
                self.types.update(dict(typed(form[1:])))
            elif form[0] == ":durative-action":
                raise ValueError("durative PDDL is unsupported")
            elif form[0] == ":action":
                if len(form) < 2:
                    raise ValueError("malformed action")
                fields = action_fields(form)
                needed = (":parameters", ":precondition", ":effect")
                if not all(key in fields for key in needed):
                    raise ValueError("incomplete action schema " + form[1])
                parameters = typed(fields[":parameters"])
                self.actions.append((form[1], parameters, fields[":precondition"], fields[":effect"]))
                self.effect_predicates(fields[":effect"], changed)
        if not self.actions:
            raise ValueError("domain has no action schemas")

        self.objects, init, self.goal = {}, set(), None
        for form in problem[1:]:
            if not isinstance(form, list) or not form:
                continue
            if form[0] == ":objects":
                self.objects.update(dict(typed(form[1:])))
            elif form[0] == ":init":
                for atom in form[1:]:
                    if not isinstance(atom, list) or not atom:
                        continue
                    if atom[0] in NUMERIC:
                        raise ValueError("numeric PDDL is unsupported")
                    if atom[0] not in ("not", "="):
                        init.add(tuple(atom))
            elif form[0] == ":goal":
                if len(form) != 2:
                    raise ValueError("malformed goal")
                self.goal = form[1]
        if self.goal is None:
            raise ValueError("problem has no goal")

        self.by_type = collections.defaultdict(list)
        for obj, typ in self.objects.items():
            for ancestor in self.ancestors(typ):
                self.by_type[ancestor].append(obj)
        self.static_predicates = {atom[0] for atom in init if atom[0] not in changed}
        self.fixed = frozenset(atom for atom in init if atom[0] in self.static_predicates)
        self.initial = frozenset(atom for atom in init if atom[0] not in self.static_predicates)

    def ancestors(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ)
            yield typ
            typ = self.types.get(typ)

    def effect_predicates(self, expr, output):
        if not isinstance(expr, list) or not expr:
            raise ValueError("malformed effect")
        op = expr[0]
        if op == "and":
            for child in expr[1:]:
                self.effect_predicates(child, output)
        elif op == "not":
            if len(expr) != 2 or not isinstance(expr[1], list) or not expr[1]:
                raise ValueError("malformed delete effect")
            output.add(expr[1][0])
        elif op in ("when", "forall"):
            if len(expr) != 3:
                raise ValueError("malformed conditional or quantified effect")
            self.effect_predicates(expr[2], output)
        elif op in NUMERIC:
            raise ValueError("numeric PDDL is unsupported")
        elif op not in LOGICAL:
            output.add(op)

    @staticmethod
    def substitute(expr, env):
        if isinstance(expr, str):
            return env.get(expr, expr)
        return [Model.substitute(item, env) for item in expr]

    def formula(self, expr, facts, env=None):
        env = {} if env is None else env
        if not isinstance(expr, list) or not expr:
            raise ValueError("malformed logical formula")
        op = expr[0]
        if op == "and":
            return all(self.formula(child, facts, env) for child in expr[1:])
        if op == "or":
            return any(self.formula(child, facts, env) for child in expr[1:])
        if op == "not":
            return len(expr) == 2 and not self.formula(expr[1], facts, env)
        if op == "imply":
            return len(expr) == 3 and (not self.formula(expr[1], facts, env) or self.formula(expr[2], facts, env))
        if op == "=":
            return len(expr) == 3 and env.get(expr[1], expr[1]) == env.get(expr[2], expr[2])
        if op in ("forall", "exists"):
            if len(expr) != 3:
                raise ValueError("malformed quantifier")
            variables = typed(expr[1])
            values = []
            domains = [self.by_type[t] for _, t in variables]
            for values_tuple in itertools.product(*domains):
                local = dict(env)
                local.update(dict(zip((v for v, _ in variables), values_tuple)))
                values.append(self.formula(expr[2], facts, local))
            return all(values) if op == "forall" else any(values)
        return tuple(env.get(symbol, symbol) for symbol in expr) in facts

    def apply(self, effect, state, env):
        before = self.fixed | state
        after = set(before)

        def walk(expr, local):
            if not isinstance(expr, list) or not expr:
                raise ValueError("malformed effect")
            op = expr[0]
            if op == "and":
                for child in expr[1:]:
                    walk(child, local)
            elif op == "not":
                if len(expr) != 2 or not isinstance(expr[1], list):
                    raise ValueError("malformed negative effect")
                after.discard(tuple(local.get(x, x) for x in expr[1]))
            elif op == "when":
                if len(expr) != 3:
                    raise ValueError("malformed conditional effect")
                if self.formula(expr[1], before, local):
                    walk(expr[2], local)
            elif op == "forall":
                if len(expr) != 3:
                    raise ValueError("malformed quantified effect")
                variables = typed(expr[1])
                for vals in itertools.product(*[self.by_type[t] for _, t in variables]):
                    scoped = dict(local)
                    scoped.update(dict(zip((v for v, _ in variables), vals)))
                    walk(expr[2], scoped)
            elif op in NUMERIC:
                raise ValueError("numeric PDDL is unsupported")
            else:
                after.add(tuple(local.get(x, x) for x in expr))

        walk(effect, env)
        return frozenset(atom for atom in after if atom[0] not in self.static_predicates)

    def static_positive_atoms(self, expr):
        if not isinstance(expr, list) or not expr:
            return []
        if expr[0] == "and":
            answer = []
            for child in expr[1:]:
                answer.extend(self.static_positive_atoms(child))
            return answer
        if expr[0] not in LOGICAL and expr[0] in self.static_predicates:
            return [tuple(expr)]
        return []

    def ground_actions(self):
        static_index = collections.defaultdict(list)
        for atom in self.fixed:
            static_index[atom[0]].append(atom)
        grounded = []
        for name, params, precondition, effect in self.actions:
            variables = [v for v, _ in params]
            domains = {v: self.by_type[t] for v, t in params}
            constraints = self.static_positive_atoms(precondition)

            def complete(env):
                remaining = [v for v in variables if v not in env]
                if not remaining:
                    grounded.append((name, tuple(env[v] for v in variables), env, precondition, effect))
                    return
                var = min(remaining, key=lambda v: len(domains[v]))
                for obj in domains[var]:
                    extended = dict(env)
                    extended[var] = obj
                    complete(extended)

            def match(env, remaining):
                if not remaining:
                    complete(env)
                    return
                atom = max(remaining, key=lambda a: sum(x in env for x in a[1:]))
                rest = list(remaining)
                rest.remove(atom)
                for fact in static_index[atom[0]]:
                    if len(atom) != len(fact):
                        continue
                    extended, good = dict(env), True
                    for term, obj in zip(atom[1:], fact[1:]):
                        if isinstance(term, str) and term.startswith("?"):
                            if term not in domains or obj not in domains[term] or (term in extended and extended[term] != obj):
                                good = False
                                break
                            extended[term] = obj
                        elif term != obj:
                            good = False
                            break
                    if good:
                        match(extended, rest)

            match({}, constraints)
        return grounded


def positive_goal_atoms(expr):
    if not isinstance(expr, list) or not expr:
        return []
    if expr[0] == "and":
        result = []
        for child in expr[1:]:
            result.extend(positive_goal_atoms(child))
        return result
    return [tuple(expr)] if expr[0] not in LOGICAL else []


def solve(model, time_limit):
    if model.formula(model.goal, model.fixed | model.initial):
        return []
    actions = model.ground_actions()
    if not actions:
        return None
    goals = positive_goal_atoms(model.goal)

    def heuristic(state):
        return sum(atom not in model.fixed and atom not in state for atom in goals)

    deadline = time.monotonic() + time_limit
    counter = 0
    best = {model.initial: 0}
    parent = {model.initial: (None, None)}
    queue = [(heuristic(model.initial), 0, counter, model.initial)]
    while queue:
        if time.monotonic() > deadline:
            raise TimeoutError("search time limit reached")
        _, cost, _, state = heapq.heappop(queue)
        if best.get(state) != cost:
            continue
        for name, args, env, precondition, effect in actions:
            if not model.formula(precondition, model.fixed | state, env):
                continue
            successor = model.apply(effect, state, env)
            new_cost = cost + 1
            if successor == state or new_cost >= best.get(successor, 10 ** 18):
                continue
            best[successor] = new_cost
            parent[successor] = (state, (name, args))
            if model.formula(model.goal, model.fixed | successor):
                plan = []
                while parent[successor][0] is not None:
                    predecessor, action = parent[successor]
                    plan.append(action)
                    successor = predecessor
                return list(reversed(plan))
            counter += 1
            heapq.heappush(queue, (new_cost + heuristic(successor), new_cost, counter, successor))
    return None


def read_plan(path):
    result = []
    for line_number, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.split(";", 1)[0].strip().lower()
        if not line:
            continue
        match = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
        if match:
            args = tuple(x.strip() for x in match.group(2).split(",") if x.strip())
        else:
            match = re.fullmatch(r"\(\s*([a-z0-9_-]+)((?:\s+[a-z0-9_-]+)*)\s*\)", line)
            if not match:
                raise ValueError("invalid plan line %d" % line_number)
            args = tuple(match.group(2).split())
        result.append((match.group(1), args))
    return result


def validate(model, plan):
    schemas = {name: (params, pre, effect) for name, params, pre, effect in model.actions}
    state = model.initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in schemas:
            return {"valid": False, "step": step, "reason": "undeclared action"}
        params, precondition, effect = schemas[name]
        if len(params) != len(args):
            return {"valid": False, "step": step, "reason": "wrong arity"}
        env = dict(zip((v for v, _ in params), args))
        for var, expected_type in params:
            obj = env[var]
            if obj not in model.objects or expected_type not in set(model.ancestors(model.objects[obj])):
                return {"valid": False, "step": step, "reason": "ill-typed object"}
        if not model.formula(precondition, model.fixed | state, env):
            return {"valid": False, "step": step, "reason": "unsatisfied precondition"}
        state = model.apply(effect, state, env)
    if model.formula(model.goal, model.fixed | state):
        return {"valid": True, "steps": len(plan)}
    return {"valid": False, "reason": "goal not satisfied"}


def manifest_entries(path):
    document = json.load(open(path, encoding="utf-8"))
    if isinstance(document, list):
        return document
    if isinstance(document, dict):
        for key in ("tasks", "problems"):
            if isinstance(document.get(key), list):
                return document[key]
    raise ValueError("manifest must be a list or contain tasks/problems")


def resolve(path, base):
    return path if os.path.isabs(path) else os.path.join(base, path)


def check_entry(entry):
    if not isinstance(entry, dict):
        raise ValueError("task entry is not an object")
    for key in ("domain", "problem", "plan_output"):
        if not isinstance(entry.get(key), str) or not entry[key]:
            raise ValueError("entry lacks " + key)


def get_model(entry, base):
    return Model(resolve(entry["domain"], base), resolve(entry["problem"], base))


def main(request):
    manifest = os.path.abspath(request.get("manifest", "problem.json"))
    base = os.path.dirname(manifest)
    entries = manifest_entries(manifest)
    if not entries:
        raise ValueError("manifest contains no tasks")

    if request.get("mode") == "validate-manifest":
        results = []
        for entry in entries:
            label = entry.get("id") if isinstance(entry, dict) else None
            try:
                check_entry(entry)
                output = resolve(entry["plan_output"], base)
                if not os.path.isfile(output):
                    raise ValueError("required plan output is missing: " + output)
                results.append({"id": label, "plan_output": output, **validate(get_model(entry, base), read_plan(output))})
            except Exception as exc:
                results.append({"id": label, "valid": False, "reason": str(exc)})
        return {"ok": all(item.get("valid") for item in results), "results": results}

    limit = float(request.get("time_limit_sec", 240))
    results = []
    for entry in entries:
        label = entry.get("id") if isinstance(entry, dict) else None
        try:
            check_entry(entry)
            model = get_model(entry, base)
            plan = solve(model, limit)
            if plan is None:
                results.append({"id": label, "status": "unsolved"})
                continue
            replay = validate(model, plan)
            if not replay["valid"]:
                raise ValueError("internal replay failed: " + str(replay))
            output = resolve(entry["plan_output"], base)
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
            temporary = output + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                for name, args in plan:
                    handle.write(name + "(" + ",".join(args) + ")\n")
            os.replace(temporary, output)
            results.append({"id": label, "status": "solved", "plan_output": output,
                            "plan_length": len(plan), "validation": replay})
        except TimeoutError as exc:
            results.append({"id": label, "status": "timeout", "reason": str(exc)})
        except Exception as exc:
            results.append({"id": label, "status": "error", "reason": str(exc)})
    return {"ok": all(item.get("status") == "solved" for item in results), "results": results}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "error", "reason": str(exc)}))
        sys.exit(2)
