#!/usr/bin/env python3
"""Locate lexical evidence in arbitrary JSON exports. stdin/stdout are JSON objects."""
import ast, json, re, sys
from pathlib import Path
STOP = {"the","a","an","and","or","of","to","for","in","on","at","by","with","from","is","are","was","were","be","what","which","who","when","where","how","list","all","please","this","that"}

def parse_questions(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    for load in (json.loads, ast.literal_eval):
        try:
            x = load(text)
            if isinstance(x, dict): return {str(k): str(v) for k,v in x.items()}
        except Exception: pass
    found = {m.group(1).lower(): m.group(2) for m in re.finditer(r"(?im)^\s*\"?(q\d+)\"?\s*[:：]\s*(.+?)\s*$", text)}
    if found: return found
    return {f"q{i+1}": line for i,line in enumerate(x.strip() for x in text.splitlines() if x.strip())}

def terms(q):
    return sorted({x for x in re.findall(r"[A-Za-z0-9_@./:-]{2,}", q.lower()) if x not in STOP and not x.isdigit()}, key=len, reverse=True)
def text(v, cap=500):
    s = json.dumps(v, ensure_ascii=False, default=str) if isinstance(v,(dict,list)) else str(v)
    return re.sub(r"\s+", " ", s)[:cap]
def parent_preview(p, cap):
    if not isinstance(p, dict): return None
    x = {str(k): text(v,160) for k,v in p.items() if not isinstance(v,(dict,list))}
    return text(x,cap) if x else None

def walk(v, path, parent, rel, ts, hits, limit, cap, depth=0):
    if depth > 30 or len(hits) >= limit: return
    if isinstance(v, dict):
        for k,x in v.items(): walk(x, path+"."+str(k), v, rel, ts, hits, limit, cap, depth+1)
    elif isinstance(v, list):
        for i,x in enumerate(v): walk(x, path+f"[{i}]", parent, rel, ts, hits, limit, cap, depth+1)
    else:
        s = text(v, cap*3).lower(); matched = [t for t in ts if t in s]
        if matched:
            hits.append({"file":rel,"path":path,"score":sum(min(len(t),20) for t in matched)+8*(len(matched)-1),"matched_terms":matched,"value":text(v,cap),"record_preview":parent_preview(parent,cap)})
def main():
    req=json.load(sys.stdin); root=Path(req.get("root","/root/DATA")); queries=req.get("queries") or req.get("questions")
    if queries is None and req.get("question_path"): queries=parse_questions(req["question_path"])
    if not isinstance(queries,dict): raise SystemExit("provide queries/questions mapping or question_path")
    limit=int(req.get("max_hits_per_question",80)); cap=int(req.get("max_preview_chars",420)); errors=[]; result={}
    files=sorted(root.rglob("*.json")) if root.is_dir() else []
    if not files: errors.append("No JSON files found under root")
    for key,q in queries.items():
        hits=[]; ts=terms(str(q))
        for fp in files:
            if len(hits)>=limit: break
            try: walk(json.loads(fp.read_text(encoding="utf-8")), "$", None, str(fp.relative_to(root)), ts, hits, limit, cap)
            except Exception as e: errors.append(f"{fp}: {type(e).__name__}: {e}")
        result[str(key)]=sorted(hits,key=lambda x:(-x["score"],x["file"],x["path"]))
    print(json.dumps({"queries":{str(k):str(v) for k,v in queries.items()},"results":result,"errors":errors},ensure_ascii=False))
if __name__ == "__main__": main()
