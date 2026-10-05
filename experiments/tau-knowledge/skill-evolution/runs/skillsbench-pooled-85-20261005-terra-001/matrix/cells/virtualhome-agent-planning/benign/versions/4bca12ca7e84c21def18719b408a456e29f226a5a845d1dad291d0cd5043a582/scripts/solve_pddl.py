#!/usr/bin/env python3
"""Typed classical-PDDL solver/validator. JSON stdin -> JSON stdout."""
import argparse, collections, heapq, itertools, json, os, re, shutil, subprocess, sys, tempfile, time

SPECIAL = {'and','or','not','when','forall','exists','imply','=','increase','decrease','assign','scale-up','scale-down'}

def toks(text):
    text = re.sub(r';[^\n]*', '', text)
    return re.findall(r'\(|\)|[^\s()]+', text.lower())

def sexpr(text):
    out=[]; stack=[out]
    for x in toks(text):
        if x == '(':
            a=[]; stack[-1].append(a); stack.append(a)
        elif x == ')':
            if len(stack)==1: raise ValueError('unmatched )')
            stack.pop()
        else: stack[-1].append(x)
    if len(stack)!=1: raise ValueError('unclosed (')
    if len(out)!=1: raise ValueError('PDDL must contain one top-level expression')
    return out[0]

def sections(root):
    if not isinstance(root,list) or not root or root[0] != 'define': raise ValueError('not a define form')
    return root[1:]

def typed(words, default='object'):
    ans=[]; pending=[]; i=0
    while i < len(words):
        x=words[i]
        if x == '-' and i+1 < len(words):
            ans += [(p,words[i+1]) for p in pending]; pending=[]; i += 2
        else: pending.append(x); i += 1
    ans += [(p,default) for p in pending]
    return ans

def atom(x, env):
    if not isinstance(x,list) or not x: raise ValueError('expected atomic formula: %r' % (x,))
    return tuple(env.get(y,y) for y in x)

def pred(x): return x[0] if isinstance(x,list) and x else None

def atoms_in(x):
    """Atoms mentioned in a formula, excluding equality and control keywords."""
    if not isinstance(x,list) or not x: return []
    if x[0] in SPECIAL:
        r=[]
        for y in x[1:]: r += atoms_in(y)
        return r
    return [x]

