import itertools,re
class PDDLError(Exception): pass

def sx(path):
 t=re.findall(r'[()]|[^\s()]+',re.sub(r';[^\n]*','',open(path,encoding='utf8').read()).lower()); i=0
 def f():
  nonlocal i
  if i>=len(t): raise PDDLError('unexpected end')
  x=t[i];i+=1
  if x!='(': return x
  a=[]
  while i<len(t) and t[i]!=')': a.append(f())
  if i==len(t): raise PDDLError('unclosed list')
  i+=1;return a
 r=f()
 if i!=len(t): raise PDDLError('extra tokens')
 return r

def typed(a,default='object'):
 out=[]; q=[];i=0
 while i<len(a):
  if a[i]=='-':
   if i+1>=len(a): raise PDDLError('bad type')
   out += [(x,a[i+1]) for x in q];q=[];i+=2
  else:q.append(a[i]);i+=1
 return out+[(x,default) for x in q]
def fields(a,start=1):
 d={};i=start
 while i<len(a):
  if isinstance(a[i],str) and a[i].startswith(':') and i+1<len(a):d[a[i]]=a[i+1];i+=2
  else:i+=1
 return d
def load(dp,pp):
 d=sx(dp); p=sx(pp); types={'object':None}; const={}; acts=[]
 for x in d[1:]:
  if not isinstance(x,list) or not x:continue
  if x[0]==':types':types.update(typed(x[1:]))
  elif x[0]==':constants':const.update(typed(x[1:]))
  elif x[0]==':action':
   z=fields(x,2)
   if not all(k in z for k in (':parameters',':precondition',':effect')):raise PDDLError('incomplete action')
   acts.append((x[1],typed(z[':parameters']),z[':precondition'],z[':effect']))
 obj=dict(const); init=set(); goal=None
 for x in p[1:]:
  if not isinstance(x,list) or not x:continue
  if x[0]==':objects':obj.update(typed(x[1:]))
  elif x[0]==':init':init|={tuple(y) for y in x[1:] if isinstance(y,list) and y and y[0]!='not'}
  elif x[0]==':goal':goal=x[1]
 if not acts or goal is None:raise PDDLError('missing actions or goal')
 return {'types':types,'actions':acts},{'objects':obj,'init':frozenset(init),'goal':goal}
def sub(a,w,t):
 while a is not None:
  if a==w:return True
  a=t.get(a)
 return False
def atom(x,e):return tuple(e.get(y,y) for y in x)
def form(x,s,e,o,t):
 op=x[0]
 if op=='and':return all(form(y,s,e,o,t) for y in x[1:])
 if op=='or':return any(form(y,s,e,o,t) for y in x[1:])
 if op=='not':return not form(x[1],s,e,o,t)
 if op=='imply':return not form(x[1],s,e,o,t) or form(x[2],s,e,o,t)
 if op=='=':return e.get(x[1],x[1])==e.get(x[2],x[2])
 if op in ('forall','exists'):
  es=[dict(e)]
  for v,q in typed(x[1]):es=[dict(a,**{v:z}) for a in es for z,k in o.items() if sub(k,q,t)]
  return (all if op=='forall' else any)(form(x[2],s,a,o,t) for a in es)
 return atom(x,e) in s
def eff(x,s,e,o,t):
 op=x[0]
 if op=='and':
  a=set();d=set()
  for y in x[1:]:u,v=eff(y,s,e,o,t);a|=u;d|=v
  return a,d
 if op=='not':return set(),{atom(x[1],e)}
 if op=='when':return eff(x[2],s,e,o,t) if form(x[1],s,e,o,t) else (set(),set())
 if op=='forall':
  vs=typed(x[1]);a=set();d=set()
  for q in itertools.product(*[[z for z,k in o.items() if sub(k,w,t)] for _,w in vs]):
   u,v=eff(x[2],s,dict(e,**dict(zip([v for v,_ in vs],q))),o,t);a|=u;d|=v
  return a,d
 return {atom(x,e)},set()
def parse(text):
 r=[]
 for raw in text.splitlines():
  z=raw.split(';',1)[0].strip().lower()
  if not z:continue
  m=re.fullmatch(r'([\w-]+)\s*\(([^()]*)\)',z)
  if m:r.append((m[1],tuple(x for x in re.split(r'[\s,]+',m[2].strip()) if x)));continue
  m=re.fullmatch(r'\(\s*([\w-]+)((?:\s+[\w-]+)*)\s*\)',z)
  if m:r.append((m[1],tuple(m[2].split())));continue
  raise PDDLError('bad plan line: '+raw)
 return r
def validate(d,p,plan):
 sc={n:(q,pre,fx) for n,q,pre,fx in d['actions']};s=p['init']
 for i,(n,args) in enumerate(plan,1):
  if n not in sc:return False,'step %d unknown action'%i,None
  q,pre,fx=sc[n]
  if len(q)!=len(args):return False,'step %d wrong arity'%i,None
  e={}
  for (v,w),z in zip(q,args):
   if z not in p['objects'] or not sub(p['objects'][z],w,d['types']):return False,'step %d bad type'%i,None
   e[v]=z
  if not form(pre,s,e,p['objects'],d['types']):return False,'step %d precondition'%i,None
  a,x=eff(fx,s,e,p['objects'],d['types']);s=frozenset((set(s)-x)|a)
 return (True,'valid',s) if form(p['goal'],s,{},p['objects'],d['types']) else (False,'final goal unsatisfied',s)
def render(p):return ''.join('%s(%s)\n'%(n,', '.join(a)) for n,a in p)
