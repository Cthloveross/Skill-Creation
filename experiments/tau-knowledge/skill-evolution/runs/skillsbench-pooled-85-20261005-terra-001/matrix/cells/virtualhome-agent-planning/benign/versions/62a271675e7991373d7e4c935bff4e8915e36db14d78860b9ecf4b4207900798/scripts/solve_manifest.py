#!/usr/bin/env python3
"""Solve or replay typed classical PDDL tasks. JSON stdin -> JSON stdout."""
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


def tokens(text):
    return re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())


def parse_sexpr(text):
    root, stack = [], []
    stack.append(root)
    for token in tokens(text):
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
    result, pending, i = [], [], 0
    while i < len(items):
        if items[i] == "-":
            if i + 1 >= len(items) or isinstance(items[i + 1], list):
                raise ValueError("malformed typed list")
            result.extend((x, items[i + 1]) for x in pending)
            pending = []
            i += 2
        else:
            if isinstance(items[i], list):
                raise ValueError("unexpected list in typed names")
            pending.append(items[i])
            i += 1
    result.extend((x, default) for x in pending)
    return result


def substitute(expr, env):
    if isinstance(expr, str):
        return env.get(expr, expr)
    return [substitute(x, env) for x in expr]


class Model:
    def __init__(self, domain_path, problem_path):
        domain = parse_sexpr(open(domain_path, encoding="utf-8").read())
        problem = parse_sexpr(open(problem_path, encoding="utf-8").read())
        if not domain or domain[0] != "define" or not problem or problem[0] != "define":
            raise ValueError("domain and problem must be PDDL define forms")
        self.types = {"object": None}
        self.schemas = []
        self.objects = []
        self.goal = ["and"]
        initial = set()
        for item in domain[1:]:
            if not isinstance(item, list) or not item:
                continue
            if item[0] == ":types":
                self.types.update(dict(typed(item[1:])))
            elif item[0] == ":constants":
                # Constants are legal PDDL terms. Airport instances normally use objects.
                self.objects.extend(typed(item[1:]))
            elif item[0] == ":action":
                self.schemas.append(self.read_action(item))
            elif item[0] == ":durative-action":
                raise ValueError("durative actions are unsupported")
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
                    if fact[0] != "=" and fact[0] != "not":
                        initial.add(tuple(fact))
            elif item[0] == ":goal":
                if len(item) != 2:
                    raise ValueError("malformed goal")
                self.goal = item[1]
        self.objtype = dict(self.objects)
        self.bytype = collections.defaultdict(list)
        for obj, typ in self.objects:
            for ancestor in self.ancestors(typ):
                self.bytype[ancestor].append(obj)
        self.effect_predicates = set()
        for schema in self.schemas:
            self.mark_effects(schema["effect"])
        self.static_predicates = {fact[0] for fact in initial if fact[0] not in self.effect_predicates}
        self.static = frozenset(f for f in initial if f[0] in self.static_predicates)
        self.start = frozenset(f for f in initial if f[0] not in self.static_predicates)

    def read_action(self, item):
        if len(item) < 2:
            raise ValueError("malformed action")
        fields, i = {}, 2
        while i + 1 < len(item):
            if isinstance(item[i], str) and item[i].startswith(":"):
                fields[item[i]] = item[i + 1]
                i += 2
            else:
                i += 1
        for required in (":parameters", ":precondition", ":effect"):
            if required not in fields:
                raise ValueError("action %s lacks %s" % (item[1], required))
        return {"name": item[1], "params": typed(fields[":parameters"]),
                "pre": fields[":precondition"], "effect": fields[":effect"]}

    def ancestors(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ)
            yield typ
            typ = self.types.get(typ)

    def mark_effects(self, expr):
        if not isinstance(expr, list) or not expr:
            return
        op = expr[0]
        if op == "and":
            for child in expr[1:]:
                self.mark_effects(child)
        elif op == "not" and len(expr) == 2 and isinstance(expr[1], list) and expr[1]:
            self.effect_predicates.add(expr[1][0])
        elif op in ("when", "forall") and len(expr) == 3:
            self.mark_effects(expr[2])
        elif op in NUMERIC:
            raise ValueError("numeric effects are unsupported")
        elif op not in CONTROL:
            self.effect_predicates.add(op)

    def formula(self, expr, state, env=None):
        env = {} if env is None else env
        if not isinstance(expr, list) or not expr:
            raise ValueError("malformed logical formula")
        op = expr[0]
        if op == "and":
            return all(self.formula(x, state, env) for x in expr[1:])
        if op == "or":
            return any(self.formula(x, state, env) for x in expr[1:])
        if op == "not":
            return len(expr) == 2 and not self.formula(expr[1], state, env)
        if op == "imply":
            return len(expr) == 3 and (not self.formula(expr[1], state, env) or self.formula(expr[2], state, env))
        if op == "=":
            return len(expr) == 3 and env.get(expr[1], expr[1]) == env.get(expr[2], expr[2])
        if op in ("forall", "exists"):
            if len(expr) != 3:
                raise ValueError("malformed quantified formula")
            variables = typed(expr[1])
            pools = [self.bytype[t] for _, t in variables]
            values = []
            for values_tuple in itertools.product(*pools):
                next_env = dict(env)
                next_env.update(dict(zip((v for v, _ in variables), values_tuple)))
                values.append(self.formula(expr[2], state, next_env))
            return all(values) if op == "forall" else any(values)
        return tuple(env.get(x, x) for x in expr) in state

    def apply(self, effect, dynamic, env):
        # Mutate an assembled full state in expression order, matching standard simple validators.
        full = set(self.static | dynamic)
        def walk(expr, local):
            if not isinstance(expr, list) or not expr:
                raise ValueError("malformed effect")
            op = expr[0]
            if op == "and":
                for child in expr[1:]:
                    walk(child, local)
            elif op == "not":
                if len(expr) != 2 or not isinstance(expr[1], list):
                    raise ValueError("malformed delete effect")
                full.discard(tuple(local.get(x, x) for x in expr[1]))
            elif op == "when":
                if len(expr) != 3:
                    raise ValueError("malformed conditional effect")
                if self.formula(expr[1], full, local):
                    walk(expr[2], local)
            elif op == "forall":
                if len(expr) != 3:
                    raise ValueError("malformed quantified effect")
                variables = typed(expr[1])
                pools = [self.bytype[t] for _, t in variables]
                for vals in itertools.product(*pools):
                    nested = dict(local)
                    nested.update(dict(zip((v for v, _ in variables), vals)))
                    walk(expr[2], nested)
            elif op in NUMERIC:
                raise ValueError("numeric effect")
            else:
                full.add(tuple(local.get(x, x) for x in expr))
        walk(effect, env)
        return frozenset(x for x in full if x[0] not in self.static_predicates)

    def static_atoms(self, expr):
        result = []
        def visit(x):
            if not isinstance(x, list) or not x:
                return
            if x[0] == "and":
                for y in x[1:]:
                    visit(y)
            elif x[0] not in CONTROL and x[0] in self.static_predicates:
                result.append(x)
        visit(expr)
        return result

    def dynamic_positive_atoms(self, expr, env):
        result = []
        def visit(x):
            if not isinstance(x, list) or not x:
                return
            if x[0] == "and":
                for y in x[1:]:
                    visit(y)
            elif x[0] not in CONTROL and x[0] not in self.static_predicates:
                result.append(tuple(env.get(v, v) for v in x))
        visit(expr)
        return tuple(result)

    def ground_actions(self):
        facts_by_pred = collections.defaultdict(list)
        for fact in self.static:
            facts_by_pred[fact[0]].append(fact)
        grounded, seen = [], set()
        for schema in self.schemas:
            variables = [v for v, _ in schema["params"]]
            domains = {v: self.bytype[t] for v, t in schema["params"]}
            constraints = self.static_atoms(schema["pre"])
            def join(env, todo):
                if todo:
                    # Join one static positive atom, using its actual predicate facts.
                    atom = min(todo, key=lambda a: len(facts_by_pred[a[0]]))
                    rest = list(todo)
                    rest.remove(atom)
                    for fact in facts_by_pred[atom[0]]:
                        if len(fact) != len(atom):
                            continue
                        newer, ok = dict(env), True
                        for term, value in zip(atom[1:], fact[1:]):
                            if term.startswith("?"):
                                if term in newer and newer[term] != value:
                                    ok = False; break
                                if value not in domains.get(term, ()): 
                                    ok = False; break
                                newer[term] = value
                            elif term != value:
                                ok = False; break
                        if ok:
                            join(newer, rest)
                    return
                missing = [v for v in variables if v not in env]
                if missing:
                    var = min(missing, key=lambda v: len(domains[v]))
                    for value in domains[var]:
                        newer = dict(env); newer[var] = value
                        join(newer, ())
                    return
                key = (schema["name"], tuple(env[v] for v in variables))
                if key in seen:
                    return
                seen.add(key)
                # This rejects negative static/equality constraints before search.
                if not self.formula(schema["pre"], self.static, env) and not self.dynamic_positive_atoms(schema["pre"], env):
                    return
                grounded.append({"name": schema["name"], "args": key[1], "env": env,
                                 "pre": schema["pre"], "effect": schema["effect"],
                                 "positive": self.dynamic_positive_atoms(schema["pre"], env)})
            join({}, constraints)
        return grounded


