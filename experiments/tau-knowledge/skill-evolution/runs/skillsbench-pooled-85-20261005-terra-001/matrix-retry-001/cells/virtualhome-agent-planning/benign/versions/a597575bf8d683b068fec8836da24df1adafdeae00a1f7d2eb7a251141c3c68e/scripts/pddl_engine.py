"""Small dependency-free typed PDDL parser and semantic plan replayer."""
import itertools
import re

class PDDLError(Exception):
    pass

def _tokens(text):
    return re.findall(r"[()]|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())

def sexpr_file(path):
    ts = _tokens(open(path, encoding="utf-8").read())
    pos = 0
    def read():
        nonlocal pos
        if pos >= len(ts):
            raise PDDLError("unexpected end of PDDL")
        value = ts[pos]; pos += 1
        if value != "(":
            return value
        result = []
        while True:
            if pos >= len(ts):
                raise PDDLError("unclosed PDDL list")
            if ts[pos] == ")":
                pos += 1
                return result
            result.append(read())
    root = read()
    if pos != len(ts):
        raise PDDLError("extra PDDL tokens")
    return root

def typed(items, default="object"):
    result, pending, i = [], [], 0
    while i < len(items):
        item = items[i]
        if item == "-":
            if i + 1 >= len(items):
                raise PDDLError("dangling type marker")
            result.extend((x, items[i + 1]) for x in pending)
            pending = []; i += 2
        else:
            pending.append(item); i += 1
    result.extend((x, default) for x in pending)
    return result

def _entries(root):
    if not isinstance(root, list) or not root or root[0] != "define":
        raise PDDLError("expected (define ...)")
    return root[1:]

def _fields(action):
    result, i = {}, 2
    while i < len(action):
        if not isinstance(action[i], str) or not action[i].startswith(":") or i + 1 >= len(action):
            raise PDDLError("malformed action fields")
        result[action[i]] = action[i + 1]; i += 2
    return result

def parse_domain(path):
    types, constants, actions = {"object": None}, {}, []
    for form in _entries(sexpr_file(path)):
        if not isinstance(form, list) or not form:
            continue
        if form[0] == ":types":
            types.update(typed(form[1:]))
        elif form[0] == ":constants":
            constants.update(typed(form[1:]))
        elif form[0] == ":action":
            fields = _fields(form)
            if len(form) < 2 or not all(k in fields for k in (":parameters", ":precondition", ":effect")):
                raise PDDLError("action lacks a required field")
            actions.append({"name": form[1], "params": typed(fields[":parameters"]),
                            "pre": fields[":precondition"], "eff": fields[":effect"]})
    if not actions:
        raise PDDLError("domain has no action schemas")
    return {"types": types, "constants": constants, "actions": actions}

def parse_problem(path, domain):
    objects, init, goal = dict(domain["constants"]), set(), None
    for form in _entries(sexpr_file(path)):
        if not isinstance(form, list) or not form:
            continue
        if form[0] == ":objects":
            objects.update(typed(form[1:]))
        elif form[0] == ":init":
            for fact in form[1:]:
                if not isinstance(fact, list) or not fact or fact[0] == "not":
                    raise PDDLError("negative or malformed initial fact unsupported")
                init.add(tuple(fact))
        elif form[0] == ":goal":
            if len(form) != 2:
                raise PDDLError("malformed goal")
            goal = form[1]
    if goal is None:
        raise PDDLError("problem lacks goal")
    return {"objects": objects, "init": frozenset(init), "goal": goal}

def load(domain_path, problem_path):
    domain = parse_domain(domain_path)
    return domain, parse_problem(problem_path, domain)

def is_subtype(actual, wanted, types):
    while actual is not None:
        if actual == wanted:
            return True
        actual = types.get(actual)
    return False

def _atom(expr, env):
    if not isinstance(expr, list) or not expr:
        raise PDDLError("expected predicate atom")
    return tuple(env.get(x, x) for x in expr)

def formula(expr, state, env, objects, types):
    if not isinstance(expr, list) or not expr:
        raise PDDLError("invalid formula")
    op = expr[0]
    if op == "and": return all(formula(x, state, env, objects, types) for x in expr[1:])
    if op == "or": return any(formula(x, state, env, objects, types) for x in expr[1:])
    if op == "not": return not formula(expr[1], state, env, objects, types)
    if op == "imply": return not formula(expr[1], state, env, objects, types) or formula(expr[2], state, env, objects, types)
    if op == "=": return len(expr) == 3 and env.get(expr[1], expr[1]) == env.get(expr[2], expr[2])
    if op in ("forall", "exists"):
        if len(expr) != 3:
            raise PDDLError("malformed quantified formula")
        assignments = [dict(env)]
        for var, typ in typed(expr[1]):
            assignments = [dict(e, **{var: obj}) for e in assignments for obj, objtyp in objects.items()
                           if is_subtype(objtyp, typ, types)]
        values = [formula(expr[2], state, e, objects, types) for e in assignments]
        return all(values) if op == "forall" else any(values)
    return _atom(expr, env) in state

def effect_atoms(expr, state, env, objects, types):
    if not isinstance(expr, list) or not expr:
        raise PDDLError("invalid effect")
    op = expr[0]
    if op == "and":
        adds, deletes = set(), set()
        for child in expr[1:]:
            a, d = effect_atoms(child, state, env, objects, types); adds |= a; deletes |= d
        return adds, deletes
    if op == "not":
        return set(), {_atom(expr[1], env)}
    if op == "when":
        if len(expr) != 3:
            raise PDDLError("malformed conditional effect")
        return effect_atoms(expr[2], state, env, objects, types) if formula(expr[1], state, env, objects, types) else (set(), set())
    if op == "forall":
        if len(expr) != 3:
            raise PDDLError("malformed quantified effect")
        variables = typed(expr[1]); pools = [[o for o, ot in objects.items() if is_subtype(ot, t, types)] for _, t in variables]
        adds, deletes = set(), set()
        for values in itertools.product(*pools):
            local = dict(env); local.update(dict(zip((v for v, _ in variables), values)))
            a, d = effect_atoms(expr[2], state, local, objects, types); adds |= a; deletes |= d
        return adds, deletes
    return {_atom(expr, env)}, set()

def apply(action, args, state, objects, types):
    if len(args) != len(action["params"]):
        raise PDDLError("wrong argument count for " + action["name"])
    env = {}
    for (var, typ), obj in zip(action["params"], args):
        if obj not in objects:
            raise PDDLError("unknown object " + obj)
        if not is_subtype(objects[obj], typ, types):
            raise PDDLError("incompatible object %s for %s" % (obj, var))
        env[var] = obj
    if not formula(action["pre"], state, env, objects, types):
        return None
    adds, deletes = effect_atoms(action["eff"], state, env, objects, types)
    result = set(state); result.difference_update(deletes); result.update(adds)
    return frozenset(result)

def validate(domain, problem, plan):
    schemas, state = {a["name"]: a for a in domain["actions"]}, problem["init"]
    for step, (name, args) in enumerate(plan, 1):
        if name not in schemas:
            return False, "step %d: unknown action %s" % (step, name), None
        try:
            nxt = apply(schemas[name], args, state, problem["objects"], domain["types"])
        except PDDLError as exc:
            return False, "step %d: %s" % (step, exc), None
        if nxt is None:
            return False, "step %d: unsatisfied precondition for %s" % (step, name), None
        state = nxt
    try:
        ok = formula(problem["goal"], state, {}, problem["objects"], domain["types"])
    except PDDLError as exc:
        return False, "goal evaluation failed: %s" % exc, state
    return (True, "valid", state) if ok else (False, "final state does not satisfy complete goal", state)

def parse_plan_line(raw):
    line = raw.split(";", 1)[0].strip().lower()
    if not line:
        return None
    line = re.sub(r"^\s*[0-9.]+\s*:\s*", "", line)
    line = re.sub(r"\s*\[[^]]+\]\s*$", "", line)
    match = re.fullmatch(r"([\w-]+)\s*\(([^()]*)\)", line)
    if match:
        return match.group(1), tuple(x for x in re.split(r"[\s,]+", match.group(2).strip()) if x)
    match = re.fullmatch(r"\(\s*([\w-]+)((?:\s+[\w-]+)*)\s*\)", line)
    if match:
        return match.group(1), tuple(match.group(2).split())
    raise PDDLError("cannot parse plan line: " + raw.strip())

def parse_plan_text(text):
    return [item for item in (parse_plan_line(line) for line in text.splitlines()) if item is not None]

def render(plan):
    return "".join("%s(%s)\n" % (name, ", ".join(args)) for name, args in plan)
