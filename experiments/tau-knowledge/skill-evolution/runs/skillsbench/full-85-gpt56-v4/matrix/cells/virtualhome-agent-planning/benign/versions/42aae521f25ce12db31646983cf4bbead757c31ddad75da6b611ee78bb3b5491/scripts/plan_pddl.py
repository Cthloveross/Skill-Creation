#!/usr/bin/env python3
"""Small dependency-free classical PDDL planner and replay validator.
Reads a manifest path from --manifest or JSON stdin and emits JSON on stdout.
"""
import argparse, itertools, json, os, re, sys, time, heapq
from collections import defaultdict

class PDDLError(Exception): pass

def tokens(text):
    text = re.sub(r';[^\n]*', '', text)
    return re.findall(r'\(|\)|[^\s()]+', text.lower())

def parse_sexp(text):
    ts=tokens(text); stack=[]; root=None
    for t in ts:
        if t=='(':
            stack.append([])
        elif t==')':
            if not stack: raise PDDLError('unmatched closing parenthesis')
            x=stack.pop()
            if stack: stack[-1].append(x)
            elif root is None: root=x
            else: raise PDDLError('multiple top-level expressions')
        else:
            if not stack: raise PDDLError('token outside expression: '+t)
            stack[-1].append(t)
    if stack or root is None: raise PDDLError('unclosed or empty PDDL expression')
    return root

def sections(root):
    return {x[0]:x[1:] for x in root[1:] if isinstance(x,list) and x and isinstance(x[0],str) and x[0].startswith(':')}

def typed(words, default='object'):
    out=[]; buf=[]; i=0
    while i < len(words):
        w=words[i]
        if w=='-':
            if i+1>=len(words): raise PDDLError('dangling type marker')
            out += [(x,words[i+1]) for x in buf]; buf=[]; i+=2
        else: buf.append(w); i+=1
    out += [(x,default) for x in buf]
    return out

def atom(x):
    if not isinstance(x,list) or not x or not isinstance(x[0],str): raise PDDLError('expected atomic formula')
    if x[0] in ('and','or','not','when','forall','exists','imply'): raise PDDLError('non-atomic formula where atom required')
    return tuple(x)

def dnf(x):
    """Return alternatives, each a list of (positive, atom) literals."""
    if not isinstance(x,list) or not x: raise PDDLError('malformed condition')
    op=x[0]
    if op=='and':
        ans=[[]]
        for y in x[1:]:
            ans=[a+b for a in ans for b in dnf(y)]
        return ans
    if op=='or':
        ans=[]
        for y in x[1:]: ans += dnf(y)
        return ans
    if op=='not':
        if len(x)!=2: raise PDDLError('not must have one argument')
        return [[(False,atom(x[1]))]]
    if op in ('forall','exists','imply'):
        raise PDDLError('unsupported quantified/implied condition: '+op)
    return [[(True,atom(x))]]

def effects(x):
    """Return unconditional literals and (condition alternatives, effect literals)."""
    if not isinstance(x,list) or not x: raise PDDLError('malformed effect')
    if x[0]=='and':
        u=[]; c=[]
        for y in x[1:]:
            a,b=effects(y); u+=a; c+=b
        return u,c
    if x[0]=='not':
        if len(x)!=2: raise PDDLError('bad negative effect')
        return [(False,atom(x[1]))],[]
    if x[0]=='when':
        if len(x)!=3: raise PDDLError('when must have condition and effect')
        eu,ec=effects(x[2])
        if ec: raise PDDLError('nested conditional effect unsupported')
        return [],[(q,eu) for q in dnf(x[1])]
    if x[0] in ('forall','exists','assign','increase','decrease'):
        raise PDDLError('unsupported effect construct: '+x[0])
    return [(True,atom(x))],[]

def subst(a,b): return tuple(b.get(x,x) for x in a)
def isvar(x): return isinstance(x,str) and x.startswith('?')

def parse_domain(path):
    root=parse_sexp(open(path,encoding='utf8').read())
    if not root or root[0]!='define': raise PDDLError('domain is not a define form')
    ss=sections(root); hierarchy={'object':None}
    for n,t in typed(ss.get(':types',[])):
        hierarchy[n]=t
    constants=dict(typed(ss.get(':constants',[])))
    actions=[]
    for x in root[1:]:
        if not (isinstance(x,list) and x and x[0]==':action'): continue
        if len(x)<2: raise PDDLError('unnamed action')
        name=x[1]; fields={}
        i=2
        while i<len(x):
            if not isinstance(x[i],str) or not x[i].startswith(':') or i+1>=len(x): raise PDDLError('malformed action '+name)
            fields[x[i]]=x[i+1]; i+=2
        if ':parameters' not in fields or ':precondition' not in fields or ':effect' not in fields:
            raise PDDLError('action '+name+' lacks classical fields')
        ps=typed(fields[':parameters'])
        pre=dnf(fields[':precondition']); eff,cond=effects(fields[':effect'])
        actions.append((name,ps,pre,eff,cond))
    if not actions: raise PDDLError('no :action schemas found')
    return hierarchy,constants,actions

