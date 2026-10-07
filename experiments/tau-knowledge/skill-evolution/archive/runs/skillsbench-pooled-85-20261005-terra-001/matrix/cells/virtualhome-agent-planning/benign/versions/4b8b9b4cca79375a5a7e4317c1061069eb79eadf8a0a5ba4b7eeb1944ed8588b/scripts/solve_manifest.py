#!/usr/bin/env python3
"""Typed classical-PDDL manifest solver.  JSON stdin -> JSON stdout."""
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
    toks = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    root, stack = [], [[]]
    root = stack[0]
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
    if len(stack) != 1 or len(root) != 1 or not isinstance(root[0], list):
        raise ValueError("malformed PDDL expression")
    return root[0]


def typed(items, default="object"):
    out, pending, i = [], [], 0
    while i < len(items):
        x = items[i]
        if x == "-":
            if i + 1 >= len(items) or isinstance(items[i + 1], list):
                raise ValueError("malformed typed list")
            out.extend((name, items[i + 1]) for name in pending)
            pending = []
            i += 2
        else:
            if isinstance(x, list):
                raise ValueError("unexpected expression in typed list")
            pending.append(x)
            i += 1
    out.extend((name, default) for name in pending)
    return out


def fields(item):
    ans, i = {}, 2
    while i + 1 < len(item):
        if isinstance(item[i], str) and item[i].startswith(":"):
            ans[item[i]] = item[i + 1]
            i += 2
        else:
            i += 1
    return ans


