#!/usr/bin/env python3
"""Solve typed classical PDDL tasks named by a JSON manifest and write plans."""
import collections
import heapq
import itertools
import json
import os
import re
import sys
import time

NUMERIC = {"increase", "decrease", "assign", "scale-up", "scale-down"}
LOGIC = {"and", "or", "not", "imply", "=", "forall", "exists", "when"} | NUMERIC


def sx(text):
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    root, stack, cur = [], [], None
    cur = root
    for token in tokens:
        if token == "(":
            n = []
            cur.append(n)
            stack.append(cur)
            cur = n
        elif token == ")":
            if not stack:
                raise ValueError("unexpected closing parenthesis")
            cur = stack.pop()
        else:
            cur.append(token)
    if stack or len(root) != 1 or not isinstance(root[0], list):
        raise ValueError("malformed PDDL")
    return root[0]


def typed(items, default="object"):
    answer, pending, i = [], [], 0
    while i < len(items):
        x = items[i]
        if x == "-":
            if i + 1 >= len(items) or isinstance(items[i + 1], list):
                raise ValueError("malformed typed-name list")
            answer.extend((v, items[i + 1]) for v in pending)
            pending = []
            i += 2
        else:
            if isinstance(x, list):
                raise ValueError("compound types are unsupported")
            pending.append(x)
            i += 1
    answer.extend((v, default) for v in pending)
    return answer


def part(tree, marker):
    return next((x for x in tree if isinstance(x, list) and x and x[0] == marker), None)


def afields(a):
    out, i = {}, 2
    while i + 1 < len(a):
        if isinstance(a[i], str) and a[i].startswith(":"):
            out[a[i]] = a[i + 1]
            i += 2
        else:
            i += 1
    return out


