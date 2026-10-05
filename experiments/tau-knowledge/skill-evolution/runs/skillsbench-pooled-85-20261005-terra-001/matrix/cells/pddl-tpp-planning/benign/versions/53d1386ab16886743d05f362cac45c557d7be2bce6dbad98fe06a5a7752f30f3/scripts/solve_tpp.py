#!/usr/bin/env python3
"""Solve every classical typed PDDL task in a JSON manifest.

Input: JSON object on stdin with optional root, problem_json, max_expansions,
and weight fields. Output: JSON status object on stdout. Validated plans are
written to the manifest's plan_output paths as action(arg, arg) lines.
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
        token = tokens[pos]
        pos += 1
        if token == "(":
            out = []
            while pos < len(tokens) and tokens[pos] != ")":
                out.append(one())
            if pos == len(tokens):
                raise PDDLError("unclosed PDDL parenthesis")
            pos += 1
            return out
        if token == ")":
            raise PDDLError("unexpected closing parenthesis")
        return token
    tree = one()
    if pos != len(tokens) or not isinstance(tree, list) or not tree or tree[0] != "define":
        raise PDDLError("expected one PDDL define expression")
    return tree


def sec(tree, name):
    for x in tree[1:]:
        if isinstance(x, list) and x and x[0] == name:
            return x[1:]
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
            pending, i = [], i + 2
        else:
            pending.append(x)
            i += 1
    out.extend((n, "object") for n in pending)
    return out


def atom(x, where):
    if not isinstance(x, list) or not x or not isinstance(x[0], str) or any(isinstance(y, list) for y in x[1:]):
        raise PDDLError("expected atom in " + where)
    return tuple(x)


def literals(x, where, effect=False):
    """Flatten an and/not formula into positive and negative atom lists."""
    if not isinstance(x, list) or not x:
        raise PDDLError("malformed " + where)
    op = x[0]
    if op == "and":
        p, n = [], []
        for child in x[1:]:
            cp, cn = literals(child, where, effect)
            p.extend(cp); n.extend(cn)
        return p, n
    if effect and op in {"increase", "decrease", "assign", "scale-up", "scale-down"}:
        return [], []
    if op == "not":
        if len(x) != 2:
            raise PDDLError("malformed negation in " + where)
        return [], [atom(x[1], where)]
    if op in {"or", "imply", "when", "forall", "exists", "oneof", ">", "<", ">=", "<="}:
        raise PDDLError("unsupported construct " + op + " in " + where)
    return [atom(x, where)], []


def domain(path):
    tree = sexpr(path)
    parents = {"object": None}
    parents.update(dict(typed(sec(tree, ":types") or [])))
    constants = typed(sec(tree, ":constants") or [])
    actions = []
    for item in tree[1:]:
        if not isinstance(item, list) or len(item) < 2 or item[0] != ":action":
            continue
        name, fields, i = item[1], {}, 2
        if not isinstance(name, str):
            raise PDDLError("invalid action name")
        while i < len(item):
            if not isinstance(item[i], str) or not item[i].startswith(":") or i + 1 >= len(item):
                raise PDDLError("malformed action " + name)
            fields[item[i]] = item[i + 1]
            i += 2
        params = typed(fields.get(":parameters", []))
        if any(not v.startswith("?") for v, _ in params):
            raise PDDLError("non-variable action parameter")
        pp, pn = literals(fields.get(":precondition", ["and"]), "precondition")
        add, delete = literals(fields.get(":effect", ["and"]), "effect", True)
        if any(a[0] == "=" for a in add + delete):
            raise PDDLError("equality effects unsupported")
        actions.append((name, params, pp, pn, add, delete))
    if not actions:
        raise PDDLError("domain declares no actions")
    return parents, constants, actions


def problem(path):
    tree = sexpr(path)
    init, goal = sec(tree, ":init"), sec(tree, ":goal")
    if init is None or goal is None or len(goal) != 1:
        raise PDDLError("problem requires :init and one :goal")
    state = set()
    for x in init:
        if isinstance(x, list) and x and x[0] in {"=", "not"}:
            continue
        p, _ = literals(x, "initial state")
        state.update(p)
    gp, gn = literals(goal[0], "goal")
    return typed(sec(tree, ":objects") or []), frozenset(state), gp, gn


def subtype(actual, required, parents):
    seen = set()
    while actual is not None and actual not in seen:
        if actual == required:
            return True
        seen.add(actual)
        actual = parents.get(actual)
    return False


def subst(term, binding):
    return binding[term] if term.startswith("?") else term


def ground(pred, binding):
    return tuple(subst(x, binding) for x in pred)


def holds(pos, neg, state, binding):
    def has(pred):
        if pred[0] == "=":
            if len(pred) != 3:
                raise PDDLError("equality requires two terms")
            return subst(pred[1], binding) == subst(pred[2], binding)
        return ground(pred, binding) in state
    return all(has(p) for p in pos) and all(not has(n) for n in neg)


def effect(state, add, delete, binding):
    return frozenset((set(state) - {ground(x, binding) for x in delete}) | {ground(x, binding) for x in add})


def instances(schema, state, objects, parents):
    name, params, pp, pn, add, delete = schema
    indexed = defaultdict(list)
    for fact in state:
        indexed[fact[0]].append(fact)
    patterns = sorted((p for p in pp if p[0] != "="), key=lambda p: len(indexed[p[0]]))
    partials = [{}]
    for pat in patterns:
        nxt = []
        for b in partials:
            for fact in indexed[pat[0]]:
                if len(fact) != len(pat):
                    continue
                c, good = dict(b), True
                for term, value in zip(pat[1:], fact[1:]):
                    if term.startswith("?"):
                        if term in c and c[term] != value:
                            good = False; break
                        c[term] = value
                    elif term != value:
                        good = False; break
                if good:
                    nxt.append(c)
        partials = nxt
        if not partials:
            return
    choices = []
    for var, req in params:
        vals = [obj for obj, actual in objects.items() if subtype(actual, req, parents)]
        if not vals:
            return
        choices.append((var, vals))
    for part in partials:
        if any(v in part and part[v] not in vals for v, vals in choices):
            continue
        missing = [(v, vals) for v, vals in choices if v not in part]
        products = itertools.product(*(vals for _, vals in missing)) if missing else [()]
        for values in products:
            b = dict(part)
            b.update(zip((v for v, _ in missing), values))
            if holds(pp, pn, state, b):
                yield name, tuple(b[v] for v, _ in params), effect(state, add, delete, b)


def replay(parents, schemas, objects, initial, gp, gn, plan):
    by_name = {s[0]: s for s in schemas}
    state = initial
    for number, (name, args) in enumerate(plan, 1):
        if name not in by_name:
            raise PDDLError("undeclared action at step %d" % number)
        _, params, pp, pn, add, delete = by_name[name]
        if len(args) != len(params):
            raise PDDLError("wrong arity at step %d" % number)
        for arg, (_, req) in zip(args, params):
            if arg not in objects or not subtype(objects[arg], req, parents):
                raise PDDLError("type error at step %d" % number)
        b = dict(zip((v for v, _ in params), args))
        if not holds(pp, pn, state, b):
            raise PDDLError("precondition failure at step %d" % number)
        state = effect(state, add, delete, b)
    if not holds(gp, gn, state, {}):
        raise PDDLError("final state does not satisfy goal")


def solve(parents, constants, schemas, declared, initial, gp, gn, limit, weight):
    objects = dict(constants); objects.update(dict(declared))
    if any(t not in parents for t in objects.values()):
        raise PDDLError("object has undeclared type")
    if holds(gp, gn, initial, {}):
        return [], 0, objects
    def heuristic(state):
        return sum(not holds([p], [], state, {}) for p in gp) + sum(holds([p], [], state, {}) for p in gn)
    serial = itertools.count()
    queue = [(weight * heuristic(initial), 0, next(serial), initial)]
    distance, previous, expanded = {initial: 0}, {}, 0
    while queue:
        _, cost, _, state = heapq.heappop(queue)
        if distance.get(state) != cost:
            continue
        if holds(gp, gn, state, {}):
            plan, cur = [], state
            while cur != initial:
                cur, act = previous[cur]
                plan.append(act)
            plan.reverse()
            replay(parents, schemas, objects, initial, gp, gn, plan)
            return plan, expanded, objects
        expanded += 1
        if expanded > limit:
            raise PDDLError("search expansion limit exceeded (%d)" % limit)
        for schema in schemas:
            for name, args, successor in instances(schema, state, objects, parents):
                nc = cost + 1
                if nc >= distance.get(successor, 10 ** 30):
                    continue
                distance[successor] = nc
                previous[successor] = (state, (name, args))
                heapq.heappush(queue, (nc + weight * heuristic(successor), nc, next(serial), successor))
    raise PDDLError("state space exhausted without a plan")


def resolve(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


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
    out = resolve(root, item["plan_output"])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text("".join("%s(%s)\n" % (name, ", ".join(args)) for name, args in plan), encoding="utf-8")
    tmp.replace(out)
    return {"id": item["id"], "ok": True, "plan_output": str(out), "steps": len(plan), "expanded": expanded}


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
