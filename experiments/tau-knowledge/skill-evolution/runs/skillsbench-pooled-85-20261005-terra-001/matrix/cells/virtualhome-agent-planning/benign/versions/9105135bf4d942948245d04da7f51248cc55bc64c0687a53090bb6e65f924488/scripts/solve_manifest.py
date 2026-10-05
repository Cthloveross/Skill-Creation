#!/usr/bin/env python3
"""Solve or replay-validate typed classical-PDDL tasks in a JSON manifest.

stdin generation schema: {"manifest": path, "time_limit_sec": number}
stdin validation schema: {"mode": "validate-manifest", "manifest": path}
stdout: one JSON status object.  Uses only the Python standard library.
"""
import collections
import heapq
import itertools
import json
import os
import re
import sys
import time

LOGIC = {"and", "or", "not", "imply", "=", "forall", "exists", "when"}
NUMERIC = {"increase", "decrease", "assign", "scale-up", "scale-down"}


def sexpr(text):
    toks = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    root, stack = [], []
    current = root
    for tok in toks:
        if tok == "(":
            node = []
            current.append(node)
            stack.append(current)
            current = node
        elif tok == ")":
            if not stack:
                raise ValueError("unexpected closing parenthesis")
            current = stack.pop()
        else:
            current.append(tok)
    if stack or len(root) != 1 or not isinstance(root[0], list):
        raise ValueError("malformed PDDL")
    return root[0]


def typed(items, default="object"):
    out, pending, i = [], [], 0
    while i < len(items):
        item = items[i]
        if item == "-":
            if i + 1 >= len(items) or isinstance(items[i + 1], list):
                raise ValueError("malformed typed list")
            out.extend((x, items[i + 1]) for x in pending)
            pending = []
            i += 2
        else:
            if isinstance(item, list):
                raise ValueError("unexpected expression in typed list")
            pending.append(item)
            i += 1
    out.extend((x, default) for x in pending)
    return out


def action_fields(item):
    out, i = {}, 2
    while i + 1 < len(item):
        if isinstance(item[i], str) and item[i].startswith(":"):
            out[item[i]] = item[i + 1]
            i += 2
        else:
            i += 1
    return out


