#!/usr/bin/env python3
"""Generate or replay-validate plans for a JSON manifest of classical PDDL tasks.
Input:  {"manifest": path, "time_limit_sec": number} or
        {"mode":"validate-manifest", "manifest": path}
Output: JSON status object on stdout.  No third-party dependencies are used.
"""
import collections
import heapq
import itertools
import json
import os
import re
import sys
import time

CONTROL = {"and", "or", "not", "imply", "=", "forall", "exists", "when"}
NUMERIC = {"increase", "decrease", "assign", "scale-up", "scale-down"}


def parse_sexpr(text):
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    stack = [[]]
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
    if len(stack) != 1 or len(stack[0]) != 1 or not isinstance(stack[0][0], list):
        raise ValueError("malformed PDDL expression")
    return stack[0][0]


def typed_names(items, default="object"):
    result, pending, index = [], [], 0
    while index < len(items):
        value = items[index]
        if value == "-":
            if index + 1 >= len(items) or isinstance(items[index + 1], list):
                raise ValueError("malformed typed-name list")
            result.extend((name, items[index + 1]) for name in pending)
            pending = []
            index += 2
        else:
            if isinstance(value, list):
                raise ValueError("unexpected list in typed-name list")
            pending.append(value)
            index += 1
    result.extend((name, default) for name in pending)
    return result


def fields(action):
    result, index = {}, 2
    while index + 1 < len(action):
        if isinstance(action[index], str) and action[index].startswith(":"):
            result[action[index]] = action[index + 1]
            index += 2
        else:
            index += 1
    return result


