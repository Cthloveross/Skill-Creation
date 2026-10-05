#!/usr/bin/env python3
"""Solve typed classical PDDL tasks listed in a JSON manifest and write plans."""
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


def parse(text):
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    root, stack = [], []
    current = root
    for token in tokens:
        if token == "(":
            node = []
            current.append(node)
            stack.append(current)
            current = node
        elif token == ")":
            if not stack:
                raise ValueError("unexpected closing parenthesis")
            current = stack.pop()
        else:
            current.append(token)
    if stack or len(root) != 1 or not isinstance(root[0], list):
        raise ValueError("malformed PDDL")
    return root[0]


def typed(items, default="object"):
    result, pending, i = [], [], 0
    while i < len(items):
        x = items[i]
        if x == "-":
            if i + 1 >= len(items) or isinstance(items[i + 1], list):
                raise ValueError("malformed typed-name list")
            result.extend((v, items[i + 1]) for v in pending)
            pending = []
            i += 2
        else:
            if isinstance(x, list):
                raise ValueError("compound types are unsupported")
            pending.append(x)
            i += 1
    result.extend((v, default) for v in pending)
    return result


def section(tree, name):
    for x in tree:
        if isinstance(x, list) and x and x[0] == name:
            return x
    return None


def action_fields(item):
    ans, i = {}, 2
    while i + 1 < len(item):
        if isinstance(item[i], str) and item[i].startswith(":"):
            ans[item[i]] = item[i + 1]
            i += 2
        else:
            i += 1
    return ans