def goal_atoms(expr):
    answer = []
    def visit(x):
        if not isinstance(x, list) or not x:
            return
        if x[0] == "and":
            for y in x[1:]:
                visit(y)
        elif x[0] not in CONTROL:
            answer.append(tuple(x))
    visit(expr)
    return answer


def solve(model, limit):
    if model.formula(model.goal, model.static | model.start):
        return []
    actions = model.ground_actions()
    if not actions:
        return None
    indexed, always = collections.defaultdict(set), set()
    for number, action in enumerate(actions):
        if action["positive"]:
            for fact in action["positive"]:
                indexed[fact].add(number)
        else:
            always.add(number)
    target_atoms = goal_atoms(model.goal)
    def heuristic(state):
        full = state | model.static
        return sum(1 for fact in target_atoms if fact not in full)
    deadline = time.monotonic() + limit
    serial, queue = 0, []
    heapq.heappush(queue, (2 * heuristic(model.start), 0, serial, model.start))
    best = {model.start: 0}
    parents = {model.start: (None, None)}
    while queue:
        if time.monotonic() > deadline:
            raise TimeoutError("search time limit reached")
        _, cost, _, state = heapq.heappop(queue)
        if best.get(state) != cost:
            continue
        candidates = set(always)
        for fact in state:
            candidates.update(indexed.get(fact, ()))
        for number in candidates:
            action = actions[number]
            if not model.formula(action["pre"], state | model.static, action["env"]):
                continue
            next_state = model.apply(action["effect"], state, action["env"])
            if next_state == state or cost + 1 >= best.get(next_state, 10 ** 18):
                continue
            best[next_state] = cost + 1
            parents[next_state] = (state, action)
            if model.formula(model.goal, next_state | model.static):
                plan, cursor = [], next_state
                while parents[cursor][0] is not None:
                    previous, used = parents[cursor]
                    plan.append((used["name"], used["args"]))
                    cursor = previous
                return list(reversed(plan))
            serial += 1
            heapq.heappush(queue, (cost + 1 + 2 * heuristic(next_state), cost + 1, serial, next_state))
    return None