class Model:
    def __init__(self, domain_file, problem_file):
        self.domain_file=domain_file; self.problem_file=problem_file
        d=sections(sexpr(open(domain_file,encoding='utf8').read()))
        p=sections(sexpr(open(problem_file,encoding='utf8').read()))
        self.types={'object':None}; self.constants=[]; self.schemas=[]
        self.predicates=set(); self.effect_preds=set()
        for s in d:
            if not isinstance(s,list) or not s: continue
            if s[0]==':types':
                for n,parent in typed(s[1:]): self.types[n]=parent
            elif s[0]==':constants': self.constants += typed(s[1:])
            elif s[0]==':predicates':
                self.predicates.update(q[0] for q in s[1:] if isinstance(q,list) and q)
            elif s[0]==':action': self.schemas.append(self.parse_action(s))
            elif s[0] in (':durative-action',':derived'):
                raise ValueError('durative actions and derived predicates are unsupported by the built-in solver')
        self.objects=list(self.constants)
        self.init=set(); self.goal=['and']
        for s in p:
            if not isinstance(s,list) or not s: continue
            if s[0]==':objects': self.objects += typed(s[1:])
            elif s[0]==':init':
                for q in s[1:]:
                    if isinstance(q,list) and q and q[0] not in ('=', 'increase', 'assign'):
                        if q[0]=='not': raise ValueError('negative init facts unsupported')
                        self.init.add(tuple(q))
            elif s[0]==':goal': self.goal=s[1] if len(s)>1 else ['and']
        self.objtype={n:t for n,t in self.objects}
        self.bytype=collections.defaultdict(list)
        for n,t in self.objects:
            for u in self.types_of(t): self.bytype[u].append(n)
        for a in self.schemas: self.mark_effects(a['eff'])
        self.static_preds=self.predicates-self.effect_preds
        self.static={x for x in self.init if x[0] in self.static_preds}
        self.dynamic_init=frozenset(x for x in self.init if x[0] not in self.static_preds)

    def parse_action(self,s):
        if len(s)<2: raise ValueError('malformed action')
        a={'name':s[1], 'params':[], 'pre':['and'], 'eff':['and']}
        i=2
        while i<len(s):
            key=s[i]
            if key==':parameters' and i+1<len(s): a['params']=typed(s[i+1]); i+=2
            elif key==':precondition' and i+1<len(s): a['pre']=s[i+1]; i+=2
            elif key==':effect' and i+1<len(s): a['eff']=s[i+1]; i+=2
            else: i+=1
        return a

    def types_of(self,t):
        seen=set()
        while t and t not in seen:
            seen.add(t); yield t; t=self.types.get(t)

    def mark_effects(self,e):
        if not isinstance(e,list) or not e: return
        op=e[0]
        if op=='and':
            for z in e[1:]: self.mark_effects(z)
        elif op=='not':
            if len(e)>1 and isinstance(e[1],list) and e[1]: self.effect_preds.add(e[1][0])
        elif op=='when':
            if len(e)>2: self.mark_effects(e[2])
        elif op=='forall':
            if len(e)>2: self.mark_effects(e[2])
        elif op not in SPECIAL: self.effect_preds.add(op)

    def formula(self, f, state, env):
        if not isinstance(f,list) or not f: return True
        op=f[0]
        if op=='and': return all(self.formula(x,state,env) for x in f[1:])
        if op=='or': return any(self.formula(x,state,env) for x in f[1:])
        if op=='not': return not self.formula(f[1],state,env)
        if op=='imply': return (not self.formula(f[1],state,env)) or self.formula(f[2],state,env)
        if op=='=': return env.get(f[1],f[1]) == env.get(f[2],f[2])
        if op in ('forall','exists'):
            vs=typed(f[1]); pools=[self.bytype[t] for _,t in vs]
            vals=(self.formula(f[2],state,dict(env,**dict(zip([v for v,_ in vs],z)))) for z in itertools.product(*pools))
            return all(vals) if op=='forall' else any(vals)
        return atom(f,env) in state

    def simple_literals(self,f,env):
        """Return conjunction's positive/negative dynamic atoms, else (None,None)."""
        pos=[]; neg=[]
        def walk(x):
            if not isinstance(x,list) or not x: return False
            if x[0]=='and': return all(walk(y) for y in x[1:])
            if x[0]=='not' and len(x)==2 and isinstance(x[1],list) and x[1] and x[1][0] not in SPECIAL:
                a=atom(x[1],env)
                (neg if a[0] not in self.static_preds else []).append(a); return True
            if x[0] not in SPECIAL:
                a=atom(x,env)
                (pos if a[0] not in self.static_preds else []).append(a); return True
            return False
        return (tuple(pos),tuple(neg)) if walk(f) else (None,None)

    def unconditional_adds(self,e,env):
        r=[]
        def walk(x):
            if not isinstance(x,list) or not x: return
            if x[0]=='and':
                for z in x[1:]: walk(z)
            elif x[0] not in SPECIAL: r.append(atom(x,env))
        walk(e); return tuple(a for a in r if a[0] not in self.static_preds)

    def apply_effect(self,e,state,env):
        add=set(); delete=set()
        def walk(x,ee):
            if not isinstance(x,list) or not x: return
            op=x[0]
            if op=='and':
                for z in x[1:]: walk(z,ee)
            elif op=='not' and len(x)>1:
                a=atom(x[1],ee)
                if a[0] not in self.static_preds: delete.add(a)
            elif op=='when' and len(x)>2:
                if self.formula(x[1], state|self.static, ee): walk(x[2],ee)
            elif op=='forall' and len(x)>2:
                vs=typed(x[1]); pools=[self.bytype[t] for _,t in vs]
                for z in itertools.product(*pools): walk(x[2],dict(ee,**dict(zip([v for v,_ in vs],z))))
            elif op in ('increase','decrease','assign','scale-up','scale-down'):
                raise ValueError('numeric effects unsupported')
            elif op not in SPECIAL:
                a=atom(x,ee)
                if a[0] not in self.static_preds: add.add(a)
        walk(e,env)
        return frozenset((set(state)-delete)|add)

    def static_constraints(self, f):
        """Positive static atomic conjuncts, used only to reduce sound grounding."""
        r=[]
        def walk(x):
            if not isinstance(x,list) or not x: return
            if x[0]=='and':
                for z in x[1:]: walk(z)
            elif x[0] not in SPECIAL and x[0] in self.static_preds: r.append(x)
        walk(f); return r

    def ground(self):
        actions=[]; seen=set(); static_by=collections.defaultdict(list)
        for x in self.static: static_by[x[0]].append(x)
        for schema in self.schemas:
            vs=[x for x,_ in schema['params']]; domains={x:self.bytype[t] for x,t in schema['params']}
            cons=self.static_constraints(schema['pre'])
            def rec(env, remaining):
                usable=[]
                for c in remaining:
                    matches=[]
                    for fact in static_by[c[0]]:
                        e=dict(env); ok=True
                        for v,val in zip(c[1:],fact[1:]):
                            if v.startswith('?'):
                                if v in e and e[v]!=val: ok=False; break
                                if val not in domains.get(v,[]): ok=False; break
                                e[v]=val
                            elif v!=val: ok=False; break
                        if ok: matches.append(e)
                    usable.append((len(matches),c,matches))
                if usable:
                    _,c,ms=min(usable,key=lambda q:q[0])
                    nr=[q for q in remaining if q is not c]
                    for e in ms: rec(e,nr)
                    return
                unknown=[v for v in vs if v not in env]
                if unknown:
                    v=min(unknown,key=lambda q:len(domains[q]))
                    for val in domains[v]:
                        e=dict(env); e[v]=val; rec(e,remaining)
                    return
                # The complete formula test below retains negative static/equality/complex semantics.
                key=(schema['name'],tuple(env[v] for v in vs))
                if key in seen: return
                seen.add(key)
                pos,neg=self.simple_literals(schema['pre'],env)
                actions.append({'name':schema['name'],'args':key[1],'env':dict(env),'pre':schema['pre'],'eff':schema['eff'],
                                'pos':pos,'neg':neg,'adds':self.unconditional_adds(schema['eff'],env)})
            rec({},cons)
        return actions