class Model:
    def __init__(self, domain_path, problem_path):
        domain = sx(open(domain_path, encoding="utf-8").read())
        problem = sx(open(problem_path, encoding="utf-8").read())
        if not domain or not problem or domain[0] != "define" or problem[0] != "define":
            raise ValueError("domain and problem must be define expressions")
        self.types = {"object": None}
        ts = part(domain, ":types")
        if ts:
            self.types.update(dict(typed(ts[1:])))
        self.objects = {}
        os = part(problem, ":objects")
        if os:
            self.objects.update(dict(typed(os[1:])))
        self.of_type = collections.defaultdict(list)
        for obj, typ in self.objects.items():
            for parent in self.ancestors(typ):
                self.of_type[parent].append(obj)
        self.actions = []
        changed = set()
        for a in domain:
            if not isinstance(a, list) or not a:
                continue
            if a[0] == ":durative-action":
                raise ValueError("durative PDDL is unsupported")
            if a[0] != ":action":
                continue
            f = afields(a)
            if len(a) < 2 or any(k not in f for k in (":parameters", ":precondition", ":effect")):
                raise ValueError("incomplete action schema")
            rec = (a[1], typed(f[":parameters"]), f[":precondition"], f[":effect"])
            self.actions.append(rec)
            self.effect_heads(rec[3], changed)
        if not self.actions:
            raise ValueError("domain has no action schemas")
        init, goal = part(problem, ":init"), part(problem, ":goal")
        if init is None or goal is None or len(goal) != 2:
            raise ValueError("problem lacks init or goal")
        initial = set()
        for atom in init[1:]:
            if not isinstance(atom, list) or not atom:
                continue
            if atom[0] in NUMERIC:
                raise ValueError("numeric PDDL is unsupported")
            if atom[0] not in {"not", "="}:
                initial.add(tuple(atom))
        self.goal = goal[1]
        self.static_heads = {a[0] for a in initial if a[0] not in changed}
        self.fixed = frozenset(a for a in initial if a[0] in self.static_heads)
        self.initial = frozenset(a for a in initial if a[0] not in self.static_heads)

    def ancestors(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ)
            yield typ
            typ = self.types.get(typ)

    def effect_heads(self, e, result):
        if not isinstance(e, list) or not e:
            raise ValueError("malformed effect")
        op = e[0]
        if op == "and":
            for x in e[1:]:
                self.effect_heads(x, result)
        elif op == "not":
            if len(e) != 2 or not isinstance(e[1], list):
                raise ValueError("malformed delete effect")
            result.add(e[1][0])
        elif op in {"when", "forall"}:
            if len(e) != 3:
                raise ValueError("malformed conditional or quantified effect")
            self.effect_heads(e[2], result)
        elif op in NUMERIC:
            raise ValueError("numeric PDDL is unsupported")
        elif op not in LOGIC:
            result.add(op)

    def truth(self, e, state, env=None):
        env = {} if env is None else env
        if not isinstance(e, list) or not e:
            raise ValueError("malformed formula")
        op = e[0]
        if op == "and":
            return all(self.truth(x, state, env) for x in e[1:])
        if op == "or":
            return any(self.truth(x, state, env) for x in e[1:])
        if op == "not":
            return len(e) == 2 and not self.truth(e[1], state, env)
        if op == "imply":
            return len(e) == 3 and (not self.truth(e[1], state, env) or self.truth(e[2], state, env))
        if op == "=":
            return len(e) == 3 and env.get(e[1], e[1]) == env.get(e[2], e[2])
        if op in {"forall", "exists"}:
            if len(e) != 3:
                raise ValueError("malformed quantifier")
            variables = typed(e[1])
            values = []
            for values_for_vars in itertools.product(*[self.of_type[t] for _, t in variables]):
                scoped = dict(env)
                scoped.update(dict(zip((v for v, _ in variables), values_for_vars)))
                values.append(self.truth(e[2], state, scoped))
            return all(values) if op == "forall" else any(values)
        return tuple(env.get(x, x) for x in e) in state

    def apply(self, effect, dynamic, env):
        full = set(self.fixed | dynamic)
        def walk(e, scope):
            if not isinstance(e, list) or not e:
                raise ValueError("malformed effect")
            op = e[0]
            if op == "and":
                for x in e[1:]:
                    walk(x, scope)
            elif op == "not":
                if len(e) != 2 or not isinstance(e[1], list):
                    raise ValueError("malformed delete effect")
                full.discard(tuple(scope.get(x, x) for x in e[1]))
            elif op == "when":
                if len(e) != 3:
                    raise ValueError("malformed conditional effect")
                if self.truth(e[1], full, scope):
                    walk(e[2], scope)
            elif op == "forall":
                if len(e) != 3:
                    raise ValueError("malformed quantified effect")
                vs = typed(e[1])
                for xs in itertools.product(*[self.of_type[t] for _, t in vs]):
                    local = dict(scope)
                    local.update(dict(zip((v for v, _ in vs), xs)))
                    walk(e[2], local)
            elif op in NUMERIC:
                raise ValueError("numeric PDDL is unsupported")
            else:
                full.add(tuple(scope.get(x, x) for x in e))
        walk(effect, env)
        return frozenset(x for x in full if x[0] not in self.static_heads)

    def static_requirements(self, e):
        if not isinstance(e, list) or not e:
            return []
        if e[0] == "and":
            return sum((self.static_requirements(x) for x in e[1:]), [])
        return [e] if e[0] in self.static_heads else []

    def ground(self):
        fixed_by_head = collections.defaultdict(list)
        for fact in self.fixed:
            fixed_by_head[fact[0]].append(fact)
        all_actions = []
        for name, params, pre, effect in self.actions:
            names = [v for v, _ in params]
            domains = {v: self.of_type[t] for v, t in params}
            def complete(env):
                missing = [v for v in names if v not in env]
                if missing:
                    v = min(missing, key=lambda z: len(domains[z]))
                    for obj in domains[v]:
                        nxt = dict(env)
                        nxt[v] = obj
                        complete(nxt)
                    return
                all_actions.append((name, tuple(env[v] for v in names), dict(env), pre, effect))
            def bind(requirements, env):
                if not requirements:
                    complete(env)
                    return
                atom = requirements[0]
                for fact in fixed_by_head[atom[0]]:
                    if len(atom) != len(fact):
                        continue
                    nxt, ok = dict(env), True
                    for term, value in zip(atom[1:], fact[1:]):
                        if isinstance(term, str) and term.startswith("?"):
                            if term not in domains or value not in domains[term] or (term in nxt and nxt[term] != value):
                                ok = False
                                break
                            nxt[term] = value
                        elif term != value:
                            ok = False
                            break
                    if ok:
                        bind(requirements[1:], nxt)
            bind(self.static_requirements(pre), {})
        return all_actions


def positive_goal_atoms(e):
    if not isinstance(e, list) or not e:
        return []
    if e[0] == "and":
        return sum((positive_goal_atoms(x) for x in e[1:]), [])
    return [tuple(e)] if e[0] not in LOGIC else []