class Model:
    def __init__(self, domain_file, problem_file):
        domain = sexpr(open(domain_file, encoding="utf-8").read())
        problem = sexpr(open(problem_file, encoding="utf-8").read())
        if not domain or domain[0] != "define" or not problem or problem[0] != "define":
            raise ValueError("domain and problem must be PDDL define forms")
        self.types = {"object": None}
        self.objects, self.schemas = [], []
        initial, self.goal = set(), ["and"]
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
                f = fields(item)
                if len(item) < 2 or any(k not in f for k in (":parameters", ":precondition", ":effect")):
                    raise ValueError("malformed action")
                self.schemas.append({"name": item[1], "params": typed(f[":parameters"]),
                                     "pre": f[":precondition"], "effect": f[":effect"]})
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
                    if fact[0] not in ("not", "="):
                        initial.add(tuple(fact))
            elif item[0] == ":goal":
                if len(item) != 2:
                    raise ValueError("malformed goal")
                self.goal = item[1]
        self.objtype = dict(self.objects)
        self.bytype = collections.defaultdict(list)
        for obj, typ in self.objects:
            for parent in self.ancestors(typ):
                self.bytype[parent].append(obj)
        self.changed = set()
        for action in self.schemas:
            self.mark_changed(action["effect"])
        self.static_predicates = {x[0] for x in initial if x[0] not in self.changed}
        self.static = frozenset(x for x in initial if x[0] in self.static_predicates)
        self.start = frozenset(x for x in initial if x[0] not in self.static_predicates)

    def ancestors(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ)
            yield typ
            typ = self.types.get(typ)

    def mark_changed(self, x):
        if not isinstance(x, list) or not x:
            return
        op = x[0]
        if op == "and":
            for y in x[1:]: self.mark_changed(y)
        elif op == "not" and len(x) == 2 and isinstance(x[1], list) and x[1]:
            self.changed.add(x[1][0])
        elif op in ("when", "forall") and len(x) == 3:
            self.mark_changed(x[2])
        elif op in NUMERIC:
            raise ValueError("numeric effects are unsupported")
        elif op not in CONTROL:
            self.changed.add(op)

    def formula(self, x, state, env=None):
        env = {} if env is None else env
        if not isinstance(x, list) or not x:
            raise ValueError("malformed logical formula")
        op = x[0]
        if op == "and": return all(self.formula(y, state, env) for y in x[1:])
        if op == "or": return any(self.formula(y, state, env) for y in x[1:])
        if op == "not": return len(x) == 2 and not self.formula(x[1], state, env)
        if op == "imply": return len(x) == 3 and (not self.formula(x[1], state, env) or self.formula(x[2], state, env))
        if op == "=": return len(x) == 3 and env.get(x[1], x[1]) == env.get(x[2], x[2])
        if op in ("forall", "exists"):
            if len(x) != 3: raise ValueError("malformed quantified formula")
            vars_ = typed(x[1])
            values = []
            for vals in itertools.product(*(self.bytype[t] for _, t in vars_)):
                e = dict(env); e.update(dict(zip((v for v, _ in vars_), vals)))
                values.append(self.formula(x[2], state, e))
            return all(values) if op == "forall" else any(values)
        return tuple(env.get(v, v) for v in x) in state

    def apply(self, effect, dynamic, env):
        full = set(self.static | dynamic)
        def walk(x, e):
            if not isinstance(x, list) or not x: raise ValueError("malformed effect")
            op = x[0]
            if op == "and":
                for y in x[1:]: walk(y, e)
            elif op == "not":
                if len(x) != 2 or not isinstance(x[1], list): raise ValueError("malformed delete effect")
                full.discard(tuple(e.get(v, v) for v in x[1]))
            elif op == "when":
                if len(x) != 3: raise ValueError("malformed conditional effect")
                if self.formula(x[1], full, e): walk(x[2], e)
            elif op == "forall":
                if len(x) != 3: raise ValueError("malformed quantified effect")
                vars_ = typed(x[1])
                for vals in itertools.product(*(self.bytype[t] for _, t in vars_)):
                    ne = dict(e); ne.update(dict(zip((v for v, _ in vars_), vals)))
                    walk(x[2], ne)
            elif op in NUMERIC:
                raise ValueError("numeric effects are unsupported")
            else:
                full.add(tuple(e.get(v, v) for v in x))
        walk(effect, env)
        return frozenset(x for x in full if x[0] not in self.static_predicates)

    def static_atoms(self, x):
        answer = []
        def visit(y):
            if not isinstance(y, list) or not y: return
            if y[0] == "and":
                for z in y[1:]: visit(z)
            elif y[0] not in CONTROL and y[0] in self.static_predicates:
                answer.append(y)
        visit(x)
        return answer

    def positive_dynamic(self, x, env):
        answer = []
        def visit(y):
            if not isinstance(y, list) or not y: return
            if y[0] == "and":
                for z in y[1:]: visit(z)
            elif y[0] not in CONTROL and y[0] not in self.static_predicates:
                answer.append(tuple(env.get(v, v) for v in y))
        visit(x)
        return tuple(answer)

    def ground(self):
        static_by_pred = collections.defaultdict(list)
        for fact in self.static: static_by_pred[fact[0]].append(fact)
        result, seen = [], set()
        for schema in self.schemas:
            variables = [v for v, _ in schema["params"]]
            domains = {v: self.bytype[t] for v, t in schema["params"]}
            def join(env, constraints):
                if constraints:
                    atom = min(constraints, key=lambda a: len(static_by_pred[a[0]]))
                    rest = list(constraints); rest.remove(atom)
                    for fact in static_by_pred[atom[0]]:
                        if len(fact) != len(atom): continue
                        e, ok = dict(env), True
                        for term, value in zip(atom[1:], fact[1:]):
                            if term.startswith("?"):
                                if term in e and e[term] != value: ok = False; break
                                if value not in domains.get(term, ()): ok = False; break
                                e[term] = value
                            elif term != value: ok = False; break
                        if ok: join(e, rest)
                    return
                missing = [v for v in variables if v not in env]
                if missing:
                    v = min(missing, key=lambda q: len(domains[q]))
                    for value in domains[v]:
                        e = dict(env); e[v] = value; join(e, ())
                    return
                key = (schema["name"], tuple(env[v] for v in variables))
                if key in seen: return
                seen.add(key)
                result.append({"name": schema["name"], "args": key[1], "env": env,
                               "pre": schema["pre"], "effect": schema["effect"],
                               "positive": self.positive_dynamic(schema["pre"], env)})
            join({}, self.static_atoms(schema["pre"]))
        return result


def goal_atoms(x):
    out = []
    def visit(y):
        if not isinstance(y, list) or not y: return
        if y[0] == "and":
            for z in y[1:]: visit(z)
        elif y[0] not in CONTROL: out.append(tuple(y))
    visit(x)
    return out


def solve(model, limit):
    if model.formula(model.goal, model.static | model.start): return []
    actions = model.ground()
    if not actions: return None
    indexed, always = collections.defaultdict(set), set()
    for i, action in enumerate(actions):
        if action["positive"]:
            for fact in action["positive"]: indexed[fact].add(i)
        else: always.add(i)
    goals = goal_atoms(model.goal)
    def h(state): return sum(g not in state and g not in model.static for g in goals)
    deadline = time.monotonic() + limit
    heap, serial = [(2 * h(model.start), 0, 0, model.start)], 0
    best, parent = {model.start: 0}, {model.start: (None, None)}
    while heap:
        if time.monotonic() > deadline: raise TimeoutError("search time limit reached")
        _, cost, _, state = heapq.heappop(heap)
        if best.get(state) != cost: continue
        candidates = set(always)
        for fact in state: candidates.update(indexed.get(fact, ()))
        for number in candidates:
            action = actions[number]
            if not model.formula(action["pre"], state | model.static, action["env"]): continue
            nxt = model.apply(action["effect"], state, action["env"])
            if nxt == state or cost + 1 >= best.get(nxt, 10 ** 18): continue
            best[nxt], parent[nxt] = cost + 1, (state, action)
            if model.formula(model.goal, nxt | model.static):
                plan, cursor = [], nxt
                while parent[cursor][0] is not None:
                    previous, used = parent[cursor]
                    plan.append((used["name"], used["args"])); cursor = previous
                return list(reversed(plan))
            serial += 1
            heapq.heappush(heap, (cost + 1 + 2 * h(nxt), cost + 1, serial, nxt))
    return None


