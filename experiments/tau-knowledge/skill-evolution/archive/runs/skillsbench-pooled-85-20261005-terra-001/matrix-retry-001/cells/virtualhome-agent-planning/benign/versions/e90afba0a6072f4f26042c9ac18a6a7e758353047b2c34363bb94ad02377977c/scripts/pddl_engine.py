"""Dependency-free PDDL reader and grounded ADL plan replayer."""
import itertools
import re

class PDDLError(Exception):
    pass

def sxfile(path):
    text = re.sub(r";[^\n]*", "", open(path, encoding="utf8").read()).lower()
    toks = re.findall(r"[()]|[^\s()]+", text)
    index = 0
    def parse():
        nonlocal index
        if index >= len(toks):
            raise PDDLError("unexpected end of PDDL")
        token = toks[index]; index += 1
        if token != "(":
            return token
        result = []
        while True:
            if index >= len(toks):
                raise PDDLError("unclosed PDDL list")
            if toks[index] == ")":
                index += 1
                return result
            result.append(parse())
    root = parse()
    if index != len(toks):
        raise PDDLError("extra PDDL tokens")
    return root

def typed(items, default="object"):
    result, pending, i = [], [], 0
    while i < len(items):
        if items[i] == "-":
            if i + 1 >= len(items):
                raise PDDLError("dangling type marker")
            result.extend((name, items[i + 1]) for name in pending)
            pending = []; i += 2
        else:
            pending.append(items[i]); i += 1
    result.extend((name, default) for name in pending)
    return result

def entries(root):
    if not isinstance(root, list) or not root or root[0] != "define":
        raise PDDLError("expected PDDL define form")
    return root[1:]

def fields(action):
    result, i = {}, 2
    while i < len(action):
        if not isinstance(action[i], str) or not action[i].startswith(":") or i + 1 >= len(action):
            raise PDDLError("malformed action fields")
        result[action[i]] = action[i + 1]; i += 2
    return result

def load(domain_path, problem_path):
    types, constants, actions = {"object": None}, {}, []
    for item in entries(sxfile(domain_path)):
        if not isinstance(item, list) or not item:
            continue
        if item[0] == ":types":
            types.update(typed(item[1:]))
        elif item[0] == ":constants":
            constants.update(typed(item[1:]))
        elif item[0] == ":action":
            spec = fields(item)
            if not all(k in spec for k in (":parameters", ":precondition", ":effect")):
                raise PDDLError("incomplete action schema")
            actions.append((item[1], typed(spec[":parameters"]), spec[":precondition"], spec[":effect"]))
    if not actions:
        raise PDDLError("domain declares no actions")
    objects, initial, goal = dict(constants), set(), None
    for item in entries(sxfile(problem_path)):
        if not isinstance(item, list) or not item:
            continue
        if item[0] == ":objects":
            objects.update(typed(item[1:]))
        elif item[0] == ":init":
            for atom in item[1:]:
                if not isinstance(atom, list) or not atom or atom[0] == "not":
                    raise PDDLError("unsupported negative or malformed init")
                initial.add(tuple(atom))
        elif item[0] == ":goal":
            if len(item) != 2:
                raise PDDLError("malformed goal")
            goal = item[1]
    if goal is None:
        raise PDDLError("problem has no goal")
    return {"types": types, "actions": actions}, {"objects": objects, "init": frozenset(initial), "goal": goal}

def subtype(actual, wanted, types):
    while actual is not None:
        if actual == wanted:
            return True
        actual = types.get(actual)
    return False

def atom(expr, env):
    if not isinstance(expr, list) or not expr:
        raise PDDLError("expected atom")
    return tuple(env.get(x, x) for x in expr)

def formula(expr, state, env, objects, types):
    if not isinstance(expr, list) or not expr:
        raise PDDLError("malformed formula")
    op = expr[0]
    if op == "and": return all(formula(x, state, env, objects, types) for x in expr[1:])
    if op == "or": return any(formula(x, state, env, objects, types) for x in expr[1:])
    if op == "not": return not formula(expr[1], state, env, objects, types)
    if op == "imply": return not formula(expr[1], state, env, objects, types) or formula(expr[2], state, env, objects, types)
    if op == "=": return len(expr) == 3 and env.get(expr[1], expr[1]) == env.get(expr[2], expr[2])
    if op in ("forall", "exists"):
        envs = [dict(env)]
        for var, typ in typed(expr[1]):
            envs = [dict(old, **{var: obj}) for old in envs for obj, actual in objects.items() if subtype(actual, typ, types)]
        values = [formula(expr[2], state, e, objects, types) for e in envs]
        return all(values) if op == "forall" else any(values)
    return atom(expr, env) in state

def effects(expr, state, env, objects, types):
    if not isinstance(expr, list) or not expr:
        raise PDDLError("malformed effect")
    op = expr[0]
    if op == "and":
        add, delete = set(), set()
        for child in expr[1:]:
            a, d = effects(child, state, env, objects, types); add |= a; delete |= d
        return add, delete
    if op == "not": return set(), {atom(expr[1], env)}
    if op == "when": return effects(expr[2], state, env, objects, types) if formula(expr[1], state, env, objects, types) else (set(), set())
    if op == "forall":
        vars_ = typed(expr[1]); pools = [[obj for obj, actual in objects.items() if subtype(actual, typ, types)] for _, typ in vars_]
        add, delete = set(), set()
        for values in itertools.product(*pools):
            extended = dict(env); extended.update(dict(zip([v for v, _ in vars_], values)))
            a, d = effects(expr[2], state, extended, objects, types); add |= a; delete |= d
        return add, delete
    return {atom(expr, env)}, set()

def validate(domain, problem, plan):
    schemas = {name: (params, pre, effect) for name, params, pre, effect in domain["actions"]}
    state = problem["init"]
    for number, (name, args) in enumerate(plan, 1):
        if name not in schemas:
            return False, "step %d: unknown action %s" % (number, name), None
        params, precondition, effect = schemas[name]
        if len(args) != len(params):
            return False, "step %d: wrong argument count" % number, None
        env = {}
        for (var, wanted), obj in zip(params, args):
            if obj not in problem["objects"] or not subtype(problem["objects"][obj], wanted, domain["types"]):
                return False, "step %d: incompatible object" % number, None
            env[var] = obj
        if not formula(precondition, state, env, problem["objects"], domain["types"]):
            return False, "step %d: unsatisfied precondition" % number, None
        add, delete = effects(effect, state, env, problem["objects"], domain["types"])
        state = frozenset((set(state) - delete) | add)
    if not formula(problem["goal"], state, {}, problem["objects"], domain["types"]):
        return False, "final goal unsatisfied", state
    return True, "valid", state

def parse_plan_text(text):
    plan = []
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip().lower()
        if not line:
            continue
        line = re.sub(r"^\s*[0-9.]+\s*:\s*", "", line)
        line = re.sub(r"\s*\[[^]]+\]\s*$", "", line)
        match = re.fullmatch(r"([\w-]+)\s*\(([^()]*)\)", line)
        if match:
            args = tuple(x for x in re.split(r"[\s,]+", match.group(2).strip()) if x)
            plan.append((match.group(1), args)); continue
        match = re.fullmatch(r"\(\s*([\w-]+)((?:\s+[\w-]+)*)\s*\)", line)
        if match:
            plan.append((match.group(1), tuple(match.group(2).split()))); continue
        raise PDDLError("cannot parse plan line: " + raw)
    return plan

def render(plan):
    return "".join("%s(%s)\n" % (name, ", ".join(args)) for name, args in plan)
