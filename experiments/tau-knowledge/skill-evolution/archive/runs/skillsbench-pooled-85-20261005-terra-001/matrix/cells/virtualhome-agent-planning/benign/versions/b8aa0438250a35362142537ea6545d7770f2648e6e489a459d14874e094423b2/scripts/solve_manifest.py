#!/usr/bin/env python3
"""Manifest-driven typed classical PDDL planner and plan-file validator."""
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


def sexpr(text):
    toks = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    root, stack = [], []
    cur = root
    for tok in toks:
        if tok == "(":
            node = []; cur.append(node); stack.append(cur); cur = node
        elif tok == ")":
            if not stack: raise ValueError("unexpected closing parenthesis")
            cur = stack.pop()
        else: cur.append(tok)
    if stack or len(root) != 1 or not isinstance(root[0], list):
        raise ValueError("malformed PDDL")
    return root[0]


def typed(items, default="object"):
    out, pending, i = [], [], 0
    while i < len(items):
        x = items[i]
        if x == "-":
            if i + 1 >= len(items) or isinstance(items[i + 1], list):
                raise ValueError("malformed typed-name list")
            out += [(v, items[i + 1]) for v in pending]
            pending = []; i += 2
        else:
            if isinstance(x, list): raise ValueError("compound type is unsupported")
            pending.append(x); i += 1
    return out + [(v, default) for v in pending]