def validate(model, plan):
    state = model.start
    schema_by_name = {s["name"]: s for s in model.schemas}
    for step, (name, args) in enumerate(plan, 1):
        schema = schema_by_name.get(name)
        if schema is None:
            return {"valid": False, "step": step, "reason": "undeclared action " + name}
        if len(args) != len(schema["params"]):
            return {"valid": False, "step": step, "reason": "wrong action arity"}
        env = dict(zip((v for v, _ in schema["params"]), args))
        for variable, required_type in schema["params"]:
            obj = env[variable]
            if obj not in model.objtype or required_type not in set(model.ancestors(model.objtype[obj])):
                return {"valid": False, "step": step, "reason": "unknown or ill-typed object " + obj}
        if not model.formula(schema["pre"], state | model.static, env):
            return {"valid": False, "step": step, "reason": "unsatisfied precondition"}
        state = model.apply(schema["effect"], state, env)
    if not model.formula(model.goal, state | model.static):
        return {"valid": False, "step": len(plan), "reason": "goal not satisfied"}
    return {"valid": True, "steps": len(plan)}


def read_plan(path):
    result = []
    for line_no, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.split(";", 1)[0].strip().lower()
        if not line:
            continue
        match = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
        if not match:
            raise ValueError("line %d is not a grounded action primitive" % line_no)
        args = tuple(x.strip() for x in match.group(2).split(",") if x.strip())
        if any(not re.fullmatch(r"[a-z0-9_-]+", x) for x in args):
            raise ValueError("line %d has malformed argument" % line_no)
        result.append((match.group(1), args))
    return result


