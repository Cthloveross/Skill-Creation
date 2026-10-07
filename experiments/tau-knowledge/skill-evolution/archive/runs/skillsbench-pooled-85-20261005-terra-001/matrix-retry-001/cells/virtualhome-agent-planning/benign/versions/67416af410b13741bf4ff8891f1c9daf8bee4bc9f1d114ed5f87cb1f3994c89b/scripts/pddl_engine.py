import itertools,re,time,heapq
class PDDLError(Exception): pass

def sx(path):
 t=re.findall(r'[()]|[^\s()]+',re.sub(r';[^\n]*','',open(path,encoding='utf8').read()).lower()); i=0
 def r():
  nonlocal i
  if i>=len(t): raise PDDLError('unexpected end of PDDL')
  x=t[i];i+=1
  if x!='(': return x
  z=[]
  while i<len(t) and t[i]!=')': z.append(r())
  if i==len(t): raise PDDLError('unclosed PDDL list')
  i+=1;return z
 z=r()
 if i!=len(t): raise PDDLError('extra PDDL tokens')
 return z

def typed(a,default='object'):
 out=[]; pending=[]; i=0
 while i<len(a):
  if a[i]=='-':
   if i+1>=len(a): raise PDDLError('dangling type marker')
   out += [(x,a[i+1]) for x in pending];pending=[];i+=2
  else: pending.append(a[i]);i+=1
 return out+[(x,default) for x in pending]
def fields(a,start=1):
 d={};i=start
 while i<len(a):
  if isinstance(a[i],str) and a[i].startswith(':') and i+1<len(a): d[a[i]]=a[i+1];i+=2
  else:i+=1
 return d
def load(dp,pp):
 d,p=sx(dp),sx(pp); parents={'object':None};const={};acts=[]
 for x in d[1:]:
  if not isinstance(x,list) or not x: continue
  if x[0]==':types': parents.update(typed(x[1:]))
  elif x[0]==':constants': const.update(typed(x[1:]))
  elif x[0]==':action':
   f=fields(x,2)
   if not all(k in f for k in (':parameters',':precondition',':effect')): raise PDDLError('incomplete action '+str(x[1]))
   acts.append((x[1],typed(f[':parameters']),f[':precondition'],f[':effect']))
 obj=dict(const);init=set();goal=None
 for x in p[1:]:
  if not isinstance(x,list) or not x:continue
  if x[0]==':objects':obj.update(typed(x[1:]))
  elif x[0]==':init':init|={tuple(y) for y in x[1:] if isinstance(y,list) and y and y[0]!='not'}
  elif x[0]==':goal':goal=x[1]
 if not acts or goal is None: raise PDDLError('missing actions or goal')
 return {'types':parents,'actions':acts},{'objects':obj,'init':frozenset(init),'goal':goal}
def subtype(a,w,parents):
 while a is not None:
  if a==w:return True
  a=parents.get(a)
 return False
def atom(x,e):return tuple(e.get(v,v) for v in x)
def formula(x,s,e,o,parents):
 op=x[0]
 if op=='and':return all(formula(y,s,e,o,parents) for y in x[1:])
 if op=='or':return any(formula(y,s,e,o,parents) for y in x[1:])
 if op=='not':return not formula(x[1],s,e,o,parents)
 if op=='imply':return not formula(x[1],s,e,o,parents) or formula(x[2],s,e,o,parents)
 if op=='=':return e.get(x[1],x[1])==e.get(x[2],x[2])
 if op in ('forall','exists'):
  es=[dict(e)]
  for v,t in typed(x[1]):es=[dict(q,**{v:a}) for q in es for a,u in o.items() if subtype(u,t,parents)]
  z=[formula(x[2],s,q,o,parents) for q in es];return all(z) if op=='forall' else any(z)
 return atom(x,e) in s
def effects(x,s,e,o,parents):
 op=x[0]
 if op=='and':
  a=set();d=set()
  for y in x[1:]:q,r=effects(y,s,e,o,parents);a|=q;d|=r
  return a,d
 if op=='not':return set(),{atom(x[1],e)}
 if op=='when':return effects(x[2],s,e,o,parents) if formula(x[1],s,e,o,parents) else (set(),set())
 if op=='forall':
  vs=typed(x[1]);a=set();d=set(); choices=[[v for v,t in o.items() if subtype(t,w,parents)] for _,w in vs]
  for vals in itertools.product(*choices):q,r=effects(x[2],s,dict(e,**dict(zip([v for v,_ in vs],vals))),o,parents);a|=q;d|=r
  return a,d
 return {atom(x,e)},set()
def parse(text):
 z=[]
 for raw in text.splitlines():
  line=raw.split(';',1)[0].strip().lower()
  if not line:continue
  m=re.fullmatch(r'([\w-]+)\s*\(([^()]*)\)',line)
  if m:z.append((m[1],tuple(x for x in re.split(r'[\s,]+',m[2].strip()) if x)));continue
  m=re.fullmatch(r'\(\s*([\w-]+)((?:\s+[\w-]+)*)\s*\)',line)
  if m:z.append((m[1],tuple(m[2].split())));continue
  raise PDDLError('bad plan line: '+raw)
 return z