def goal_atoms(f):
    r=[]
    def walk(x):
        if not isinstance(x,list) or not x: return
        if x[0]=='and':
            for z in x[1:]: walk(z)
        elif x[0] not in SPECIAL: r.append(tuple(x))
    walk(f); return r

def internal_solve(m, limit):
    actions=m.ground()
    if not actions: return [] if m.formula(m.goal,m.static|m.dynamic_init,{}) else None
    index=collections.defaultdict(list); always=[]
    for i,a in enumerate(actions):
        if a['pos'] is None or not a['pos']: always.append(i)
        else:
            for q in a['pos']: index[q].append(i)
    goals=goal_atoms(m.goal)
    deadline=time.monotonic()+limit
    def heuristic(st):
        if not goals: return 0
        cost={x:0 for x in st|m.static}
        changed=True
        # h_add relaxed propagation. Cap iterations for malformed/no-progress domains.
        for _ in range(max(4,len(actions)+2)):
            if not changed: break
            changed=False
            for a in actions:
                if a['pos'] is None: continue
                if any(q not in cost for q in a['pos']): continue
                c=1+sum(cost[q] for q in a['pos'])
                for q in a['adds']:
                    if c < cost.get(q,10**9): cost[q]=c; changed=True
        vals=[cost.get(q,10**6) for q in goals]
        return sum(vals)
    start=m.dynamic_init
    if m.formula(m.goal,start|m.static,{}): return []
    pq=[]; serial=0; h0=heuristic(start)
    heapq.heappush(pq,(h0,0,serial,start)); parent={start:(None,None)}; best={start:0}
    while pq:
        if time.monotonic()>deadline: raise TimeoutError('internal search time limit reached')
        _,g,_,st=heapq.heappop(pq)
        if g!=best.get(st): continue
        candidates=set(always)
        for x in st: candidates.update(index.get(x,()))
        for i in candidates:
            a=actions[i]
            full=st|m.static
            if not m.formula(a['pre'],full,a['env']): continue
            ns=m.apply_effect(a['eff'],st,a['env'])
            if ns==st or g+1>=best.get(ns,10**18): continue
            parent[ns]=(st,a); best[ns]=g+1
            if m.formula(m.goal,ns|m.static,{}):
                plan=[]; cur=ns
                while parent[cur][0] is not None:
                    old,act=parent[cur]; plan.append((act['name'],act['args'])); cur=old
                return list(reversed(plan))
            serial+=1; h=heuristic(ns)
            heapq.heappush(pq,(g+1+3*h,g+1,serial,ns))
    return None

def parse_plan(text):
    out=[]
    for raw in text.splitlines():
        line=raw.strip().lower()
        if not line or line.startswith(';') or line.startswith('#'): continue
        line=re.sub(r'^\s*\d+(?:\.\d+)?\s*:\s*','',line)
        m=re.search(r'\(([^()]*)\)',line)
        body=m.group(1) if m else line
        xs=[z for z in re.split(r'[\s,]+',body.strip()) if z]
        if xs and not xs[0].startswith(';'): out.append((xs[0],tuple(xs[1:])))
    return out