def section(tree, name):
    return next((x for x in tree if isinstance(x, list) and x and x[0] == name), None)


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
        if not d or not p or d[0] != "define" or p[0] != "define":
            raise ValueError("domain and problem must be define forms")
        self.types = {"object": None}
        t = section(d, ":types")
        if t: self.types.update(dict(typed(t[1:])))
        # Domain constants are legal in formulae, but plan arguments must be
        # problem objects under the supplied validator's contract.
        self.objects = {}
        o = section(p, ":objects")
        if o: self.objects.update(dict(typed(o[1:])))
        self.bytype = collections.defaultdict(list)
        for obj, typ in self.objects.items():
            for parent in self.parents(typ): self.bytype[parent].append(obj)
        self.actions, changing = [], set()
        for item in d:
            if not isinstance(item, list) or not item: continue
            if item[0] == ":durative-action": raise ValueError("durative PDDL is unsupported")
            if item[0] != ":action": continue
            f = fields(item)
            if len(item) < 2 or any(k not in f for k in (":parameters", ":precondition", ":effect")):
                raise ValueError("incomplete action schema")
            rec = (item[1], typed(f[":parameters"]), f[":precondition"], f[":effect"])
            self.actions.append(rec); self.effect_heads(rec[3], changing)
        if not self.actions: raise ValueError("domain contains no actions")
        ini, goal = section(p, ":init"), section(p, ":goal")
        if ini is None or goal is None or len(goal) != 2: raise ValueError("problem lacks init or goal")
        facts = set()
        for atom in ini[1:]:
            if not isinstance(atom, list) or not atom: continue
            if atom[0] in NUMERIC: raise ValueError("numeric PDDL is unsupported")
            if atom[0] not in {"not", "="}: facts.add(tuple(atom))
        self.goal = goal[1]
        self.static_heads = {x[0] for x in facts if x[0] not in changing}
        self.fixed = frozenset(x for x in facts if x[0] in self.static_heads)
        self.initial = frozenset(x for x in facts if x[0] not in self.static_heads)

    def parents(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ); yield typ; typ = self.types.get(typ)

    def effect_heads(self, e, out):
        if not isinstance(e, list) or not e: raise ValueError("malformed effect")
        op = e[0]
        if op == "and":
            for child in e[1:]: self.effect_heads(child, out)
        elif op == "not":
            if len(e) != 2 or not isinstance(e[1], list): raise ValueError("malformed delete effect")
            out.add(e[1][0])
        elif op in {"when", "forall"}:
            if len(e) != 3: raise ValueError("malformed conditional effect")
            self.effect_heads(e[2], out)
        elif op in NUMERIC: raise ValueError("numeric PDDL is unsupported")
        elif op not in LOGIC: out.add(op)

    def truth(self, e, state, env=None):
        env = {} if env is None else env
        if not isinstance(e, list) or not e: raise ValueError("malformed formula")
        op = e[0]
        if op == "and": return all(self.truth(x, state, env) for x in e[1:])
        if op == "or": return any(self.truth(x, state, env) for x in e[1:])
        if op == "not": return len(e) == 2 and not self.truth(e[1], state, env)
        if op == "imply": return len(e) == 3 and (not self.truth(e[1], state, env) or self.truth(e[2], state, env))
        if op == "=": return len(e) == 3 and env.get(e[1], e[1]) == env.get(e[2], e[2])
        if op in {"forall", "exists"}:
            if len(e) != 3: raise ValueError("malformed quantifier")
            vs = typed(e[1]); vals = []
            for xs in itertools.product(*[self.bytype[t] for _, t in vs]):
                local = dict(env); local.update(dict(zip((v for v, _ in vs), xs)))
                vals.append(self.truth(e[2], state, local))
            return all(vals) if op == "forall" else any(vals)
        return tuple(env.get(x, x) for x in e) in state

    def apply(self, effect, dynamic, env):
        full = set(self.fixed | dynamic)
        def walk(e, local):
            if not isinstance(e, list) or not e: raise ValueError("malformed effect")
            op = e[0]
            if op == "and":
                for x in e[1:]: walk(x, local)
            elif op == "not":
                if len(e) != 2 or not isinstance(e[1], list): raise ValueError("malformed delete effect")
                full.discard(tuple(local.get(x, x) for x in e[1]))
            elif op == "when":
                if len(e) != 3: raise ValueError("malformed conditional effect")
                if self.truth(e[1], full, local): walk(e[2], local)
            elif op == "forall":
                if len(e) != 3: raise ValueError("malformed quantified effect")
                vs = typed(e[1])
                for xs in itertools.product(*[self.bytype[t] for _, t in vs]):
                    scoped = dict(local); scoped.update(dict(zip((v for v, _ in vs), xs)))
                    walk(e[2], scoped)
            elif op in NUMERIC: raise ValueError("numeric PDDL is unsupported")
            else: full.add(tuple(local.get(x, x) for x in e))
        walk(effect, env)
        return frozenset(x for x in full if x[0] not in self.static_heads)

    def static_requirements(self, e):
        if not isinstance(e, list) or not e: return []
        if e[0] == "and": return sum((self.static_requirements(x) for x in e[1:]), [])
        return [e] if e[0] in self.static_heads else []

    def ground(self):
        facts = collections.defaultdict(list)
        for f in self.fixed: facts[f[0]].append(f)
        result = []
        for name, params, pre, eff in self.actions:
            variables = [v for v, _ in params]
            domains = {v: self.bytype[t] for v, t in params}
            def complete(env):
                missing = [v for v in variables if v not in env]
                if missing:
                    v = min(missing, key=lambda z: len(domains[z]))
                    for obj in domains[v]:
                        nxt = dict(env); nxt[v] = obj; complete(nxt)
                    return
                result.append((name, tuple(env[v] for v in variables), dict(env), pre, eff))
            def bind(reqs, env):
                if not reqs: complete(env); return
                atom = reqs[0]
                for fact in facts[atom[0]]:
                    if len(atom) != len(fact): continue
                    nxt, good = dict(env), True
                    for term, obj in zip(atom[1:], fact[1:]):
                        if isinstance(term, str) and term.startswith("?"):
                            if term not in domains or obj not in domains[term] or (term in nxt and nxt[term] != obj): good = False; break
                            nxt[term] = obj
                        elif term != obj: good = False; break
                    if good: bind(reqs[1:], nxt)
            bind(self.static_requirements(pre), {})
        return result


def goal_atoms(e):
    if not isinstance(e, list) or not e: return []
    if e[0] == "and": return sum((goal_atoms(x) for x in e[1:]), [])
    return [tuple(e)] if e[0] not in LOGIC else []


def solve(model, limit):
    if model.truth(model.goal, model.fixed | model.initial): return []
    acts = model.ground()
    if not acts: return None
    wanted = goal_atoms(model.goal)
    def h(s): return sum(x not in model.fixed and x not in s for x in wanted)
    best, parent, serial = {model.initial: 0}, {model.initial: None}, 0
    queue = [(h(model.initial), 0, serial, model.initial)]
    deadline = time.monotonic() + limit
    while queue:
        if time.monotonic() > deadline: raise TimeoutError("search time limit reached")
        _, cost, _, state = heapq.heappop(queue)
        if best.get(state) != cost: continue
        for name, args, env, pre, eff in acts:
            if not model.truth(pre, model.fixed | state, env): continue
            nxt = model.apply(eff, state, env); nc = cost + 1
            if nxt == state or nc >= best.get(nxt, 10**18): continue
            best[nxt] = nc; parent[nxt] = (state, (name, args))
            if model.truth(model.goal, model.fixed | nxt):
                plan, cur = [], nxt
                while parent[cur] is not None:
                    cur, action = parent[cur]; plan.append(action)
                return list(reversed(plan))
            serial += 1; heapq.heappush(queue, (nc + h(nxt), nc, serial, nxt))
    return None


