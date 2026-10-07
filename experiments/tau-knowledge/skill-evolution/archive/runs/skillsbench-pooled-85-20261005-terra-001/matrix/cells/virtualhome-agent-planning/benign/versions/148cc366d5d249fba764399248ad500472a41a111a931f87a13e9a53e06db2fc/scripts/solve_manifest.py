#!/usr/bin/env python3
"""Solve or replay-validate all typed classical PDDL plans named by a JSON manifest.
Reads one JSON object from stdin and emits one JSON object on stdout.
"""
import collections
import heapq
import itertools
import json
import os
import re
import sys
import time

NUMERIC = {"increase", "decrease", "assign", "scale-up", "scale-down"}
LOGIC = {"and", "or", "not", "imply", "=", "forall", "exists", "when"}


def sexpr(text):
    toks = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    root, stack = [], [[]]
    for tok in toks:
        if tok == "(":
            node = []
            stack[-1].append(node)
            stack.append(node)
        elif tok == ")":
            if len(stack) == 1:
                raise ValueError("unexpected closing parenthesis")
            stack.pop()
        else:
            stack[-1].append(tok)
    if len(stack) != 1 or len(root) != 0 or len(stack[0]) != 1:
        raise ValueError("malformed PDDL")
    return stack[0][0]


def typed(items, default="object"):
    out, waiting, i = [], [], 0
    while i < len(items):
        x = items[i]
        if x == "-":
            if i + 1 >= len(items) or isinstance(items[i + 1], list):
                raise ValueError("malformed typed list")
            out.extend((v, items[i + 1]) for v in waiting)
            waiting = []
            i += 2
        else:
            if isinstance(x, list):
                raise ValueError("expression in typed list")
            waiting.append(x)
            i += 1
    out.extend((v, default) for v in waiting)
    return out


def fields(form):
    out, i = {}, 2
    while i + 1 < len(form):
        if isinstance(form[i], str) and form[i].startswith(":"):
            out[form[i]] = form[i + 1]
            i += 2
        else:
            i += 1
    return out


