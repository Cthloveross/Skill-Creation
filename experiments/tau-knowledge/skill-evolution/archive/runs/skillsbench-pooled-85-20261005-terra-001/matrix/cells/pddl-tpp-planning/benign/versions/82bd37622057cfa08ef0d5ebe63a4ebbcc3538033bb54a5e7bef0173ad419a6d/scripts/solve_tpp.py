#!/usr/bin/env python3
"""Solve a typed classical-PDDL manifest. JSON stdin -> JSON stdout."""
import heapq, itertools, json, re, sys
from collections import defaultdict
from pathlib import Path

class Error(Exception): pass

def parse(path):
    ts = re.findall(r'\(|\)|[^\s()]+', re.sub(r';[^\n]*', '', Path(path).read_text()).lower())
    i = 0
    def one():
        nonlocal i
        if i >= len(ts): raise Error('unexpected end of PDDL')
        x = ts[i]; i += 1
        if x == '(':
            z = []
            while i < len(ts) and ts[i] != ')': z.append(one())
            if i == len(ts): raise Error('unclosed parenthesis')
            i += 1
            return z
        if x == ')': raise Error('unexpected closing parenthesis')
        return x
    result = one()
    if i != len(ts) or not isinstance(result, list) or not result or result[0] != 'define':
        raise Error('expected one PDDL define form')
    return result

def section(tree, key):
    for x in tree[1:]:
        if isinstance(x, list) and x and x[0] == key: return x[1:]
    return None

def typed(xs):
    out, pending, i = [], [], 0
    while i < len(xs):
        x = xs[i]
        if not isinstance(x, str): raise Error('malformed typed list')
        if x == '-':
            if not pending or i + 1 == len(xs) or not isinstance(xs[i + 1], str): raise Error('malformed typed list')
            out += [(v, xs[i + 1]) for v in pending]; pending = []; i += 2
        else: pending.append(x); i += 1
    return out + [(v, 'object') for v in pending]

def atom(x):
    if not isinstance(x, list) or not x or not isinstance(x[0], str) or any(isinstance(y, list) for y in x[1:]):
        raise Error('expected a propositional atom')
    return tuple(x)

def literals(x, where, effects=False):
    if not isinstance(x, list) or not x: raise Error('malformed ' + where)
    op = x[0]
    if op == 'and':
        p, n = [], []
        for y in x[1:]:
            a, b = literals(y, where, effects); p += a; n += b
        return p, n
    if effects and op in {'increase','decrease','assign','scale-up','scale-down'}: return [], []
    if op == 'not':
        if len(x) != 2: raise Error('malformed negation in ' + where)
        return [], [atom(x[1])]
    if op in {'or','forall','exists','imply','when','>','<','>=','<='}:
        raise Error('unsupported ' + op + ' in ' + where)
    return [atom(x)], []

def read_domain(path):
    t = parse(path)
    parents = {'object': None}; parents.update(dict(typed(section(t, ':types') or [])))
    schemas = []
    for x in t[1:]:
        if not (isinstance(x, list) and len(x) >= 2 and x[0] == ':action'): continue
        fields, i = {}, 2
        while i < len(x):
            if not isinstance(x[i], str) or not x[i].startswith(':') or i + 1 >= len(x): raise Error('malformed action ' + x[1])
            fields[x[i]] = x[i + 1]; i += 2
        params = typed(fields.get(':parameters', []))
        if any(not v.startswith('?') for v, _ in params): raise Error('invalid parameter in ' + x[1])
        pp, pn = literals(fields.get(':precondition', ['and']), 'precondition')
        add, delete = literals(fields.get(':effect', ['and']), 'effect', True)
        if any(a[0] == '=' for a in add + delete): raise Error('equality effects are unsupported')
        schemas.append((x[1], params, pp, pn, add, delete))
    if not schemas: raise Error('domain declares no actions')
    return parents, typed(section(t, ':constants') or []), schemas

def read_problem(path):
    t = parse(path); init = set()
    raw = section(t, ':init')
    if raw is None: raise Error('problem has no init')
    for x in raw:
        if isinstance(x, list) and x and x[0] == '=': continue
        p, n = literals(x, 'initial state')
        if n: raise Error('negative initial facts unsupported')
        init.update(p)
    goal = section(t, ':goal')
    if goal is None or len(goal) != 1: raise Error('problem has malformed goal')
    gp, gn = literals(goal[0], 'goal')
    return typed(section(t, ':objects') or []), frozenset(init), gp, gn

def subtype(actual, required, parents):
    seen = set()
    while actual is not None and actual not in seen:
        if actual == required: return True
        seen.add(actual); actual = parents.get(actual)
    return False

def term(x, env): return env[x] if isinstance(x, str) and x.startswith('?') else x
def grounded(a, env): return tuple(term(x, env) for x in a)
def equal(a, env):
    if len(a) != 3: raise Error('equality must have two terms')
    return term(a[1], env) == term(a[2], env)
def holds(pos, neg, state, env):
    for a in pos:
        if not (equal(a, env) if a[0] == '=' else grounded(a, env) in state): return False
    for a in neg:
        if equal(a, env) if a[0] == '=' else grounded(a, env) in state: return False
    return True

