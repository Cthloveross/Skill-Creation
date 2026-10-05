#!/usr/bin/env python3
"""Solve typed conjunction-only classical PDDL tasks from a JSON manifest.

Input stdin JSON:
  {"root": "/app", "problem_json": "/app/problem.json",
   "max_expansions": 5000000, "weight": 2}
Output stdout JSON has top-level ok and one status object per manifest entry.
Successful entries are written to their manifest plan_output as action(arg, arg) lines.
"""
import heapq
import itertools
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


class PDDLError(Exception):
    pass


def sexpr(path):
    text = Path(path).read_text(encoding="utf-8")
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())
    pos = 0
    def one():
        nonlocal pos
        if pos >= len(tokens):
            raise PDDLError("unexpected end of PDDL")
        x = tokens[pos]
        pos += 1
        if x == "(":
            out = []
            while pos < len(tokens) and tokens[pos] != ")":
                out.append(one())
            if pos >= len(tokens):
                raise PDDLError("unclosed PDDL parenthesis")
            pos += 1
            return out
        if x == ")":
            raise PDDLError("unexpected closing parenthesis")
        return x
    tree = one()
    if pos != len(tokens) or not isinstance(tree, list) or not tree or tree[0] != "define":
        raise PDDLError("expected exactly one PDDL define form")
    return tree


def section(tree, name):
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] == name:
            return item[1:]
    return None


def typed(items):
    out, pending, i = [], [], 0
    while i < len(items):
        x = items[i]
        if not isinstance(x, str):
            raise PDDLError("malformed typed-name list")
        if x == "-":
            if not pending or i + 1 >= len(items) or not isinstance(items[i + 1], str):
                raise PDDLError("malformed typed-name list")
            out.extend((n, items[i + 1]) for n in pending)
            pending = []
            i += 2
        else:
            pending.append(x)
            i += 1
    out.extend((n, "object") for n in pending)
    return out


def atom(x, where):
    if not isinstance(x, list) or not x or not isinstance(x[0], str) or any(isinstance(y, list) for y in x[1:]):
        raise PDDLError("expected atomic formula in " + where)
    return tuple(x)


def literals(x, where, effects=False):
    """Convert an and/not-only formula to (positive atoms, negative atoms)."""
    if not isinstance(x, list) or not x:
        raise PDDLError("malformed " + where)
    op = x[0]
    if op == "and":
        p, n = [], []
        for child in x[1:]:
            cp, cn = literals(child, where, effects)
            p.extend(cp); n.extend(cn)
        return p, n
    if effects and op in {"increase", "decrease", "assign", "scale-up", "scale-down"}:
        # The supplied evaluator treats numeric bookkeeping as non-propositional.
        return [], []
    if op == "not":
        if len(x) != 2:
            raise PDDLError("malformed negation in " + where)
        return [], [atom(x[1], where)]
    if op in {"or", "imply", "when", "forall", "exists", "oneof", ">", "<", ">=", "<="}:
        raise PDDLError("unsupported logical construct " + op + " in " + where)
    return [atom(x, where)], []


def domain(path):
    tree = sexpr(path)
    parents = {"object": None}
    parents.update(dict(typed(section(tree, ":types") or [])))
    constants = typed(section(tree, ":constants") or [])
    actions = []
    for item in tree[1:]:
        if not (isinstance(item, list) and len(item) >= 2 and item[0] == ":action"):
            continue
        name = item[1]
        if not isinstance(name, str):
            raise PDDLError("invalid action name")
        fields, i = {}, 2
        while i < len(item):
            if not isinstance(item[i], str) or not item[i].startswith(":") or i + 1 >= len(item):
                raise PDDLError("malformed action " + name)
            fields[item[i]] = item[i + 1]
            i += 2
        params = typed(fields.get(":parameters", []))
        if any(not v.startswith("?") for v, _ in params):
            raise PDDLError("non-variable action parameter in " + name)
        pp, pn = literals(fields.get(":precondition", ["and"]), "precondition")
        add, delete = literals(fields.get(":effect", ["and"]), "effect", True)
        if any(a[0] == "=" for a in add + delete):
            raise PDDLError("equality effects are unsupported")
        actions.append((name, params, pp, pn, add, delete))
    if not actions:
        raise PDDLError("domain declares no actions")
    return parents, constants, actions


