#!/usr/bin/env python3
"""Classical typed-PDDL manifest solver and plan publisher.
JSON stdin: root, problem_json, max_expansions, weight. JSON stdout: status.
"""
import heapq, itertools, json, re, sys
from collections import defaultdict
from pathlib import Path

class Error(Exception): pass

def sexpr(path):
    tokens=re.findall(r'\(|\)|[^\s()]+',re.sub(r';[^\n]*','',Path(path).read_text()).lower())
    i=0
    def one():
        nonlocal i
        if i>=len(tokens): raise Error('unexpected end of PDDL')
        x=tokens[i]; i+=1
        if x=='(':
            a=[]
            while i<len(tokens) and tokens[i]!=')': a.append(one())
            if i==len(tokens): raise Error('unclosed parenthesis')
            i+=1; return a
        if x==')': raise Error('unexpected closing parenthesis')
        return x
    tree=one()
    if i!=len(tokens) or not isinstance(tree,list) or not tree or tree[0]!='define': raise Error('expected one define expression')
    return tree

def sec(tree,key):
    for x in tree[1:]:
        if isinstance(x,list) and x and x[0]==key: return x[1:]
    return None

def typed(xs):
    out=[]; pending=[]; i=0
    while i<len(xs):
        x=xs[i]
        if not isinstance(x,str): raise Error('malformed typed names')
        if x=='-':
            if not pending or i+1>=len(xs) or not isinstance(xs[i+1],str): raise Error('malformed typed names')
            out += [(n,xs[i+1]) for n in pending]; pending=[]; i+=2
        else: pending.append(x); i+=1
    return out+[(n,'object') for n in pending]

def atom(x):
    if not isinstance(x,list) or not x or not isinstance(x[0],str) or any(isinstance(y,list) for y in x[1:]): raise Error('expected atom')
    return tuple(x)

def literals(x,effect=False):
    if not isinstance(x,list) or not x: raise Error('malformed formula')
    if x[0]=='and':
        p=[]; n=[]
        for y in x[1:]:
            a,b=literals(y,effect); p+=a; n+=b
        return p,n
    if x[0]=='not':
        if len(x)!=2: raise Error('malformed negation')
        return [],[atom(x[1])]
    if effect and x[0] in ('increase','decrease','assign','scale-up','scale-down'): return [],[]
    if x[0] in ('or','imply','when','forall','exists','oneof','>','<','>=','<='): raise Error('unsupported formula '+x[0])
    return [atom(x)],[]

def domain(path):
    t=sexpr(path); parents={'object':None}; parents.update(dict(typed(sec(t,':types') or [])))
    schemas=[]
    for x in t[1:]:
        if not isinstance(x,list) or len(x)<2 or x[0]!=':action': continue
        f={}; i=2
        while i<len(x):
            if not isinstance(x[i],str) or not x[i].startswith(':') or i+1>=len(x): raise Error('malformed action '+str(x[1]))
            f[x[i]]=x[i+1]; i+=2
        params=typed(f.get(':parameters',[]))
        if any(not v.startswith('?') for v,_ in params): raise Error('non-variable parameter')
        pp,pn=literals(f.get(':precondition',['and'])); add,delete=literals(f.get(':effect',['and']),True)
        if any(z[0]=='=' for z in add+delete): raise Error('equality effect unsupported')
        schemas.append((x[1],params,pp,pn,add,delete))
    if not schemas: raise Error('domain has no actions')
    return parents,typed(sec(t,':constants') or []),schemas

def problem(path):
    t=sexpr(path); init=sec(t,':init'); goal=sec(t,':goal')
    if init is None or goal is None or len(goal)!=1: raise Error('problem requires init and one goal')
    state=set()
    for x in init:
        if isinstance(x,list) and x and x[0] not in ('=','not'): state.add(atom(x))
    gp,gn=literals(goal[0]); return typed(sec(t,':objects') or []),frozenset(state),gp,gn

def subtype(a,w,parents):
    seen=set()
    while a is not None and a not in seen:
        if a==w:return True
        seen.add(a); a=parents.get(a)
    return False

def subst(x,b): return b[x] if x.startswith('?') else x
def grd(p,b): return tuple(subst(x,b) for x in p)
def holds(pos,neg,state,b):
    def yes(p):
        if p[0]=='=':
            if len(p)!=3: raise Error('bad equality')
            return subst(p[1],b)==subst(p[2],b)
        return grd(p,b) in state
    return all(yes(p) for p in pos) and all(not yes(p) for p in neg)
def effect(state,add,delete,b): return frozenset((set(state)-{grd(x,b) for x in delete})|{grd(x,b) for x in add})

