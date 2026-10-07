#!/usr/bin/env python3
"""Solve and validate typed classical PDDL plan manifests. JSON stdin/stdout."""
import collections, heapq, itertools, json, os, re, sys, time

NUM={"increase","decrease","assign","scale-up","scale-down"}
LOG={"and","or","not","imply","=","forall","exists","when"}

def sexpr(s):
    tok=re.findall(r"\(|\)|[^\s()]+",re.sub(r";[^\n]*","",s).lower())
    root=[]; stack=[root]
    for x in tok:
        if x=="(":
            n=[]; stack[-1].append(n); stack.append(n)
        elif x==")":
            if len(stack)==1: raise ValueError("unexpected closing parenthesis")
            stack.pop()
        else: stack[-1].append(x)
    if len(stack)!=1 or len(root)!=1 or not isinstance(root[0],list): raise ValueError("malformed PDDL")
    return root[0]

def typed(xs,default="object"):
    out=[]; pending=[]; i=0
    while i<len(xs):
        if xs[i]=="-":
            if i+1>=len(xs) or isinstance(xs[i+1],list): raise ValueError("malformed typed list")
            out += [(x,xs[i+1]) for x in pending]; pending=[]; i+=2
        else:
            if isinstance(xs[i],list): raise ValueError("expression in typed list")
            pending.append(xs[i]); i+=1
    return out+[(x,default) for x in pending]

def fields(x):
    r={}; i=2
    while i+1<len(x):
        if isinstance(x[i],str) and x[i].startswith(":"): r[x[i]]=x[i+1]; i+=2
        else: i+=1
    return r