def entries_from_manifest(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("tasks", "problems"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError("manifest must be a task list or contain tasks/problems")


def input_path(value, manifest_dir):
    if os.path.isabs(value):
        return value
    candidate = os.path.join(manifest_dir, value)
    return candidate if os.path.exists(candidate) else os.path.abspath(value)


def output_path(value):
    return value if os.path.isabs(value) else os.path.abspath(value)


def solve_entry(entry, manifest_dir, limit):
    label = entry.get("id") if isinstance(entry, dict) else None
    try:
        if not isinstance(entry, dict) or any(not entry.get(k) for k in ("domain", "problem", "plan_output")):
            raise ValueError("entry requires domain, problem, and plan_output")
        model = Model(input_path(entry["domain"], manifest_dir), input_path(entry["problem"], manifest_dir))
        plan = solve(model, limit)
        if plan is None:
            return {"id": label, "status": "unsolved"}
        verdict = validate(model, plan)
        if not verdict["valid"]:
            return {"id": label, "status": "error", "reason": "internal replay failed", "validation": verdict}
        destination = output_path(entry["plan_output"])
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        with open(destination, "w", encoding="utf-8") as handle:
            for name, args in plan:
                handle.write("%s(%s)\n" % (name, ", ".join(args)))
        return {"id": label, "status": "solved", "plan_output": destination,
                "plan_length": len(plan), "validation": verdict}
    except TimeoutError as exc:
        return {"id": label, "status": "timeout", "reason": str(exc)}
    except Exception as exc:
        return {"id": label, "status": "error", "reason": str(exc)}


def validate_manifest(manifest):
    base = os.path.dirname(os.path.abspath(manifest))
    results = []
    for entry in entries_from_manifest(manifest):
        label = entry.get("id") if isinstance(entry, dict) else None
        try:
            if not isinstance(entry, dict) or any(not entry.get(k) for k in ("domain", "problem", "plan_output")):
                raise ValueError("entry requires domain, problem, and plan_output")
            destination = output_path(entry["plan_output"])
            if not os.path.isfile(destination):
                raise ValueError("required plan output is missing: " + destination)
            model = Model(input_path(entry["domain"], base), input_path(entry["problem"], base))
            verdict = validate(model, read_plan(destination))
            results.append({"id": label, "plan_output": destination, **verdict})
        except Exception as exc:
            results.append({"id": label, "valid": False, "reason": str(exc)})
    return {"ok": all(r.get("valid") for r in results), "results": results}


def main(request):
    manifest = request.get("manifest", "problem.json")
    if request.get("mode") == "validate-manifest":
        return validate_manifest(manifest)
    base = os.path.dirname(os.path.abspath(manifest))
    limit = float(request.get("time_limit_sec", 240))
    results = [solve_entry(entry, base, limit) for entry in entries_from_manifest(manifest)]
    return {"ok": all(r.get("status") == "solved" for r in results), "results": results}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "error", "reason": str(exc)}))
        sys.exit(2)