class Model:
    def __init__(self, domain_path, problem_path):
        with open(domain_path, encoding="utf-8") as stream:
            domain = parse_sexpr(stream.read())
        with open(problem_path, encoding="utf-8") as stream:
            problem = parse_sexpr(stream.read())
        if not domain or domain[0] != "define" or not problem or problem[0] != "define":
            raise ValueError("domain and problem must be PDDL define forms")

        self.types = {"object": None}
        self.schemas = []
        for section in domain[1:]:
            if not isinstance(section, list) or not section:
                continue
            if section[0] == ":types":
                self.types.update(dict(typed_names(section[1:])))
            elif section[0] == ":durative-action":
                raise ValueError("durative actions are unsupported")
            elif section[0] == ":action":
                if len(section) < 2:
                    raise ValueError("unnamed action")
                f = fields(section)
                if not all(key in f for key in (":parameters", ":precondition", ":effect")):
                    raise ValueError("action %s lacks parameters, precondition, or effect" % section[1])
                self.schemas.append({"name": section[1], "params": typed_names(f[":parameters"]),
                                     "pre": f[":precondition"], "effect": f[":effect"]})

        objects, initial, self.goal = [], set(), ["and"]
        for section in problem[1:]:
            if not isinstance(section, list) or not section:
                continue
            if section[0] == ":objects":
                objects.extend(typed_names(section[1:]))
            elif section[0] == ":init":
                for atom in section[1:]:
                    if not isinstance(atom, list) or not atom:
                        continue
                    if atom[0] in NUMERIC or atom[0] == "=":
                        if atom[0] in NUMERIC:
                            raise ValueError("numeric PDDL is unsupported")
                    elif atom[0] != "not":
                        initial.add(tuple(atom))
            elif section[0] == ":goal":
                if len(section) != 2:
                    raise ValueError("malformed goal")
                self.goal = section[1]

        self.objtype = dict(objects)
        self.bytype = collections.defaultdict(list)
        for obj, typ in objects:
            for ancestor in self.ancestors(typ):
                self.bytype[ancestor].append(obj)

        changed = set()
        for schema in self.schemas:
            self.changed_predicates(schema["effect"], changed)
        self.static_predicates = {fact[0] for fact in initial if fact[0] not in changed}
        self.static = frozenset(fact for fact in initial if fact[0] in self.static_predicates)
        self.start = frozenset(fact for fact in initial if fact[0] not in self.static_predicates)

    def ancestors(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ)
            yield typ
            typ = self.types.get(typ)

    def changed_predicates(self, expr, result):
        if not isinstance(expr, list) or not expr:
            return
        op = expr[0]
        if op == "and":
            for child in expr[1:]:
                self.changed_predicates(child, result)
        elif op == "not":
            if len(expr) == 2 and isinstance(expr[1], list) and expr[1]:
                result.add(expr[1][0])
        elif op in ("when", "forall"):
            if len(expr) == 3:
                self.changed_predicates(expr[2], result)
        elif op in NUMERIC:
            raise ValueError("numeric PDDL is unsupported")
        elif op not in CONTROL:
            result.add(op)

    def formula(self, expr, full_state, env=None):
        env = {} if env is None else env
        if not isinstance(expr, list) or not expr:
            raise ValueError("malformed logical formula")
        op = expr[0]
        if op == "and":
            return all(self.formula(child, full_state, env) for child in expr[1:])
        if op == "or":
            return any(self.formula(child, full_state, env) for child in expr[1:])
        if op == "not":
            return len(expr) == 2 and not self.formula(expr[1], full_state, env)
        if op == "imply":
            return len(expr) == 3 and (not self.formula(expr[1], full_state, env) or self.formula(expr[2], full_state, env))
        if op == "=":
            return len(expr) == 3 and env.get(expr[1], expr[1]) == env.get(expr[2], expr[2])
        if op in ("forall", "exists"):
            if len(expr) != 3:
                raise ValueError("malformed quantified formula")
            variables = typed_names(expr[1])
            choices = [self.bytype[typ] for _, typ in variables]
            values = []
            for assignment in itertools.product(*choices):
                extended = dict(env)
                extended.update(dict(zip((var for var, _ in variables), assignment)))
                values.append(self.formula(expr[2], full_state, extended))
            return all(values) if op == "forall" else any(values)
        return tuple(env.get(term, term) for term in expr) in full_state

    def apply(self, effect, state, env):
        full = set(self.static | state)

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
                full.discard(tuple(local.get(term, term) for term in expr[1]))
            elif op == "when":
                if len(expr) != 3:
                    raise ValueError("malformed conditional effect")
                if self.formula(expr[1], full, local):
                    walk(expr[2], local)
            elif op == "forall":
                if len(expr) != 3:
                    raise ValueError("malformed quantified effect")
                variables = typed_names(expr[1])
                for assignment in itertools.product(*[self.bytype[t] for _, t in variables]):
                    extended = dict(local)
                    extended.update(dict(zip((v for v, _ in variables), assignment)))
                    walk(expr[2], extended)
            elif op in NUMERIC:
                raise ValueError("numeric PDDL is unsupported")
            else:
                full.add(tuple(local.get(term, term) for term in expr))

        walk(effect, env)
        return frozenset(fact for fact in full if fact[0] not in self.static_predicates)

    def positive_atoms(self, expr, include_static, env=None):
        env = {} if env is None else env
        answer = []
        def visit(node):
            if not isinstance(node, list) or not node:
                return
            if node[0] == "and":
                for child in node[1:]:
                    visit(child)
            elif node[0] not in CONTROL and ((node[0] in self.static_predicates) == include_static):
                answer.append(tuple(env.get(term, term) for term in node))
        visit(expr)
        return answer

    def ground_actions(self):
        static_index = collections.defaultdict(list)
        for fact in self.static:
            static_index[fact[0]].append(fact)
        answer, emitted = [], set()

        for schema in self.schemas:
            variables = [v for v, _ in schema["params"]]
            domains = {v: self.bytype[t] for v, t in schema["params"]}
            constraints = self.positive_atoms(schema["pre"], True)

            def complete(env):
                missing = [v for v in variables if v not in env]
                if missing:
                    var = min(missing, key=lambda v: len(domains[v]))
                    for value in domains[var]:
                        e = dict(env); e[var] = value
                        complete(e)
                    return
                if not self.formula(schema["pre"], self.static, env):
                    # This rejects impossible static, equality, and negative-static bindings.
                    # Dynamic atoms being absent here is harmless because formula would reject;
                    # use a state containing those atoms only for static-only checking below.
                    dynamic = set()
                    for atom in self.positive_atoms(schema["pre"], False, env):
                        dynamic.add(atom)
                    if not self.formula(schema["pre"], self.static | dynamic, env):
                        return
                key = (schema["name"], tuple(env[v] for v in variables))
                if key in emitted:
                    return
                emitted.add(key)
                answer.append({"name": schema["name"], "args": key[1], "env": dict(env),
                               "pre": schema["pre"], "effect": schema["effect"],
                               "positive": self.positive_atoms(schema["pre"], False, env)})

            def bind(env, left):
                if not left:
                    complete(env)
                    return
                atom = min(left, key=lambda a: len(static_index[a[0]]))
                rest = list(left); rest.remove(atom)
                for fact in static_index[atom[0]]:
                    if len(fact) != len(atom):
                        continue
                    extended, valid = dict(env), True
                    for term, value in zip(atom[1:], fact[1:]):
                        if term.startswith("?"):
                            if term in extended and extended[term] != value:
                                valid = False; break
                            if value not in domains.get(term, ()): 
                                valid = False; break
                            extended[term] = value
                        elif term != value:
                            valid = False; break
                    if valid:
                        bind(extended, rest)
            bind({}, constraints)
        return answer


