#!/usr/bin/env python3
"""Typed classical-PDDL manifest solver. Reads JSON stdin and writes JSON stdout."""
import collections, heapq, itertools, json, os, re, sys, time

LOGIC={"and","or","not","imply","=","forall","exists","when"}
NUM={"increase","decrease","assign","scale-up","scale-down"}

def parse(text):
    ts=re.findall(r"\(|\)|[^\s()]+",re.sub(r";[^\n]*","",text).lower())
    root=[]; cur=root; stack=[]
    for t in ts:
        if t=="(":
            x=[]; cur.append(x); stack.append(cur); cur=x
        elif t==")":
            if not stack: raise ValueError("unexpected )")
            cur=stack.pop()
        else: cur.append(t)
    if stack or len(root)!=1 or not isinstance(root[0],list): raise ValueError("malformed PDDL")
    return root[0]

def typed(xs, default="object"):
    ans=[]; pending=[]; i=0
    while i<len(xs):
        if xs[i]=="-":
            if i+1==len(xs) or isinstance(xs[i+1],list): raise ValueError("bad typed list")
            ans += [(x,xs[i+1]) for x in pending]; pending=[]; i+=2
        else:
            if isinstance(xs[i],list): raise ValueError("expression in typed list")
            pending.append(xs[i]); i+=1
    return ans+[(x,default) for x in pending]

def fields(x):
    d={}; i=2
    while i+1<len(x):
        if isinstance(x[i],str) and x[i].startswith(":"): d[x[i]]=x[i+1]; i+=2
        else: i+=1
    return d

