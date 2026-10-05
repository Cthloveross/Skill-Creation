#!/usr/bin/env python3
"""Typed classical-PDDL manifest solver. JSON stdin -> JSON stdout."""
import heapq, itertools, json, re, sys
from collections import defaultdict
from pathlib import Path

class Error(Exception): pass

def tokens(s):
    return re.findall(r'\(|\)|[^\s()]+', re.sub(r';[^\n]*', '', s).lower())

def parse_file(path):
    ts, i = tokens(Path(path).read_text(encoding='utf-8')), 0
    def one():
        nonlocal i
        if i >= len(ts): raise Error('unexpected end of PDDL')
        x = ts[i]; i += 1
        if x == '(':
            out = []
            while i < len(ts) and ts[i] != ')': out.append(one())
            if i == len(ts): raise Error('unclosed parenthesis')
            i += 1; return out
        if x == ')': raise Error('unexpected closing parenthesis')
        return x
    out = one()
    if i != len(ts) or not isinstance(out, list) or not out or out[0] != 'define':
        raise Error('expected exactly one (define ...) form')
    return out

def sec(tree, name):
    for x in tree[1:]:
        if isinstance(x, list) and x and x[0] == name: return x[1:]
    return None

def typed(xs):
    out, pending, i = [], [], 0
    while i < len(xs):
        x = xs[i]
        if not isinstance(x, str): raise Error('nested item in typed list')
        if x == '-':
            if not pending or i + 1 >= len(xs) or not isinstance(xs[i+1], str):
                raise Error('malformed typed list')
            out += [(v, xs[i+1]) for v in pending]; pending = []; i += 2
        else: pending.append(x); i += 1
    return out + [(v, 'object') for v in pending]

def atom(x):
    if not isinstance(x, list) or not x or not isinstance(x[0], str) or any(isinstance(v, list) for v in x[1:]):
        raise Error('expected a propositional atom')
    return tuple(x)

def logic(x, where, effect=False):
    if not isinstance(x, list) or not x: raise Error('malformed ' + where)
    op = x[0]
    if op == 'and':
        p, n = [], []
        for y in x[1:]:
            a, b = logic(y, where, effect); p += a; n += b
        return p, n
    if effect and op in ('increase','decrease','assign','scale-up','scale-down'):
        return [], []
    if op == 'not':
        if len(x) != 2: raise Error('malformed negation in ' + where)
        return [], [atom(x[1])]
    if op in ('or','forall','exists','imply','when') or op in ('>','<','>=','<='):
        raise Error('unsupported ' + str(op) + ' in ' + where)
    return [atom(x)], []

def domain(path):
    t = parse_file(path); parents = {'object': None}
    parents.update(dict(typed(sec(t, ':types') or [])))
    actions = []
    for d in t[1:]:
        if not (isinstance(d, list) and len(d) >= 2 and d[0] == ':action'): continue
        f, i = {}, 2
        while i < len(d):
            if not isinstance(d[i], str) or not d[i].startswith(':') or i + 1 >= len(d):
                raise Error('malformed action ' + d[1])
            f[d[i]] = d[i+1]; i += 2
        if not isinstance(f.get(':parameters'), list): raise Error('action lacks parameters: ' + d[1])
        params = typed(f[':parameters'])
        if any(not v.startswith('?') for v, _ in params): raise Error('non-variable action parameter')
        pp, pn = logic(f.get(':precondition', ['and']), 'precondition', False)
        add, delete = logic(f.get(':effect', ['and']), 'effect', True)
        if any(x[0] == '=' for x in add + delete): raise Error('equality effect unsupported')
        actions.append((d[1], params, pp, pn, add, delete))
    if not actions: raise Error('domain declares no actions')
    return parents, typed(sec(t, ':constants') or []), actions

def problem(path):
    t = parse_file(path); initial = set()
    raw = sec(t, ':init')
    if raw is None: raise Error('problem has no :init')
    for x in raw:
        # PDDL numeric fluent initializers have nested function terms.
        if isinstance(x, list) and x and x[0] == '=': continue
        p, n = logic(x, 'initial state')
        if n: raise Error('negative initial literals unsupported')
        initial.update(p)
    g = sec(t, ':goal')
    if g is None or len(g) != 1: raise Error('problem has malformed :goal')
    gp, gn = logic(g[0], 'goal')
    return typed(sec(t, ':objects') or []), frozenset(initial), gp, gn

def subtype(actual, need, parents):
    seen = set()
    while actual is not None and actual not in seen:
        if actual == need: return True
        seen.add(actual); actual = parents.get(actual)
    return False

def sub(x, env): return env[x] if isinstance(x, str) and x.startswith('?') else x
def ground(x, env): return tuple(sub(v, env) for v in x)
def eq(x, env):
    if len(x) != 3: raise Error('equality must have two terms')
    return sub(x[1], env) == sub(x[2], env)
def holds(pos, neg, state, env):
    for x in pos:
        if not (eq(x, env) if x[0] == '=' else ground(x, env) in state): return False
    for x in neg:
        if eq(x, env) if x[0] == '=' else ground(x, env) in state: return False
    return True