class Model:
    def __init__(self, domain_path, problem_path):
        d = sexpr(open(domain_path, encoding="utf-8").read())
        p = sexpr(open(problem_path, encoding="utf-8").read())
        if not (isinstance(d, list) and isinstance(p, list) and d and p and d[0] == p[0] == "define"):
            raise ValueError("expected PDDL define forms")
        self.types = {"object": None}
        self.actions, changed = [], set()
        for x in d[1:]:
            if not isinstance(x, list) or not x:
                continue
            if x[0] == ":types":
                self.types.update(dict(typed(x[1:])))
            elif x[0] == ":durative-action":
                raise ValueError("durative PDDL is unsupported")
            elif x[0] == ":action":
                f = fields(x)
                if len(x) < 2 or not all(k in f for k in (":parameters", ":precondition", ":effect")):
                    raise ValueError("incomplete action schema")
                a = (x[1], typed(f[":parameters"]), f[":precondition"], f[":effect"])
                self.actions.append(a)
                self.effect_predicates(a[3], changed)
        if not self.actions:
            raise ValueError("domain has no action schemas")
        self.objects, init, self.goal = {}, set(), None
        for x in p[1:]:
            if not isinstance(x, list) or not x:
                continue
            if x[0] == ":objects":
                self.objects.update(dict(typed(x[1:])))
            elif x[0] == ":init":
                for atom in x[1:]:
                    if not isinstance(atom, list) or not atom:
                        continue
                    if atom[0] in NUMERIC:
                        raise ValueError("numeric PDDL is unsupported")
                    if atom[0] not in {"not", "="}:
                        init.add(tuple(atom))
            elif x[0] == ":goal":
                if len(x) != 2:
                    raise ValueError("malformed goal")
                self.goal = x[1]
        if self.goal is None:
            raise ValueError("problem lacks a goal")
        self.by_type = collections.defaultdict(list)
        for obj, typ in self.objects.items():
            for ancestor in self.ancestors(typ):
                self.by_type[ancestor].append(obj)
        self.static_predicates = {a[0] for a in init if a[0] not in changed}
        self.fixed = frozenset(a for a in init if a[0] in self.static_predicates)
        self.initial = frozenset(a for a in init if a[0] not in self.static_predicates)

    def ancestors(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ)
            yield typ
            typ = self.types.get(typ)

    def effect_predicates(self, e, out):
        if not isinstance(e, list) or not e:
            raise ValueError("malformed effect")
        op = e[0]
        if op == "and":
            for z in e[1:]: self.effect_predicates(z, out)
        elif op == "not":
            if len(e) != 2 or not isinstance(e[1], list): raise ValueError("malformed delete effect")
            out.add(e[1][0])
        elif op in {"when", "forall"}:
            if len(e) != 3: raise ValueError("malformed conditional/quantified effect")
            self.effect_predicates(e[2], out)
        elif op in NUMERIC:
            raise ValueError("numeric PDDL is unsupported")
        elif op not in LOGIC:
            out.add(op)

    def formula(self, e, facts, env=None):
        env = {} if env is None else env
        if not isinstance(e, list) or not e:
            raise ValueError("malformed formula")
        op = e[0]
        if op == "and": return all(self.formula(x, facts, env) for x in e[1:])
        if op == "or": return any(self.formula(x, facts, env) for x in e[1:])
        if op == "not": return len(e) == 2 and not self.formula(e[1], facts, env)
        if op == "imply": return len(e) == 3 and (not self.formula(e[1], facts, env) or self.formula(e[2], facts, env))
        if op == "=": return len(e) == 3 and env.get(e[1], e[1]) == env.get(e[2], e[2])
        if op in {"forall", "exists"}:
            if len(e) != 3: raise ValueError("malformed quantifier")
            vs = typed(e[1]); vals = []
            for choice in itertools.product(*[self.by_type[t] for _, t in vs]):
                local = dict(env); local.update(dict(zip((v for v, _ in vs), choice)))
                vals.append(self.formula(e[2], facts, local))
            return all(vals) if op == "forall" else any(vals)
        return tuple(env.get(x, x) for x in e) in facts

    def apply(self, effect, state, env):
        before, after = self.fixed | state, set(self.fixed | state)
        def walk(e, local):
            if not isinstance(e, list) or not e: raise ValueError("malformed effect")
            op = e[0]
            if op == "and":
                for x in e[1:]: walk(x, local)
            elif op == "not":
                if len(e) != 2 or not isinstance(e[1], list): raise ValueError("malformed delete effect")
                after.discard(tuple(local.get(x, x) for x in e[1]))
            elif op == "when":
                if len(e) != 3: raise ValueError("malformed conditional effect")
                if self.formula(e[1], before, local): walk(e[2], local)
            elif op == "forall":
                if len(e) != 3: raise ValueError("malformed quantified effect")
                vs = typed(e[1])
                for choice in itertools.product(*[self.by_type[t] for _, t in vs]):
                    scoped = dict(local); scoped.update(dict(zip((v for v, _ in vs), choice)))
                    walk(e[2], scoped)
            elif op in NUMERIC:
                raise ValueError("numeric PDDL is unsupported")
            else:
                after.add(tuple(local.get(x, x) for x in e))
        walk(effect, env)
        return frozenset(a for a in after if a[0] not in self.static_predicates)

    def static_atoms(self, e):
        if not isinstance(e, list) or not e: return []
        if e[0] == "and":
            return sum((self.static_atoms(x) for x in e[1:]), [])
        return [tuple(e)] if e[0] in self.static_predicates else []

    def ground_actions(self):
        index = collections.defaultdict(list)
        for f in self.fixed: index[f[0]].append(f)
        answer = []
        for name, params, pre, eff in self.actions:
            variables = [v for v, _ in params]
            domains = {v: self.by_type[t] for v, t in params}
            constraints = self.static_atoms(pre)
            def finish(env):
                left = [v for v in variables if v not in env]
                if not left:
                    answer.append((name, tuple(env[v] for v in variables), env, pre, eff)); return
                v = min(left, key=lambda q: len(domains[q]))
                for obj in domains[v]:
                    nxt = dict(env); nxt[v] = obj; finish(nxt)
            def match(env, todo):
                if not todo: finish(env); return
                atom = max(todo, key=lambda q: sum(x in env for x in q[1:]))
                rest = list(todo); rest.remove(atom)
                for fact in index[atom[0]]:
                    if len(fact) != len(atom): continue
                    nxt, good = dict(env), True
                    for term, obj in zip(atom[1:], fact[1:]):
                        if isinstance(term, str) and term.startswith("?"):
                            if term not in domains or obj not in domains[term] or (term in nxt and nxt[term] != obj): good = False; break
                            nxt[term] = obj
                        elif term != obj: good = False; break
                    if good: match(nxt, rest)
            match({}, constraints)
        return answer


def goal_atoms(e):
    if not isinstance(e, list) or not e: return []
    if e[0] == "and": return sum((goal_atoms(x) for x in e[1:]), [])
    return [tuple(e)] if e[0] not in LOGIC else []