class Model:
 def __init__(self,df,pf):
    with open(df,encoding="utf-8") as f: d=parse(f.read())
    with open(pf,encoding="utf-8") as f: p=parse(f.read())
    if not d or not p or d[0]!="define" or p[0]!="define": raise ValueError("expected PDDL define forms")
    self.types={"object":None}; self.schemas=[]
    for x in d[1:]:
        if not isinstance(x,list) or not x: continue
        if x[0]==":types": self.types.update(dict(typed(x[1:])))
        elif x[0]==":durative-action": raise ValueError("durative PDDL unsupported")
        elif x[0]==":action":
            q=fields(x)
            if len(x)<2 or not all(k in q for k in (":parameters",":precondition",":effect")):
                raise ValueError("incomplete action schema")
            self.schemas.append((x[1],typed(q[":parameters"]),q[":precondition"],q[":effect"]))
    if not self.schemas: raise ValueError("domain has no actions")
    self.objtype={}; init=set(); self.goal=None
    for x in p[1:]:
        if not isinstance(x,list) or not x: continue
        if x[0]==":objects": self.objtype.update(dict(typed(x[1:])))
        elif x[0]==":init":
            for a in x[1:]:
                if not isinstance(a,list) or not a: continue
                if a[0] in NUM: raise ValueError("numeric PDDL unsupported")
                if a[0] not in ("not","="): init.add(tuple(a))
        elif x[0]==":goal":
            if len(x)!=2: raise ValueError("bad goal")
            self.goal=x[1]
    if self.goal is None: raise ValueError("missing goal")
    self.bytype=collections.defaultdict(list)
    for o,t in self.objtype.items():
        for a in self.ancestors(t): self.bytype[a].append(o)
    changed=set()
    for _,_,_,e in self.schemas: self.effect_preds(e,changed)
    self.static_pred={a[0] for a in init if a[0] not in changed}
    self.static=frozenset(a for a in init if a[0] in self.static_pred)
    self.start=frozenset(a for a in init if a[0] not in self.static_pred)
 def ancestors(self,t):
    seen=set()
    while t is not None and t not in seen:
        seen.add(t); yield t; t=self.types.get(t)
 def effect_preds(self,x,out):
    if not isinstance(x,list) or not x: raise ValueError("bad effect")
    op=x[0]
    if op=="and":
        for y in x[1:]: self.effect_preds(y,out)
    elif op=="not":
        if len(x)!=2 or not isinstance(x[1],list) or not x[1]: raise ValueError("bad delete")
        out.add(x[1][0])
    elif op in ("when","forall"):
        if len(x)!=3: raise ValueError("bad conditional/quantified effect")
        self.effect_preds(x[2],out)
    elif op in NUM: raise ValueError("numeric PDDL unsupported")
    elif op not in LOGIC: out.add(op)
 def formula(self,x,state,env=None):
    env={} if env is None else env
    if not isinstance(x,list) or not x: raise ValueError("bad formula")
    op=x[0]
    if op=="and": return all(self.formula(y,state,env) for y in x[1:])
    if op=="or": return any(self.formula(y,state,env) for y in x[1:])
    if op=="not": return len(x)==2 and not self.formula(x[1],state,env)
    if op=="imply": return len(x)==3 and (not self.formula(x[1],state,env) or self.formula(x[2],state,env))
    if op=="=": return len(x)==3 and env.get(x[1],x[1])==env.get(x[2],x[2])
    if op in ("forall","exists"):
        if len(x)!=3: raise ValueError("bad quantifier")
        vs=typed(x[1]); vals=[]
        for tup in itertools.product(*[self.bytype[t] for _,t in vs]):
            e=dict(env); e.update(dict(zip([v for v,_ in vs],tup))); vals.append(self.formula(x[2],state,e))
        return all(vals) if op=="forall" else any(vals)
    return tuple(env.get(z,z) for z in x) in state
 def apply(self,e,dyn,env):
    full=set(self.static|dyn)
    def walk(x,local):
        if not isinstance(x,list) or not x: raise ValueError("bad effect")
        op=x[0]
        if op=="and":
            for y in x[1:]: walk(y,local)
        elif op=="not":
            if len(x)!=2 or not isinstance(x[1],list): raise ValueError("bad delete")
            full.discard(tuple(local.get(z,z) for z in x[1]))
        elif op=="when":
            if len(x)!=3: raise ValueError("bad conditional effect")
            if self.formula(x[1],full,local): walk(x[2],local)
        elif op=="forall":
            if len(x)!=3: raise ValueError("bad quantified effect")
            vs=typed(x[1])
            for tup in itertools.product(*[self.bytype[t] for _,t in vs]):
                q=dict(local); q.update(dict(zip([v for v,_ in vs],tup))); walk(x[2],q)
        elif op in NUM: raise ValueError("numeric PDDL unsupported")
        else: full.add(tuple(local.get(z,z) for z in x))
    walk(e,env)
    return frozenset(a for a in full if a[0] not in self.static_pred)
 def pos_conj(self,x,want_static):
    if not isinstance(x,list) or not x: return []
    if x[0]=="and":
        r=[]
        for y in x[1:]: r+=self.pos_conj(y,want_static)
        return r
    if x[0] not in LOGIC and ((x[0] in self.static_pred)==want_static): return [tuple(x)]
    return []
 def grounded(self):
    idx=collections.defaultdict(list)
    for a in self.static: idx[a[0]].append(a)
    result=[]
    for name,ps,pre,eff in self.schemas:
        vars=[v for v,_ in ps]; domains={v:self.bytype[t] for v,t in ps}
        needs=self.pos_conj(pre,True)
        def emit(e):
            miss=[v for v in vars if v not in e]
            if miss:
                v=min(miss,key=lambda z:len(domains[z]))
                for o in domains[v]: q=dict(e); q[v]=o; emit(q)
            else:
                args=tuple(e[v] for v in vars)
                dyn=tuple(tuple(e.get(z,z) for z in a) for a in self.pos_conj(pre,False))
                result.append((name,args,dict(e),pre,eff,dyn))
        def join(e,left):
            if not left: emit(e); return
            a=min(left,key=lambda z:len(idx[z[0]])); rest=list(left); rest.remove(a)
            for f in idx[a[0]]:
                if len(f)!=len(a): continue
                q=dict(e); ok=True
                for z,o in zip(a[1:],f[1:]):
                    if isinstance(z,str) and z.startswith("?"):
                        if z in q and q[z]!=o: ok=False; break
                        if o not in domains.get(z,()): ok=False; break
                        q[z]=o
                    elif z!=o: ok=False; break
                if ok: join(q,rest)
        join({},needs)
    return result

def goal_atoms(x):
    if not isinstance(x,list) or not x: return []
    if x[0]=="and": return sum((goal_atoms(y) for y in x[1:]),[])
    return [tuple(x)] if x[0] not in LOGIC else []

def search(m,limit):
    if m.formula(m.goal,m.static|m.start): return []
    acts=m.grounded()
    if not acts: return None
    byneed=collections.defaultdict(set); always=set()
    for i,a in enumerate(acts):
        if a[5]:
            for f in a[5]: byneed[f].add(i)
        else: always.add(i)
    gs=goal_atoms(m.goal)
    def h(s): return sum(g not in m.static|s for g in gs)
    end=time.monotonic()+limit; serial=0
    heap=[(h(m.start),0,0,m.start)]; best={m.start:0}; parent={m.start:(None,None)}
    while heap:
        if time.monotonic()>end: raise TimeoutError("search time limit reached")
        _,cost,_,s=heapq.heappop(heap)
        if best.get(s)!=cost: continue
        choices=set(always)
        for f in s: choices.update(byneed.get(f,()))
        for i in choices:
            name,args,e,pre,eff,_=acts[i]
            if not m.formula(pre,m.static|s,e): continue
            t=m.apply(eff,s,e)
            if t==s or cost+1>=best.get(t,10**18): continue
            best[t]=cost+1; parent[t]=(s,(name,args))
            if m.formula(m.goal,m.static|t):
                ans=[]
                while parent[t][0] is not None: t,a=parent[t]; ans.append(a)
                return ans[::-1]
            serial+=1; heapq.heappush(heap,(cost+1+h(t),cost+1,serial,t))
    return None

