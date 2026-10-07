#!/usr/bin/env python3
"""Runtime PDDL STRIPS batch planner.

Reads one JSON request from stdin and emits one JSON report to stdout.  It uses
only the Python standard library and writes plan files only after replay.
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


def tokenize(text):
    text = re.sub(r";[^\n]*", "", text)
    return re.findall(r"\(|\)|[^\s()]+", text)


def sexpr(text):
    toks = tokenize(text)
    pos = 0

    def one():
        nonlocal pos
        if pos >= len(toks):
            raise PDDLError("unexpected end of PDDL")
        tok = toks[pos]
        pos += 1
        if tok == "(":
            out = []
            while True:
                if pos >= len(toks):
                    raise PDDLError("unclosed parenthesis")
                if toks[pos] == ")":
                    pos += 1
                    return out
                out.append(one())
        if tok == ")":
            raise PDDLError("unexpected close parenthesis")
        return tok

    root = one()
    if pos != len(toks):
        raise PDDLError("multiple top-level PDDL expressions")
    if not isinstance(root, list) or not root or root[0].lower() != "define":
        raise PDDLError("expected (define ...) PDDL expression")
    return root


def key(x):
    return x.lower() if isinstance(x, str) else x


def section(root, marker):
    marker = marker.lower()
    for x in root[1:]:
        if isinstance(x, list) and x and isinstance(x[0], str) and x[0].lower() == marker:
            return x
    return None


def typed_items(tokens, default="object"):
    """Return (name,type) pairs from PDDL's grouped typed-list syntax."""
    result, pending = [], []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if isinstance(t, list):
            raise PDDLError("unexpected list in typed declaration")
        if t == "-":
            if not pending or i + 1 >= len(tokens) or not isinstance(tokens[i + 1], str):
                raise PDDLError("malformed typed declaration")
            typ = tokens[i + 1]
            result.extend((n, typ) for n in pending)
            pending = []
            i += 2
        else:
            pending.append(t)
            i += 1
    result.extend((n, default) for n in pending)
    return result


def atom(x):
    if not isinstance(x, list) or not x or not isinstance(x[0], str):
        raise PDDLError("expected an atomic predicate")
    if any(isinstance(t, list) for t in x[1:]):
        raise PDDLError("function terms are unsupported")
    return tuple(x)


def literals(expr, where):
    """Flatten a conjunction into positive and negative predicate tuples."""
    if not isinstance(expr, list) or not expr:
        raise PDDLError("empty %s" % where)
    op = expr[0].lower() if isinstance(expr[0], str) else ""
    if op == "and":
        pos, neg = [], []
        for child in expr[1:]:
            a, b = literals(child, where)
            pos.extend(a)
            neg.extend(b)
        return pos, neg
    if op == "not":
        if len(expr) != 2:
            raise PDDLError("malformed negation in %s" % where)
        inner = atom(expr[1])
        if inner[0].lower() in {"and", "or", "not"}:
            raise PDDLError("non-atomic negation in %s" % where)
        return [], [inner]
    if op in {"or", "forall", "exists", "imply", "when", "increase", "decrease", "assign", "scale-up", "scale-down"}:
        raise PDDLError("unsupported %s construct in %s" % (op, where))
    a = atom(expr)
    if a[0] in {"=", ">", "<", ">=", "<="} and a[0] != "=":
        raise PDDLError("numeric/comparison expression unsupported in %s" % where)
    return [a], []


def properties(parts, start):
    out = {}
    i = start
    while i < len(parts):
        label = parts[i]
        if not isinstance(label, str) or not label.startswith(":") or i + 1 >= len(parts):
            raise PDDLError("malformed action declaration")
        out[label.lower()] = parts[i + 1]
        i += 2
    return out


def parse_domain(path):
    root = sexpr(Path(path).read_text(encoding="utf-8"))
    typ = {"object": None}
    ts = section(root, ":types")
    if ts:
        for name, parent in typed_items(ts[1:]):
            typ[name] = parent
    constants = []
    cs = section(root, ":constants")
    if cs:
        constants = typed_items(cs[1:])
    actions = []
    for item in root[1:]:
        if not (isinstance(item, list) and item and isinstance(item[0], str) and item[0].lower() == ":action"):
            continue
        if len(item) < 2:
            raise PDDLError("action missing name")
        name = item[1]
        props = properties(item, 2)
        if ":parameters" not in props:
            raise PDDLError("action %s has no parameters" % name)
        pars = props[":parameters"]
        if not isinstance(pars, list):
            raise PDDLError("malformed parameters for %s" % name)
        params = typed_items(pars)
        if any(not n.startswith("?") for n, _ in params):
            raise PDDLError("action %s has non-variable parameter" % name)
        pre = props.get(":precondition", ["and"])
        eff = props.get(":effect", ["and"])
        pp, pn = literals(pre, "precondition of " + name)
        ap, dn = literals(eff, "effect of " + name)
        if any(a[0] == "=" for a in ap + dn):
            raise PDDLError("equality cannot be an effect")
        actions.append({"name": name, "params": params, "pos": pp, "neg": pn,
                        "add": ap, "delete": dn})
    if not actions:
        raise PDDLError("domain declares no actions")
    return {"types": typ, "constants": constants, "actions": actions}