def problem(path):
    tree = sexpr(path)
    init_raw, goal_raw = section(tree, ":init"), section(tree, ":goal")
    if init_raw is None or goal_raw is None or len(goal_raw) != 1:
        raise PDDLError("problem requires init and one goal formula")
    state = set()
    for item in init_raw:
        if isinstance(item, list) and item and item[0] == "=":
            continue
        pos, neg = literals(item, "initial state")
        # Classical closed-world semantics makes explicit negative init facts
        # redundant for the propositional state representation.
        state.update(pos)
    gp, gn = literals(goal_raw[0], "goal")
    return typed(section(tree, ":objects") or []), frozenset(state), gp, gn


def subtype(actual, required, parents):
    seen = set()
    while actual is not None and actual not in seen:
        if actual == required:
            return True
        seen.add(actual)
        actual = parents.get(actual)
    return False


def value(x, binding):
    return binding[x] if x.startswith("?") else x


def ground(a, binding):
    return tuple(value(x, binding) for x in a)


def holds(pos, neg, state, binding):
    def has(a):
        if a[0] == "=":
            if len(a) != 3:
                raise PDDLError("equality needs two terms")
            return value(a[1], binding) == value(a[2], binding)
        return ground(a, binding) in state
    return all(has(a) for a in pos) and all(not has(a) for a in neg)


def effect(state, add, delete, binding):
    return frozenset((set(state) - {ground(a, binding) for a in delete}) |
                     {ground(a, binding) for a in add})


def instances(schema, state, objects, parents):
    name, params, pp, pn, add, delete = schema
    by_pred = defaultdict(list)
    for fact in state:
        by_pred[fact[0]].append(fact)
    patterns = sorted((a for a in pp if a[0] != "="), key=lambda a: len(by_pred[a[0]]))
    partial = [{}]
    for pattern in patterns:
        nxt = []
        for bind in partial:
            for fact in by_pred[pattern[0]]:
                if len(fact) != len(pattern):
                    continue
                candidate, valid = dict(bind), True
                for sym, actual in zip(pattern[1:], fact[1:]):
                    if sym.startswith("?"):
                        if sym in candidate and candidate[sym] != actual:
                            valid = False; break
                        candidate[sym] = actual
                    elif sym != actual:
                        valid = False; break
                if valid:
                    nxt.append(candidate)
        partial = nxt
        if not partial:
            return
    choices = []
    for var, typ in params:
        vals = [obj for obj, actual in objects.items() if subtype(actual, typ, parents)]
        if not vals:
            return
        choices.append((var, vals))
    for partial_binding in partial:
        if any(v in partial_binding and partial_binding[v] not in vals for v, vals in choices):
            continue
        missing = [(v, vals) for v, vals in choices if v not in partial_binding]
        products = itertools.product(*(vals for _, vals in missing)) if missing else [()]
        for vals in products:
            bind = dict(partial_binding)
            bind.update(zip((v for v, _ in missing), vals))
            if holds(pp, pn, state, bind):
                args = tuple(bind[v] for v, _ in params)
                yield name, args, effect(state, add, delete, bind)