def instances(sc,state,objects,parents):
    name,pars,pos,neg,add,delete=sc; index=defaultdict(list)
    for f in state:index[f[0]].append(f)
    parts=[{}]
    for p in sorted((q for q in pos if q[0]!='='),key=lambda q:len(index[q[0]])):
        nxt=[]
        for b in parts:
            for f in index[p[0]]:
                if len(f)!=len(p):continue
                c=dict(b); ok=True
                for term,val in zip(p[1:],f[1:]):
                    if term.startswith('?'):
                        if term in c and c[term]!=val:ok=False;break
                        c[term]=val
                    elif term!=val:ok=False;break
                if ok:nxt.append(c)
        parts=nxt
        if not parts:return
    choices=[]
    for v,need in pars:
        xs=[o for o,actual in objects.items() if subtype(actual,need,parents)]
        if not xs:return
        choices.append((v,xs))
    for partial in parts:
        if any(v in partial and partial[v] not in xs for v,xs in choices):continue
        missing=[(v,xs) for v,xs in choices if v not in partial]
        for vals in (itertools.product(*(xs for _,xs in missing)) if missing else [()]):
            b=dict(partial); b.update(zip((v for v,_ in missing),vals))
            if holds(pos,neg,state,b):yield name,tuple(b[v] for v,_ in pars),effect(state,add,delete,b)

def replay(parents,schemas,objects,initial,gp,gn,plan):
    by={x[0]:x for x in schemas}; state=initial
    for step,(name,args) in enumerate(plan,1):
        if name not in by:raise Error('undeclared action at step %d'%step)
        _,pars,pos,neg,add,delete=by[name]
        if len(args)!=len(pars):raise Error('arity error at step %d'%step)
        if any(a not in objects or not subtype(objects[a],need,parents) for a,(_,need) in zip(args,pars)):raise Error('type error at step %d'%step)
        b=dict(zip((v for v,_ in pars),args))
        if not holds(pos,neg,state,b):raise Error('precondition failure at step %d'%step)
        state=effect(state,add,delete,b)
    if not holds(gp,gn,state,{}):raise Error('goal not satisfied')

def solve(parents,constants,schemas,declared,initial,gp,gn,limit,weight):
    objects=dict(constants); objects.update(dict(declared))
    if any(t not in parents for t in objects.values()):raise Error('undeclared object type')
    if holds(gp,gn,initial,{}):return [],0,objects
    def h(s):return sum(not holds([p],[],s,{}) for p in gp)+sum(holds([p],[],s,{}) for p in gn)
    serial=itertools.count(); pq=[(weight*h(initial),0,next(serial),initial)]; dist={initial:0}; prev={}; expanded=0
    while pq:
        _,g,_,s=heapq.heappop(pq)
        if dist.get(s)!=g:continue
        if holds(gp,gn,s,{}):
            plan=[]
            while s!=initial:s,a=prev[s];plan.append(a)
            plan.reverse(); replay(parents,schemas,objects,initial,gp,gn,plan); return plan,expanded,objects
        expanded+=1
        if expanded>limit:raise Error('search expansion limit exceeded')
        for sc in schemas:
            for name,args,nxt in instances(sc,s,objects,parents):
                ng=g+1
                if ng<dist.get(nxt,10**30):
                    dist[nxt]=ng;prev[nxt]=(s,(name,args));heapq.heappush(pq,(ng+weight*h(nxt),ng,next(serial),nxt))
    raise Error('state space exhausted')

def resolve(root,value):
    p=Path(value); return p if p.is_absolute() else root/p

def entry(item,root,limit,weight):
    if not isinstance(item,dict) or any(not isinstance(item.get(k),str) for k in ('id','domain','problem','plan_output')):raise Error('invalid manifest entry')
    parents,constants,schemas=domain(resolve(root,item['domain']))
    declared,initial,gp,gn=problem(resolve(root,item['problem']))
    plan,expanded,objects=solve(parents,constants,schemas,declared,initial,gp,gn,limit,weight)
    replay(parents,schemas,objects,initial,gp,gn,plan)
    out=resolve(root,item['plan_output']); out.parent.mkdir(parents=True,exist_ok=True); tmp=out.with_name(out.name+'.tmp')
    tmp.write_text(''.join('%s(%s)\n'%(n,', '.join(a)) for n,a in plan) or '\n'); tmp.replace(out)
    if not out.is_file():raise Error('plan publication failed')
    return {'id':item['id'],'ok':True,'plan_output':str(out),'steps':len(plan),'expanded':expanded}

def main():
    try:
        r=json.load(sys.stdin)
        if not isinstance(r,dict):raise Error('request must be object')
        root=Path(r.get('root','/app')); limit=r.get('max_expansions',5000000); weight=r.get('weight',2)
        if not isinstance(limit,int) or isinstance(limit,bool) or limit<=0:raise Error('invalid max_expansions')
        if not isinstance(weight,(int,float)) or isinstance(weight,bool) or weight<=0:raise Error('invalid weight')
        manifest=json.loads(resolve(root,r.get('problem_json',str(root/'problem.json'))).read_text())
        if not isinstance(manifest,list) or not manifest:raise Error('manifest must be nonempty array')
        results=[]
        for x in manifest:
            try:results.append(entry(x,root,limit,weight))
            except Exception as e:results.append({'id':x.get('id','<unknown>') if isinstance(x,dict) else '<unknown>','ok':False,'error':str(e)})
        print(json.dumps({'ok':all(x['ok'] for x in results),'results':results},sort_keys=True))
    except Exception as e:print(json.dumps({'ok':False,'error':str(e),'results':[]},sort_keys=True))
if __name__=='__main__':main()