def literal_goal_atoms(expr):
    result = []
    def visit(node):
        if not isinstance(node, list) or not node:
            return
        if node[0] == "and":
            for child in node[1:]: visit(child)
        elif node[0] not in CONTROL:
            result.append(tuple(node))
    visit(expr)
    return result


def solve(model, seconds):
    if model.formula(model.goal, model.static | model.start):
        return []
    actions = model.ground_actions()
    if not actions:
        return None
    by_need, unconditional = collections.defaultdict(set), set()
    for number, action in enumerate(actions):
        if action["positive"]:
            for atom in action["positive"]:
                by_need[atom].add(number)
        else:
            unconditional.add(number)
    goals = literal_goal_atoms(model.goal)
    def h(state):
        return sum(atom not in state and atom not in model.static for atom in goals)

    deadline = time.monotonic() + seconds
    serial = 0
    heap = [(2 * h(model.start), 0, serial, model.start)]
    best = {model.start: 0}
    parent = {model.start: (None, None)}
    while heap:
        if time.monotonic() > deadline:
            raise TimeoutError("search time limit reached")
        _, depth, _, state = heapq.heappop(heap)
        if best.get(state) != depth:
            continue
        candidates = set(unconditional)
        for atom in state:
            candidates.update(by_need.get(atom, ()))
        for number in candidates:
            action = actions[number]
            if not model.formula(action["pre"], model.static | state, action["env"]):
                continue
            successor = model.apply(action["effect"], state, action["env"])
            if successor == state or depth + 1 >= best.get(successor, 10 ** 18):
                continue
            best[successor] = depth + 1
            parent[successor] = (state, action)
            if model.formula(model.goal, model.static | successor):
                plan, cursor = [], successor
                while parent[cursor][0] is not None:
                    previous, used = parent[cursor]
                    plan.append((used["name"], used["args"]))
                    cursor = previous
                return list(reversed(plan))
            serial += 1
            heapq.heappush(heap, (depth + 1 + 2 * h(successor), depth + 1, serial, successor))
    return None