def parse_problem(path):
    root = sexpr(Path(path).read_text(encoding="utf-8"))
    os = section(root, ":objects")
    objects = typed_items(os[1:]) if os else []
    initsec = section(root, ":init")
    if initsec is None:
        raise PDDLError("problem has no :init")
    initial = set()
    for item in initsec[1:]:
        p, n = literals(item, "initial state")
        if n:
            # Closed-world PDDL normally has no negative init facts; accepting
            # these makes the state interpretation explicit without adding facts.
            if p:
                raise PDDLError("malformed initial literal")
        for a in p:
            if a[0] == "=":
                raise PDDLError("numeric initial fluent unsupported")
            initial.add(a)
    gs = section(root, ":goal")
    if gs is None or len(gs) != 2:
        raise PDDLError("problem has malformed or missing :goal")
    gp, gn = literals(gs[1], "goal")
    return {"objects": objects, "initial": frozenset(initial), "goal_pos": gp, "goal_neg": gn}


def is_subtype(actual, wanted, parents):
    seen = set()
    while actual is not None and actual not in seen:
        if actual == wanted:
            return True
        seen.add(actual)
        actual = parents.get(actual)
    return False


def ground(a, env):
    return tuple(env.get(t, t) if isinstance(t, str) and t.startswith("?") else t for t in a)


def equality_holds(a, env):
    if len(a) != 3:
        raise PDDLError("equality must have two terms")
    return ground(("_", a[1], a[2]), env)[1] == ground(("_", a[1], a[2]), env)[2]


def holds_literals(pos, neg, state, env):
    for a in pos:
        if a[0] == "=":
            if not equality_holds(a, env):
                return False
        elif ground(a, env) not in state:
            return False
    for a in neg:
        if a[0] == "=":
            if equality_holds(a, env):
                return False
        elif ground(a, env) in state:
            return False
    return True


def applicable(schema, state, object_types, parents):
    """Yield (action-name,args,new-state) for schema instances applicable now."""
    by_pred = defaultdict(list)
    for f in state:
        by_pred[f[0]].append(f)
    matchers = [p for p in schema["pos"] if p[0] != "="]
    # Matching the smallest current relation first dramatically reduces candidate
    # bindings while remaining complete.
    matchers.sort(key=lambda p: len(by_pred.get(p[0], ())))
    envs = [{}]
    for pattern in matchers:
        facts = by_pred.get(pattern[0], ())
        if not facts:
            return
        nxt = []
        for env in envs:
            for f in facts:
                if len(f) != len(pattern):
                    continue
                e = dict(env)
                good = True
                for term, value in zip(pattern[1:], f[1:]):
                    if isinstance(term, str) and term.startswith("?"):
                        old = e.get(term)
                        if old is not None and old != value:
                            good = False
                            break
                        e[term] = value
                    elif term != value:
                        good = False
                        break
                if good:
                    nxt.append(e)
        envs = nxt
        if not envs:
            return
    choices = []
    for var, wanted in schema["params"]:
        choices.append((var, [o for o, actual in object_types.items()
                              if is_subtype(actual, wanted, parents)]))
    for base in envs:
        missing = [(v, vals) for v, vals in choices if v not in base]
        if any(not vals for _, vals in missing):
            continue
        products = itertools.product(*(vals for _, vals in missing)) if missing else [()]
        for values in products:
            env = dict(base)
            env.update({v: x for (v, _), x in zip(missing, values)})
            if not holds_literals(schema["pos"], schema["neg"], state, env):
                continue
            deletes = {ground(x, env) for x in schema["delete"]}
            adds = {ground(x, env) for x in schema["add"]}
            newstate = frozenset((set(state) - deletes) | adds)
            args = tuple(env[v] for v, _ in schema["params"])
            yield schema["name"], args, newstate


def goal_holds(problem, state):
    return holds_literals(problem["goal_pos"], problem["goal_neg"], state, {})


def heuristic(problem, state):
    missing = sum(1 for a in problem["goal_pos"] if a[0] != "=" and a not in state)
    missing += sum(1 for a in problem["goal_neg"] if a[0] != "=" and a in state)
    # Ground equalities in goals have no variables in normal PDDL problems.
    missing += sum(1 for a in problem["goal_pos"] if a[0] == "=" and not equality_holds(a, {}))
    missing += sum(1 for a in problem["goal_neg"] if a[0] == "=" and equality_holds(a, {}))
    return missing