class Model:
    def __init__(self, domain_path, problem_path):
        domain = parse(open(domain_path, encoding="utf-8").read())
        problem = parse(open(problem_path, encoding="utf-8").read())
        if not domain or not problem or domain[0] != "define" or problem[0] != "define":
            raise ValueError("domain and problem must be PDDL define forms")
        self.types = {"object": None}
        self.objects = {}
        self.actions = []
        changed = set()
        ts = section(domain, ":types")
        if ts:
            self.types.update(dict(typed(ts[1:])))
        cs = section(domain, ":constants")
        if cs:
            self.objects.update(dict(typed(cs[1:])))
        for x in domain:
            if not isinstance(x, list) or not x:
                continue
            if x[0] == ":durative-action":
                raise ValueError("durative PDDL is unsupported")
            if x[0] != ":action":
                continue
            if len(x) < 2:
                raise ValueError("unnamed action")
            f = action_fields(x)
            if any(k not in f for k in (":parameters", ":precondition", ":effect")):
                raise ValueError("incomplete action " + x[1])
            params = typed(f[":parameters"])
            rec = (x[1], params, f[":precondition"], f[":effect"])
            self.actions.append(rec)
            self.effect_predicates(rec[3], changed)
        if not self.actions:
            raise ValueError("domain contains no action schemas")
        ob = section(problem, ":objects")
        if ob:
            self.objects.update(dict(typed(ob[1:])))
        self.by_type = collections.defaultdict(list)
        for obj, typ in self.objects.items():
            for ancestor in self.ancestors(typ):
                self.by_type[ancestor].append(obj)
        init = section(problem, ":init")
        goal = section(problem, ":goal")
        if init is None or goal is None or len(goal) != 2:
            raise ValueError("problem needs :init and one :goal expression")
        facts = set()
        for atom in init[1:]:
            if not isinstance(atom, list) or not atom:
                continue
            if atom[0] in NUMERIC:
                raise ValueError("numeric PDDL is unsupported")
            # The public checker uses ordinary closed-world facts and ignores
            # explicit negative init assertions, so use the same semantics.
            if atom[0] not in {"not", "="}:
                facts.add(tuple(atom))
        self.goal = goal[1]
        self.static_heads = {a[0] for a in facts if a[0] not in changed}
        self.fixed = frozenset(a for a in facts if a[0] in self.static_heads)
        self.initial = frozenset(a for a in facts if a[0] not in self.static_heads)

    def ancestors(self, typ):
        seen = set()
        while typ is not None and typ not in seen:
            seen.add(typ)
            yield typ
            typ = self.types.get(typ)

    def effect_predicates(self, expr, out):
        if not isinstance(expr, list) or not expr:
            raise ValueError("malformed action effect")
        op = expr[0]
        if op == "and":
            for child in expr[1:]:
                self.effect_predicates(child, out)
        elif op == "not":
            if len(expr) != 2 or not isinstance(expr[1], list):
                raise ValueError("malformed negative effect")
            out.add(expr[1][0])
        elif op in {"when", "forall"}:
            if len(expr) != 3:
                raise ValueError("malformed conditional/quantified effect")
            self.effect_predicates(expr[2], out)
        elif op in NUMERIC:
            raise ValueError("numeric PDDL is unsupported")
        elif op not in LOGICAL:
            out.add(op)

    def truth(self, expr, state, env=None):
        env = {} if env is None else env
        if not isinstance(expr, list) or not expr:
            raise ValueError("malformed logical formula")
        op = expr[0]
        if op == "and":
            return all(self.truth(x, state, env) for x in expr[1:])
        if op == "or":
            return any(self.truth(x, state, env) for x in expr[1:])
        if op == "not":
            return len(expr) == 2 and not self.truth(expr[1], state, env)
        if op == "imply":
            return len(expr) == 3 and (not self.truth(expr[1], state, env) or self.truth(expr[2], state, env))
        if op == "=":
            return len(expr) == 3 and env.get(expr[1], expr[1]) == env.get(expr[2], expr[2])
        if op in {"forall", "exists"}:
            if len(expr) != 3:
                raise ValueError("malformed quantifier")
            variables = typed(expr[1])
            choices = [self.by_type[t] for _, t in variables]
            values = []
            for assignment in itertools.product(*choices):
                local = dict(env)
                local.update(dict(zip((v for v, _ in variables), assignment)))
                values.append(self.truth(expr[2], state, local))
            return all(values) if op == "forall" else any(values)
        return tuple(env.get(x, x) for x in expr) in state

    def apply(self, effect, dynamic, env):
        state = set(self.fixed | dynamic)
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
                state.discard(tuple(local.get(x, x) for x in expr[1]))
            elif op == "when":
                if len(expr) != 3:
                    raise ValueError("malformed conditional effect")
                if self.truth(expr[1], state, local):
                    walk(expr[2], local)
            elif op == "forall":
                if len(expr) != 3:
                    raise ValueError("malformed quantified effect")
                variables = typed(expr[1])
                for assignment in itertools.product(*[self.by_type[t] for _, t in variables]):
                    scoped = dict(local)
                    scoped.update(dict(zip((v for v, _ in variables), assignment)))
                    walk(expr[2], scoped)
            elif op in NUMERIC:
                raise ValueError("numeric PDDL is unsupported")
            else:
                state.add(tuple(local.get(x, x) for x in expr))
        walk(effect, env)
        return frozenset(x for x in state if x[0] not in self.static_heads)

    def static_atoms(self, expr):
        """Positive static conjuncts, used only to safely restrict grounding."""
        if not isinstance(expr, list) or not expr:
            return []
        if expr[0] == "and":
            answer = []
            for child in expr[1:]:
                answer.extend(self.static_atoms(child))
            return answer
        if expr[0] in self.static_heads:
            return [expr]
        return []

    def ground_actions(self):
        by_head = collections.defaultdict(list)
        for atom in self.fixed:
            by_head[atom[0]].append(atom)
        grounded = []
        for name, params, pre, effect in self.actions:
            names = [v for v, _ in params]
            domains = {v: self.by_type[t] for v, t in params}
            seen = set()
            def finish(env):
                missing = [v for v in names if v not in env]
                if missing:
                    var = min(missing, key=lambda v: len(domains[v]))
                    for obj in domains[var]:
                        nxt = dict(env)
                        nxt[var] = obj
                        finish(nxt)
                    return
                args = tuple(env[v] for v in names)
                if args not in seen:
                    seen.add(args)
                    grounded.append((name, args, dict(env), pre, effect))
            def bind(requirements, env):
                if not requirements:
                    finish(env)
                    return
                atom = requirements[0]
                for fact in by_head[atom[0]]:
                    if len(fact) != len(atom):
                        continue
                    nxt, good = dict(env), True
                    for term, obj in zip(atom[1:], fact[1:]):
                        if isinstance(term, str) and term.startswith("?"):
                            if term not in domains or obj not in domains[term] or (term in nxt and nxt[term] != obj):
                                good = False
                                break
                            nxt[term] = obj
                        elif term != obj:
                            good = False
                            break
                    if good:
                        bind(requirements[1:], nxt)
            bind(self.static_atoms(pre), {})
        return grounded