def validate(model, plan):
    schemas = {item["name"]: item for item in model.schemas}
    state = model.start
    for step, (name, args) in enumerate(plan, 1):
        schema = schemas.get(name)
        if schema is None:
            return {"valid": False, "step": step, "reason": "undeclared action " + name}
        if len(args) != len(schema["params"]):
            return {"valid": False, "step": step, "reason": "wrong action arity"}
        env = dict(zip((v for v, _ in schema["params"]), args))
        for variable, expected in schema["params"]:
            obj = env[variable]
            if obj not in model.objtype or expected not in set(model.ancestors(model.objtype[obj])):
                return {"valid": False, "step": step, "reason": "unknown or ill-typed object " + obj}
        if not model.formula(schema["pre"], model.static | state, env):
            return {"valid": False, "step": step, "reason": "unsatisfied precondition"}
        state = model.apply(schema["effect"], state, env)
    if not model.formula(model.goal, model.static | state):
        return {"valid": False, "step": len(plan), "reason": "goal not satisfied"}
    return {"valid": True, "steps": len(plan)}


def read_plan(path):
    plan = []
    with open(path, encoding="utf-8") as stream:
        for number, raw in enumerate(stream, 1):
            line = raw.split(";", 1)[0].strip().lower()
            if not line:
                continue
            match = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
            if not match:
                raise ValueError("line %d is not a grounded action primitive" % number)
            args = tuple(x.strip() for x in match.group(2).split(",") if x.strip())
            if any(not re.fullmatch(r"[a-z0-9_-]+", arg) for arg in args):
                raise ValueError("line %d has malformed arguments" % number)
            plan.append((match.group(1), args))
    return plan


def manifest_entries(path):
    with open(path, encoding="utf-8") as stream:
        data = json.load(stream)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("tasks", "problems"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError("manifest must be a list or contain tasks/problems")


def resolve(path, base):
    return path if os.path.isabs(path) else os.path.join(base, path)


def check_entry(entry):
    if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) and entry[k]
                                               for k in ("domain", "problem", "plan_output")):
        raise ValueError("entry requires domain, problem, and plan_output strings")


def solve_one(entry, base, limit):
    label = entry.get("id") if isinstance(entry, dict) else None
    try:
        check_entry(entry)
        model = Model(resolve(entry["domain"], base), resolve(entry["problem"], base))
        plan = solve(model, limit)
        if plan is None:
            return {"id": label, "status": "unsolved"}
        verdict = validate(model, plan)
        if not verdict["valid"]:
            return {"id": label, "status": "error", "reason": "candidate replay failed", "validation": verdict}
        output = resolve(entry["plan_output"], base)
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        temporary = output + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            for name, args in plan:
                stream.write("%s(%s)\n" % (name, ", ".join(args)))
        os.replace(temporary, output)
        return {"id": label, "status": "solved", "plan_output": output,
                "plan_length": len(plan), "validation": verdict}
    except TimeoutError as exc:
        return {"id": label, "status": "timeout", "reason": str(exc)}
    except Exception as exc:
        return {"id": label, "status": "error", "reason": str(exc)}


def validate_manifest(path):
    base, results = os.path.dirname(os.path.abspath(path)), []
    for entry in manifest_entries(path):
        label = entry.get("id") if isinstance(entry, dict) else None
        try:
            check_entry(entry)
            output = resolve(entry["plan_output"], base)
            if not os.path.isfile(output):
                raise ValueError("required plan output is missing: " + output)
            model = Model(resolve(entry["domain"], base), resolve(entry["problem"], base))
            results.append({"id": label, "plan_output": output, **validate(model, read_plan(output))})
        except Exception as exc:
            results.append({"id": label, "valid": False, "reason": str(exc)})
    return {"ok": all(item.get("valid") for item in results), "results": results}


def main(request):
    manifest = os.path.abspath(request.get("manifest", "problem.json"))
    if request.get("mode") == "validate-manifest":
        return validate_manifest(manifest)
    base = os.path.dirname(manifest)
    limit = float(request.get("time_limit_sec", 240))
    results = [solve_one(entry, base, limit) for entry in manifest_entries(manifest)]
    return {"ok": all(item.get("status") == "solved" for item in results), "results": results}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "error", "reason": str(exc)}))
        sys.exit(2)