def parse_plan(path):
    plan = []
    for n, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.split(";", 1)[0].strip().lower()
        if not line: continue
        m = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
        if m:
            args = tuple(x.strip() for x in m.group(2).split(",") if x.strip())
            if any(not re.fullmatch(r"[a-z0-9_-]+", x) for x in args): raise ValueError("invalid action arguments on line %d" % n)
            plan.append((m.group(1), args)); continue
        m = re.fullmatch(r"\(\s*([a-z0-9_-]+)((?:\s+[a-z0-9_-]+)*)\s*\)", line)
        if not m: raise ValueError("invalid plan line %d" % n)
        plan.append((m.group(1), tuple(m.group(2).split())))
    return plan


def validate(model, plan):
    schemas = {n: (p, pre, eff) for n, p, pre, eff in model.actions}
    state = model.initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in schemas: return {"valid": False, "step": step, "reason": "undeclared action"}
        params, pre, eff = schemas[name]
        if len(params) != len(args): return {"valid": False, "step": step, "reason": "wrong arity"}
        env = dict(zip((v for v, _ in params), args))
        for var, typ in params:
            if env[var] not in model.objects or typ not in set(model.parents(model.objects[env[var]])):
                return {"valid": False, "step": step, "reason": "ill-typed object"}
        if not model.truth(pre, model.fixed | state, env): return {"valid": False, "step": step, "reason": "unsatisfied precondition"}
        state = model.apply(eff, state, env)
    return {"valid": True, "steps": len(plan)} if model.truth(model.goal, model.fixed | state) else {"valid": False, "steps": len(plan), "reason": "goal not satisfied"}


def entries(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for key in ("tasks", "problems"):
            if isinstance(data.get(key), list): return data[key]
    raise ValueError("manifest must be a list or contain tasks/problems")


def run(req):
    manifest = os.path.abspath(req.get("manifest", "problem.json")); base = os.path.dirname(manifest)
    tasks = entries(manifest)
    if not tasks: raise ValueError("manifest declares no tasks")
    checking, results = req.get("mode") == "validate-manifest", []
    for item in tasks:
        label = item.get("id") if isinstance(item, dict) else None
        try:
            if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k] for k in ("domain", "problem", "plan_output")):
                raise ValueError("task requires domain, problem, and plan_output")
            resolve = lambda x: x if os.path.isabs(x) else os.path.join(base, x)
            output = resolve(item["plan_output"]); model = Model(resolve(item["domain"]), resolve(item["problem"]))
            if checking:
                if not os.path.isfile(output): raise ValueError("required plan output is missing: " + output)
                results.append({"id": label, "plan_output": output, **validate(model, parse_plan(output))}); continue
            plan = solve(model, float(req.get("time_limit_sec", 240)))
            if plan is None: results.append({"id": label, "status": "unsolved", "plan_output": output}); continue
            report = validate(model, plan)
            if not report["valid"]: raise ValueError("internal replay failed: " + report["reason"])
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
            tmp = output + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for name, args in plan: f.write(name + "(" + ",".join(args) + ")\n")
            os.replace(tmp, output)
            results.append({"id": label, "status": "solved", "plan_output": output, "plan_length": len(plan), "validation": report})
        except TimeoutError as exc: results.append({"id": label, "status": "timeout", "reason": str(exc)})
        except Exception as exc:
            results.append({"id": label, **({"valid": False} if checking else {"status": "error"}), "reason": str(exc)})
    ok = all(r.get("valid", False) for r in results) if checking else all(r.get("status") == "solved" for r in results)
    return {"ok": ok, "results": results}


if __name__ == "__main__":
    try: print(json.dumps(run(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "error", "reason": str(exc)}, sort_keys=True)); sys.exit(2)