class Model:
    def __init__(self, domain_file, problem_file):
        with open(domain_file, encoding="utf-8") as f:
            domain = sexpr(f.read())
        with open(problem_file, encoding="utf-8") as f:
            problem = sexpr(f.read())
        if not domain or domain[0] != "define" or not problem or problem[0] != "define":
            raise ValueError("domain and problem must be define forms")
        self.types = {"object": None}
        self.schemas = []
        for part in domain[1:]:
            if not isinstance(part, list) or not part:
                continue
            if part[0] == ":types":
                self.types.update(dict(typed(part[1:])))
            elif part[0] == ":durative-action":
                raise ValueError("durative actions are unsupported")
            elif part[0] == ":action":
                if len(part) < 2:
                    raise ValueError("unnamed action")
                f = action_fields(part)
                for key in (":parameters", ":precondition", ":effect"):
                    if key not in f:
                        raise ValueError("action %s lacks %s" % (part[1], key))
                self.schemas.append((part[1], typed(f[":parameters"]), f[":precondition"], f[":effect"]))
        if not self.schemas:
            raise ValueError("domain has no action schemas")

        objects, initial, goal = [], set(), None
        for part in problem[1:]:
            if not isinstance(part, list) or not part:
                continue
            if part[0] == ":objects":
                objects.extend(typed(part[1:]))
            elif part[0] == ":init":
                for fact in part[1:]:
                    if not isinstance(fact, list) or not fact:
                        continue
                    if fact[0] in NUMERIC:
                        raise ValueError("numeric PDDL is unsupported")
                    if fact[0] not in ("not", "="):
                        initial.add(tuple(fact))
            elif part[0] == ":goal":
                if len(part) != 2:
                    raise ValueError("malformed goal")
                goal = part[1]
        if goal is None:
            raise ValueError("problem lacks goal")
        self.goal = goal
        self.objtype = dict(objects)
        self.bytype = collections.defaultdict(list)
        for obj, typ in objects:
            for ancestor in self.ancestors(typ):
                self.bytype[ancestor].append(obj)

        changed = set()
        for _, _, _, effect in self.schemas:
            self.effect_predicates(effect, changed)
        self.static_predicates = {x[0] for x in initial if x[0] not in changed}
        self.static = frozenset(x for x in initial if x[0] in self.static_predicates)
        self.start = frozenset(x for x in initial if x[0] not in self.static_predicates)

    def ancestors(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ)
            yield typ
            typ = self.types.get(typ)

    def effect_predicates(self, node, result):
        if not isinstance(node, list) or not node:
            raise ValueError("malformed effect")
        op = node[0]
        if op == "and":
            for child in node[1:]:
                self.effect_predicates(child, result)
        elif op == "not":
            if len(node) != 2 or not isinstance(node[1], list) or not node[1]:
                raise ValueError("malformed delete effect")
            result.add(node[1][0])
        elif op in ("when", "forall"):
            if len(node) != 3:
                raise ValueError("malformed conditional or quantified effect")
            self.effect_predicates(node[2], result)
        elif op in NUMERIC:
            raise ValueError("numeric PDDL is unsupported")
        elif op not in LOGIC:
            result.add(op)

    def formula(self, node, state, env=None):
        env = {} if env is None else env
        if not isinstance(node, list) or not node:
            raise ValueError("malformed formula")
        op = node[0]
        if op == "and":
            return all(self.formula(x, state, env) for x in node[1:])
        if op == "or":
            return any(self.formula(x, state, env) for x in node[1:])
        if op == "not":
            return len(node) == 2 and not self.formula(node[1], state, env)
        if op == "imply":
            return len(node) == 3 and (not self.formula(node[1], state, env) or self.formula(node[2], state, env))
        if op == "=":
            return len(node) == 3 and env.get(node[1], node[1]) == env.get(node[2], node[2])
        if op in ("forall", "exists"):
            if len(node) != 3:
                raise ValueError("malformed quantified formula")
            vars_ = typed(node[1])
            values = []
            for assignment in itertools.product(*[self.bytype[t] for _, t in vars_]):
                e = dict(env)
                e.update(dict(zip((v for v, _ in vars_), assignment)))
                values.append(self.formula(node[2], state, e))
            return all(values) if op == "forall" else any(values)
        return tuple(env.get(x, x) for x in node) in state

    def apply(self, effect, dynamic, env):
        full = set(self.static | dynamic)
        def walk(node, local):
            if not isinstance(node, list) or not node:
                raise ValueError("malformed effect")
            op = node[0]
            if op == "and":
                for child in node[1:]:
                    walk(child, local)
            elif op == "not":
                if len(node) != 2 or not isinstance(node[1], list):
                    raise ValueError("malformed delete effect")
                full.discard(tuple(local.get(x, x) for x in node[1]))
            elif op == "when":
                if len(node) != 3:
                    raise ValueError("malformed conditional effect")
                if self.formula(node[1], full, local):
                    walk(node[2], local)
            elif op == "forall":
                if len(node) != 3:
                    raise ValueError("malformed quantified effect")
                vars_ = typed(node[1])
                for assignment in itertools.product(*[self.bytype[t] for _, t in vars_]):
                    e = dict(local)
                    e.update(dict(zip((v for v, _ in vars_), assignment)))
                    walk(node[2], e)
            elif op in NUMERIC:
                raise ValueError("numeric PDDL is unsupported")
            else:
                full.add(tuple(local.get(x, x) for x in node))
        walk(effect, env)
        return frozenset(x for x in full if x[0] not in self.static_predicates)

    def conjunction_atoms(self, node, wanted_static):
        """Safe positive literals required by a pure conjunction; otherwise no pruning."""
        if not isinstance(node, list) or not node:
            return []
        if node[0] == "and":
            out = []
            for child in node[1:]:
                out.extend(self.conjunction_atoms(child, wanted_static))
            return out
        if node[0] not in LOGIC and ((node[0] in self.static_predicates) == wanted_static):
            return [tuple(node)]
        return []

    def ground_actions(self):
        index = collections.defaultdict(list)
        for fact in self.static:
            index[fact[0]].append(fact)
        answer, emitted = [], set()
        for name, params, pre, effect in self.schemas:
            vars_ = [v for v, _ in params]
            domains = {v: self.bytype[t] for v, t in params}
            static_needs = self.conjunction_atoms(pre, True)

            def finish(env):
                missing = [v for v in vars_ if v not in env]
                if missing:
                    var = min(missing, key=lambda x: len(domains[x]))
                    for value in domains[var]:
                        e = dict(env)
                        e[var] = value
                        finish(e)
                    return
                args = tuple(env[v] for v in vars_)
                key = (name, args)
                if key not in emitted:
                    emitted.add(key)
                    answer.append((name, args, dict(env), pre, effect,
                                   self.conjunction_atoms_substituted(pre, False, env)))

            def join(env, remaining):
                if not remaining:
                    finish(env)
                    return
                atom = min(remaining, key=lambda a: len(index[a[0]]))
                rest = list(remaining)
                rest.remove(atom)
                for fact in index[atom[0]]:
                    if len(fact) != len(atom):
                        continue
                    e, ok = dict(env), True
                    for term, value in zip(atom[1:], fact[1:]):
                        if isinstance(term, str) and term.startswith("?"):
                            if term in e and e[term] != value:
                                ok = False
                                break
                            if value not in domains.get(term, ()):
                                ok = False
                                break
                            e[term] = value
                        elif term != value:
                            ok = False
                            break
                    if ok:
                        join(e, rest)
            join({}, static_needs)
        return answer

    def conjunction_atoms_substituted(self, node, wanted_static, env):
        return [tuple(env.get(x, x) for x in atom)
                for atom in self.conjunction_atoms(node, wanted_static)]