def positive_goal_atoms(expr):
    if not isinstance(expr, list) or not expr:
        return []
    if expr[0] == "and":
        answer = []
        for child in expr[1:]:
            answer.extend(positive_goal_atoms(child))
        return answer
    return [tuple(expr)] if expr[0] not in LOGICAL else []


def solve(model, seconds):
    if model.truth(model.goal, model.fixed | model.initial):
        return []
    actions = model.ground_actions()
    if not actions:
        return None
    goal_atoms = positive_goal_atoms(model.goal)
    def heuristic(state):
        allfacts = model.fixed | state
        return sum(atom not in allfacts for atom in goal_atoms)
    deadline = time.monotonic() + seconds
    best = {model.initial: 0}
    parent = {model.initial: None}
    serial = 0
    queue = [(heuristic(model.initial), 0, serial, model.initial)]
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
                plan, cursor = [], nxt
                while parent[cursor] is not None:
                    cursor, action = parent[cursor]
                    plan.append(action)
                return list(reversed(plan))
            serial += 1
            heapq.heappush(queue, (new_cost + heuristic(nxt), new_cost, serial, nxt))
    return None


def read_plan(path):
    plan = []
    for lineno, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.split(";", 1)[0].strip().lower()
        if not line:
            continue
        match = re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)", line)
        if match:
            args = tuple(x.strip() for x in match.group(2).split(",") if x.strip())
            if any(not re.fullmatch(r"[a-z0-9_-]+", x) for x in args):
                raise ValueError("invalid plan arguments on line %d" % lineno)
            plan.append((match.group(1), args))
            continue
        match = re.fullmatch(r"\(\s*([a-z0-9_-]+)((?:\s+[a-z0-9_-]+)*)\s*\)", line)
        if not match:
            raise ValueError("invalid plan line %d" % lineno)
        plan.append((match.group(1), tuple(match.group(2).split())))
    return plan


def validate(model, plan):
    schemas = {name: (params, pre, eff) for name, params, pre, eff in model.actions}
    state = model.initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in schemas:
            return {"valid": False, "step": step, "reason": "undeclared action"}
        params, pre, effect = schemas[name]
        if len(params) != len(args):
            return {"valid": False, "step": step, "reason": "wrong arity"}
        env = dict(zip((v for v, _ in params), args))
        for variable, typ in params:
            obj = env[variable]
            if obj not in model.objects or typ not in set(model.ancestors(model.objects[obj])):
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
    for entry in tasks:
        label = entry.get("id") if isinstance(entry, dict) else None
        try:
            if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or not entry[k] for k in ("domain", "problem", "plan_output")):
                raise ValueError("task requires domain, problem, and plan_output")
            def resolve(value):
                return value if os.path.isabs(value) else os.path.join(base, value)
            output = resolve(entry["plan_output"])
            model = Model(resolve(entry["domain"]), resolve(entry["problem"]))
            if checking:
                if not os.path.isfile(output):
                    raise ValueError("required plan output is missing: " + output)
                results.append({"id": label, "plan_output": output, **validate(model, read_plan(output))})
                continue
            plan = solve(model, float(request.get("time_limit_sec", 500)))
            if plan is None:
                results.append({"id": label, "status": "unsolved", "plan_output": output})
                continue
            report = validate(model, plan)
            if not report["valid"]:
                raise ValueError("internal plan replay failed: " + report["reason"])
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
            temporary = output + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                for name, args in plan:
                    handle.write(name + "(" + ",".join(args) + ")\n")
            os.replace(temporary, output)
            results.append({"id": label, "status": "solved", "plan_output": output, "plan_length": len(plan), "validation": report})
        except TimeoutError as exc:
            results.append({"id": label, "status": "timeout", "reason": str(exc)})
        except Exception as exc:
            if checking:
                results.append({"id": label, "valid": False, "reason": str(exc)})
            else:
                results.append({"id": label, "status": "error", "reason": str(exc)})
    ok = all(r.get("valid", False) for r in results) if checking else all(r.get("status") == "solved" for r in results)
    return {"ok": ok, "results": results}


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "error", "reason": str(exc)}, sort_keys=True))
        sys.exit(2)
