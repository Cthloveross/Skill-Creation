#!/usr/bin/env python3
"""Read a PDDL manifest, write grounded plans, or validate its plan artifacts."""
import collections
import heapq
import itertools
import json
import os
import re
import sys
import time

NUMERIC = {"increase", "decrease", "assign", "scale-up", "scale-down"}
SPECIAL = {"and", "or", "not", "imply", "=", "forall", "exists", "when"} | NUMERIC


def sexpr(text):
    toks = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    stack = [[]]
    for tok in toks:
        if tok == "(":
            n = []; stack[-1].append(n); stack.append(n)
        elif tok == ")":
            if len(stack) == 1: raise ValueError("unexpected closing parenthesis")
            stack.pop()
        else: stack[-1].append(tok)
    if len(stack) != 1 or len(stack[0]) != 1 or not isinstance(stack[0][0], list):
        raise ValueError("malformed PDDL")
    return stack[0][0]


def typed(items, default="object"):
    out, pending, i = [], [], 0
    while i < len(items):
        x = items[i]
        if x == "-":
            if i + 1 == len(items) or isinstance(items[i + 1], list): raise ValueError("bad typed list")
            out += [(v, items[i + 1]) for v in pending]; pending = []; i += 2
        else:
            if isinstance(x, list): raise ValueError("compound type is unsupported")
            pending.append(x); i += 1
    return out + [(v, default) for v in pending]


def fields(action):
    ans, i = {}, 2
    while i + 1 < len(action):
        if isinstance(action[i], str) and action[i].startswith(":"):
            ans[action[i]] = action[i + 1]; i += 2
        else: i += 1
    return ans


