"""Small dependency-free PDDL reader and ADL grounded-plan replayer."""
import itertools
import re

class PDDLError(Exception):
    pass

def _tokens(s):
    return re.findall(r"[()]|[^\s()]+", re.sub(r";[^\n]*", "", s).lower())

def sexpr_file(path):
    ts = _tokens(open(path, encoding="utf-8").read()); i = 0
    def read():
        nonlocal i
        if i >= len(ts): raise PDDLError("unexpected end of PDDL")
        x = ts[i]; i += 1
        if x != "(": return x
        out = []
        while True:
            if i >= len(ts): raise PDDLError("unclosed PDDL list")
            if ts[i] == ")": i += 1; return out
            out.append(read())
    root = read()
    if i != len(ts): raise PDDLError("extra PDDL tokens")
    return root

def typed(items, default="object"):
    out=[]; waiting=[]; i=0
    while i < len(items):
        if items[i] == "-":
            if i + 1 >= len(items): raise PDDLError("dangling type marker")
            out += [(x, items[i+1]) for x in waiting]; waiting=[]; i += 2
        else: waiting.append(items[i]); i += 1
    return out + [(x, default) for x in waiting]

def _entries(root):
    if not isinstance(root, list) or not root or root[0] != "define": raise PDDLError("expected define")
    return root[1:]

def _fields(a):
    out={}; i=2
    while i < len(a):
        if not isinstance(a[i], str) or not a[i].startswith(":") or i+1 >= len(a): raise PDDLError("malformed action")
        out[a[i]]=a[i+1]; i += 2
    return out

def parse_domain(path):
    types={"object":None}; constants={}; actions=[]
    for x in _entries(sexpr_file(path)):
        if not isinstance(x,list) or not x: continue
        if x[0] == ":types": types.update(typed(x[1:]))
        elif x[0] == ":constants": constants.update(typed(x[1:]))
        elif x[0] == ":action":
            f=_fields(x)
            if len(x)<2 or not all(k in f for k in (":parameters",":precondition",":effect")): raise PDDLError("incomplete action")
            actions.append({"name":x[1],"params":typed(f[":parameters"]),"pre":f[":precondition"],"eff":f[":effect"]})
    if not actions: raise PDDLError("domain has no actions")
    return {"types":types,"constants":constants,"actions":actions}

def parse_problem(path, domain):
    objects=dict(domain["constants"]); initial=set(); goal=None
    for x in _entries(sexpr_file(path)):
        if not isinstance(x,list) or not x: continue
        if x[0] == ":objects": objects.update(typed(x[1:]))
        elif x[0] == ":init":
            for a in x[1:]:
                if not isinstance(a,list) or not a or a[0] == "not": raise PDDLError("malformed or negative initial fact")
                initial.add(tuple(a))
        elif x[0] == ":goal":
            if len(x)!=2: raise PDDLError("malformed goal")
            goal=x[1]
    if goal is None: raise PDDLError("problem lacks goal")
    return {"objects":objects,"init":frozenset(initial),"goal":goal}

def load(domain_path, problem_path):
    d=parse_domain(domain_path); return d,parse_problem(problem_path,d)

def is_subtype(actual,wanted,types):
    while actual is not None:
        if actual==wanted:return True
        actual=types.get(actual)
    return False

def _atom(x,e):
    if not isinstance(x,list) or not x: raise PDDLError("expected predicate atom")
    return tuple(e.get(v,v) for v in x)

def formula(x,state,e,objects,types):
    if not isinstance(x,list) or not x: raise PDDLError("invalid formula")
    op=x[0]
    if op=="and": return all(formula(y,state,e,objects,types) for y in x[1:])
    if op=="or": return any(formula(y,state,e,objects,types) for y in x[1:])
    if op=="not": return not formula(x[1],state,e,objects,types)
    if op=="imply": return not formula(x[1],state,e,objects,types) or formula(x[2],state,e,objects,types)
    if op=="=": return len(x)==3 and e.get(x[1],x[1])==e.get(x[2],x[2])
    if op in ("forall","exists"):
        if len(x)!=3: raise PDDLError("malformed quantifier")
        es=[dict(e)]
        for v,t in typed(x[1]):
            es=[dict(z,**{v:o}) for z in es for o,ot in objects.items() if is_subtype(ot,t,types)]
        values=[formula(x[2],state,z,objects,types) for z in es]
        return all(values) if op=="forall" else any(values)
    return _atom(x,e) in state

def effects(x,state,e,objects,types):
    if not isinstance(x,list) or not x: raise PDDLError("invalid effect")
    op=x[0]
    if op=="and":
        a=set(); d=set()
        for y in x[1:]:
            aa,dd=effects(y,state,e,objects,types); a|=aa; d|=dd
        return a,d
    if op=="not": return set(),{_atom(x[1],e)}
    if op=="when": return effects(x[2],state,e,objects,types) if formula(x[1],state,e,objects,types) else (set(),set())
    if op=="forall":
        vs=typed(x[1]); pools=[[o for o,ot in objects.items() if is_subtype(ot,t,types)] for _,t in vs]
        a=set(); d=set()
        for values in itertools.product(*pools):
            z=dict(e); z.update(dict(zip([v for v,_ in vs],values)))
            aa,dd=effects(x[2],state,z,objects,types); a|=aa; d|=dd
        return a,d
    return {_atom(x,e)},set()

def apply(action,args,state,objects,types):
    if len(args)!=len(action["params"]): raise PDDLError("wrong argument count")
    e={}
    for (v,t),o in zip(action["params"],args):
        if o not in objects: raise PDDLError("unknown object "+o)
        if not is_subtype(objects[o],t,types): raise PDDLError("incompatible object "+o)
        e[v]=o
    if not formula(action["pre"],state,e,objects,types): return None
    a,d=effects(action["eff"],state,e,objects,types)
    return frozenset((set(state)-d)|a)

def validate(domain,problem,plan):
    schemas={a["name"]:a for a in domain["actions"]}; state=problem["init"]
    for n,(name,args) in enumerate(plan,1):
        if name not in schemas:return False,"step %d: unknown action %s"%(n,name),None
        try: nxt=apply(schemas[name],args,state,problem["objects"],domain["types"])
        except PDDLError as ex:return False,"step %d: %s"%(n,ex),None
        if nxt is None:return False,"step %d: unsatisfied precondition"%n,None
        state=nxt
    try: ok=formula(problem["goal"],state,{},problem["objects"],domain["types"])
    except PDDLError as ex:return False,"goal evaluation failed: "+str(ex),state
    return (True,"valid",state) if ok else (False,"final state does not satisfy complete goal",state)

def parse_plan_line(raw):
    s=raw.split(";",1)[0].strip().lower()
    if not s:return None
    s=re.sub(r"^\s*[0-9.]+\s*:\s*","",s); s=re.sub(r"\s*\[[^]]+\]\s*$","",s)
    m=re.fullmatch(r"([\w-]+)\s*\(([^()]*)\)",s)
    if m:return m.group(1),tuple(x for x in re.split(r"[\s,]+",m.group(2).strip()) if x)
    m=re.fullmatch(r"\(\s*([\w-]+)((?:\s+[\w-]+)*)\s*\)",s)
    if m:return m.group(1),tuple(m.group(2).split())
    raise PDDLError("cannot parse plan line: "+raw.strip())

def parse_plan_text(text): return [x for x in (parse_plan_line(line) for line in text.splitlines()) if x is not None]
def render(plan): return "".join("%s(%s)\n"%(n,", ".join(a)) for n,a in plan)