def solve(model, seconds):
    if model.truth(model.goal, model.fixed | model.initial):
        return []
    actions = model.ground()
    if not actions:
        return None
    wanted = positive_goal_atoms(model.goal)
    def heuristic(state):
        return sum(x not in model.fixed and x not in state for x in wanted)
    best = {model.initial: 0}
    parent = {model.initial: None}
    serial = 0
    queue = [(heuristic(model.initial), 0, serial, model.initial)]
    deadline = time.monotonic() + seconds
    while queue:
        if time.monotonic() > deadline:
            raise TimeoutError("search time limit reached")
        _, cost, _, state = heapq.heappop(queue)
        if best.get(state) != cost:
            continue
        for name, args, env, pre, effect in actions:
            if not model.truth(pre, model.fixed | state, env):
                continue
            nxt = model.apply(effect, state, env)
            new_cost = cost + 1
            if nxt == state or new_cost >= best.get(nxt, 10 ** 18):
                continue
            best[nxt] = new_cost
            parent[nxt] = (state, (name, args))
            if model.truth(model.goal, model.fixed | nxt):
                plan, cur = [], nxt
                while parent[cur] is not None:
                    cur, action = parent[cur]
                    plan.append(action)
                return list(reversed(plan))
            serial += 1
            heapq.heappush(queue, (new_cost + heuristic(nxt), new_cost, serial, nxt))
    return None


def parse_plan(path):
    result = []
    for line_number, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.split(";", 1)[0].strip().lower()
        if not line:
            continue
        m = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
        if m:
            args = tuple(x.strip() for x in m.group(2).split(",") if x.strip())
            if any(not re.fullmatch(r"[a-z0-9_-]+", x) for x in args):
                raise ValueError("invalid action argument on line %d" % line_number)
            result.append((m.group(1), args))
            continue
        m = re.fullmatch(r"\(\s*([a-z0-9_-]+)((?:\s+[a-z0-9_-]+)*)\s*\)", line)
        if not m:
            raise ValueError("invalid plan line %d" % line_number)
        result.append((m.group(1), tuple(m.group(2).split())))
    return result


def validate(model, plan):
    schemas = {name: (params, pre, effect) for name, params, pre, effect in model.actions}
    state = model.initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in schemas:
            return {"valid": False, "step": step, "reason": "undeclared action"}
        params, pre, effect = schemas[name]
        if len(params) != len(args):
            return {"valid": False, "step": step, "reason": "wrong arity"}
        env = dict(zip((v for v, _ in params), args))
        for var, expected in params:
            actual = model.objects.get(env[var])
            if actual is None or expected not in set(model.ancestors(actual)):
                return {"valid": False, "step": step, "reason": "ill-typed object"}
        if not model.truth(pre, model.fixed | state, env):
            return {"valid": False, "step": step, "reason": "unsatisfied precondition"}
        state = model.apply(effect, state, env)
    if not model.truth(model.goal, model.fixed | state):
        return {"valid": False, "steps": len(plan), "reason": "goal not satisfied"}
    return {"valid": True, "steps": len(plan)}


def manifest_entries(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("tasks", "problems"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError("manifest must be a list or contain tasks/problems")


def run(request):
    manifest = os.path.abspath(request.get("manifest", "problem.json"))
    base = os.path.dirname(manifest)
    tasks = manifest_entries(manifest)
    if not tasks:
        raise ValueError("manifest declares no tasks")
    checking = request.get("mode") == "validate-manifest"
    results = []
    for task in tasks:
        label = task.get("id") if isinstance(task, dict) else None
        try:
            if not isinstance(task, dict) or any(not isinstance(task.get(k), str) or not task[k] for k in ("domain", "problem", "plan_output")):
                raise ValueError("task requires domain, problem, and plan_output")
            def resolve(value):
                return value if os.path.isabs(value) else os.path.join(base, value)
            output = resolve(task["plan_output"])
            model = Model(resolve(task["domain"]), resolve(task["problem"]))
            if checking:
                if not os.path.isfile(output):
                    raise ValueError("required plan output is missing: " + output)
                results.append({"id": label, "plan_output": output, **validate(model, parse_plan(output))})
                continue
            plan = solve(model, float(request.get("time_limit_sec", 240)))
            if plan is None:
                results.append({"id": label, "status": "unsolved", "plan_output": output})
                continue
            report = validate(model, plan)
            if not report["valid"]:
                raise ValueError("internal replay failed: " + report["reason"])
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
            temporary = output + ".tmp"
            with open(temporary, "w", encoding="utf-8") as f:
                for name, args in plan:
                    f.write(name + "(" + ",".join(args) + ")\n")
            os.replace(temporary, output)
            if not os.path.isfile(output):
                raise ValueError("failed to create declared plan output")
            results.append({"id": label, "status": "solved", "plan_output": output, "plan_length": len(plan), "validation": report})
        except TimeoutError as exc:
            results.append({"id": label, "status": "timeout", "reason": str(exc)})
        except Exception as exc:
            results.append({"id": label, **({"valid": False} if checking else {"status": "error"}), "reason": str(exc)})
    ok = all(r.get("valid", False) for r in results) if checking else all(r.get("status") == "solved" for r in results)
    return {"ok": ok, "results": results}


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "error", "reason": str(exc)}, sort_keys=True))
        sys.exit(2)
