"""Dependency-free PDDL parser and grounded ADL plan replayer."""
import itertools
import re


class PDDLError(Exception):
    pass


def sxfile(path):
    text = re.sub(r";[^\n]*", "", open(path, encoding="utf8").read()).lower()
    tokens = re.findall(r"[()]|[^\s()]+", text)
    pos = 0
    def read():
        nonlocal pos
        if pos >= len(tokens):
            raise PDDLError("unexpected end of PDDL")
        token = tokens[pos]; pos += 1
        if token != "(":
            return token
        result = []
        while True:
            if pos >= len(tokens):
                raise PDDLError("unclosed PDDL list")
            if tokens[pos] == ")":
                pos += 1
                return result
            result.append(read())
    root = read()
    if pos != len(tokens):
        raise PDDLError("extra PDDL tokens")
    return root


def typed(items, default="object"):
    answer, pending, i = [], [], 0
    while i < len(items):
        if items[i] == "-":
            if i + 1 == len(items):
                raise PDDLError("dangling type marker")
            answer.extend((x, items[i + 1]) for x in pending)
            pending = []; i += 2
        else:
            pending.append(items[i]); i += 1
    answer.extend((x, default) for x in pending)
    return answer


def _entries(root):
    if not isinstance(root, list) or not root or root[0] != "define":
        raise PDDLError("expected PDDL define form")
    return root[1:]


def _fields(form):
    out, i = {}, 2
    while i < len(form):
        if not isinstance(form[i], str) or not form[i].startswith(":") or i + 1 >= len(form):
            raise PDDLError("malformed action fields")
        out[form[i]] = form[i + 1]; i += 2
    return out


def load(domain_path, problem_path):
    types, constants, actions = {"object": None}, {}, []
    for part in _entries(sxfile(domain_path)):
        if not isinstance(part, list) or not part:
            continue
        if part[0] == ":types":
            types.update(typed(part[1:]))
        elif part[0] == ":constants":
            constants.update(typed(part[1:]))
        elif part[0] == ":action":
            spec = _fields(part)
            if not all(x in spec for x in (":parameters", ":precondition", ":effect")):
                raise PDDLError("incomplete action schema")
            actions.append((part[1], typed(spec[":parameters"]), spec[":precondition"], spec[":effect"]))
    if not actions:
        raise PDDLError("domain declares no actions")
    objects, init, goal = dict(constants), set(), None
    for part in _entries(sxfile(problem_path)):
        if not isinstance(part, list) or not part:
            continue
        if part[0] == ":objects":
            objects.update(typed(part[1:]))
        elif part[0] == ":init":
            for fact in part[1:]:
                if not isinstance(fact, list) or not fact or fact[0] == "not":
                    raise PDDLError("unsupported negative or malformed init")
                init.add(tuple(fact))
        elif part[0] == ":goal":
            if len(part) != 2:
                raise PDDLError("malformed goal")
            goal = part[1]
    if goal is None:
        raise PDDLError("problem has no goal")
    return {"types": types, "actions": actions}, {"objects": objects, "init": frozenset(init), "goal": goal}


def subtype(actual, wanted, types):
    while actual is not None:
        if actual == wanted:
            return True
        actual = types.get(actual)
    return False


def _atom(expr, env):
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
        values = [formula(expr[2], state, item, objects, types) for item in envs]
        return all(values) if op == "forall" else any(values)
    return _atom(expr, env) in state


def effects(expr, state, env, objects, types):
    if not isinstance(expr, list) or not expr:
        raise PDDLError("malformed effect")
    op = expr[0]
    if op == "and":
        adds, deletes = set(), set()
        for child in expr[1:]:
            add, delete = effects(child, state, env, objects, types)
            adds |= add; deletes |= delete
        return adds, deletes
    if op == "not": return set(), {_atom(expr[1], env)}
    if op == "when":
        return effects(expr[2], state, env, objects, types) if formula(expr[1], state, env, objects, types) else (set(), set())
    if op == "forall":
        variables = typed(expr[1])
        pools = [[obj for obj, actual in objects.items() if subtype(actual, typ, types)] for _, typ in variables]
        adds, deletes = set(), set()
        for values in itertools.product(*pools):
            extended = dict(env); extended.update(dict(zip([v for v, _ in variables], values)))
            add, delete = effects(expr[2], state, extended, objects, types)
            adds |= add; deletes |= delete
        return adds, deletes
    return {_atom(expr, env)}, set()


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
        for (variable, expected), obj in zip(params, args):
            if obj not in problem["objects"] or not subtype(problem["objects"][obj], expected, domain["types"]):
                return False, "step %d: incompatible object" % number, None
            env[variable] = obj
        if not formula(precondition, state, env, problem["objects"], domain["types"]):
            return False, "step %d: unsatisfied precondition" % number, None
        adds, deletes = effects(effect, state, env, problem["objects"], domain["types"])
        state = frozenset((set(state) - deletes) | adds)
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
            plan.append((match.group(1), tuple(x for x in re.split(r"[\s,]+", match.group(2).strip()) if x)))
            continue
        match = re.fullmatch(r"\(\s*([\w-]+)((?:\s+[\w-]+)*)\s*\)", line)
        if match:
            plan.append((match.group(1), tuple(match.group(2).split())))
            continue
        raise PDDLError("cannot parse plan line: " + raw)
    return plan


def render(plan):
    return "".join("%s(%s)\n" % (name, ", ".join(args)) for name, args in plan)
