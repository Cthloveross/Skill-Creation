import itertools
import re

class PDDLError(Exception):
    pass


def sx(path):
    text = re.sub(r';[^\n]*', '', open(path, encoding='utf8').read()).lower()
    tokens = re.findall(r'[()]|[^\s()]+', text)
    index = 0
    def read():
        nonlocal index
        if index >= len(tokens):
            raise PDDLError('unexpected end of PDDL')
        token = tokens[index]
        index += 1
        if token != '(':
            return token
        result = []
        while index < len(tokens) and tokens[index] != ')':
            result.append(read())
        if index == len(tokens):
            raise PDDLError('unclosed PDDL list')
        index += 1
        return result
    result = read()
    if index != len(tokens):
        raise PDDLError('extra PDDL tokens')
    return result


def typed(items, default='object'):
    result, pending, index = [], [], 0
    while index < len(items):
        if items[index] == '-':
            if index + 1 >= len(items):
                raise PDDLError('dangling type marker')
            result.extend((name, items[index + 1]) for name in pending)
            pending = []
            index += 2
        else:
            pending.append(items[index])
            index += 1
    result.extend((name, default) for name in pending)
    return result


def fields(form, start=1):
    result, index = {}, start
    while index < len(form):
        if isinstance(form[index], str) and form[index].startswith(':') and index + 1 < len(form):
            result[form[index]] = form[index + 1]
            index += 2
        else:
            index += 1
    return result


def load(domain_path, problem_path):
    domain, problem = sx(domain_path), sx(problem_path)
    parents, constants, actions = {'object': None}, {}, []
    for part in domain[1:]:
        if not isinstance(part, list) or not part:
            continue
        if part[0] == ':types':
            parents.update(typed(part[1:]))
        elif part[0] == ':constants':
            constants.update(typed(part[1:]))
        elif part[0] == ':action':
            data = fields(part, 2)
            if not all(key in data for key in (':parameters', ':precondition', ':effect')):
                raise PDDLError('incomplete action schema ' + str(part[1]))
            actions.append((part[1], typed(data[':parameters']), data[':precondition'], data[':effect']))
    objects, init, goal = dict(constants), set(), None
    for part in problem[1:]:
        if not isinstance(part, list) or not part:
            continue
        if part[0] == ':objects':
            objects.update(typed(part[1:]))
        elif part[0] == ':init':
            init |= {tuple(x) for x in part[1:] if isinstance(x, list) and x and x[0] != 'not'}
        elif part[0] == ':goal':
            goal = part[1]
    if not actions or goal is None:
        raise PDDLError('domain has no actions or problem has no goal')
    return {'types': parents, 'actions': actions}, {'objects': objects, 'init': frozenset(init), 'goal': goal}


def subtype(actual, wanted, parents):
    while actual is not None:
        if actual == wanted:
            return True
        actual = parents.get(actual)
    return False


def atom(expr, env):
    return tuple(env.get(value, value) for value in expr)


def formula(expr, state, env, objects, parents):
    op = expr[0]
    if op == 'and': return all(formula(x, state, env, objects, parents) for x in expr[1:])
    if op == 'or': return any(formula(x, state, env, objects, parents) for x in expr[1:])
    if op == 'not': return not formula(expr[1], state, env, objects, parents)
    if op == 'imply': return not formula(expr[1], state, env, objects, parents) or formula(expr[2], state, env, objects, parents)
    if op == '=': return env.get(expr[1], expr[1]) == env.get(expr[2], expr[2])
    if op in ('forall', 'exists'):
        envs = [dict(env)]
        for variable, typ in typed(expr[1]):
            envs = [dict(old, **{variable: obj}) for old in envs for obj, actual in objects.items() if subtype(actual, typ, parents)]
        values = [formula(expr[2], state, item, objects, parents) for item in envs]
        return all(values) if op == 'forall' else any(values)
    return atom(expr, env) in state


def effects(expr, state, env, objects, parents):
    op = expr[0]
    if op == 'and':
        adds, deletes = set(), set()
        for item in expr[1:]:
            add, delete = effects(item, state, env, objects, parents)
            adds |= add; deletes |= delete
        return adds, deletes
    if op == 'not': return set(), {atom(expr[1], env)}
    if op == 'when':
        return effects(expr[2], state, env, objects, parents) if formula(expr[1], state, env, objects, parents) else (set(), set())
    if op == 'forall':
        variables = typed(expr[1]); adds, deletes = set(), set()
        choices = [[obj for obj, actual in objects.items() if subtype(actual, typ, parents)] for _, typ in variables]
        for values in itertools.product(*choices):
            expanded = dict(env, **dict(zip([var for var, _ in variables], values)))
            add, delete = effects(expr[2], state, expanded, objects, parents)
            adds |= add; deletes |= delete
        return adds, deletes
    return {atom(expr, env)}, set()


def parse(text):
    plan = []
    for raw in text.splitlines():
        line = raw.split(';', 1)[0].strip().lower()
        if not line:
            continue
        match = re.fullmatch(r'([\w-]+)\s*\(([^()]*)\)', line)
        if match:
            plan.append((match[1], tuple(x for x in re.split(r'[\s,]+', match[2].strip()) if x)))
            continue
        match = re.fullmatch(r'\(\s*([\w-]+)((?:\s+[\w-]+)*)\s*\)', line)
        if match:
            plan.append((match[1], tuple(match[2].split())))
            continue
        raise PDDLError('bad plan line: ' + raw)
    return plan


def validate(domain, problem, plan):
    schemas = {name: (params, precondition, effect) for name, params, precondition, effect in domain['actions']}
    state = problem['init']
    for step, (name, arguments) in enumerate(plan, 1):
        if name not in schemas:
            return False, 'step %d uses unknown action' % step, None
        params, precondition, effect = schemas[name]
        if len(params) != len(arguments):
            return False, 'step %d has wrong arity' % step, None
        env = {}
        for (variable, typ), value in zip(params, arguments):
            if value not in problem['objects'] or not subtype(problem['objects'][value], typ, domain['types']):
                return False, 'step %d has an unknown or mistyped object' % step, None
            env[variable] = value
        if not formula(precondition, state, env, problem['objects'], domain['types']):
            return False, 'step %d has unsatisfied preconditions' % step, None
        adds, deletes = effects(effect, state, env, problem['objects'], domain['types'])
        state = frozenset((set(state) - deletes) | adds)
    if not formula(problem['goal'], state, {}, problem['objects'], domain['types']):
        return False, 'final goal is unsatisfied', state
    return True, 'valid', state


def render(plan):
    return ''.join('%s(%s)\n' % (name, ', '.join(args)) for name, args in plan)
