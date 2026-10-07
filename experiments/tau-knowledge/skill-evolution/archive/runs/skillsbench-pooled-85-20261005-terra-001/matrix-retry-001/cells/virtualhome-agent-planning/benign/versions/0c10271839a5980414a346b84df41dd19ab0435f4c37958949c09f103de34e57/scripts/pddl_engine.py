"""Dependency-free parser and semantic replayer for typed PDDL plans."""
import itertools
import heapq
import re
from collections import defaultdict

class PDDLError(Exception):
    pass

def _tokens(text):
    return re.findall(r"[()]|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())

def sexpr_file(path):
    ts = _tokens(open(path, encoding="utf-8").read()); pos = 0
    def read():
        nonlocal pos
        if pos >= len(ts): raise PDDLError("unexpected end of PDDL")
        x = ts[pos]; pos += 1
        if x != "(": return x
        out = []
        while True:
            if pos >= len(ts): raise PDDLError("unclosed PDDL list")
            if ts[pos] == ")": pos += 1; return out
            out.append(read())
    root = read()
    if pos != len(ts): raise PDDLError("extra PDDL tokens")
    return root

def typed(items, default="object"):
    ans, pending, i = [], [], 0
    while i < len(items):
        if items[i] == "-":
            if i + 1 >= len(items): raise PDDLError("dangling type marker")
            ans.extend((x, items[i + 1]) for x in pending); pending = []; i += 2
        else: pending.append(items[i]); i += 1
    ans.extend((x, default) for x in pending)
    return ans

def _entries(root):
    if not isinstance(root, list) or not root or root[0] != "define": raise PDDLError("expected (define ...)")
    return root[1:]

def _fields(form, start=2):
    out, i = {}, start
    while i < len(form):
        if not isinstance(form[i], str) or not form[i].startswith(":") or i + 1 >= len(form):
            raise PDDLError("malformed keyword fields")
        out[form[i]] = form[i + 1]; i += 2
    return out

def parse_domain(path):
    types, constants, actions = {"object": None}, {}, []
    for x in _entries(sexpr_file(path)):
        if not isinstance(x, list) or not x: continue
        if x[0] == ":types": types.update(typed(x[1:]))
        elif x[0] == ":constants": constants.update(typed(x[1:]))
        elif x[0] == ":action":
            if len(x) < 2: raise PDDLError("unnamed action")
            f = _fields(x)
            if not all(k in f for k in (":parameters", ":precondition", ":effect")):
                raise PDDLError("action %s lacks required fields" % x[1])
            actions.append({"name": x[1], "params": typed(f[":parameters"]),
                            "pre": f[":precondition"], "eff": f[":effect"]})
    if not actions: raise PDDLError("domain has no action schemas")
    return {"types": types, "constants": constants, "actions": actions}

def parse_problem(path, domain):
    objects, init, goal = dict(domain["constants"]), set(), None
    for x in _entries(sexpr_file(path)):
        if not isinstance(x, list) or not x: continue
        if x[0] == ":objects": objects.update(typed(x[1:]))
        elif x[0] == ":init":
            for fact in x[1:]:
                if not isinstance(fact, list) or not fact: raise PDDLError("malformed initial fact")
                if fact[0] == "not": raise PDDLError("negative initial facts unsupported")
                init.add(tuple(fact))
        elif x[0] == ":goal":
            if len(x) != 2: raise PDDLError("malformed goal")
            goal = x[1]
    if goal is None: raise PDDLError("problem lacks goal")
    return {"objects": objects, "init": frozenset(init), "goal": goal}

def load(domain_path, problem_path):
    d = parse_domain(domain_path); return d, parse_problem(problem_path, d)

def is_subtype(actual, wanted, types):
    while actual is not None:
        if actual == wanted: return True
        actual = types.get(actual)
    return False

def _atom(x, env):
    if not isinstance(x, list) or not x: raise PDDLError("expected predicate atom")
    return tuple(env.get(v, v) for v in x)

def formula(f, state, env, objects, types):
    if not isinstance(f, list) or not f: raise PDDLError("invalid formula")
    op = f[0]
    if op == "and": return all(formula(z, state, env, objects, types) for z in f[1:])
    if op == "or": return any(formula(z, state, env, objects, types) for z in f[1:])
    if op == "not": return not formula(f[1], state, env, objects, types)
    if op == "imply": return not formula(f[1], state, env, objects, types) or formula(f[2], state, env, objects, types)
    if op in ("forall", "exists"):
        if len(f) != 3: raise PDDLError("malformed quantified formula")
        assignments = [dict(env)]
        for var, typ in typed(f[1]):
            assignments = [dict(e, **{var: obj}) for e in assignments for obj, ot in objects.items() if is_subtype(ot, typ, types)]
        values = [formula(f[2], state, e, objects, types) for e in assignments]
        return all(values) if op == "forall" else any(values)
    if op == "=":
        if len(f) != 3: raise PDDLError("malformed equality")
        return env.get(f[1], f[1]) == env.get(f[2], f[2])
    return _atom(f, env) in state

def effect_atoms(eff, state, env, objects, types):
    if not isinstance(eff, list) or not eff: raise PDDLError("invalid effect")
    op = eff[0]
    if op == "and":
        adds, deletes = set(), set()
        for z in eff[1:]:
            a, d = effect_atoms(z, state, env, objects, types); adds |= a; deletes |= d
        return adds, deletes
    if op == "not": return set(), {_atom(eff[1], env)}
    if op == "when":
        if len(eff) != 3: raise PDDLError("malformed conditional effect")
        return effect_atoms(eff[2], state, env, objects, types) if formula(eff[1], state, env, objects, types) else (set(), set())
    if op == "forall":
        if len(eff) != 3: raise PDDLError("malformed quantified effect")
        vars_ = typed(eff[1]); adds, deletes = set(), set()
        pools = [[o for o, ot in objects.items() if is_subtype(ot, t, types)] for _, t in vars_]
        for vals in itertools.product(*pools):
            e = dict(env); e.update(dict(zip((v for v, _ in vars_), vals)))
            a, d = effect_atoms(eff[2], state, e, objects, types); adds |= a; deletes |= d
        return adds, deletes
    return {_atom(eff, env)}, set()

def ground(action, args, objects, types):
    if len(args) != len(action["params"]): raise PDDLError("wrong argument count for " + action["name"])
    env = {}
    for (var, typ), obj in zip(action["params"], args):
        if obj not in objects: raise PDDLError("unknown object " + obj)
        if not is_subtype(objects[obj], typ, types): raise PDDLError("incompatible object %s for %s" % (obj, var))
        env[var] = obj
    return env

def apply(action, args, state, objects, types):
    env = ground(action, args, objects, types)
    if not formula(action["pre"], state, env, objects, types): return None
    adds, deletes = effect_atoms(action["eff"], state, env, objects, types)
    nxt = set(state); nxt.difference_update(deletes); nxt.update(adds)
    return frozenset(nxt)

def validate(domain, problem, plan):
    schemas, state = {a["name"]: a for a in domain["actions"]}, problem["init"]
    for n, (name, args) in enumerate(plan, 1):
        if name not in schemas: return False, "step %d: unknown action %s" % (n, name), None
        try: nxt = apply(schemas[name], args, state, problem["objects"], domain["types"])
        except PDDLError as exc: return False, "step %d: %s" % (n, exc), None
        if nxt is None: return False, "step %d: unsatisfied precondition for %s" % (n, name), None
        state = nxt
    try: ok = formula(problem["goal"], state, {}, problem["objects"], domain["types"])
    except PDDLError as exc: return False, "goal evaluation failed: %s" % exc, state
    return (True, "valid", state) if ok else (False, "final state does not satisfy complete goal", state)

def applicable(domain, problem, state):
    """Exhaustive typed grounding, used only by the bounded small-instance fallback."""
    for action in domain["actions"]:
        pools = [[o for o, ot in problem["objects"].items() if is_subtype(ot, typ, domain["types"])] for _, typ in action["params"]]
        for args in itertools.product(*pools):
            nxt = apply(action, args, state, problem["objects"], domain["types"])
            if nxt is not None: yield action, args, nxt

def fallback_search(domain, problem, max_states=250000):
    start = problem["init"]
    if formula(problem["goal"], start, {}, problem["objects"], domain["types"]): return []
    def score(s): return 0 if formula(problem["goal"], s, {}, problem["objects"], domain["types"]) else 1
    heap, parents, serial, expanded = [(score(start), 0, 0, start)], {start: None}, 1, 0
    while heap and expanded < max_states:
        _, depth, _, state = heapq.heappop(heap); expanded += 1
        for action, args, nxt in applicable(domain, problem, state):
            if nxt in parents: continue
            parents[nxt] = (state, (action["name"], args))
            if formula(problem["goal"], nxt, {}, problem["objects"], domain["types"]):
                out = []
                while parents[nxt] is not None: nxt, step = parents[nxt]; out.append(step)
                return list(reversed(out))
            heapq.heappush(heap, (score(nxt), depth + 1, serial, nxt)); serial += 1
    raise PDDLError("fallback search exhausted %d states" % expanded)

def parse_plan_line(raw):
    line = raw.split(";", 1)[0].strip().lower()
    if not line: return None
    line = re.sub(r"^\s*[0-9.]+\s*:\s*", "", line); line = re.sub(r"\s*\[[^]]+\]\s*$", "", line)
    m = re.fullmatch(r"([\w-]+)\s*\(([^()]*)\)", line)
    if m: return m.group(1), tuple(x for x in re.split(r"[\s,]+", m.group(2).strip()) if x)
    m = re.fullmatch(r"\(\s*([\w-]+)((?:\s+[\w-]+)*)\s*\)", line)
    if m: return m.group(1), tuple(m.group(2).split())
    raise PDDLError("cannot parse plan line: " + raw.strip())

def parse_plan_text(text):
    return [x for x in (parse_plan_line(line) for line in text.splitlines()) if x is not None]

def render(plan):
    return "".join("%s(%s)\n" % (name, ", ".join(args)) for name, args in plan)