def applicable(schema, state, types, parents):
    name, params, pp, pn, add, delete = schema
    bypred = defaultdict(list)
    for f in state: bypred[f[0]].append(f)
    patterns = sorted((x for x in pp if x[0] != '='), key=lambda x: len(bypred[x[0]]))
    envs = [{}]
    for pat in patterns:
        nxt = []
        for env in envs:
            for fact in bypred[pat[0]]:
                if len(fact) != len(pat): continue
                e, good = dict(env), True
                for q, value in zip(pat[1:], fact[1:]):
                    if q.startswith('?'):
                        if q in e and e[q] != value: good = False; break
                        e[q] = value
                    elif q != value: good = False; break
                if good: nxt.append(e)
        envs = nxt
        if not envs: return
    options = [(v, [o for o, typ in types.items() if subtype(typ, want, parents)]) for v, want in params]
    for e in envs:
        if any(v in e and e[v] not in vals for v, vals in options): continue
        missing = [(v, vals) for v, vals in options if v not in e]
        if any(not vals for _, vals in missing): continue
        for values in (itertools.product(*(z for _, z in missing)) if missing else [()]):
            z = dict(e); z.update(dict(zip((v for v, _ in missing), values)))
            if holds(pp, pn, state, z):
                yield (name, tuple(z[v] for v, _ in params),
                       frozenset((set(state) - {ground(x,z) for x in delete}) | {ground(x,z) for x in add}))

def solve(parents, constants, actions, objects, initial, gp, gn, limit, weight):
    types = dict(constants)
    for o, typ in objects:
        if o in types and types[o] != typ: raise Error('conflicting type for ' + o)
        types[o] = typ
    if any(t not in parents for t in types.values()): raise Error('object has undeclared type')
    goal = lambda s: holds(gp, gn, s, {})
    if goal(initial): return [], 0, types
    def h(s): return sum((not eq(x,{}) if x[0]=='=' else x not in s) for x in gp) + sum((eq(x,{}) if x[0]=='=' else x in s) for x in gn)
    q, counter, best, prev = [], itertools.count(), {initial: 0}, {}
    heapq.heappush(q, (weight*h(initial), h(initial), 0, next(counter), initial)); expanded = 0
    while q:
        _, _, cost, _, state = heapq.heappop(q)
        if best.get(state) != cost: continue
        if goal(state):
            plan, cur = [], state
            while cur != initial:
                cur, act = prev[cur]; plan.append(act)
            plan.reverse(); replay(parents, actions, initial, gp, gn, types, plan)
            return plan, expanded, types
        expanded += 1
        if expanded > limit: raise Error('search expansion limit exceeded (%d)' % limit)
        for a in actions:
            for name, args, nxt in applicable(a, state, types, parents):
                nc = cost + 1
                if nc >= best.get(nxt, 10**30): continue
                best[nxt], prev[nxt] = nc, (state, (name, args)); nh = h(nxt)
                heapq.heappush(q, (nc + weight*nh, nh, nc, next(counter), nxt))
    raise Error('state space exhausted without a plan')

def replay(parents, actions, initial, gp, gn, types, plan):
    table, state = {a[0]:a for a in actions}, initial
    for step, (name, args) in enumerate(plan, 1):
        if name not in table: raise Error('undeclared action at step %d' % step)
        _, params, pp, pn, add, delete = table[name]
        if len(args) != len(params): raise Error('wrong arity at step %d' % step)
        env = dict(zip((v for v,_ in params), args))
        if any(x not in types or not subtype(types[x], req, parents) for x, (_,req) in zip(args, params)):
            raise Error('type error at step %d' % step)
        if not holds(pp, pn, state, env): raise Error('precondition fails at step %d' % step)
        state = frozenset((set(state)-{ground(x,env) for x in delete}) | {ground(x,env) for x in add})
    if not holds(gp, gn, state, {}): raise Error('final state does not satisfy goal')

def resolve(root, value):
    p = Path(value); return p if p.is_absolute() else root / p

def entry(e, root, limit, weight):
    for k in ('id','domain','problem','plan_output'):
        if k not in e: raise Error('manifest entry lacks ' + k)
    parents, constants, actions = domain(resolve(root, e['domain']))
    objects, initial, gp, gn = problem(resolve(root, e['problem']))
    plan, expanded, _ = solve(parents, constants, actions, objects, initial, gp, gn, limit, weight)
    out = resolve(root, e['plan_output']); out.parent.mkdir(parents=True, exist_ok=True)
    data = ''.join('%s(%s)\n' % (n, ', '.join(a)) for n, a in plan)
    tmp = out.with_name(out.name + '.tmp'); tmp.write_text(data, encoding='utf-8'); tmp.replace(out)
    return {'id':e['id'], 'ok':True, 'plan_output':str(out), 'steps':len(plan), 'expanded':expanded}

def main():
    try:
        r = json.load(sys.stdin)
        if not isinstance(r, dict): raise Error('request must be an object')
        root = Path(r.get('root','/app')); mp = resolve(root, r.get('problem_json', str(root/'problem.json')))
        manifest = json.loads(mp.read_text(encoding='utf-8'))
        limit, weight = r.get('max_expansions',5000000), r.get('weight',3)
        if not isinstance(manifest,list) or not manifest: raise Error('problem.json must be a nonempty array')
        if not isinstance(limit,int) or limit <= 0 or not isinstance(weight,(int,float)) or weight <= 0: raise Error('invalid search limits')
        results=[]
        for e in manifest:
            try:
                if not isinstance(e,dict): raise Error('manifest entry is not an object')
                results.append(entry(e,root,limit,weight))
            except Exception as x: results.append({'id':e.get('id','<unknown>') if isinstance(e,dict) else '<unknown>','ok':False,'error':str(x)})
        print(json.dumps({'ok':all(x['ok'] for x in results),'results':results}, sort_keys=True))
    except Exception as x: print(json.dumps({'ok':False,'error':str(x),'results':[]}, sort_keys=True))
if __name__ == '__main__': main()
