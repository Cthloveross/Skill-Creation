import itertools, re, time


class PDDLError(Exception):
    pass


def sx(path):
    text = open(path, encoding='utf8').read()
    tokens = re.findall(r'[()]|[^\s()]+', re.sub(r';[^\n]*', '', text).lower())
    pos = 0
    def read():
        nonlocal pos
        if pos >= len(tokens):
            raise PDDLError('unexpected end of PDDL')
        token = tokens[pos]
        pos += 1
        if token != '(':
            return token
        result = []
        while pos < len(tokens) and tokens[pos] != ')':
            result.append(read())
        if pos == len(tokens):
            raise PDDLError('unclosed PDDL list')
        pos += 1
        return result
    result = read()
    if pos != len(tokens):
        raise PDDLError('extra PDDL tokens')
    return result


def typed(items, default='object'):
    result, pending, i = [], [], 0
    while i < len(items):
        if items[i] == '-':
            if i + 1 >= len(items):
                raise PDDLError('dangling type marker')
            result.extend((x, items[i + 1]) for x in pending)
            pending = []
            i += 2
        else:
            pending.append(items[i])
            i += 1
    result.extend((x, default) for x in pending)
    return result


def fields(form, start=1):
    result, i = {}, start
    while i < len(form):
        if isinstance(form[i], str) and form[i].startswith(':') and i + 1 < len(form):
            result[form[i]] = form[i + 1]
            i += 2
        else:
            i += 1
    return result


def load(domain_path, problem_path):
    domain_form, problem_form = sx(domain_path), sx(problem_path)
    parents, objects, actions = {'object': None}, {}, []
    for part in domain_form[1:]:
        if not isinstance(part, list) or not part:
            continue
        if part[0] == ':types':
            parents.update(typed(part[1:]))
        elif part[0] == ':constants':
            objects.update(typed(part[1:]))
        elif part[0] == ':action':
            f = fields(part, 2)
            required = (':parameters', ':precondition', ':effect')
            if not all(k in f for k in required):
                raise PDDLError('incomplete action ' + str(part[1]))
            actions.append((part[1], typed(f[':parameters']), f[':precondition'], f[':effect']))
    initial, goal = set(), None
    for part in problem_form[1:]:
        if not isinstance(part, list) or not part:
            continue
        if part[0] == ':objects':
            objects.update(typed(part[1:]))
        elif part[0] == ':init':
            initial.update(tuple(x) for x in part[1:]
                           if isinstance(x, list) and x and x[0] != 'not')
        elif part[0] == ':goal':
            goal = part[1]
    if not actions or goal is None:
        raise PDDLError('missing actions or goal')
    return {'types': parents, 'actions': actions}, {
        'objects': objects, 'init': frozenset(initial), 'goal': goal,
    }


def subtype(actual, wanted, parents):
    while actual is not None:
        if actual == wanted:
            return True
        actual = parents.get(actual)
    return False


def atom(form, env):
    return tuple(env.get(x, x) for x in form)


def formula(form, state, env, objects, parents):
    op = form[0]
    if op == 'and':
        return all(formula(x, state, env, objects, parents) for x in form[1:])
    if op == 'or':
        return any(formula(x, state, env, objects, parents) for x in form[1:])
    if op == 'not':
        return not formula(form[1], state, env, objects, parents)
    if op == 'imply':
        return (not formula(form[1], state, env, objects, parents)
                or formula(form[2], state, env, objects, parents))
    if op == '=':
        return env.get(form[1], form[1]) == env.get(form[2], form[2])
    if op in ('forall', 'exists'):
        environments = [dict(env)]
        for variable, wanted in typed(form[1]):
            environments = [dict(e, **{variable: obj}) for e in environments
                            for obj, actual in objects.items()
                            if subtype(actual, wanted, parents)]
        values = [formula(form[2], state, e, objects, parents) for e in environments]
        return all(values) if op == 'forall' else any(values)
    return atom(form, env) in state