def successors(schema, state, types, parents):
    name, params, pp, pn, add, delete = schema
    index = defaultdict(list)
    for f in state: index[f[0]].append(f)
    pats = sorted((a for a in pp if a[0] != '='), key=lambda a: len(index[a[0]]))
    envs = [{}]
    for pat in pats:
        nxt = []
        for env in envs:
            for fact in index[pat[0]]:
                if len(fact) != len(pat): continue
                e, good = dict(env), True
                for q, v in zip(pat[1:], fact[1:]):
                    if q.startswith('?'):
                        if q in e and e[q] != v: good = False; break
                        e[q] = v
                    elif q != v: good = False; break
                if good: nxt.append(e)
        envs = nxt
        if not envs: return
    choices = [(v, [o for o, typ in types.items() if subtype(typ, wanted, parents)]) for v, wanted in params]
    for env in envs:
        if any(v in env and env[v] not in vals for v, vals in choices): continue
        missing = [(v, vals) for v, vals in choices if v not in env]
        if any(not vals for _, vals in missing): continue
        products = itertools.product(*(vals for _, vals in missing)) if missing else [()]
        for values in products:
            e = dict(env); e.update(zip((v for v, _ in missing), values))
            if holds(pp, pn, state, e):
                ns = frozenset((set(state) - {grounded(a, e) for a in delete}) | {grounded(a, e) for a in add})
                yield name, tuple(e[v] for v, _ in params), ns

def replay(parents, schemas, initial, gp, gn, types, plan):
    table, state = {x[0]: x for x in schemas}, initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in table: raise Error('undeclared action at step %d' % step)
        _, params, pp, pn, add, delete = table[name]
        if len(args) != len(params): raise Error('wrong arity at step %d' % step)
        if any(a not in types or not subtype(types[a], req, parents) for a, (_, req) in zip(args, params)):
            raise Error('type error at step %d' % step)
        env = dict(zip((v for v, _ in params), args))
        if not holds(pp, pn, state, env): raise Error('precondition failure at step %d' % step)
        state = frozenset((set(state) - {grounded(a, env) for a in delete}) | {grounded(a, env) for a in add})
    if not holds(gp, gn, state, {}): raise Error('final state does not satisfy goal')

def solve(parents, constants, schemas, objects, initial, gp, gn, limit, weight):
    types = dict(constants); types.update(dict(objects))
    if any(t not in parents for t in types.values()): raise Error('undeclared object type')
    if holds(gp, gn, initial, {}): return [], 0
    def heuristic(s):
        return sum(not (equal(a,{}) if a[0] == '=' else a in s) for a in gp) + sum(equal(a,{}) if a[0] == '=' else a in s for a in gn)
    queue, serial, best, previous = [], itertools.count(), {initial: 0}, {}
    heapq.heappush(queue, (weight * heuristic(initial), 0, next(serial), initial)); expanded = 0
    while queue:
        _, cost, _, state = heapq.heappop(queue)
        if best.get(state) != cost: continue
        if holds(gp, gn, state, {}):
            plan, cur = [], state
            while cur != initial:
                cur, action = previous[cur]; plan.append(action)
            plan.reverse(); replay(parents, schemas, initial, gp, gn, types, plan)
            return plan, expanded
        expanded += 1
        if expanded > limit: raise Error('search expansion limit exceeded (%d)' % limit)
        for schema in schemas:
            for name, args, nxt in successors(schema, state, types, parents):
                nc = cost + 1
                if nc >= best.get(nxt, 10**30): continue
                best[nxt], previous[nxt] = nc, (state, (name, args))
                heapq.heappush(queue, (nc + weight * heuristic(nxt), nc, next(serial), nxt))
    raise Error('state space exhausted without a plan')

def resolve(root, value):
    p = Path(value); return p if p.is_absolute() else root / p

def process(entry, root, limit, weight):
    for k in ('id','domain','problem','plan_output'):
        if k not in entry: raise Error('manifest entry lacks ' + k)
    parents, constants, schemas = read_domain(resolve(root, entry['domain']))
    objects, initial, gp, gn = read_problem(resolve(root, entry['problem']))
    plan, expanded = solve(parents, constants, schemas, objects, initial, gp, gn, limit, weight)
    output = resolve(root, entry['plan_output']); output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.tmp')
    temporary.write_text(''.join('%s(%s)\n' % (n, ', '.join(a)) for n, a in plan))
    temporary.replace(output)
    return {'id': entry['id'], 'ok': True, 'plan_output': str(output), 'steps': len(plan), 'expanded': expanded}

def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict): raise Error('request must be a JSON object')
        root = Path(request.get('root', '/app'))
        manifest_path = resolve(root, request.get('problem_json', str(root / 'problem.json')))
        manifest = json.loads(manifest_path.read_text())
        limit, weight = request.get('max_expansions', 5000000), request.get('weight', 3)
        if not isinstance(manifest, list) or not manifest: raise Error('problem.json must be a nonempty array')
        if not isinstance(limit, int) or limit <= 0 or not isinstance(weight, (int, float)) or weight <= 0: raise Error('invalid search settings')
        results = []
        for entry in manifest:
            try:
                if not isinstance(entry, dict): raise Error('manifest entry is not an object')
                results.append(process(entry, root, limit, weight))
            except Exception as exc:
                results.append({'id': entry.get('id', '<unknown>') if isinstance(entry, dict) else '<unknown>', 'ok': False, 'error': str(exc)})
        print(json.dumps({'ok': all(x['ok'] for x in results), 'results': results}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc), 'results': []}, sort_keys=True))

if __name__ == '__main__': main()
