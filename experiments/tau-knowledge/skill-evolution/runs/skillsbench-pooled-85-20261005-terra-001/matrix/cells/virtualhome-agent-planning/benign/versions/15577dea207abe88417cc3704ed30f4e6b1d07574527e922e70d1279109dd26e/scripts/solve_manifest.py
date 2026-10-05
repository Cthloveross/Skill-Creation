#!/usr/bin/env python3
"""Manifest-driven sound planner for small typed classical PDDL instances.
Reads JSON stdin and emits a JSON status object.  In solve mode it writes each
manifest plan_output only after independently replaying the whole plan.
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
LOGICAL = {"and", "or", "not", "imply", "=", "forall", "exists", "when"} | NUMERIC


def parse_sexpr(text):
    toks = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    root, stack = [], []
    cur = root
    for tok in toks:
        if tok == "(":
            child = []
            cur.append(child)
            stack.append(cur)
            cur = child
        elif tok == ")":
            if not stack:
                raise ValueError("unexpected closing parenthesis")
            cur = stack.pop()
        else:
            cur.append(tok)
    if stack or len(root) != 1 or not isinstance(root[0], list):
        raise ValueError("malformed PDDL S-expression")
    return root[0]


def typed_names(items, default="object"):
    result, pending, i = [], [], 0
    while i < len(items):
        value = items[i]
        if value == "-":
            if i + 1 >= len(items) or isinstance(items[i + 1], list):
                raise ValueError("malformed typed name list")
            result.extend((x, items[i + 1]) for x in pending)
            pending = []
            i += 2
        else:
            if isinstance(value, list):
                raise ValueError("compound types are unsupported")
            pending.append(value)
            i += 1
    result.extend((x, default) for x in pending)
    return result


def section(tree, name):
    return next((x for x in tree if isinstance(x, list) and x and x[0] == name), None)


def action_fields(node):
    fields, i = {}, 2
    while i + 1 < len(node):
        if isinstance(node[i], str) and node[i].startswith(":"):
            fields[node[i]] = node[i + 1]
            i += 2
        else:
            i += 1
    return fields


class Model:
    def __init__(self, domain_file, problem_file):
        domain = parse_sexpr(open(domain_file, encoding="utf-8").read())
        problem = parse_sexpr(open(problem_file, encoding="utf-8").read())
        if not domain or not problem or domain[0] != "define" or problem[0] != "define":
            raise ValueError("domain and problem must be PDDL define forms")
        if any(isinstance(x, list) and x and x[0] == ":durative-action" for x in domain):
            raise ValueError("durative PDDL is unsupported")

        self.parents = {"object": None}
        ts = section(domain, ":types")
        if ts:
            self.parents.update(dict(typed_names(ts[1:])))
        self.objects = {}
        os_ = section(problem, ":objects")
        if os_:
            self.objects.update(dict(typed_names(os_[1:])))
        self.by_type = collections.defaultdict(list)
        for obj, typ in self.objects.items():
            for parent in self.ancestors(typ):
                self.by_type[parent].append(obj)

        self.actions = []
        changed_heads = set()
        for node in domain:
            if not (isinstance(node, list) and node and node[0] == ":action"):
                continue
            if len(node) < 2:
                raise ValueError("action lacks a name")
            fields = action_fields(node)
            if any(k not in fields for k in (":parameters", ":precondition", ":effect")):
                raise ValueError("action %s is incomplete" % node[1])
            record = (node[1], typed_names(fields[":parameters"]), fields[":precondition"], fields[":effect"])
            self.actions.append(record)
            self.collect_effect_heads(record[3], changed_heads)
        if not self.actions:
            raise ValueError("domain declares no action schemas")

        init, goal = section(problem, ":init"), section(problem, ":goal")
        if init is None or goal is None or len(goal) != 2:
            raise ValueError("problem lacks a well-formed init or goal")
        all_init = set()
        for atom in init[1:]:
            if not isinstance(atom, list) or not atom:
                continue
            if atom[0] in NUMERIC or atom[0] == "=":
                raise ValueError("numeric PDDL is unsupported")
            if atom[0] != "not":
                all_init.add(tuple(atom))
        self.static_heads = {a[0] for a in all_init if a[0] not in changed_heads}
        self.fixed = frozenset(a for a in all_init if a[0] in self.static_heads)
        self.initial = frozenset(a for a in all_init if a[0] not in self.static_heads)
        self.goal = goal[1]

    def ancestors(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ)
            yield typ
            typ = self.parents.get(typ)

    def collect_effect_heads(self, expr, result):
        if not isinstance(expr, list) or not expr:
            raise ValueError("malformed action effect")
        op = expr[0]
        if op == "and":
            for x in expr[1:]:
                self.collect_effect_heads(x, result)
        elif op == "not":
            if len(expr) != 2 or not isinstance(expr[1], list) or not expr[1]:
                raise ValueError("malformed negative effect")
            result.add(expr[1][0])
        elif op == "when":
            if len(expr) != 3:
                raise ValueError("malformed conditional effect")
            self.collect_effect_heads(expr[2], result)
        elif op == "forall":
            if len(expr) != 3:
                raise ValueError("malformed quantified effect")
            self.collect_effect_heads(expr[2], result)
        elif op in NUMERIC:
            raise ValueError("numeric PDDL is unsupported")
        elif op not in LOGICAL:
            result.add(op)

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
            vs = typed_names(expr[1])
            values = []
            for assignment in itertools.product(*[self.by_type[t] for _, t in vs]):
                local = dict(env)
                local.update(dict(zip((v for v, _ in vs), assignment)))
                values.append(self.formula(expr[2], state, local))
            return all(values) if op == "forall" else any(values)
        return tuple(env.get(x, x) for x in expr) in state

    def apply(self, effect, dynamic, env):
        full = set(self.fixed | dynamic)
        def walk(expr, scope):
            if not isinstance(expr, list) or not expr:
                raise ValueError("malformed effect")
            op = expr[0]
            if op == "and":
                for child in expr[1:]:
                    walk(child, scope)
            elif op == "not":
                if len(expr) != 2 or not isinstance(expr[1], list):
                    raise ValueError("malformed negative effect")
                full.discard(tuple(scope.get(x, x) for x in expr[1]))
            elif op == "when":
                if len(expr) != 3:
                    raise ValueError("malformed conditional effect")
                if self.formula(expr[1], full, scope):
                    walk(expr[2], scope)
            elif op == "forall":
                if len(expr) != 3:
                    raise ValueError("malformed quantified effect")
                vs = typed_names(expr[1])
                for assignment in itertools.product(*[self.by_type[t] for _, t in vs]):
                    local = dict(scope)
                    local.update(dict(zip((v for v, _ in vs), assignment)))
                    walk(expr[2], local)
            elif op in NUMERIC:
                raise ValueError("numeric PDDL is unsupported")
            else:
                full.add(tuple(scope.get(x, x) for x in expr))
        walk(effect, env)
        return frozenset(fact for fact in full if fact[0] not in self.static_heads)

    def static_atoms(self, expr):
        if not isinstance(expr, list) or not expr:
            return []
        if expr[0] == "and":
            out = []
            for x in expr[1:]:
                out.extend(self.static_atoms(x))
            return out
        return [expr] if expr[0] in self.static_heads else []

    def grounded_actions(self):
        fixed_by_pred = collections.defaultdict(list)
        for fact in self.fixed:
            fixed_by_pred[fact[0]].append(fact)
        answer = []
        for name, parameters, precondition, effect in self.actions:
            names = [v for v, _ in parameters]
            allowed = {v: self.by_type[t] for v, t in parameters}
            constraints = self.static_atoms(precondition)

            def finish(env):
                missing = [v for v in names if v not in env]
                if missing:
                    var = min(missing, key=lambda x: len(allowed[x]))
                    for value in allowed[var]:
                        nxt = dict(env)
                        nxt[var] = value
                        finish(nxt)
                else:
                    answer.append((name, tuple(env[v] for v in names), dict(env), precondition, effect))

            def bind(index, env):
                if index == len(constraints):
                    finish(env)
                    return
                atom = constraints[index]
                # A static atom is a positive predicate atom; all other ADL
                # forms remain checked by formula after ordinary grounding.
                if not isinstance(atom, list) or not atom or atom[0] not in fixed_by_pred:
                    return
                for fact in fixed_by_pred[atom[0]]:
                    if len(fact) != len(atom):
                        continue
                    nxt, ok = dict(env), True
                    for term, value in zip(atom[1:], fact[1:]):
                        if isinstance(term, str) and term.startswith("?"):
                            if term not in allowed or value not in allowed[term] or (term in nxt and nxt[term] != value):
                                ok = False
                                break
                            nxt[term] = value
                        elif term != value:
                            ok = False
                            break
                    if ok:
                        bind(index + 1, nxt)
            bind(0, {})
        return answer


def positive_goal_atoms(expr):
    if not isinstance(expr, list) or not expr:
        return []
    if expr[0] == "and":
        out = []
        for x in expr[1:]:
            out.extend(positive_goal_atoms(x))
        return out
    return [tuple(expr)] if expr[0] not in LOGICAL else []


def solve(model, seconds):
    full_initial = model.fixed | model.initial
    if model.formula(model.goal, full_initial):
        return []
    actions = model.grounded_actions()
    if not actions:
        return None
    wanted = positive_goal_atoms(model.goal)
    def heuristic(state):
        return sum(atom not in model.fixed and atom not in state for atom in wanted)
    best = {model.initial: 0}
    parents = {model.initial: None}
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
            if not model.formula(pre, model.fixed | state, env):
                continue
            nxt = model.apply(effect, state, env)
            newcost = cost + 1
            if nxt == state or newcost >= best.get(nxt, 10 ** 18):
                continue
            best[nxt] = newcost
            parents[nxt] = (state, (name, args))
            if model.formula(model.goal, model.fixed | nxt):
                plan, cur = [], nxt
                while parents[cur] is not None:
                    cur, action = parents[cur]
                    plan.append(action)
                return list(reversed(plan))
            serial += 1
            heapq.heappush(queue, (newcost + heuristic(nxt), newcost, serial, nxt))
    return None


def parse_plan(path):
    plan = []
    for lineno, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.split(";", 1)[0].strip().lower()
        if not line:
            continue
        comma = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
        if comma:
            args = tuple(x.strip() for x in comma.group(2).split(",") if x.strip())
            if any(not re.fullmatch(r"[a-z0-9_-]+", x) for x in args):
                raise ValueError("invalid argument on plan line %d" % lineno)
            plan.append((comma.group(1), args))
            continue
        standard = re.fullmatch(r"\(\s*([a-z0-9_-]+)((?:\s+[a-z0-9_-]+)*)\s*\)", line)
        if not standard:
            raise ValueError("invalid plan line %d" % lineno)
        plan.append((standard.group(1), tuple(standard.group(2).split())))
    return plan


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
        for var, typ in params:
            actual = model.objects.get(env[var])
            if actual is None or typ not in set(model.ancestors(actual)):
                return {"valid": False, "step": step, "reason": "ill-typed object"}
        if not model.formula(pre, model.fixed | state, env):
            return {"valid": False, "step": step, "reason": "unsatisfied precondition"}
        state = model.apply(effect, state, env)
    if not model.formula(model.goal, model.fixed | state):
        return {"valid": False, "steps": len(plan), "reason": "goal not satisfied"}
    return {"valid": True, "steps": len(plan)}


def entries(manifest_path):
    data = json.load(open(manifest_path, encoding="utf-8"))
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
    tasks = entries(manifest)
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
            replay = validate(model, plan)
            if not replay["valid"]:
                raise ValueError("internal plan replay failed: " + replay["reason"])
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
            temporary = output + ".tmp"
            with open(temporary, "w", encoding="utf-8") as f:
                for name, args in plan:
                    f.write(name + "(" + ",".join(args) + ")\n")
            os.replace(temporary, output)
            if not os.path.isfile(output):
                raise ValueError("failed to create declared plan output")
            results.append({"id": label, "status": "solved", "plan_output": output, "plan_length": len(plan), "validation": replay})
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