class Model:
    def __init__(self,domain,problem):
        d=sexpr(open(domain,encoding="utf-8").read()); p=sexpr(open(problem,encoding="utf-8").read())
        if not d or not p or d[0]!="define" or p[0]!="define": raise ValueError("expected PDDL define forms")
        self.types={"object":None}; self.actions=[]; changed=set()
        for x in d[1:]:
            if not isinstance(x,list) or not x: continue
            if x[0]==":types": self.types.update(dict(typed(x[1:])))
            elif x[0]==":durative-action": raise ValueError("durative PDDL is unsupported")
            elif x[0]==":action":
                q=fields(x)
                if len(x)<2 or not all(k in q for k in (":parameters",":precondition",":effect")):
                    raise ValueError("incomplete action schema")
                self.actions.append((x[1],typed(q[":parameters"]),q[":precondition"],q[":effect"]))
                self.effect_predicates(q[":effect"],changed)
        if not self.actions: raise ValueError("domain has no action schemas")
        self.obj={}; self.init=set(); self.goal=None
        for x in p[1:]:
            if not isinstance(x,list) or not x: continue
            if x[0]==":objects": self.obj.update(dict(typed(x[1:])))
            elif x[0]==":init":
                for a in x[1:]:
                    if not isinstance(a,list) or not a: continue
                    if a[0] in NUM: raise ValueError("numeric PDDL is unsupported")
                    if a[0] not in ("not","="): self.init.add(tuple(a))
            elif x[0]==":goal":
                if len(x)!=2: raise ValueError("malformed goal")
                self.goal=x[1]
        if self.goal is None: raise ValueError("missing goal")
        self.bytype=collections.defaultdict(list)
        for o,t in self.obj.items():
            for u in self.ancestors(t): self.bytype[u].append(o)
        self.static_pred={a[0] for a in self.init if a[0] not in changed}
        self.static=frozenset(a for a in self.init if a[0] in self.static_pred)
        self.start=frozenset(a for a in self.init if a[0] not in self.static_pred)

    def ancestors(self,t):
        seen=set()
        while t is not None and t not in seen:
            seen.add(t); yield t; t=self.types.get(t)

    def effect_predicates(self,x,out):
        if not isinstance(x,list) or not x: raise ValueError("malformed effect")
        op=x[0]
        if op=="and":
            for y in x[1:]: self.effect_predicates(y,out)
        elif op=="not":
            if len(x)!=2 or not isinstance(x[1],list) or not x[1]: raise ValueError("malformed delete effect")
            out.add(x[1][0])
        elif op in ("when","forall"):
            if len(x)!=3: raise ValueError("malformed conditional/quantified effect")
            self.effect_predicates(x[2],out)
        elif op in NUM: raise ValueError("numeric PDDL is unsupported")
        elif op not in LOG: out.add(op)

    def formula(self,x,state,env=None):
        env={} if env is None else env
        if not isinstance(x,list) or not x: raise ValueError("malformed logical formula")
        op=x[0]
        if op=="and": return all(self.formula(y,state,env) for y in x[1:])
        if op=="or": return any(self.formula(y,state,env) for y in x[1:])
        if op=="not": return len(x)==2 and not self.formula(x[1],state,env)
        if op=="imply": return len(x)==3 and (not self.formula(x[1],state,env) or self.formula(x[2],state,env))
        if op=="=": return len(x)==3 and env.get(x[1],x[1])==env.get(x[2],x[2])
        if op in ("forall","exists"):
            if len(x)!=3: raise ValueError("malformed quantifier")
            vs=typed(x[1]); vals=[]
            for tup in itertools.product(*[self.bytype[t] for _,t in vs]):
                e=dict(env); e.update(dict(zip([v for v,_ in vs],tup))); vals.append(self.formula(x[2],state,e))
            return all(vals) if op=="forall" else any(vals)
        return tuple(env.get(z,z) for z in x) in state

    def apply(self,e,state,env):
        full=set(self.static|state)
        def walk(x,local):
            if not isinstance(x,list) or not x: raise ValueError("malformed effect")
            op=x[0]
            if op=="and":
                for y in x[1:]: walk(y,local)
            elif op=="not":
                if len(x)!=2 or not isinstance(x[1],list): raise ValueError("malformed delete")
                full.discard(tuple(local.get(z,z) for z in x[1]))
            elif op=="when":
                if len(x)!=3: raise ValueError("malformed conditional effect")
                if self.formula(x[1],full,local): walk(x[2],local)
            elif op=="forall":
                if len(x)!=3: raise ValueError("malformed quantified effect")
                vs=typed(x[1])
                for tup in itertools.product(*[self.bytype[t] for _,t in vs]):
                    q=dict(local); q.update(dict(zip([v for v,_ in vs],tup))); walk(x[2],q)
            elif op in NUM: raise ValueError("numeric PDDL is unsupported")
            else: full.add(tuple(local.get(z,z) for z in x))
        walk(e,env)
        return frozenset(a for a in full if a[0] not in self.static_pred)

    def static_atoms(self,x):
        if not isinstance(x,list) or not x: return []
        if x[0]=="and": return sum((self.static_atoms(y) for y in x[1:]),[])
        return [tuple(x)] if x[0] not in LOG and x[0] in self.static_pred else []

    def ground(self):
        index=collections.defaultdict(list)
        for a in self.static: index[a[0]].append(a)
        result=[]
        for name,params,pre,eff in self.actions:
            vs=[v for v,_ in params]; domains={v:self.bytype[t] for v,t in params}; atoms=self.static_atoms(pre)
            def finish(env):
                missing=[v for v in vs if v not in env]
                if missing:
                    v=min(missing,key=lambda z:len(domains[z]))
                    for o in domains[v]: q=dict(env); q[v]=o; finish(q)
                else: result.append((name,tuple(env[v] for v in vs),env,pre,eff))
            def join(env,left):
                if not left: finish(env); return
                a=max(left,key=lambda z:sum(w in env for w in z[1:]))
                rest=list(left); rest.remove(a)
                for f in index[a[0]]:
                    if len(f)!=len(a): continue
                    q=dict(env); ok=True
                    for z,o in zip(a[1:],f[1:]):
                        if isinstance(z,str) and z.startswith("?"):
                            if z not in domains or o not in domains[z] or (z in q and q[z]!=o): ok=False; break
                            q[z]=o
                        elif z!=o: ok=False; break
                    if ok: join(q,rest)
            join({},atoms)
        return result

def positive_goals(x):
    if not isinstance(x,list) or not x: return []
    if x[0]=="and": return sum((positive_goals(y) for y in x[1:]),[])
    return [tuple(x)] if x[0] not in LOG else []

def solve(m,limit):
    if m.formula(m.goal,m.static|m.start): return []
    acts=m.ground()
    if not acts: return None
    goals=positive_goals(m.goal)
    def h(s): return sum(g not in m.static and g not in s for g in goals)
    until=time.monotonic()+limit; serial=0; best={m.start:0}; parent={m.start:(None,None)}
    heap=[(h(m.start),0,serial,m.start)]
    while heap:
        if time.monotonic()>until: raise TimeoutError("search time limit reached")
        _,cost,_,state=heapq.heappop(heap)
        if best.get(state)!=cost: continue
        for name,args,env,pre,eff in acts:
            if not m.formula(pre,m.static|state,env): continue
            nxt=m.apply(eff,state,env); nc=cost+1
            if nxt==state or nc>=best.get(nxt,10**18): continue
            best[nxt]=nc; parent[nxt]=(state,(name,args))
            if m.formula(m.goal,m.static|nxt):
                ans=[]
                while parent[nxt][0] is not None: nxt,a=parent[nxt]; ans.append(a)
                return ans[::-1]
            serial+=1; heapq.heappush(heap,(nc+h(nxt),nc,serial,nxt))
    return None