def validate(m, plan):
    byname=collections.defaultdict(list)
    # Grounded instances are necessary for exact arity/type/static checking.
    for a in m.ground(): byname[(a['name'],a['args'])].append(a)
    st=m.dynamic_init
    for n,(name,args) in enumerate(plan,1):
        aa=byname.get((name,tuple(args)))
        if not aa: return {'valid':False,'step':n,'reason':'unknown action, wrong arity/type, or static-incompatible arguments: %s%s' % (name,args)}
        a=aa[0]
        if not m.formula(a['pre'],st|m.static,a['env']):
            return {'valid':False,'step':n,'reason':'precondition is false for %s%s' % (name,args)}
        try: st=m.apply_effect(a['eff'],st,a['env'])
        except Exception as e: return {'valid':False,'step':n,'reason':str(e)}
    if not m.formula(m.goal,st|m.static,{}): return {'valid':False,'step':len(plan),'reason':'final state does not satisfy goal'}
    return {'valid':True,'steps':len(plan)}

def external_fd(domain, problem, seconds):
    exe=shutil.which('fast-downward.py') or shutil.which('downward')
    if not exe: return None
    with tempfile.TemporaryDirectory(prefix='pddl-plan-') as td:
        pf=os.path.join(td,'plan')
        cmd=[exe,'--plan-file',pf,domain,problem,'--search','lazy_greedy([ff()],preferred=[ff()])']
        try: subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=max(5,int(seconds)),cwd=td,check=False)
        except (subprocess.TimeoutExpired,OSError): return None
        candidates=[pf]+[os.path.join(td,x) for x in os.listdir(td) if x.startswith('plan.')]
        for x in candidates:
            if os.path.isfile(x):
                q=parse_plan(open(x,encoding='utf8').read())
                if q: return q
    return None

def resolve(path, manifest_dir=None, output=False):
    if os.path.isabs(path): return path
    if not output and manifest_dir:
        p=os.path.join(manifest_dir,path)
        if os.path.exists(p): return p
    return os.path.abspath(path)

def solve_task(task, limit, planner, manifest_dir):
    try:
        domain=resolve(task['domain'],manifest_dir); problem=resolve(task['problem'],manifest_dir)
        output=resolve(task['plan_output'],None,True); m=Model(domain,problem)
        plan=None; source='internal'
        if planner in ('auto','fast-downward'):
            plan=external_fd(domain,problem,max(5,limit*.85)); source='fast-downward'
        if plan is None and planner != 'fast-downward': plan=internal_solve(m,limit)
        if plan is None: return {'id':task.get('id'),'status':'unsolved','reason':'no plan found by selected planner'}
        verdict=validate(m,plan)
        if not verdict['valid']: return {'id':task.get('id'),'status':'error','reason':'candidate replay failed','validation':verdict}
        os.makedirs(os.path.dirname(output) or '.',exist_ok=True)
        with open(output,'w',encoding='utf8') as f:
            for name,args in plan: f.write('%s(%s)\n' % (name,', '.join(args)))
        return {'id':task.get('id'),'status':'solved','plan_output':output,'plan_length':len(plan),'source':source,'validation':verdict}
    except TimeoutError as e: return {'id':task.get('id'),'status':'timeout','reason':str(e)}
    except Exception as e: return {'id':task.get('id'),'status':'error','reason':str(e)}

def main(inp):
    if inp.get('mode')=='validate':
        try:
            m=Model(inp['domain'],inp['problem']); p=parse_plan(open(inp['plan'],encoding='utf8').read())
            return validate(m,p)
        except Exception as e: return {'valid':False,'reason':str(e)}
    if 'tasks' in inp: tasks=inp['tasks']; md=None
    else:
        mp=inp.get('manifest','problem.json'); md=os.path.dirname(os.path.abspath(mp))
        with open(mp,encoding='utf8') as f: tasks=json.load(f)
    if not isinstance(tasks,list): raise ValueError('manifest/tasks must be an array')
    limit=float(inp.get('time_limit_sec',300)); planner=inp.get('planner','auto')
    if planner not in ('auto','fast-downward','internal'): raise ValueError('planner must be auto, fast-downward, or internal')
    return {'results':[solve_task(t,limit,planner,md) for t in tasks]}

if __name__=='__main__':
    try: print(json.dumps(main(json.load(sys.stdin)),sort_keys=True))
    except Exception as e: print(json.dumps({'status':'error','reason':str(e)})); sys.exit(2)