def positive_goal_literals(node):
    if not isinstance(node, list) or not node:
        return []
    if node[0] == "and":
        out = []
        for x in node[1:]:
            out.extend(positive_goal_literals(x))
        return out
    return [tuple(node)] if node[0] not in LOGIC else []


def solve(model, limit):
    if model.formula(model.goal, model.static | model.start):
        return []
    actions = model.ground_actions()
    if not actions:
        return None
    needed, always = collections.defaultdict(set), set()
    for n, action in enumerate(actions):
        dynamic_positive = action[5]
        if dynamic_positive:
            for atom in dynamic_positive:
                needed[atom].add(n)
        else:
            always.add(n)
    goals = positive_goal_literals(model.goal)
    def heuristic(state):
        allfacts = model.static | state
        return sum(g not in allfacts for g in goals)

    deadline = time.monotonic() + limit
    serial = 0
    queue = [(heuristic(model.start), 0, serial, model.start)]
    best = {model.start: 0}
    parent = {model.start: (None, None)}
    while queue:
        if time.monotonic() > deadline:
            raise TimeoutError("search time limit reached")
        _, depth, _, state = heapq.heappop(queue)
        if best.get(state) != depth:
            continue
        candidates = set(always)
        for atom in state:
            candidates.update(needed.get(atom, ()))
        for number in candidates:
            name, args, env, pre, effect, _ = actions[number]
            if not model.formula(pre, model.static | state, env):
                continue
            successor = model.apply(effect, state, env)
            if successor == state or depth + 1 >= best.get(successor, 10 ** 18):
                continue
            best[successor] = depth + 1
            parent[successor] = (state, (name, args))
            if model.formula(model.goal, model.static | successor):
                result, cursor = [], successor
                while parent[cursor][0] is not None:
                    previous, action = parent[cursor]
                    result.append(action)
                    cursor = previous
                return list(reversed(result))
            serial += 1
            heapq.heappush(queue, (depth + 1 + heuristic(successor), depth + 1, serial, successor))
    return None