def read_plan(path):
    ans=[]
    for n,line in enumerate(open(path,encoding="utf-8"),1):
        line=line.split(";",1)[0].strip().lower()
        if not line: continue
        z=re.fullmatch(r"([a-z0-9_-]+)\s*\(\s*([^()]*)\s*\)",line)
        if z: args=tuple(x.strip() for x in z.group(2).split(",") if x.strip())
        else:
            z=re.fullmatch(r"\(\s*([a-z0-9_-]+)((?:\s+[a-z0-9_-]+)*)\s*\)",line)
            if not z: raise ValueError("invalid plan line %d"%n)
            args=tuple(z.group(2).split())
        ans.append((z.group(1),args))
    return ans

def validate(m,plan):
    schemas={n:(p,pre,e) for n,p,pre,e in m.actions}; state=m.start
    for step,(name,args) in enumerate(plan,1):
        if name not in schemas: return {"valid":False,"step":step,"reason":"undeclared action"}
        ps,pre,eff=schemas[name]
        if len(ps)!=len(args): return {"valid":False,"step":step,"reason":"wrong arity"}
        env=dict(zip([v for v,_ in ps],args))
        for v,t in ps:
            if env[v] not in m.obj or t not in set(m.ancestors(m.obj[env[v]])):
                return {"valid":False,"step":step,"reason":"ill-typed object"}
        if not m.formula(pre,m.static|state,env): return {"valid":False,"step":step,"reason":"unsatisfied precondition"}
        state=m.apply(eff,state,env)
    return {"valid":True,"steps":len(plan)} if m.formula(m.goal,m.static|state) else {"valid":False,"reason":"goal not satisfied"}

def entries(path):
    x=json.load(open(path,encoding="utf-8"))
    if isinstance(x,list): return x
    if isinstance(x,dict):
        for k in ("tasks","problems"):
            if isinstance(x.get(k),list): return x[k]
    raise ValueError("manifest must be a list or contain tasks/problems")
def pathof(x,base): return x if os.path.isabs(x) else os.path.join(base,x)
def check(e):
    if not isinstance(e,dict) or not all(isinstance(e.get(k),str) and e[k] for k in ("domain","problem","plan_output")): raise ValueError("entry lacks domain/problem/plan_output")
def model(e,base): return Model(pathof(e["domain"],base),pathof(e["problem"],base))

def main(q):
    manifest=os.path.abspath(q.get("manifest","problem.json")); base=os.path.dirname(manifest); es=entries(manifest)
    if q.get("mode")=="validate-manifest":
        rs=[]
        for e in es:
            try:
                check(e); out=pathof(e["plan_output"],base)
                if not os.path.isfile(out): raise ValueError("required plan output is missing: "+out)
                rs.append({"id":e.get("id"),"plan_output":out,**validate(model(e,base),read_plan(out))})
            except Exception as x: rs.append({"id":e.get("id") if isinstance(e,dict) else None,"valid":False,"reason":str(x)})
        return {"ok":all(r.get("valid") for r in rs),"results":rs}
    limit=float(q.get("time_limit_sec",240)); rs=[]
    for e in es:
        try:
            check(e); m=model(e,base); plan=solve(m,limit)
            if plan is None: rs.append({"id":e.get("id"),"status":"unsolved"}); continue
            v=validate(m,plan)
            if not v["valid"]: raise ValueError("internal replay failed: "+str(v))
            out=pathof(e["plan_output"],base); os.makedirs(os.path.dirname(out) or ".",exist_ok=True)
            tmp=out+".tmp"
            with open(tmp,"w",encoding="utf-8") as f:
                for n,a in plan: f.write(n+"("+", ".join(a)+")\n")
            os.replace(tmp,out); rs.append({"id":e.get("id"),"status":"solved","plan_output":out,"plan_length":len(plan),"validation":v})
        except TimeoutError as x: rs.append({"id":e.get("id") if isinstance(e,dict) else None,"status":"timeout","reason":str(x)})
        except Exception as x: rs.append({"id":e.get("id") if isinstance(e,dict) else None,"status":"error","reason":str(x)})
    return {"ok":all(r.get("status")=="solved" for r in rs),"results":rs}

if __name__=="__main__":
    try: print(json.dumps(main(json.load(sys.stdin)),sort_keys=True))
    except Exception as x: print(json.dumps({"ok":False,"status":"error","reason":str(x)})); sys.exit(2)