def effects(form, state, env, objects, parents):
    op = form[0]
    if op == 'and':
        adds, deletes = set(), set()
        for child in form[1:]:
            a, d = effects(child, state, env, objects, parents)
            adds.update(a)
            deletes.update(d)
        return adds, deletes
    if op == 'not':
        return set(), {atom(form[1], env)}
    if op == 'when':
        return (effects(form[2], state, env, objects, parents)
                if formula(form[1], state, env, objects, parents) else (set(), set()))
    if op == 'forall':
        variables = typed(form[1])
        choices = [[obj for obj, actual in objects.items() if subtype(actual, wanted, parents)]
                   for _, wanted in variables]
        adds, deletes = set(), set()
        for values in itertools.product(*choices):
            extended = dict(env, **dict(zip((v for v, _ in variables), values)))
            a, d = effects(form[2], state, extended, objects, parents)
            adds.update(a)
            deletes.update(d)
        return adds, deletes
    return {atom(form, env)}, set()


def parse(text):
    result = []
    for raw in text.splitlines():
        line = raw.split(';', 1)[0].strip().lower()
        if not line:
            continue
        match = re.fullmatch(r'([\w-]+)\s*\(([^()]*)\)', line)
        if match:
            args = tuple(x for x in re.split(r'[\s,]+', match[2].strip()) if x)
            result.append((match[1], args))
            continue
        match = re.fullmatch(r'\(\s*([\w-]+)((?:\s+[\w-]+)*)\s*\)', line)
        if match:
            result.append((match[1], tuple(match[2].split())))
            continue
        raise PDDLError('bad plan line: ' + raw)
    return result


def validate(domain, problem, plan):
    schemas = {name: (variables, precondition, effect)
               for name, variables, precondition, effect in domain['actions']}
    state = problem['init']
    for number, (name, args) in enumerate(plan, 1):
        if name not in schemas:
            return False, 'step %d uses unknown action' % number, None
        variables, precondition, effect = schemas[name]
        if len(variables) != len(args):
            return False, 'step %d has wrong arity' % number, None
        env = {}
        for (variable, wanted), obj in zip(variables, args):
            actual = problem['objects'].get(obj)
            if actual is None or not subtype(actual, wanted, domain['types']):
                return False, 'step %d has unknown or mistyped object' % number, None
            env[variable] = obj
        if not formula(precondition, state, env, problem['objects'], domain['types']):
            return False, 'step %d has unsatisfied preconditions' % number, None
        adds, deletes = effects(effect, state, env, problem['objects'], domain['types'])
        state = frozenset((set(state) - deletes) | adds)
    if formula(problem['goal'], state, {}, problem['objects'], domain['types']):
        return True, 'valid', state
    return False, 'final goal is unsatisfied', state


def render(plan):
    return ''.join('%s(%s)\n' % (name, ', '.join(args)) for name, args in plan)


def search(domain, problem, seconds=1, max_expansions=20000, max_groundings=100000):
    if formula(problem['goal'], problem['init'], {}, problem['objects'], domain['types']):
        return []
    deadline = time.monotonic() + max(.01, float(seconds))
    ground = []
    for name, variables, precondition, effect in domain['actions']:
        choices = [[obj for obj, actual in problem['objects'].items()
                    if subtype(actual, wanted, domain['types'])]
                   for _, wanted in variables]
        for values in itertools.product(*choices):
            if time.monotonic() >= deadline or len(ground) >= int(max_groundings):
                return None
            ground.append((name, values, variables, precondition, effect))
    start = problem['init']
    queue, predecessor, head = [start], {start: None}, 0
    while head < len(queue) and head < int(max_expansions) and time.monotonic() < deadline:
        state = queue[head]
        head += 1
        for name, args, variables, precondition, effect in ground:
            env = {variable: obj for (variable, _), obj in zip(variables, args)}
            if not formula(precondition, state, env, problem['objects'], domain['types']):
                continue
            adds, deletes = effects(effect, state, env, problem['objects'], domain['types'])
            successor = frozenset((set(state) - deletes) | adds)
            if successor in predecessor:
                continue
            predecessor[successor] = (state, (name, args))
            if formula(problem['goal'], successor, {}, problem['objects'], domain['types']):
                answer = []
                while predecessor[successor] is not None:
                    successor, action = predecessor[successor]
                    answer.append(action)
                return list(reversed(answer))
            queue.append(successor)
    return None