def replay(parents, schemas, objects, initial, gp, gn, plan):
    table, state = {a[0]: a for a in schemas}, initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in table:
            raise PDDLError("undeclared action at step %d" % step)
        _, params, pp, pn, add, delete = table[name]
        if len(params) != len(args):
            raise PDDLError("incorrect action arity at step %d" % step)
        for arg, (_, required) in zip(args, params):
            if arg not in objects or not subtype(objects[arg], required, parents):
                raise PDDLError("type error at step %d" % step)
        bind = dict(zip((v for v, _ in params), args))
        if not holds(pp, pn, state, bind):
            raise PDDLError("precondition failure at step %d" % step)
        state = effect(state, add, delete, bind)
    if not holds(gp, gn, state, {}):
        raise PDDLError("final state does not satisfy goal")


def solve(parents, constants, schemas, declared, initial, gp, gn, limit, weight):
    objects = dict(constants)
    objects.update(dict(declared))
    if any(t not in parents for t in objects.values()):
        raise PDDLError("object has undeclared type")
    if holds(gp, gn, initial, {}):
        return [], 0, objects
    def heuristic(state):
        return sum(not holds([a], [], state, {}) for a in gp) + sum(holds([a], [], state, {}) for a in gn)
    counter = itertools.count()
    queue = [(weight * heuristic(initial), 0, next(counter), initial)]
    dist, prior, expanded = {initial: 0}, {}, 0
    while queue:
        _, cost, _, state = heapq.heappop(queue)
        if dist.get(state) != cost:
            continue
        if holds(gp, gn, state, {}):
            plan, cur = [], state
            while cur != initial:
                cur, action = prior[cur]
                plan.append(action)
            plan.reverse()
            replay(parents, schemas, objects, initial, gp, gn, plan)
            return plan, expanded, objects
        expanded += 1
        if expanded > limit:
            raise PDDLError("search expansion limit exceeded (%d)" % limit)
        for schema in schemas:
            for name, args, nxt in instances(schema, state, objects, parents):
                nc = cost + 1
                if nc >= dist.get(nxt, 10 ** 30):
                    continue
                dist[nxt] = nc
                prior[nxt] = (state, (name, args))
                heapq.heappush(queue, (nc + weight * heuristic(nxt), nc, next(counter), nxt))
    raise PDDLError("state space exhausted without a plan")


def resolve(root, name):
    p = Path(name)
    return p if p.is_absolute() else root / p


def entry(item, root, limit, weight):
    if not isinstance(item, dict):
        raise PDDLError("manifest entry is not an object")
    for key in ("id", "domain", "problem", "plan_output"):
        if not isinstance(item.get(key), str):
            raise PDDLError("manifest entry lacks string " + key)
    parents, constants, schemas = domain(resolve(root, item["domain"]))
    declared, initial, gp, gn = problem(resolve(root, item["problem"]))
    plan, expanded, objects = solve(parents, constants, schemas, declared, initial, gp, gn, limit, weight)
    replay(parents, schemas, objects, initial, gp, gn, plan)
    target = resolve(root, item["plan_output"])
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text("".join("%s(%s)\n" % (n, ", ".join(args)) for n, args in plan), encoding="utf-8")
    temp.replace(target)
    return {"id": item["id"], "ok": True, "plan_output": str(target), "steps": len(plan), "expanded": expanded}


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise PDDLError("request must be a JSON object")
        root = Path(request.get("root", "/app"))
        manifest_path = resolve(root, request.get("problem_json", str(root / "problem.json")))
        limit, weight = request.get("max_expansions", 5000000), request.get("weight", 2)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise PDDLError("max_expansions must be a positive integer")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0:
            raise PDDLError("weight must be positive")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, list) or not manifest:
            raise PDDLError("problem.json must be a nonempty array")
        results = []
        for item in manifest:
            try:
                results.append(entry(item, root, limit, weight))
            except Exception as exc:
                ident = item.get("id", "<unknown>") if isinstance(item, dict) else "<unknown>"
                results.append({"id": ident, "ok": False, "error": str(exc)})
        print(json.dumps({"ok": all(r["ok"] for r in results), "results": results}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "results": []}, sort_keys=True))


if __name__ == "__main__":
    main()
