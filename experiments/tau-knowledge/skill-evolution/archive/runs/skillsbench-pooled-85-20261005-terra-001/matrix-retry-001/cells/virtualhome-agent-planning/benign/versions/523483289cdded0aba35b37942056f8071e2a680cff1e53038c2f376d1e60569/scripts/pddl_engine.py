"""Small dependency-free typed classical-PDDL parser, simulator, and fallback search."""
import itertools
import heapq
import re
from collections import defaultdict

class PDDLError(Exception):
    pass

def _tokens(text):
    text = re.sub(r";[^\n]*", "", text)
    return re.findall(r"[()]|[^\s()]+", text.lower())

def sexpr_file(path):
    ts = _tokens(open(path, encoding="utf-8").read())
    pos = 0
    def read():
        nonlocal pos
        if pos >= len(ts): raise PDDLError("unexpected end of PDDL")
        t = ts[pos]; pos += 1
        if t != "(": return t
        out = []
        while True:
            if pos >= len(ts): raise PDDLError("unclosed list")
            if ts[pos] == ")": pos += 1; return out
            out.append(read())
    root = read()
    if pos != len(ts): raise PDDLError("extra PDDL tokens")
    return root

def typed(items, default="object"):
    """Return [(symbol,type)] for PDDL's a b - type c - type notation."""
    out, pending, i = [], [], 0
    while i < len(items):
        x = items[i]
        if x == "-":
            if i + 1 >= len(items): raise PDDLError("type marker without type")
            out += [(v, items[i+1]) for v in pending]; pending = []; i += 2
        else:
            pending.append(x); i += 1
    out += [(v, default) for v in pending]
    return out

def flatten_formula(x, where="formula"):
    if not isinstance(x, list) or not x: raise PDDLError("malformed " + where)
    if x[0] == "and":
        ans = []
        for y in x[1:]: ans.extend(flatten_formula(y, where))
        return ans
    if x[0] == "not":
        if len(x) != 2 or not isinstance(x[1], list): raise PDDLError("malformed negation")
        return [(False, tuple(x[1]))]
    if x[0] in ("or", "forall", "exists", "when", "imply", "increase", "decrease", "assign"):
        raise PDDLError("unsupported non-classical construct " + x[0])
    return [(True, tuple(x))]

def entries(root):
    if not isinstance(root, list) or not root or root[0] != "define": raise PDDLError("expected (define ...)")
    return root[1:]

def parse_domain(path):
    es = entries(sexpr_file(path)); types = {"object": None}; constants = {}; actions = []
    for e in es:
        if not isinstance(e, list) or not e: continue
        tag = e[0]
        if tag == ":types":
            for name, parent in typed(e[1:]): types[name] = parent
        elif tag == ":constants":
            constants.update(typed(e[1:]))
        elif tag == ":action":
            if len(e) < 2: raise PDDLError("action without a name")
            fields = {}; i = 2
            while i < len(e):
                if not isinstance(e[i], str) or not e[i].startswith(":") or i+1 >= len(e):
                    raise PDDLError("malformed action " + e[1])
                fields[e[i]] = e[i+1]; i += 2
            for needed in (":parameters", ":precondition", ":effect"):
                if needed not in fields: raise PDDLError("action %s lacks %s" % (e[1], needed))
            actions.append({"name": e[1], "params": typed(fields[":parameters"]),
                            "pre": flatten_formula(fields[":precondition"], "precondition"),
                            "eff": flatten_formula(fields[":effect"], "effect")})
    if not actions: raise PDDLError("domain has no actions")
    return {"types": types, "constants": constants, "actions": actions}

def parse_problem(path, domain):
    es = entries(sexpr_file(path)); objects = dict(domain["constants"]); init = set(); goal = None
    for e in es:
        if not isinstance(e, list) or not e: continue
        if e[0] == ":objects": objects.update(typed(e[1:]))
        elif e[0] == ":init":
            for fact in e[1:]:
                for sign, atom in flatten_formula(fact, "initial fact"):
                    if not sign: raise PDDLError("negative initial facts are unsupported")
                    init.add(atom)
        elif e[0] == ":goal":
            if len(e) != 2: raise PDDLError("malformed goal")
            goal = flatten_formula(e[1], "goal")
    if goal is None: raise PDDLError("problem lacks a goal")
    return {"objects": objects, "init": frozenset(init), "goal": goal}

def load(domain_path, problem_path):
    d = parse_domain(domain_path); p = parse_problem(problem_path, d); return d, p

def is_subtype(actual, wanted, types):
    while actual is not None:
        if actual == wanted: return True
        actual = types.get(actual)
    return False

def subst_atom(atom, env):
    return tuple(env.get(x, x) if isinstance(x, str) and x.startswith("?") else x for x in atom)

def literal_true(lit, state, env):
    sign, atom = lit; atom = subst_atom(atom, env)
    if atom and atom[0] == "=":
        if len(atom) != 3: raise PDDLError("bad equality")
        value = atom[1] == atom[2]
    else: value = atom in state
    return value if sign else not value

def goal_true(goal, state): return all(literal_true(x, state, {}) for x in goal)