def parse_plan(path):
    plan = []
    with open(path, encoding="utf-8") as f:
        for number, raw in enumerate(f, 1):
            line = raw.split(";", 1)[0].strip().lower()
            if not line:
                continue
            m = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
            if m:
                args = tuple(x.strip() for x in m.group(2).split(",") if x.strip())
            else:
                m = re.fullmatch(r"\(\s*([a-z0-9_-]+)((?:\s+[a-z0-9_-]+)*)\s*\)", line)
                if not m:
                    raise ValueError("line %d is not a grounded action" % number)
                args = tuple(m.group(2).split())
            if any(not re.fullmatch(r"[a-z0-9_-]+", x) for x in args):
                raise ValueError("line %d has malformed arguments" % number)
            plan.append((m.group(1), args))
    return plan


def validate(model, plan):
    schemas = {name: (params, pre, effect) for name, params, pre, effect in model.schemas}
    state = model.start
    for step, (name, args) in enumerate(plan, 1):
        schema = schemas.get(name)
        if schema is None:
            return {"valid": False, "step": step, "reason": "undeclared action " + name}
        params, pre, effect = schema
        if len(args) != len(params):
            return {"valid": False, "step": step, "reason": "wrong action arity"}
        env = dict(zip((v for v, _ in params), args))
        for var, expected in params:
            actual = model.objtype.get(env[var])
            if actual is None or expected not in set(model.ancestors(actual)):
                return {"valid": False, "step": step, "reason": "unknown or ill-typed object " + env[var]}
        if not model.formula(pre, model.static | state, env):
            return {"valid": False, "step": step, "reason": "unsatisfied precondition"}
        state = model.apply(effect, state, env)
    if not model.formula(model.goal, model.static | state):
        return {"valid": False, "step": len(plan), "reason": "goal not satisfied"}
    return {"valid": True, "steps": len(plan)}


def entries(manifest):
    with open(manifest, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("tasks", "problems"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError("manifest must be a list or contain tasks/problems")


def required(entry):
    if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) and entry[k]
                                               for k in ("domain", "problem", "plan_output")):
        raise ValueError("entry requires domain, problem, and plan_output strings")


def resolved(path, base):
    return path if os.path.isabs(path) else os.path.join(base, path)


def solve_entry(entry, base, limit):
    label = entry.get("id") if isinstance(entry, dict) else None
    try:
        required(entry)
        model = Model(resolved(entry["domain"], base), resolved(entry["problem"], base))
        plan = solve(model, limit)
        if plan is None:
            return {"id": label, "status": "unsolved"}
        verdict = validate(model, plan)
        if not verdict["valid"]:
            return {"id": label, "status": "error", "reason": "candidate replay failed", "validation": verdict}
        output = resolved(entry["plan_output"], base)
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        temp = output + ".tmp"
        with open(temp, "w", encoding="utf-8") as f:
            for name, args in plan:
                f.write("%s(%s)\n" % (name, ", ".join(args)))
        os.replace(temp, output)
        return {"id": label, "status": "solved", "plan_output": output,
                "plan_length": len(plan), "validation": verdict}
    except TimeoutError as exc:
        return {"id": label, "status": "timeout", "reason": str(exc)}
    except Exception as exc:
        return {"id": label, "status": "error", "reason": str(exc)}


def validate_manifest(manifest):
    base, results = os.path.dirname(os.path.abspath(manifest)), []
    for entry in entries(manifest):
        label = entry.get("id") if isinstance(entry, dict) else None
        try:
            required(entry)
            output = resolved(entry["plan_output"], base)
            if not os.path.isfile(output):
                raise ValueError("required plan output is missing: " + output)
            model = Model(resolved(entry["domain"], base), resolved(entry["problem"], base))
            results.append({"id": label, "plan_output": output, **validate(model, parse_plan(output))})
        except Exception as exc:
            results.append({"id": label, "valid": False, "reason": str(exc)})
    return {"ok": all(x.get("valid") for x in results), "results": results}


def main(request):
    manifest = os.path.abspath(request.get("manifest", "problem.json"))
    if request.get("mode") == "validate-manifest":
        return validate_manifest(manifest)
    limit = float(request.get("time_limit_sec", 240))
    base = os.path.dirname(manifest)
    results = [solve_entry(entry, base, limit) for entry in entries(manifest)]
    return {"ok": all(x.get("status") == "solved" for x in results), "results": results}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "error", "reason": str(exc)}))
        sys.exit(2)
