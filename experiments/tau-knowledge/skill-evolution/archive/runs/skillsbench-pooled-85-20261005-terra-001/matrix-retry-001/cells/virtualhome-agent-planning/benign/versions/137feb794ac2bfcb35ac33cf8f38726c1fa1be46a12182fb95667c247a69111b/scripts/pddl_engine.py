import itertools, heapq, re, time
class PDDLError(Exception): pass

def sx(path):
    ts=re.findall(r'[()]|[^\s()]+', re.sub(r';[^\n]*','',open(path,encoding='utf8').read()).lower()); pos=0
    def read():
        nonlocal pos
        if pos>=len(ts): raise PDDLError('unexpected end of PDDL')
        x=ts[pos]; pos+=1
        if x!='(': return x
        out=[]
        while pos<len(ts) and ts[pos]!=')': out.append(read())
        if pos==len(ts): raise PDDLError('unclosed PDDL list')
        pos+=1; return out
    ans=read()
    if pos!=len(ts): raise PDDLError('extra PDDL tokens')
    return ans

def typed(xs, default='object'):
    out=[]; pending=[]; i=0
    while i<len(xs):
        if xs[i]=='-':
            if i+1>=len(xs): raise PDDLError('dangling type marker')
            out += [(x,xs[i+1]) for x in pending]; pending=[]; i+=2
        else: pending.append(xs[i]); i+=1
    return out+[(x,default) for x in pending]
def fields(x, start=1):
    out={}; i=start
    while i<len(x):
        if isinstance(x[i],str) and x[i].startswith(':') and i+1<len(x): out[x[i]]=x[i+1]; i+=2
        else: i+=1
    return out
def load(domain, problem):
    d,p=sx(domain),sx(problem); parents={'object':None}; objects={}; actions=[]
    for x in d[1:]:
        if not isinstance(x,list) or not x: continue
        if x[0]==':types': parents.update(typed(x[1:]))
        elif x[0]==':constants': objects.update(typed(x[1:]))
        elif x[0]==':action':
            f=fields(x,2)
            if not all(k in f for k in (':parameters',':precondition',':effect')): raise PDDLError('incomplete action '+str(x[1]))
            actions.append((x[1],typed(f[':parameters']),f[':precondition'],f[':effect']))
    init=set(); goal=None
    for x in p[1:]:
        if not isinstance(x,list) or not x: continue
        if x[0]==':objects': objects.update(typed(x[1:]))
        elif x[0]==':init': init|={tuple(y) for y in x[1:] if isinstance(y,list) and y and y[0]!='not'}
        elif x[0]==':goal': goal=x[1]
    if not actions or goal is None: raise PDDLError('missing actions or goal')
    return {'types':parents,'actions':actions},{'objects':objects,'init':frozenset(init),'goal':goal}
def subtype(actual, wanted, parents):
    while actual is not None:
        if actual==wanted: return True
        actual=parents.get(actual)
    return False
def atom(x, env): return tuple(env.get(v,v) for v in x)
def formula(x, state, env, objects, parents):
    op=x[0]
    if op=='and': return all(formula(y,state,env,objects,parents) for y in x[1:])
    if op=='or': return any(formula(y,state,env,objects,parents) for y in x[1:])
    if op=='not': return not formula(x[1],state,env,objects,parents)
    if op=='imply': return not formula(x[1],state,env,objects,parents) or formula(x[2],state,env,objects,parents)
    if op=='=': return env.get(x[1],x[1])==env.get(x[2],x[2])
    if op in ('forall','exists'):
        envs=[dict(env)]
        for v,t in typed(x[1]): envs=[dict(e,**{v:o}) for e in envs for o,u in objects.items() if subtype(u,t,parents)]
        values=[formula(x[2],state,e,objects,parents) for e in envs]
        return all(values) if op=='forall' else any(values)
    return atom(x,env) in state
def effects(x,state,env,objects,parents):
    op=x[0]
    if op=='and':
        adds=set(); deletes=set()
        for y in x[1:]:
            a,d=effects(y,state,env,objects,parents); adds|=a; deletes|=d
        return adds,deletes
    if op=='not': return set(),{atom(x[1],env)}
    if op=='when': return effects(x[2],state,env,objects,parents) if formula(x[1],state,env,objects,parents) else (set(),set())
    if op=='forall':
        vs=typed(x[1]); adds=set(); deletes=set(); choices=[[o for o,t in objects.items() if subtype(t,w,parents)] for _,w in vs]
        for vals in itertools.product(*choices):
            a,d=effects(x[2],state,dict(env,**dict(zip([v for v,_ in vs],vals))),objects,parents); adds|=a; deletes|=d
        return adds,deletes
    return {atom(x,env)},set()
def parse(text):
    out=[]
    for raw in text.splitlines():
        line=raw.split(';',1)[0].strip().lower()
        if not line: continue
        m=re.fullmatch(r'([\w-]+)\s*\(([^()]*)\)',line)
        if m: out.append((m[1],tuple(x for x in re.split(r'[\s,]+',m[2].strip()) if x))); continue
        m=re.fullmatch(r'\(\s*([\w-]+)((?:\s+[\w-]+)*)\s*\)',line)
        if m: out.append((m[1],tuple(m[2].split()))); continue
        raise PDDLError('bad plan line: '+raw)
    return out
def validate(d,p,plan):
    schemas={n:(v,pre,eff) for n,v,pre,eff in d['actions']}; state=p['init']
    for step,(name,args) in enumerate(plan,1):
        if name not in schemas: return False,'step %d uses unknown action'%step,None
        vs,pre,eff=schemas[name]
        if len(vs)!=len(args): return False,'step %d has wrong arity'%step,None
        env={}
        for (v,t),obj in zip(vs,args):
            if obj not in p['objects'] or not subtype(p['objects'][obj],t,d['types']): return False,'step %d has unknown or mistyped object'%step,None
            env[v]=obj
        if not formula(pre,state,env,p['objects'],d['types']): return False,'step %d has unsatisfied preconditions'%step,None
        adds,deletes=effects(eff,state,env,p['objects'],d['types']); state=frozenset((set(state)-deletes)|adds)
    return (True,'valid',state) if formula(p['goal'],state,{},p['objects'],d['types']) else (False,'final goal is unsatisfied',state)
def render(plan): return ''.join('%s(%s)\n'%(name,', '.join(args)) for name,args in plan)

def search(d,p,seconds=.1,max_expansions=20000):
    if formula(p['goal'],p['init'],{},p['objects'],d['types']): return []
    ground=[]
    for name,vs,pre,eff in d['actions']:
        choices=[[o for o,t in p['objects'].items() if subtype(t,w,d['types'])] for _,w in vs]
        for vals in itertools.product(*choices): ground.append((name,vals,vs,pre,eff))
    start=p['init']; q=[start]; prev={start:None}; deadline=time.monotonic()+max(.01,float(seconds)); head=0
    while head<len(q) and head<max_expansions and time.monotonic()<deadline:
        state=q[head]; head+=1
        for name,args,vs,pre,eff in ground:
            env={v:o for (v,_),o in zip(vs,args)}
            if not formula(pre,state,env,p['objects'],d['types']): continue
            adds,deletes=effects(eff,state,env,p['objects'],d['types']); nxt=frozenset((set(state)-deletes)|adds)
            if nxt in prev: continue
            prev[nxt]=(state,(name,args))
            if formula(p['goal'],nxt,{},p['objects'],d['types']):
                ans=[]
                while prev[nxt] is not None: nxt,a=prev[nxt]; ans.append(a)
                return list(reversed(ans))
            q.append(nxt)
    return None
