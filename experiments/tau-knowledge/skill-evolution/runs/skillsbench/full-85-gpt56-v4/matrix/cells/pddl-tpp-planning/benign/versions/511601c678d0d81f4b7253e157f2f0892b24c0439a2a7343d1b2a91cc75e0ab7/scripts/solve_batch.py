#!/usr/bin/env python3
"""Read batch configuration JSON from stdin, write validated plans, emit JSON summary."""
import json, os, re, sys, time, heapq, shutil, subprocess, tempfile
from collections import defaultdict

class PDDLError(Exception): pass
class SearchLimit(Exception): pass

def tokens(text):
    text = re.sub(r';[^\n]*', '', text)
    return re.findall(r'\(|\)|[^\s()]+', text.lower())

def sexpr(text):
    ts=tokens(text); pos=0
    def one():
        nonlocal pos
        if pos>=len(ts): raise PDDLError('unexpected end of PDDL')
        x=ts[pos]; pos+=1
        if x!='(': return x
        out=[]
        while True:
            if pos>=len(ts): raise PDDLError('unclosed parenthesis')
            if ts[pos]==')': pos+=1; return out
            out.append(one())
    root=one()
    if pos != len(ts): raise PDDLError('extra PDDL expression')
    return root

def typed(items, default='object'):
    """Return (name,type) pairs from a PDDL typed-list."""
    ans=[]; pending=[]; i=0
    while i<len(items):
        x=items[i]
        if x=='-':
            if i+1>=len(items): raise PDDLError('type marker without type')
            ans += [(n,items[i+1]) for n in pending]; pending=[]; i+=2
        else:
            pending.append(x); i+=1
    ans += [(n,default) for n in pending]
    return ans

def literals(formula, where):
    if formula == []: return []
    if not isinstance(formula,list): raise PDDLError('%s is not a formula' % where)
    if formula and formula[0]=='and':
        out=[]
        for x in formula[1:]: out += literals(x,where)
        return out
    if formula and formula[0]=='not':
        if len(formula)!=2 or not isinstance(formula[1],list): raise PDDLError('bad not in '+where)
        return [(False,tuple(formula[1]))]
    if formula and formula[0] in ('or','forall','exists','when','increase','decrease','assign'):
        raise PDDLError('unsupported PDDL construct %s in %s' % (formula[0],where))
    return [(True,tuple(formula))]

def section(root, key):
    for x in root[1:]:
        if isinstance(x,list) and x and x[0]==key: return x
    return None

def parse_domain(path):
    root=sexpr(open(path,encoding='utf8').read())
    if not isinstance(root,list) or not root or root[0]!='define': raise PDDLError('not a PDDL domain')
    types={'object':None}
    s=section(root,':types')
    if s:
        for n,t in typed(s[1:]): types[n]=t
    constants={}
    s=section(root,':constants')
    if s:
        constants=dict(typed(s[1:]))
    actions=[]
    for x in root[1:]:
        if not (isinstance(x,list) and x and x[0]==':action'): continue
        if len(x)<2: raise PDDLError('unnamed action')
        d={}; i=2
        while i<len(x):
            if not isinstance(x[i],str) or not x[i].startswith(':') or i+1>=len(x):
                raise PDDLError('malformed action '+x[1])
            d[x[i]]=x[i+1]; i+=2
        if ':parameters' not in d or ':precondition' not in d or ':effect' not in d:
            raise PDDLError('action %s lacks STRIPS fields' % x[1])
        params=typed(d[':parameters'])
        actions.append({'name':x[1], 'params':params,
                        'pre':literals(d[':precondition'],'precondition of '+x[1]),
                        'eff':literals(d[':effect'],'effect of '+x[1])})
    if not actions: raise PDDLError('domain has no actions')
    return {'types':types,'constants':constants,'actions':actions}

def parse_problem(path, dom):
    root=sexpr(open(path,encoding='utf8').read())
    if not isinstance(root,list) or not root or root[0]!='define': raise PDDLError('not a PDDL problem')
    objects=dict(dom['constants'])
    s=section(root,':objects')
    if s: objects.update(dict(typed(s[1:])))
    initsec=section(root,':init'); goalsec=section(root,':goal')
    if initsec is None or goalsec is None: raise PDDLError('problem lacks :init or :goal')
    init=[]
    for z in initsec[1:]:
        ls=literals(z,':init')
        if any(not sign for sign,a in ls): raise PDDLError('negative initial facts are unsupported')
        init += [a for sign,a in ls]
    goal=literals(goalsec[1],':goal')
    return {'objects':objects,'init':frozenset(init),'goal':goal}