class Model:
    def __init__(self, domain_file, problem_file):
        d = sexpr(open(domain_file, encoding="utf-8").read())
        p = sexpr(open(problem_file, encoding="utf-8").read())
        if not (d and p and d[0] == p[0] == "define"): raise ValueError("expected PDDL define forms")
        self.types = {"object": None}; self.actions = []; self.objects = {}
        changed = set()
        for part in d[1:]:
            if not isinstance(part, list) or not part: continue
            if part[0] == ":types": self.types.update(dict(typed(part[1:])))
            elif part[0] == ":constants": self.objects.update(dict(typed(part[1:])))
            elif part[0] == ":durative-action": raise ValueError("durative PDDL is unsupported")
            elif part[0] == ":action":
                f = fields(part)
                if len(part) < 2 or any(k not in f for k in (":parameters", ":precondition", ":effect")):
                    raise ValueError("incomplete action schema")
                a = (part[1], typed(f[":parameters"]), f[":precondition"], f[":effect"])
                self.actions.append(a); self.effect_heads(a[3], changed)
        if not self.actions: raise ValueError("domain has no actions")
        initial = set(); self.goal = None
        for part in p[1:]:
            if not isinstance(part, list) or not part: continue
            if part[0] == ":objects": self.objects.update(dict(typed(part[1:])))
            elif part[0] == ":init":
                for atom in part[1:]:
                    if not isinstance(atom, list) or not atom: continue
                    if atom[0] in NUMERIC: raise ValueError("numeric PDDL is unsupported")
                    if atom[0] not in {"not", "="}: initial.add(tuple(atom))
            elif part[0] == ":goal":
                if len(part) != 2: raise ValueError("malformed goal")
                self.goal = part[1]
        if self.goal is None: raise ValueError("problem has no goal")
        self.by_type = collections.defaultdict(list)
        for obj, typ in self.objects.items():
            for parent in self.parents(typ): self.by_type[parent].append(obj)
        self.static_heads = {a[0] for a in initial if a[0] not in changed}
        self.fixed = frozenset(a for a in initial if a[0] in self.static_heads)
        self.initial = frozenset(a for a in initial if a[0] not in self.static_heads)

    def parents(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ); yield typ; typ = self.types.get(typ)

    def effect_heads(self, e, out):
        if not isinstance(e, list) or not e: raise ValueError("malformed effect")
        if e[0] == "and":
            for c in e[1:]: self.effect_heads(c, out)
        elif e[0] == "not":
            if len(e) != 2 or not isinstance(e[1], list): raise ValueError("malformed delete")
            out.add(e[1][0])
        elif e[0] in {"when", "forall"}:
            if len(e) != 3: raise ValueError("malformed conditional effect")
            self.effect_heads(e[2], out)
        elif e[0] in NUMERIC: raise ValueError("numeric PDDL is unsupported")
        elif e[0] not in SPECIAL: out.add(e[0])

    def truth(self, e, facts, env=None):
        env = {} if env is None else env
        if not isinstance(e, list) or not e: raise ValueError("malformed formula")
        op = e[0]
        if op == "and": return all(self.truth(x, facts, env) for x in e[1:])
        if op == "or": return any(self.truth(x, facts, env) for x in e[1:])
        if op == "not": return len(e) == 2 and not self.truth(e[1], facts, env)
        if op == "imply": return len(e) == 3 and (not self.truth(e[1], facts, env) or self.truth(e[2], facts, env))
        if op == "=": return len(e) == 3 and env.get(e[1], e[1]) == env.get(e[2], e[2])
        if op in {"forall", "exists"}:
            if len(e) != 3: raise ValueError("malformed quantifier")
            vs = typed(e[1]); vals = []
            for choice in itertools.product(*[self.by_type[t] for _, t in vs]):
                local = dict(env); local.update(dict(zip((v for v, _ in vs), choice)))
                vals.append(self.truth(e[2], facts, local))
            return all(vals) if op == "forall" else any(vals)
        return tuple(env.get(x, x) for x in e) in facts

    def apply(self, effect, state, env):
        result = set(self.fixed | state)
        def walk(e, local):
            if not isinstance(e, list) or not e: raise ValueError("malformed effect")
            op = e[0]
            if op == "and":
                for x in e[1:]: walk(x, local)
            elif op == "not":
                if len(e) != 2 or not isinstance(e[1], list): raise ValueError("malformed delete")
                result.discard(tuple(local.get(x, x) for x in e[1]))
            elif op == "when":
                if len(e) != 3: raise ValueError("malformed conditional effect")
                if self.truth(e[1], result, local): walk(e[2], local)
            elif op == "forall":
                if len(e) != 3: raise ValueError("malformed quantified effect")
                for choice in itertools.product(*[self.by_type[t] for _, t in typed(e[1])]):
                    scoped = dict(local); scoped.update(dict(zip((v for v, _ in typed(e[1])), choice)))
                    walk(e[2], scoped)
            elif op in NUMERIC: raise ValueError("numeric PDDL is unsupported")
            else: result.add(tuple(local.get(x, x) for x in e))
        walk(effect, env)
        return frozenset(x for x in result if x[0] not in self.static_heads)

    def static_requirements(self, e):
        if not isinstance(e, list) or not e: return []
        if e[0] == "and": return sum((self.static_requirements(x) for x in e[1:]), [])
        return [tuple(e)] if e[0] in self.static_heads else []

    def ground(self):
        byhead = collections.defaultdict(list)
        for a in self.fixed: byhead[a[0]].append(a)
        answer = []
        for name, params, pre, eff in self.actions:
            names = [v for v, _ in params]; domains = {v: self.by_type[t] for v, t in params}
            reqs = self.static_requirements(pre); found = set()
            def finish(env):
                missing = [v for v in names if v not in env]
                if not missing:
                    args = tuple(env[v] for v in names)
                    if args not in found:
                        found.add(args); answer.append((name, args, dict(env), pre, eff))
                    return
                v = min(missing, key=lambda z: len(domains[z]))
                for o in domains[v]:
                    nxt = dict(env); nxt[v] = o; finish(nxt)
            def match(todo, env):
                if not todo: finish(env); return
                atom = todo[0]
                for fact in byhead[atom[0]]:
                    if len(fact) != len(atom): continue
                    nxt = dict(env); good = True
                    for term, obj in zip(atom[1:], fact[1:]):
                        if isinstance(term, str) and term.startswith("?"):
                            if term not in domains or obj not in domains[term] or (term in nxt and nxt[term] != obj): good = False; break
                            nxt[term] = obj
                        elif term != obj: good = False; break
                    if good: match(todo[1:], nxt)
            match(reqs, {})
        return answer


def positive_goals(e):
    if not isinstance(e, list) or not e: return []
    if e[0] == "and": return sum((positive_goals(x) for x in e[1:]), [])
    return [tuple(e)] if e[0] not in SPECIAL else []