def solve(m, limit):
    if m.formula(m.goal, m.fixed | m.initial): return []
    actions = m.ground_actions()
    if not actions: return None
    goals, deadline = goal_atoms(m.goal), time.monotonic() + limit
    def h(s): return sum(g not in m.fixed and g not in s for g in goals)
    best, parent = {m.initial: 0}, {m.initial: (None, None)}
    serial, heap = 0, [(h(m.initial), 0, serial, m.initial)]
    while heap:
        if time.monotonic() > deadline: raise TimeoutError("search time limit reached")
        _, cost, _, state = heapq.heappop(heap)
        if best.get(state) != cost: continue
        for name, args, env, pre, eff in actions:
            if not m.formula(pre, m.fixed | state, env): continue
            nxt = m.apply(eff, state, env); nc = cost + 1
            if nxt == state or nc >= best.get(nxt, 10**18): continue
            best[nxt], parent[nxt] = nc, (state, (name, args))
            if m.formula(m.goal, m.fixed | nxt):
                out = []
                while parent[nxt][0] is not None:
                    nxt, act = parent[nxt]; out.append(act)
                return list(reversed(out))
            serial += 1; heapq.heappush(heap, (nc + h(nxt), nc, serial, nxt))
    return None


def read_plan(path):
    out = []
    for no, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.split(";", 1)[0].strip().lower()
        if not line: continue
        q = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
        if q: args = tuple(x.strip() for x in q.group(2).split(",") if x.strip())
        else:
            q = re.fullmatch(r"\(\s*([a-z0-9_-]+)((?:\s+[a-z0-9_-]+)*)\s*\)", line)
            if not q: raise ValueError("invalid plan line %d" % no)
            args = tuple(q.group(2).split())
        out.append((q.group(1), args))
    return out


def validate(m, plan):
    schemas = {n: (p, pre, eff) for n, p, pre, eff in m.actions}; state = m.initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in schemas: return {"valid": False, "step": step, "reason": "undeclared action"}
        ps, pre, eff = schemas[name]
        if len(ps) != len(args): return {"valid": False, "step": step, "reason": "wrong arity"}
        env = dict(zip((v for v, _ in ps), args))
        for v, typ in ps:
            if env[v] not in m.objects or typ not in set(m.ancestors(m.objects[env[v]])):
                return {"valid": False, "step": step, "reason": "ill-typed object"}
        if not m.formula(pre, m.fixed | state, env): return {"valid": False, "step": step, "reason": "unsatisfied precondition"}
        state = m.apply(eff, state, env)
    return {"valid": True, "steps": len(plan)} if m.formula(m.goal, m.fixed | state) else {"valid": False, "reason": "goal not satisfied"}


def entries(path):
    x = json.load(open(path, encoding="utf-8"))
    if isinstance(x, list): return x
    if isinstance(x, dict):
        for k in ("tasks", "problems"):
            if isinstance(x.get(k), list): return x[k]
    raise ValueError("manifest must be a list or contain tasks/problems")


def main(req):
    manifest = os.path.abspath(req.get("manifest", "problem.json")); base = os.path.dirname(manifest); es = entries(manifest)
    if not es: raise ValueError("manifest has no tasks")
    def paths(e):
        if not isinstance(e, dict) or any(not isinstance(e.get(k), str) or not e[k] for k in ("domain", "problem", "plan_output")):
            raise ValueError("entry requires domain, problem, and plan_output")
        cvt = lambda q: q if os.path.isabs(q) else os.path.join(base, q)
        return cvt(e["domain"]), cvt(e["problem"]), cvt(e["plan_output"])
    results = []
    checking = req.get("mode") == "validate-manifest"
    for e in es:
        label = e.get("id") if isinstance(e, dict) else None
        try:
            dp, pp, op = paths(e); model = Model(dp, pp)
            if checking:
                if not os.path.isfile(op): raise ValueError("required plan output is missing: " + op)
                results.append({"id": label, "plan_output": op, **validate(model, read_plan(op))}); continue
            plan = solve(model, float(req.get("time_limit_sec", 240)))
            if plan is None: results.append({"id": label, "status": "unsolved"}); continue
            replay = validate(model, plan)
            if not replay["valid"]: raise ValueError("internal replay failed")
            os.makedirs(os.path.dirname(op) or ".", exist_ok=True)
            tmp = op + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for name, args in plan: f.write(name + "(" + ",".join(args) + ")\n")
            os.replace(tmp, op)
            results.append({"id": label, "status": "solved", "plan_output": op, "plan_length": len(plan), "validation": replay})
        except TimeoutError as x: results.append({"id": label, "status": "timeout", "reason": str(x)})
        except Exception as x:
            if checking: results.append({"id": label, "valid": False, "reason": str(x)})
            else: results.append({"id": label, "status": "error", "reason": str(x)})
    return {"ok": all((r.get("valid") if checking else r.get("status") == "solved") for r in results), "results": results}

if __name__ == "__main__":
    try: print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "error", "reason": str(exc)})); sys.exit(2)