def parse_problem(path, constants):
    root=parse_sexp(open(path,encoding='utf8').read())
    if not root or root[0]!='define': raise PDDLError('problem is not a define form')
    ss=sections(root); objs=dict(constants); objs.update(dict(typed(ss.get(':objects',[]))))
    init=set()
    for x in ss.get(':init',[]):
        if isinstance(x,list) and x and x[0] in ('=', 'increase','assign'): raise PDDLError('numeric fluents are unsupported')
        if isinstance(x,list) and x and x[0]=='not': continue
        init.add(atom(x))
    g=ss.get(':goal')
    if not g: raise PDDLError('problem has no goal')
    return objs,init,dnf(g[0])

def subtype(t, wanted, hierarchy):
    seen=set()
    while t is not None and t not in seen:
        if t==wanted: return True
        seen.add(t); t=hierarchy.get(t)
    return False

def bind_static_literals(lits, static, changed, binding):
    """Yield bindings satisfying positive predicates that are static."""
    work=[l for l in lits if l[0] and l[1][0] != '=' and l[1][0] not in changed]
    work.sort(key=lambda l: len(static.get(l[1][0],())))
    def rec(i,b):
        if i==len(work): yield b; return
        _,pat=work[i]
        for fact in static.get(pat[0],()):
            if len(fact)!=len(pat): continue
            nb=dict(b); good=True
            for p,v in zip(pat[1:],fact[1:]):
                if isvar(p):
                    if p in nb and nb[p]!=v: good=False; break
                    nb[p]=v
                elif p!=v: good=False; break
            if good: yield from rec(i+1,nb)
    yield from rec(0,binding)

def compile_problem(domain_path, problem_path):
    hierarchy,constants,schemas=parse_domain(domain_path)
    objects,init,goals=parse_problem(problem_path,constants)
    # Any predicate appearing in an effect is dynamic. Conditional effects count too.
    changed=set()
    for _,_,_,eu,ce in schemas:
        changed.update(a[0] for _,a in eu)
        for _,ee in ce: changed.update(a[0] for _,a in ee)
    static=defaultdict(set)
    for a in init:
        if a[0] not in changed: static[a[0]].add(a)
    initial=frozenset(a for a in init if a[0] in changed)
    bytype=defaultdict(list)
    for o,t in objects.items():
        for wanted in hierarchy:
            if subtype(t,wanted,hierarchy): bytype[wanted].append(o)
    ground=[]
    for name,params,alternatives,eu,ce in schemas:
        domains={v:bytype[t] for v,t in params}
        for v,ds in domains.items():
            if not ds: continue
        for pre in alternatives:
            # Static positive literals constrain grounding; all other literals are verified after grounding.
            for base in bind_static_literals(pre,static,changed,{}):
                missing=[v for v,_ in params if v not in base]
                if any(not domains[v] for v in missing): continue
                products=itertools.product(*(domains[v] for v in missing))
                for vals in products:
                    b=dict(base); b.update(zip(missing,vals))
                    gp=[(sign,subst(a,b)) for sign,a in pre]
                    # Reject impossible static tests now, reducing stored actions.
                    if not all(holds(l,initial,static,changed) for l in gp if l[1][0] not in changed): continue
                    gu=[(sign,subst(a,b)) for sign,a in eu]
                    gc=[ ([(s,subst(a,b)) for s,a in q], [(s,subst(a,b)) for s,a in ee]) for q,ee in ce ]
                    args=tuple(b[v] for v,_ in params)
                    ground.append((name,args,gp,gu,gc))
    if not ground: raise PDDLError('static grounding produced no actions')
    return static,changed,initial,goals,ground

def holds(lit,state,static,changed):
    sign,a=lit
    if a[0]=='=':
        val=(len(a)==3 and a[1]==a[2])
    else:
        val=a in (state if a[0] in changed else static.get(a[0],set()))
    return val if sign else not val

def apply(action,state,static,changed):
    _,_,pre,uncond,conds=action
    if not all(holds(x,state,static,changed) for x in pre): return None
    adds=set(); dels=set()
    def collect(es):
        for sign,a in es:
            if a[0] not in changed: continue
            (adds if sign else dels).add(a)
    collect(uncond)
    for q,ee in conds:
        if all(holds(x,state,static,changed) for x in q): collect(ee)
    ns=frozenset((set(state)-dels)|adds)
    return ns

