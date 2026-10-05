#!/usr/bin/env python3
"""Check that proposed person values have bounded relation-record evidence.
stdin: {root, question, candidates, max_records?}; stdout: candidate evidence.
Only explicitly labelled identity-like fields are used for metadata links.
"""
import json, re, sys
from pathlib import Path

IDENTITY = ("id", "email", "mail", "user", "employee", "author", "owner", "member", "person", "participant", "reviewer")
RELATION = ("author", "review", "reviewer", "reviewed", "approv", "contributor", "owner", "editor")

def scalar_values(v):
    if isinstance(v, dict):
        out=[]
        for x in v.values(): out.extend(scalar_values(x))
        return out
    if isinstance(v, list):
        out=[]
        for x in v: out.extend(scalar_values(x))
        return out
    if isinstance(v, (str, int, float)) and not isinstance(v, bool):
        s=str(v).strip()
        return [s] if s else []
    return []

def identities(v):
    found=set()
    if isinstance(v, dict):
        for key, child in v.items():
            label=str(key).casefold()
            if any(word in label for word in IDENTITY) and isinstance(child, (str,int,float)) and not isinstance(child,bool):
                value=str(child).strip().casefold()
                if len(value) >= 4: found.add(value)
            if isinstance(child, (dict,list)): found.update(identities(child))
    elif isinstance(v, list):
        for child in v: found.update(identities(child))
    return found

def preview(v, cap=900):
    return re.sub(r"\s+", " ", json.dumps(v, ensure_ascii=False, default=str))[:cap]

def records(root):
    out=[]
    def visit(v, file, path, depth=0):
        if isinstance(v, dict):
            values=scalar_values(v)
            text=" ".join(values).casefold()
            if depth > 0 and 2 <= len(values) <= 180 and len(text) <= 14000:
                out.append({"file":file,"path":path,"text":text,"ids":identities(v),"preview":preview(v)})
            for k,x in v.items(): visit(x,file,path+"."+str(k),depth+1)
        elif isinstance(v,list):
            for i,x in enumerate(v): visit(x,file,path+f"[{i}]",depth+1)
    errors=[]
    for fp in sorted(root.rglob("*.json")):
        try: visit(json.loads(fp.read_text(encoding="utf-8")),str(fp.relative_to(root)),"$")
        except Exception as exc: errors.append(f"{fp}: {type(exc).__name__}: {exc}")
    return out,errors

def main():
    req=json.load(sys.stdin)
    root=Path(req.get("root","/root/DATA")); question=str(req.get("question",""))
    candidates=req.get("candidates",[])
    if not root.is_dir(): raise SystemExit("root is not a directory")
    if not isinstance(candidates,list): raise SystemExit("candidates must be a list")
    rows, errors=records(root)
    qwords=set(re.findall(r"[a-z][a-z0-9_-]{3,}",question.casefold()))
    asked_relation={w for w in qwords if any(r in w for r in RELATION)}
    # If no relation word was stated, this checker exposes candidate/anchor evidence
    # but does not claim a person relation exists.
    relation_words=asked_relation or set()
    limit=max(1,int(req.get("max_records",12)))
    result={}
    for raw in candidates:
        candidate=str(raw).strip(); needle=candidate.casefold()
        containing=[r for r in rows if needle and needle in r["text"]]
        direct=[r for r in containing if relation_words and any(w in r["text"] for w in relation_words)]
        candidate_ids=set()
        for r in containing: candidate_ids.update(r["ids"])
        linked=[r for r in rows if relation_words and any(w in r["text"] for w in relation_words) and candidate_ids.intersection(r["ids"])]
        def render(rs):
            return [{"file":r["file"],"path":r["path"],"identity_values":sorted(r["ids"]),"preview":r["preview"]} for r in rs[:limit]]
        result[candidate]={"direct_relation_records":render(direct),"linked_relation_records":render(linked),"candidate_identity_values":sorted(candidate_ids),"records_containing_candidate":render(containing)}
    print(json.dumps({"question":question,"relation_terms":sorted(relation_words),"candidates":result,"errors":errors},ensure_ascii=False))
if __name__ == "__main__": main()
