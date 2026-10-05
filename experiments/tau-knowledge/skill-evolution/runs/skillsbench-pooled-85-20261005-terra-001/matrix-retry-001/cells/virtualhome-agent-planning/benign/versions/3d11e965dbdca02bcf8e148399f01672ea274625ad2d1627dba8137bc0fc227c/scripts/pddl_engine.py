"""Dependency-free PDDL reader and grounded ADL plan replayer."""
import itertools,re
class PDDLError(Exception): pass

def sxfile(path):
 t=re.findall(r"[()]|[^\s()]+",re.sub(r";[^\n]*","",open(path,encoding="utf8").read()).lower()); i=0
 def get():
  nonlocal i
  if i>=len(t): raise PDDLError("unexpected end")
  x=t[i];i+=1
  if x!="(": return x
  a=[]
  while True:
   if i>=len(t): raise PDDLError("unclosed list")
   if t[i]==")": i+=1;return a
   a.append(get())
 r=get()
 if i!=len(t): raise PDDLError("extra tokens")
 return r

def typed(xs,default="object"):
 ans=[]; pending=[]; i=0
 while i<len(xs):
  if xs[i]=="-":
   if i+1==len(xs): raise PDDLError("dangling type")
   ans += [(x,xs[i+1]) for x in pending];pending=[];i+=2
  else: pending.append(xs[i]);i+=1
 return ans+[(x,default) for x in pending]
def entries(root):
 if not isinstance(root,list) or not root or root[0]!="define": raise PDDLError("expected define")
 return root[1:]
def fields(a):
 d={};i=2
 while i<len(a):
  if not isinstance(a[i],str) or not a[i].startswith(":") or i+1>=len(a): raise PDDLError("malformed action")
  d[a[i]]=a[i+1];i+=2
 return d
def load(dp,pp):
 types={"object":None};constants={};actions=[]
 for x in entries(sxfile(dp)):
  if not isinstance(x,list) or not x: continue
  if x[0]==":types": types.update(typed(x[1:]))
  elif x[0]==":constants": constants.update(typed(x[1:]))
  elif x[0]==":action":
   f=fields(x)
   if not all(k in f for k in (":parameters",":precondition",":effect")): raise PDDLError("incomplete action")
   actions.append((x[1],typed(f[":parameters"]),f[":precondition"],f[":effect"]))
 if not actions: raise PDDLError("no actions")
 objs=dict(constants);init=set();goal=None
 for x in entries(sxfile(pp)):
  if not isinstance(x,list) or not x: continue
  if x[0]==":objects": objs.update(typed(x[1:]))
  elif x[0]==":init":
   for a in x[1:]:
    if not isinstance(a,list) or not a or a[0]=="not": raise PDDLError("unsupported init")
    init.add(tuple(a))
  elif x[0]==":goal":
   if len(x)!=2: raise PDDLError("malformed goal")
   goal=x[1]
 if goal is None: raise PDDLError("no goal")
 return {"types":types,"actions":actions},{"objects":objs,"init":frozenset(init),"goal":goal}
def sub(a,w,ts):
 while a is not None:
  if a==w:return True
  a=ts.get(a)
 return False
def atom(x,e):
 if not isinstance(x,list) or not x: raise PDDLError("expected atom")
 return tuple(e.get(v,v) for v in x)
def form(x,state,e,objs,ts):
 if not isinstance(x,list) or not x: raise PDDLError("bad formula")
 op=x[0]
 if op=="and":return all(form(y,state,e,objs,ts) for y in x[1:])
 if op=="or":return any(form(y,state,e,objs,ts) for y in x[1:])
 if op=="not":return not form(x[1],state,e,objs,ts)
 if op=="imply":return not form(x[1],state,e,objs,ts) or form(x[2],state,e,objs,ts)
 if op=="=":return len(x)==3 and e.get(x[1],x[1])==e.get(x[2],x[2])
 if op in ("forall","exists"):
  es=[dict(e)]
  for v,t in typed(x[1]): es=[dict(z,**{v:o}) for z in es for o,ot in objs.items() if sub(ot,t,ts)]
  q=[form(x[2],state,z,objs,ts) for z in es]
  return all(q) if op=="forall" else any(q)
 return atom(x,e) in state
def eff(x,state,e,objs,ts):
 if not isinstance(x,list) or not x: raise PDDLError("bad effect")
 op=x[0]
 if op=="and":
  a=set();d=set()
  for y in x[1:]: aa,dd=eff(y,state,e,objs,ts);a|=aa;d|=dd
  return a,d
 if op=="not":return set(),{atom(x[1],e)}
 if op=="when":return eff(x[2],state,e,objs,ts) if form(x[1],state,e,objs,ts) else (set(),set())
 if op=="forall":
  vs=typed(x[1]);a=set();d=set(); pools=[[o for o,ot in objs.items() if sub(ot,t,ts)] for _,t in vs]
  for vals in itertools.product(*pools):
   z=dict(e);z.update(dict(zip([v for v,_ in vs],vals)));aa,dd=eff(x[2],state,z,objs,ts);a|=aa;d|=dd
  return a,d
 return {atom(x,e)},set()
def validate(d,p,plan):
 schemas={n:(ps,pre,fx) for n,ps,pre,fx in d["actions"]};s=p["init"]
 for k,(n,args) in enumerate(plan,1):
  if n not in schemas:return False,"step %d: unknown action %s"%(k,n),None
  ps,pre,fx=schemas[n]
  if len(args)!=len(ps):return False,"step %d: wrong argument count"%k,None
  e={}
  for (v,t),o in zip(ps,args):
   if o not in p["objects"] or not sub(p["objects"][o],t,d["types"]):return False,"step %d: incompatible object"%k,None
   e[v]=o
  if not form(pre,s,e,p["objects"],d["types"]):return False,"step %d: unsatisfied precondition"%k,None
  a,rm=eff(fx,s,e,p["objects"],d["types"]);s=frozenset((set(s)-rm)|a)
 return (True,"valid",s) if form(p["goal"],s,{},p["objects"],d["types"]) else (False,"final goal unsatisfied",s)
def parse_plan_text(text):
 ans=[]
 for raw in text.splitlines():
  s=raw.split(";",1)[0].strip().lower()
  if not s:continue
  s=re.sub(r"^\s*[0-9.]+\s*:\s*","",s);s=re.sub(r"\s*\[[^]]+\]\s*$","",s)
  m=re.fullmatch(r"([\w-]+)\s*\(([^()]*)\)",s)
  if m: ans.append((m.group(1),tuple(x for x in re.split(r"[\s,]+",m.group(2).strip()) if x)));continue
  m=re.fullmatch(r"\(\s*([\w-]+)((?:\s+[\w-]+)*)\s*\)",s)
  if m: ans.append((m.group(1),tuple(m.group(2).split())));continue
  raise PDDLError("cannot parse plan line: "+raw)
 return ans
def render(plan):return "".join("%s(%s)\n"%(n,", ".join(a)) for n,a in plan)