def ground_action(action, args, objects, types):
    if len(args) != len(action["params"]): raise PDDLError("wrong argument count for " + action["name"])
    env = {}
    for (var, typ), obj in zip(action["params"], args):
        if obj not in objects: raise PDDLError("unknown object " + obj)
        if not is_subtype(objects[obj], typ, types): raise PDDLError("object %s has incompatible type for %s" % (obj, var))
        env[var] = obj
    return env

def apply(action, args, state, objects, types):
    env = ground_action(action, args, objects, types)
    for lit in action["pre"]:
        if not literal_true(lit, state, env): return None
    nxt = set(state)
    for sign, atom in action["eff"]:
        atom = subst_atom(atom, env)
        if atom[0] == "=": raise PDDLError("equality cannot be an effect")
        if sign: nxt.add(atom)
        else: nxt.discard(atom)
    return frozenset(nxt)

def _unify(pattern, fact, env):
    if len(pattern) != len(fact) or pattern[0] != fact[0]: return None
    result = dict(env)
    for p, f in zip(pattern[1:], fact[1:]):
        if p.startswith("?"):
            if p in result and result[p] != f: return None
            result[p] = f
        elif p != f: return None
    return result

def applicable(domain, problem, state):
    """Lazily bind action parameters through positive facts, then test all literals."""
    bypred = defaultdict(list)
    for f in state: bypred[f[0]].append(f)
    objects, types = problem["objects"], domain["types"]
    bytype = defaultdict(list)
    for o, t in objects.items(): bytype[t].append(o)
    def choices(wanted):
        return [o for o, t in objects.items() if is_subtype(t, wanted, types)]
    for a in domain["actions"]:
        positives = [atom for sign, atom in a["pre"] if sign and atom[0] != "="]
        positives.sort(key=lambda x: len(bypred[x[0]]))
        envs = [{}]
        for pat in positives:
            new = []
            for env in envs:
                for fact in bypred[pat[0]]:
                    u = _unify(pat, fact, env)
                    if u is not None: new.append(u)
            envs = new
            if not envs: break
        for env in envs:
            missing = [(v, t) for v, t in a["params"] if v not in env]
            pools = [choices(t) for _, t in missing]
            for vals in itertools.product(*pools):
                full = dict(env); full.update(dict(zip((v for v, _ in missing), vals)))
                args = tuple(full[v] for v, _ in a["params"])
                if all(literal_true(x, state, full) for x in a["pre"]):
                    yield a, args, apply(a, args, state, objects, types)

def fallback_search(domain, problem, max_states=250000):
    start = problem["init"]
    if goal_true(problem["goal"], start): return []
    # Greedy best first is complete only up to max_states; parent records permit replay.
    def score(s): return sum(not literal_true(g, s, {}) for g in problem["goal"])
    queue = [(score(start), 0, 0, start)]; serial = 1; parent = {start: None}; expanded = 0
    while queue and expanded < max_states:
        _, depth, _, state = heapq.heappop(queue); expanded += 1
        for action, args, nxt in applicable(domain, problem, state):
            if nxt in parent: continue
            parent[nxt] = (state, (action["name"], args))
            if goal_true(problem["goal"], nxt):
                result = []
                while parent[nxt] is not None:
                    nxt, step = parent[nxt]; result.append(step)
                return list(reversed(result))
            heapq.heappush(queue, (score(nxt), depth+1, serial, nxt)); serial += 1
    raise PDDLError("fallback search exhausted %d states without a plan" % expanded)

def parse_plan_line(line):
    line = line.strip().lower()
    if not line or line.startswith(";"): return None
    # Accept FD '(a x y)', task 'a(x, y)', or a timestamped FD line.
    line = re.sub(r"^\s*[0-9.]+\s*:\s*", "", line)
    line = re.sub(r"\s*\[[^]]+\]\s*$", "", line)
    m = re.match(r"^\(?\s*([^\s(),]+)\s*(?:\(([^)]*)\)|([^)]*))\)?\s*$", line)
    if not m: raise PDDLError("cannot parse plan line: " + line)
    name = m.group(1); tail = (m.group(2) if m.group(2) is not None else m.group(3)).strip()
    args = tuple(x for x in re.split(r"[\s,]+", tail) if x)
    return name, args

def parse_plan_text(text):
    out = []
    for raw in text.splitlines():
        p = parse_plan_line(raw)
        if p: out.append(p)
    return out

def validate(domain, problem, plan):
    actions = {a["name"]: a for a in domain["actions"]}; state = problem["init"]
    for i, (name, args) in enumerate(plan, 1):
        if name not in actions: return False, "step %d: unknown action %s" % (i, name), None
        try: nxt = apply(actions[name], args, state, problem["objects"], domain["types"])
        except PDDLError as e: return False, "step %d: %s" % (i, e), None
        if nxt is None:
            return False, "step %d: unsatisfied precondition for %s" % (i, name), None
        state = nxt
    missing = [str(a) for a in problem["goal"] if not literal_true(a, state, {})]
    if missing: return False, "final state misses goal literals: " + ", ".join(missing), state
    return True, "valid", state

def render(plan):
    return "\n".join("%s(%s)" % (name, ", ".join(args)) for name, args in plan) + ("\n" if plan else "")