def solve(m, seconds):
    if m.truth(m.goal, m.fixed | m.initial): return []
    actions = m.ground()
    if not actions: return None
    goals = positive_goals(m.goal); deadline = time.monotonic() + seconds
    def h(s): return sum(g not in m.fixed and g not in s for g in goals)
    best = {m.initial: 0}; parent = {m.initial: None}; counter = 0
    q = [(h(m.initial), 0, counter, m.initial)]
    while q:
        if time.monotonic() > deadline: raise TimeoutError("search time limit reached")
        _, cost, _, state = heapq.heappop(q)
        if best.get(state) != cost: continue
        for name, args, env, pre, eff in actions:
            if not m.truth(pre, m.fixed | state, env): continue
            nxt = m.apply(eff, state, env); nc = cost + 1
            if nxt == state or nc >= best.get(nxt, 10 ** 18): continue
            best[nxt] = nc; parent[nxt] = (state, (name, args))
            if m.truth(m.goal, m.fixed | nxt):
                plan = []; cur = nxt
                while parent[cur] is not None:
                    cur, act = parent[cur]; plan.append(act)
                return list(reversed(plan))
            counter += 1; heapq.heappush(q, (nc + h(nxt), nc, counter, nxt))
    return None


def read_plan(path):
    out = []
    for n, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.split(";", 1)[0].strip().lower()
        if not line: continue
        x = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
        if x: out.append((x.group(1), tuple(a.strip() for a in x.group(2).split(",") if a.strip()))); continue
        x = re.fullmatch(r"\(\s*([a-z0-9_-]+)((?:\s+[a-z0-9_-]+)*)\s*\)", line)
        if not x: raise ValueError("invalid plan line %d" % n)
        out.append((x.group(1), tuple(x.group(2).split())))
    return out


def validate(m, plan):
    schemas = {n: (p, pre, eff) for n, p, pre, eff in m.actions}; state = m.initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in schemas: return {"valid": False, "step": step, "reason": "undeclared action"}
        pars, pre, eff = schemas[name]
        if len(pars) != len(args): return {"valid": False, "step": step, "reason": "wrong arity"}
        env = dict(zip((v for v, _ in pars), args))
        for v, typ in pars:
            if env[v] not in m.objects or typ not in set(m.parents(m.objects[env[v]])):
                return {"valid": False, "step": step, "reason": "ill-typed object"}
        if not m.truth(pre, m.fixed | state, env): return {"valid": False, "step": step, "reason": "unsatisfied precondition"}
        state = m.apply(eff, state, env)
    return {"valid": m.truth(m.goal, m.fixed | state), "steps": len(plan), "reason": "goal not satisfied"}


def entries(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for key in ("tasks", "problems"):
            if isinstance(data.get(key), list): return data[key]
    raise ValueError("manifest must be a list or contain tasks/problems")


def main(req):
    manifest = os.path.abspath(req.get("manifest", "problem.json")); base = os.path.dirname(manifest)
    todo = entries(manifest)
    if not todo: raise ValueError("manifest has no tasks")
    checking = req.get("mode") == "validate-manifest"; results = []
    for entry in todo:
        label = entry.get("id") if isinstance(entry, dict) else None
        try:
            if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or not entry[k] for k in ("domain", "problem", "plan_output")):
                raise ValueError("entry requires domain, problem, and plan_output")
            def path(v): return v if os.path.isabs(v) else os.path.join(base, v)
            out = path(entry["plan_output"]); model = Model(path(entry["domain"]), path(entry["problem"]))
            if checking:
                if not os.path.isfile(out): raise ValueError("required plan output is missing: " + out)
                results.append({"id": label, "plan_output": out, **validate(model, read_plan(out))}); continue
            plan = solve(model, float(req.get("time_limit_sec", 250)))
            if plan is None: results.append({"id": label, "status": "unsolved", "plan_output": out}); continue
            check = validate(model, plan)
            if not check["valid"]: raise ValueError("internal replay failed")
            os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
            tmp = out + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for name, args in plan: f.write(name + "(" + ",".join(args) + ")\n")
            os.replace(tmp, out)
            results.append({"id": label, "status": "solved", "plan_output": out, "plan_length": len(plan), "validation": check})
        except TimeoutError as e: results.append({"id": label, "status": "timeout", "reason": str(e)})
        except Exception as e:
            results.append({"id": label, **({"valid": False} if checking else {"status": "error"}), "reason": str(e)})
    ok = all(r.get("valid") if checking else r.get("status") == "solved" for r in results)
    return {"ok": ok, "results": results}

if __name__ == "__main__":
    try: print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as e:
        print(json.dumps({"ok": False, "status": "error", "reason": str(e)}, sort_keys=True)); sys.exit(2)