def validate(d,p,plan):
 sc={n:(v,pre,ef) for n,v,pre,ef in d['actions']};s=p['init']
 for i,(n,args) in enumerate(plan,1):
  if n not in sc:return False,'step %d uses unknown action'%i,None
  vs,pre,ef=sc[n]
  if len(vs)!=len(args):return False,'step %d has wrong arity'%i,None
  e={}
  for (v,t),a in zip(vs,args):
   if a not in p['objects'] or not subtype(p['objects'][a],t,d['types']):return False,'step %d has unknown or mistyped object'%i,None
   e[v]=a
  if not formula(pre,s,e,p['objects'],d['types']):return False,'step %d has unsatisfied preconditions'%i,None
  a,r=effects(ef,s,e,p['objects'],d['types']);s=frozenset((set(s)-r)|a)
 return (True,'valid',s) if formula(p['goal'],s,{},p['objects'],d['types']) else (False,'final goal is unsatisfied',s)
def render(plan):return ''.join('%s(%s)\n'%(n,', '.join(a)) for n,a in plan)

def _changed(x,out):
 if not isinstance(x,list) or not x:return
 if x[0]=='and':
  for y in x[1:]:_changed(y,out)
 elif x[0]=='not':
  if isinstance(x[1],list):out.add(x[1][0])
 elif x[0]=='when':_changed(x[2],out)
 elif x[0]=='forall':_changed(x[2],out)
 else:out.add(x[0])
def _static_atoms(x,static,out):
 if not isinstance(x,list) or not x:return
 if x[0]=='and':
  for y in x[1:]:_static_atoms(y,static,out)
 elif x[0] not in ('or','not','imply','forall','exists','=') and x[0] in static:out.append(x)
def _candidates(d,p):
 changed=set()
 for _,_,_,ef in d['actions']:_changed(ef,changed)
 static={a[0] for a in p['init'] if a and a[0] not in changed}; by={}
 for a in p['init']:
  if a and a[0] in static:by.setdefault(a[0],[]).append(a)
 ans=[]
 for n,vs,pre,ef in d['actions']:
  atoms=[];_static_atoms(pre,static,atoms); envs=[{}]
  for pat in atoms:
   nxt=[]
   for e in envs:
    for f in by.get(pat[0],[]):
     if len(f)!=len(pat):continue
     q=dict(e);ok=True
     for x,y in zip(pat[1:],f[1:]):
      if x.startswith('?'):
       if x in q and q[x]!=y:ok=False;break
       q[x]=y
      elif x!=y:ok=False;break
     if ok:nxt.append(q)
   envs=nxt
  vals=[]
  for e in envs:
   missing=[(v,t) for v,t in vs if v not in e]; choices=[[a for a,u in p['objects'].items() if subtype(u,t,d['types'])] for _,t in missing]
   for take in itertools.product(*choices):
    q=dict(e);q.update(dict(zip([v for v,_ in missing],take)));vals.append((n,tuple(q[v] for v,_ in vs),pre,ef))
  ans.extend(vals)
 return ans
def _h(g,s,e,o,t):
 if g[0]=='and':return sum(_h(x,s,e,o,t) for x in g[1:])
 if g[0]=='or':return min([_h(x,s,e,o,t) for x in g[1:]] or [0])
 return 0 if formula(g,s,e,o,t) else 1
def search(d,p,seconds=3,max_expansions=100000):
 if formula(p['goal'],p['init'],{},p['objects'],d['types']):return []
 acts=_candidates(d,p); deadline=time.monotonic()+max(.05,float(seconds)); start=p['init'];q=[];serial=0
 heapq.heappush(q,(_h(p['goal'],start,{},p['objects'],d['types']),0,serial,start)); seen={start};prev={};expanded=0
 while q and expanded<max_expansions and time.monotonic()<deadline:
  _,depth,_,s=heapq.heappop(q);expanded+=1
  for n,args,pre,ef in acts:
   e={v:a for (v,_),a in zip(next(v for nn,v,pp,ee in d['actions'] if nn==n),args)}
   if not formula(pre,s,e,p['objects'],d['types']):continue
   a,r=effects(ef,s,e,p['objects'],d['types']);ns=frozenset((set(s)-r)|a)
   if ns in seen:continue
   seen.add(ns);prev[ns]=(s,(n,args))
   if formula(p['goal'],ns,{},p['objects'],d['types']):
    out=[]
    while ns!=start:ns,z=prev[ns];out.append(z)
    return list(reversed(out))
   serial+=1;heapq.heappush(q,(_h(p['goal'],ns,{},p['objects'],d['types']),depth+1,serial,ns))
 return None