def readplan(path):
    out=[]
    for no,line in enumerate(open(path,encoding="utf-8"),1):
        line=line.split(";",1)[0].strip().lower()
        if not line: continue
        z=re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)",line)
        if z: args=tuple(a.strip() for a in z.group(2).split(",") if a.strip())
        else:
            z=re.fullmatch(r"\(\s*([a-z0-9_-]+)((?:\s+[a-z0-9_-]+)*)\s*\)",line)
            if not z: raise ValueError("invalid plan line %d"%no)
            args=tuple(z.group(2).split())
        out.append((z.group(1),args))
    return out

def validate(m,plan):
    ss={n:(p,pre,e) for n,p,pre,e in m.schemas}; state=m.start
    for k,(n,args) in enumerate(plan,1):
        if n not in ss: return {"valid":False,"step":k,"reason":"undeclared action"}
        ps,pre,eff=ss[n]
        if len(ps)!=len(args): return {"valid":False,"step":k,"reason":"wrong arity"}
        env=dict(zip([v for v,_ in ps],args))
        for v,t in ps:
            if env[v] not in m.objtype or t not in set(m.ancestors(m.objtype[env[v]])):
                return {"valid":False,"step":k,"reason":"ill-typed object"}
        if not m.formula(pre,m.static|state,env): return {"valid":False,"step":k,"reason":"unsatisfied precondition"}
        state=m.apply(eff,state,env)
    return {"valid":True,"steps":len(plan)} if m.formula(m.goal,m.static|state) else {"valid":False,"reason":"goal not satisfied"}

def entries(path):
    d=json.load(open(path,encoding="utf-8"))
    if isinstance(d,list): return d
    if isinstance(d,dict):
        for k in ("tasks","problems"):
            if isinstance(d.get(k),list): return d[k]
    raise ValueError("manifest must be list or tasks/problems object")
def pathof(x,base): return x if os.path.isabs(x) else os.path.join(base,x)
def check(e):
    if not isinstance(e,dict) or not all(isinstance(e.get(k),str) and e[k] for k in ("domain","problem","plan_output")): raise ValueError("entry lacks domain/problem/plan_output")
def solveone(e,base,limit):
    label=e.get("id") if isinstance(e,dict) else None
    try:
        check(e); m=Model(pathof(e["domain"],base),pathof(e["problem"],base)); plan=search(m,limit)
        if plan is None: return {"id":label,"status":"unsolved"}
        v=validate(m,plan)
        if not v["valid"]: return {"id":label,"status":"error","reason":"replay failed","validation":v}
        out=pathof(e["plan_output"],base); os.makedirs(os.path.dirname(out) or ".",exist_ok=True)
        tmp=out+".tmp"
        with open(tmp,"w",encoding="utf-8") as f:
            for n,a in plan: f.write("%s(%s)\n"%(n,", ".join(a)))
        os.replace(tmp,out); return {"id":label,"status":"solved","plan_output":out,"plan_length":len(plan),"validation":v}
    except TimeoutError as x: return {"id":label,"status":"timeout","reason":str(x)}
    except Exception as x: return {"id":label,"status":"error","reason":str(x)}
def main(q):
    manifest=os.path.abspath(q.get("manifest","problem.json")); base=os.path.dirname(manifest); es=entries(manifest)
    if q.get("mode")=="validate-manifest":
        rs=[]
        for e in es:
            try:
                check(e); out=pathof(e["plan_output"],base)
                if not os.path.isfile(out): raise ValueError("required plan output is missing: "+out)
                m=Model(pathof(e["domain"],base),pathof(e["problem"],base)); rs.append({"id":e.get("id"),"plan_output":out,**validate(m,readplan(out))})
            except Exception as x: rs.append({"id":e.get("id") if isinstance(e,dict) else None,"valid":False,"reason":str(x)})
        return {"ok":all(r.get("valid") for r in rs),"results":rs}
    limit=float(q.get("time_limit_sec",240)); rs=[solveone(e,base,limit) for e in es]
    return {"ok":all(r.get("status")=="solved" for r in rs),"results":rs}
if __name__=="__main__":
    try: print(json.dumps(main(json.load(sys.stdin)),sort_keys=True))
    except Exception as x: print(json.dumps({"ok":False,"status":"error","reason":str(x)})); sys.exit(2)