def validate(model, plan):
    schemas = {x["name"]: x for x in model.schemas}
    state = model.start
    for step, (name, args) in enumerate(plan, 1):
        schema = schemas.get(name)
        if not schema: return {"valid": False, "step": step, "reason": "undeclared action " + name}
        if len(args) != len(schema["params"]): return {"valid": False, "step": step, "reason": "wrong action arity"}
        env = dict(zip((v for v, _ in schema["params"]), args))
        for var, required in schema["params"]:
            obj = env[var]
            if obj not in model.objtype or required not in set(model.ancestors(model.objtype[obj])):
                return {"valid": False, "step": step, "reason": "unknown or ill-typed object " + obj}
        if not model.formula(schema["pre"], state | model.static, env):
            return {"valid": False, "step": step, "reason": "unsatisfied precondition"}
        state = model.apply(schema["effect"], state, env)
    if not model.formula(model.goal, state | model.static):
        return {"valid": False, "step": len(plan), "reason": "goal not satisfied"}
    return {"valid": True, "steps": len(plan)}


def read_plan(path):
    plan = []
    for line_no, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.split(";", 1)[0].strip().lower()
        if not line: continue
        m = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
        if not m: raise ValueError("line %d is not a grounded action primitive" % line_no)
        args = tuple(x.strip() for x in m.group(2).split(",") if x.strip())
        if any(not re.fullmatch(r"[a-z0-9_-]+", x) for x in args):
            raise ValueError("line %d has malformed argument" % line_no)
        plan.append((m.group(1), args))
    return plan


def entries(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for key in ("tasks", "problems"):
            if isinstance(data.get(key), list): return data[key]
    raise ValueError("manifest must be a list or contain tasks/problems")


def resolve(value, base):
    return value if os.path.isabs(value) else os.path.join(base, value)


def solve_one(entry, base, limit):
    label = entry.get("id") if isinstance(entry, dict) else None
    try:
        if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or not entry[k] for k in ("domain", "problem", "plan_output")):
            raise ValueError("entry requires domain, problem, and plan_output")
        model = Model(resolve(entry["domain"], base), resolve(entry["problem"], base))
        plan = solve(model, limit)
        if plan is None: return {"id": label, "status": "unsolved"}
        verdict = validate(model, plan)
        if not verdict["valid"]: return {"id": label, "status": "error", "reason": "internal replay failed", "validation": verdict}
        output = resolve(entry["plan_output"], base)
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        temporary = output + ".tmp"
        with open(temporary, "w", encoding="utf-8") as f:
            for name, args in plan: f.write("%s(%s)\n" % (name, ", ".join(args)))
        os.replace(temporary, output)
        return {"id": label, "status": "solved", "plan_output": output, "plan_length": len(plan), "validation": verdict}
    except TimeoutError as exc: return {"id": label, "status": "timeout", "reason": str(exc)}
    except Exception as exc: return {"id": label, "status": "error", "reason": str(exc)}


def validate_manifest(path):
    base, result = os.path.dirname(os.path.abspath(path)), []
    for entry in entries(path):
        label = entry.get("id") if isinstance(entry, dict) else None
        try:
            if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or not entry[k] for k in ("domain", "problem", "plan_output")):
                raise ValueError("entry requires domain, problem, and plan_output")
            output = resolve(entry["plan_output"], base)
            if not os.path.isfile(output): raise ValueError("required plan output is missing: " + output)
            verdict = validate(Model(resolve(entry["domain"], base), resolve(entry["problem"], base)), read_plan(output))
            result.append({"id": label, "plan_output": output, **verdict})
        except Exception as exc: result.append({"id": label, "valid": False, "reason": str(exc)})
    return {"ok": all(x.get("valid") for x in result), "results": result}


def main(request):
    manifest = os.path.abspath(request.get("manifest", "problem.json"))
    if request.get("mode") == "validate-manifest": return validate_manifest(manifest)
    base, limit = os.path.dirname(manifest), float(request.get("time_limit_sec", 240))
    result = [solve_one(entry, base, limit) for entry in entries(manifest)]
    return {"ok": all(x.get("status") == "solved" for x in result), "results": result}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "error", "reason": str(exc)}))
        sys.exit(2)