def is_type(actual, wanted, hierarchy):
    while actual is not None:
        if actual==wanted or wanted=='object': return True
        actual=hierarchy.get(actual)
    return False

def subst(atom, bind):
    return tuple(bind.get(x,x) if x.startswith('?') else x for x in atom)

def holds(lit, state):
    sign,a=lit
    if a and a[0]=='=':
        if len(a)!=3: raise PDDLError('bad equality')
        return (a[1]==a[2]) == sign
    return (a in state) == sign

def make_grounder(dom, prob):
    objects=prob['objects']; hierarchy=dom['types']
    bytype=defaultdict(list)
    for obj,typ in objects.items():
        for wanted in hierarchy:
            if is_type(typ,wanted,hierarchy): bytype[wanted].append(obj)
    for v in bytype.values(): v.sort()

    def applicable(state, action_cap=None):
        index=defaultdict(list)
        for f in state: index[f[0]].append(f)
        for v in index.values(): v.sort()
        emitted=0
        for ac in dom['actions']:
            ptypes=dict(ac['params'])
            positives=[a for sign,a in ac['pre'] if sign and not (a and a[0]=='=')]
            positives.sort(key=lambda a:len(index.get(a[0],())))
            def rec(k, bind):
                nonlocal emitted
                if action_cap is not None and emitted>=action_cap: return
                if k<len(positives):
                    pat=positives[k]
                    for fact in index.get(pat[0],()):
                        if len(fact)!=len(pat): continue
                        b=dict(bind); ok=True
                        for term,val in zip(pat[1:],fact[1:]):
                            if term.startswith('?'):
                                if term in b and b[term]!=val: ok=False; break
                                typ=ptypes.get(term)
                                if typ and not is_type(objects.get(val,''),typ,hierarchy): ok=False; break
                                b[term]=val
                            elif term!=val: ok=False; break
                        if ok: yield from rec(k+1,b)
                    return
                missing=[(v,t) for v,t in ac['params'] if v not in bind]
                def fill(j,b):
                    nonlocal emitted
                    if action_cap is not None and emitted>=action_cap: return
                    if j<len(missing):
                        v,t=missing[j]
                        for o in bytype.get(t,[]):
                            b[v]=o; yield from fill(j+1,b)
                        b.pop(v,None); return
                    # Check all conditions after all variables are bound.
                    groundpre=[(sg,subst(a,b)) for sg,a in ac['pre']]
                    if all(holds(q,state) for q in groundpre):
                        emitted+=1
                        add=frozenset(subst(a,b) for sg,a in ac['eff'] if sg)
                        delete=frozenset(subst(a,b) for sg,a in ac['eff'] if not sg)
                        args=tuple(b[v] for v,t in ac['params'])
                        yield (ac['name'],args,add,delete)
                yield from fill(0,dict(bind))
            yield from rec(0,{})
    return applicable

def apply(state, step):
    return frozenset((set(state)-set(step[3])) | set(step[2]))

def validate(plan, dom, prob, ground):
    """Replay plan by matching the exact emitted grounding in each state."""
    st=prob['init']
    for n,args in plan:
        match=None
        for z in ground(st):
            if z[0]==n and z[1]==args: match=z; break
        if match is None: raise PDDLError('invalid action during replay: %s(%s)' % (n,','.join(args)))
        st=apply(st,match)
    if not all(holds(q,st) for q in prob['goal']): raise PDDLError('replayed final state does not satisfy goal')

