"""Dependency-free typed PDDL parser and semantic grounded-plan replayer."""
import itertools
import re


class PDDLError(Exception):
    pass


def _tokens(text):
    return re.findall(r"[()]|[^\s()]+", re.sub(r";[^\n]*", "", text).lower())


def sexpr_file(path):
    tokens = _tokens(open(path, encoding="utf-8").read())
    position = 0

    def read():
        nonlocal position
        if position >= len(tokens):
            raise PDDLError("unexpected end of PDDL")
        token = tokens[position]
        position += 1
        if token != "(":
            return token
        result = []
        while True:
            if position >= len(tokens):
                raise PDDLError("unclosed PDDL list")
            if tokens[position] == ")":
                position += 1
                return result
            result.append(read())

    root = read()
    if position != len(tokens):
        raise PDDLError("extra PDDL tokens")
    return root


def typed(items, default="object"):
    answer, pending, index = [], [], 0
    while index < len(items):
        item = items[index]
        if item == "-":
            if index + 1 >= len(items):
                raise PDDLError("dangling type marker")
            answer.extend((name, items[index + 1]) for name in pending)
            pending = []
            index += 2
        else:
            pending.append(item)
            index += 1
    answer.extend((name, default) for name in pending)
    return answer


def _entries(root):
    if not isinstance(root, list) or not root or root[0] != "define":
        raise PDDLError("expected (define ...)")
    return root[1:]


def _fields(action):
    result, index = {}, 2
    while index < len(action):
        if (not isinstance(action[index], str) or not action[index].startswith(":")
                or index + 1 >= len(action)):
            raise PDDLError("malformed action fields")
        result[action[index]] = action[index + 1]
        index += 2
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
            if len(form) < 2:
                raise PDDLError("unnamed action")
            fields = _fields(form)
            if not all(key in fields for key in (":parameters", ":precondition", ":effect")):
                raise PDDLError("action lacks a required field")
            actions.append({"name": form[1], "params": typed(fields[":parameters"]),
                            "pre": fields[":precondition"], "eff": fields[":effect"]})
    if not actions:
        raise PDDLError("domain has no action schemas")
    return {"types": types, "constants": constants, "actions": actions}


def parse_problem(path, domain):
    objects, initial, goal = dict(domain["constants"]), set(), None
    for form in _entries(sexpr_file(path)):
        if not isinstance(form, list) or not form:
            continue
        if form[0] == ":objects":
            objects.update(typed(form[1:]))
        elif form[0] == ":init":
            for fact in form[1:]:
                if not isinstance(fact, list) or not fact or fact[0] == "not":
                    raise PDDLError("negative or malformed initial fact unsupported")
                initial.add(tuple(fact))
        elif form[0] == ":goal":
            if len(form) != 2:
                raise PDDLError("malformed goal")
            goal = form[1]
    if goal is None:
        raise PDDLError("problem lacks goal")
    return {"objects": objects, "init": frozenset(initial), "goal": goal}


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
    return tuple(env.get(value, value) for value in expr)


def formula(expr, state, env, objects, types):
    if not isinstance(expr, list) or not expr:
        raise PDDLError("invalid formula")
    op = expr[0]
    if op == "and":
        return all(formula(x, state, env, objects, types) for x in expr[1:])
    if op == "or":
        return any(formula(x, state, env, objects, types) for x in expr[1:])
    if op == "not":
        return not formula(expr[1], state, env, objects, types)
    if op == "imply":
        return not formula(expr[1], state, env, objects, types) or formula(expr[2], state, env, objects, types)
    if op == "=":
        return len(expr) == 3 and env.get(expr[1], expr[1]) == env.get(expr[2], expr[2])
    if op in ("forall", "exists"):
        if len(expr) != 3:
            raise PDDLError("malformed quantified formula")
        assignments = [dict(env)]
        for variable, typ in typed(expr[1]):
            assignments = [dict(old, **{variable: obj}) for old in assignments
                           for obj, obj_type in objects.items() if is_subtype(obj_type, typ, types)]
        values = [formula(expr[2], state, assignment, objects, types) for assignment in assignments]
        return all(values) if op == "forall" else any(values)
    return _atom(expr, env) in state


def effect_atoms(expr, state, env, objects, types):
    if not isinstance(expr, list) or not expr:
        raise PDDLError("invalid effect")
    op = expr[0]
    if op == "and":
        adds, deletes = set(), set()
        for child in expr[1:]:
            child_adds, child_deletes = effect_atoms(child, state, env, objects, types)
            adds |= child_adds
            deletes |= child_deletes
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
        variables = typed(expr[1])
        pools = [[obj for obj, obj_type in objects.items() if is_subtype(obj_type, typ, types)]
                 for _, typ in variables]
        adds, deletes = set(), set()
        for values in itertools.product(*pools):
            local = dict(env)
            local.update(dict(zip((var for var, _ in variables), values)))
            child_adds, child_deletes = effect_atoms(expr[2], state, local, objects, types)
            adds |= child_adds
            deletes |= child_deletes
        return adds, deletes
    return {_atom(expr, env)}, set()


def apply(action, args, state, objects, types):
    if len(args) != len(action["params"]):
        raise PDDLError("wrong argument count for " + action["name"])
    env = {}
    for (variable, typ), obj in zip(action["params"], args):
        if obj not in objects:
            raise PDDLError("unknown object " + obj)
        if not is_subtype(objects[obj], typ, types):
            raise PDDLError("incompatible object %s for %s" % (obj, variable))
        env[variable] = obj
    if not formula(action["pre"], state, env, objects, types):
        return None
    adds, deletes = effect_atoms(action["eff"], state, env, objects, types)
    next_state = set(state)
    next_state.difference_update(deletes)
    next_state.update(adds)
    return frozenset(next_state)


def validate(domain, problem, plan):
    schemas = {action["name"]: action for action in domain["actions"]}
    state = problem["init"]
    for step, (name, args) in enumerate(plan, 1):
        if name not in schemas:
            return False, "step %d: unknown action %s" % (step, name), None
        try:
            next_state = apply(schemas[name], args, state, problem["objects"], domain["types"])
        except PDDLError as exc:
            return False, "step %d: %s" % (step, exc), None
        if next_state is None:
            return False, "step %d: unsatisfied precondition for %s" % (step, name), None
        state = next_state
    try:
        reached = formula(problem["goal"], state, {}, problem["objects"], domain["types"])
    except PDDLError as exc:
        return False, "goal evaluation failed: %s" % exc, state
    return (True, "valid", state) if reached else (False, "final state does not satisfy complete goal", state)


def parse_plan_line(raw):
    line = raw.split(";", 1)[0].strip().lower()
    if not line:
        return None
    line = re.sub(r"^\s*[0-9.]+\s*:\s*", "", line)
    line = re.sub(r"\s*\[[^]]+\]\s*$", "", line)
    match = re.fullmatch(r"([\w-]+)\s*\(([^()]*)\)", line)
    if match:
        return match.group(1), tuple(value for value in re.split(r"[\s,]+", match.group(2).strip()) if value)
    match = re.fullmatch(r"\(\s*([\w-]+)((?:\s+[\w-]+)*)\s*\)", line)
    if match:
        return match.group(1), tuple(match.group(2).split())
    raise PDDLError("cannot parse plan line: " + raw.strip())


def parse_plan_text(text):
    return [item for item in (parse_plan_line(line) for line in text.splitlines()) if item is not None]


def render(plan):
    return "".join("%s(%s)\n" % (name, ", ".join(args)) for name, args in plan)