def solve(compiled, deadline, max_expansions):
    static,changed,start,goals,actions=compiled
    def goal_index(s):
        best=None
        for g in goals:
            miss=sum(not holds(x,s,static,changed) for x in g)
            if miss==0: return 0
            best=miss if best is None or miss<best else best
        return best if best is not None else 10**9
    # Index a fully-ground action under one dynamic positive precondition. This avoids scanning
    # actions whose required location/resource fact is absent from the current joint state.
    index=defaultdict(list); always=[]
    for n,a in enumerate(actions):
        anchors=[x[1] for x in a[2] if x[0] and x[1][0] in changed]
        if anchors: index[anchors[0]].append(n)
        else: always.append(n)
    q=[]; serial=0; h=goal_index(start)
    heapq.heappush(q,(h*4,0,serial,start)); best={start:0}; parent={start:None}; expanded=0
    while q:
        if time.monotonic()>deadline: raise PDDLError('search timed out after %d expansions' % expanded)
        _,g,_,s=heapq.heappop(q)
        if best.get(s)!=g: continue
        if goal_index(s)==0:
            out=[]
            while parent[s] is not None:
                s,a=parent[s]; out.append(a)
            out.reverse(); return out
        expanded+=1
        if expanded>max_expansions: raise PDDLError('search expansion limit reached')
        candidates=list(always)
        for fact in s: candidates.extend(index.get(fact,()))
        for ai in candidates:
            ns=apply(actions[ai],s,static,changed)
            if ns is None or ns==s: continue
            ng=g+1
            if ng < best.get(ns,10**18):
                best[ns]=ng; parent[ns]=(s,actions[ai]); serial+=1
                heapq.heappush(q,(ng+4*goal_index(ns),ng,serial,ns))
    raise PDDLError('state space exhausted without a goal')

def serialize(plan):
    return '\n'.join('%s(%s)'%(n,', '.join(args)) for n,args,_,_,_ in plan)+'\n'

def read_plan(path):
    ans=[]
    for line in open(path,encoding='utf8'):
        line=line.strip()
        if not line or line.startswith(';'): continue
        m=re.fullmatch(r'\(?\s*([^\s(),]+)(?:\s*\(?\s*([^)]*?)\s*\)?)?\s*\)?',line)
        if not m: raise PDDLError('invalid plan line: '+line)
        name=m.group(1); rest=(m.group(2) or '').strip()
        args=tuple(x.strip() for x in re.split(r'[\s,]+',rest) if x.strip())
        ans.append((name,args))
    return ans

def validate(compiled, plan):
    static,changed,state,goals,actions=compiled
    lookup=defaultdict(list)
    for a in actions: lookup[(a[0],a[1])].append(a)
    for step,key in enumerate(plan,1):
        opts=lookup.get(key,[]); nexts=[]
        for a in opts:
            ns=apply(a,state,static,changed)
            if ns is not None: nexts.append(ns)
        if not nexts: raise PDDLError('plan action %d is unknown or inapplicable: %s%s' % (step,key[0],key[1]))
        state=nexts[0]
    if not any(all(holds(x,state,static,changed) for x in g) for g in goals):
        raise PDDLError('plan ends without satisfying the goal')
    return True

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--manifest'); ap.add_argument('--timeout',type=float,default=560)
    ap.add_argument('--max-expansions',type=int,default=1000000); ap.add_argument('--validate-only',action='store_true')
    ns=ap.parse_args(); supplied={}
    if not ns.manifest and not sys.stdin.isatty():
        supplied=json.load(sys.stdin); ns.manifest=supplied.get('manifest'); ns.timeout=float(supplied.get('timeout',ns.timeout)); ns.max_expansions=int(supplied.get('max_expansions',ns.max_expansions))
    if not ns.manifest: raise SystemExit('provide --manifest or JSON stdin with manifest')
    entries=json.load(open(ns.manifest,encoding='utf8'))
    if not isinstance(entries,list): raise SystemExit('manifest must be a JSON list')
    deadline=time.monotonic()+ns.timeout; results=[]
    for ent in entries:
        r={'id':ent.get('id'),'domain':ent.get('domain'),'problem':ent.get('problem'),'plan_output':ent.get('plan_output')}
        try:
            for k in ('domain','problem','plan_output'):
                if not isinstance(ent.get(k),str): raise PDDLError('manifest entry lacks string '+k)
            c=compile_problem(ent['domain'],ent['problem'])
            if ns.validate_only:
                p=read_plan(ent['plan_output']); validate(c,p); r.update(ok=True,actions=len(p),validated=True)
            else:
                plan=solve(c,deadline,ns.max_expansions); validate(c,[(a[0],a[1]) for a in plan])
                parent=os.path.dirname(ent['plan_output'])
                if parent: os.makedirs(parent,exist_ok=True)
                open(ent['plan_output'],'w',encoding='utf8').write(serialize(plan))
                r.update(ok=True,actions=len(plan))
        except Exception as e:
            r.update(ok=False,error=str(e))
        results.append(r)
    result={'ok':all(r['ok'] for r in results),'results':results}
    print(json.dumps(result,sort_keys=True))
    return 0 if result['ok'] else 1
if __name__=='__main__':
    sys.exit(main())