def builtin(dom, prob, seconds, expansion_limit):
    ground=make_grounder(dom,prob); goal=prob['goal']
    if all(holds(q,prob['init']) for q in goal): return [],ground
    cache={}
    def heuristic(st):
        if st in cache: return cache[st]
        # Delete-relaxed planning graph. A level is the earliest fact layer.
        known=set(st); levels={a:0 for a in known}; layer=0
        while layer<80:
            if all((a in known) if sg else (a not in known) for sg,a in goal):
                h=sum(levels.get(a,0) for sg,a in goal if sg)
                cache[st]=h; return h
            changed=False
            # Negative goals cannot be made true in a delete relaxation; they still
            # receive a finite weak estimate so forward search can use delete actions.
            for z in ground(frozenset(known), action_cap=100000):
                for a in z[2]:
                    if a not in known: known.add(a); levels[a]=layer+1; changed=True
            if not changed: break
            layer+=1
        missing=sum(1 for q in goal if not holds(q,st))
        h=1000000+missing*100
        cache[st]=h; return h
    start=prob['init']; deadline=time.monotonic()+seconds
    heap=[]; serial=0
    heapq.heappush(heap,(heuristic(start),0,serial,start)); best={start:0}; parent={}
    expanded=0
    while heap:
        if time.monotonic()>deadline: raise SearchLimit('built-in search timed out')
        h,g,_,st=heapq.heappop(heap)
        if best.get(st)!=g: continue
        if all(holds(q,st) for q in goal):
            out=[]
            while st!=start:
                prev,step=parent[st]; out.append((step[0],step[1])); st=prev
            out.reverse(); return out,ground
        expanded+=1
        if expanded>expansion_limit: raise SearchLimit('built-in search exceeded expansion limit')
        succ=list(ground(st))
        # Stable order helps reproducibility; heuristic breaks unhelpful action-order ties.
        succ.sort(key=lambda z:(z[0],z[1]))
        for z in succ:
            ns=apply(st,z); ng=g+1
            if ng>=best.get(ns,10**18): continue
            best[ns]=ng; parent[ns]=(st,z); serial+=1
            heapq.heappush(heap,(heuristic(ns),ng,serial,ns))
    raise SearchLimit('built-in search exhausted reachable states')

def external_plan(dompath, probpath, dom, prob, seconds):
    exe=shutil.which('fast-downward.py') or shutil.which('fast-downward')
    if not exe: return None
    with tempfile.TemporaryDirectory(prefix='pddl-plan-') as d:
        planfile=os.path.join(d,'sas_plan')
        cmd=[exe,dompath,probpath,'--plan-file',planfile,'--search','lazy_greedy([ff()], preferred=[ff()])']
        try: subprocess.run(cmd,cwd=d,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=max(2,int(seconds)),check=False)
        except subprocess.TimeoutExpired: return None
        if not os.path.exists(planfile): return None
        ans=[]
        for line in open(planfile,encoding='utf8'):
            line=line.strip()
            if not line or line.startswith(';'): continue
            m=re.match(r'^\(\s*([^\s()]+)(.*?)\)\s*$',line)
            if not m: raise PDDLError('unrecognized external plan line: '+line)
            ans.append((m.group(1),tuple(m.group(2).split())))
        return ans

def resolve(path, base): return path if os.path.isabs(path) else os.path.normpath(os.path.join(base,path))
def write_plan(path, plan):
    os.makedirs(os.path.dirname(path) or '.',exist_ok=True)
    with open(path,'w',encoding='utf8') as f:
        for name,args in plan: f.write('%s(%s)\n' % (name,', '.join(args)))

def main(cfg):
    cfg=cfg or {}; pj=os.path.abspath(cfg.get('problem_json','/app/problem.json'))
    entries=json.load(open(pj,encoding='utf8')); base=os.path.dirname(pj)
    seconds=float(cfg.get('seconds_per_problem',90)); limit=int(cfg.get('expansion_limit',250000)); mode=cfg.get('solver','auto')
    if not isinstance(entries,list): raise PDDLError('problem_json must contain an array')
    results=[]
    for ent in entries:
        try:
            dp=resolve(ent['domain'],base); pp=resolve(ent['problem'],base); op=resolve(ent['plan_output'],base)
            dom=parse_domain(dp); prob=parse_problem(pp,dom); plan=None; source='builtin'
            if mode in ('auto','fast-downward'):
                plan=external_plan(dp,pp,dom,prob,min(seconds*.55,45))
                if plan is not None: source='fast-downward'
                elif mode=='fast-downward': raise SearchLimit('Fast Downward unavailable or did not return a plan')
            if plan is None:
                plan,ground=builtin(dom,prob,seconds,limit)
            else:
                ground=make_grounder(dom,prob)
            validate(plan,dom,prob,ground); write_plan(op,plan)
            results.append({'id':ent.get('id'),'status':'solved','actions':len(plan),'output':op,'solver':source})
        except Exception as e:
            results.append({'id':ent.get('id'),'status':'failed','error':str(e)})
    return {'results':results,'solved':sum(x['status']=='solved' for x in results),'total':len(results)}
if __name__=='__main__':
    try:
        config=json.load(sys.stdin)
        print(json.dumps(main(config),sort_keys=True))
    except Exception as e:
        print(json.dumps({'status':'failed','error':str(e)})); sys.exit(2)