def replay(domain, problem, plan, object_types):
    actions = {a["name"]: a for a in domain["actions"]}
    state = problem["initial"]
    for step, (name, args) in enumerate(plan, 1):
        schema = actions.get(name)
        if schema is None:
            raise PDDLError("step %d: unknown action %s" % (step, name))
        if len(args) != len(schema["params"]):
            raise PDDLError("step %d: wrong arity for %s" % (step, name))
        env = {}
        for (var, wanted), value in zip(schema["params"], args):
            actual = object_types.get(value)
            if actual is None or not is_subtype(actual, wanted, domain["types"]):
                raise PDDLError("step %d: argument %s has incompatible type" % (step, value))
            env[var] = value
        if not holds_literals(schema["pos"], schema["neg"], state, env):
            raise PDDLError("step %d: precondition fails for %s" % (step, name))
        state = frozenset((set(state) - {ground(x, env) for x in schema["delete"]}) |
                          {ground(x, env) for x in schema["add"]})
    if not goal_holds(problem, state):
        raise PDDLError("final state does not satisfy goal")
    return state


def solve(domain, problem, limit, weight):
    object_types = {}
    for n, t in domain["constants"] + problem["objects"]:
        if n in object_types and object_types[n] != t:
            raise PDDLError("object declared with conflicting types: " + n)
        object_types[n] = t
    for _, t in object_types.items():
        if t not in domain["types"]:
            raise PDDLError("undeclared object type: " + t)
    start = problem["initial"]
    if goal_holds(problem, start):
        return [], 0, object_types
    queue, counter = [], itertools.count()
    best = {start: 0}
    parent = {}
    h = heuristic(problem, start)
    heapq.heappush(queue, (weight * h, h, 0, next(counter), start))
    expanded = 0
    while queue:
        _, _, g, _, state = heapq.heappop(queue)
        if g != best.get(state):
            continue
        if goal_holds(problem, state):
            result = []
            cur = state
            while cur != start:
                prev, act = parent[cur]
                result.append(act)
                cur = prev
            result.reverse()
            replay(domain, problem, result, object_types)
            return result, expanded, object_types
        expanded += 1
        if expanded > limit:
            raise PDDLError("search expansion limit exceeded (%d)" % limit)
        for schema in domain["actions"]:
            for name, args, nxt in applicable(schema, state, object_types, domain["types"]):
                ng = g + 1
                if ng >= best.get(nxt, 10 ** 30):
                    continue
                best[nxt] = ng
                parent[nxt] = (state, (name, args))
                nh = heuristic(problem, nxt)
                heapq.heappush(queue, (ng + weight * nh, nh, ng, next(counter), nxt))
    raise PDDLError("state space exhausted without a plan")


def resolve(root, value):
    p = Path(value)
    return p if p.is_absolute() else root / p


def solve_one(entry, root, limit, weight):
    required = ["id", "domain", "problem", "plan_output"]
    absent = [x for x in required if x not in entry]
    if absent:
        raise PDDLError("manifest entry missing " + ", ".join(absent))
    domain = parse_domain(resolve(root, entry["domain"]))
    problem = parse_problem(resolve(root, entry["problem"]))
    plan, expanded, _ = solve(domain, problem, limit, weight)
    output = resolve(root, entry["plan_output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join("%s(%s)" % (name, ", ".join(args)) for name, args in plan)
    output.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return {"id": entry["id"], "ok": True, "plan_output": str(output),
            "steps": len(plan), "expanded": expanded}


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise PDDLError("request must be a JSON object")
        root = Path(request.get("root", "/app"))
        manifest_path = resolve(root, request.get("problem_json", str(root / "problem.json")))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, list):
            raise PDDLError("problem.json must contain an array")
        limit = request.get("max_expansions", 1000000)
        weight = request.get("weight", 3)
        if not isinstance(limit, int) or limit <= 0:
            raise PDDLError("max_expansions must be a positive integer")
        if not isinstance(weight, (int, float)) or weight <= 0:
            raise PDDLError("weight must be positive")
        selected = request.get("ids")
        if selected is not None:
            if not isinstance(selected, list) or not all(isinstance(x, str) for x in selected):
                raise PDDLError("ids must be an array of strings")
            wanted = set(selected)
            manifest = [e for e in manifest if isinstance(e, dict) and e.get("id") in wanted]
            missing = wanted - {e.get("id") for e in manifest}
            if missing:
                raise PDDLError("requested IDs absent from manifest: " + ", ".join(sorted(missing)))
        results = []
        for entry in manifest:
            try:
                if not isinstance(entry, dict):
                    raise PDDLError("manifest entry is not an object")
                results.append(solve_one(entry, root, limit, weight))
            except Exception as exc:
                results.append({"id": entry.get("id", "<unknown>") if isinstance(entry, dict) else "<unknown>",
                                "ok": False, "error": str(exc)})
        print(json.dumps({"ok": all(r["ok"] for r in results), "results": results}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "results": []}, sort_keys=True))


if __name__ == "__main__":
    main()
