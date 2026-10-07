#!/usr/bin/env python3
"""Atomically write typed answer JSON; stdin: answers, output_path?, questions_path?, tokens?."""
import ast, json, math, os, re, sys
from pathlib import Path

def qkeys(path):
    text=Path(path).read_text(encoding="utf-8")
    for load in (json.loads,ast.literal_eval):
        try:
            x=load(text)
            if isinstance(x,dict): return [str(k) for k in x]
        except Exception: pass
    return [x.lower() for x in re.findall(r'(?im)^\s*"?(q\d+)"?\s*[:：]',text)]
def numeric(v):
    if isinstance(v,bool): return False
    if isinstance(v,(int,float)): return math.isfinite(v) and v>=0
    if isinstance(v,str): return re.fullmatch(r"\s*\d+(?:\.\d+)?\s*",v) is not None
    return False
def main():
    req=json.load(sys.stdin); answers=req.get("answers")
    if not isinstance(answers,dict): raise SystemExit("answers must be an object keyed by question ID")
    expected=qkeys(req["questions_path"]) if req.get("questions_path") else []
    rendered_keys=[str(k) for k in answers]
    if expected and set(expected)!=set(rendered_keys): raise SystemExit("answer keys do not match questions; missing=%s extra=%s"%(sorted(set(expected)-set(rendered_keys)),sorted(set(rendered_keys)-set(expected))))
    supplied=req.get("tokens",0); rendered={}
    for key,value in answers.items():
        if not isinstance(value,list): raise SystemExit(f"{key}.answer must be a list")
        tok=supplied.get(str(key),0) if isinstance(supplied,dict) else supplied
        if not numeric(tok): raise SystemExit(f"{key}.tokens must be a non-negative numeric count")
        rendered[str(key)]={"answer":value,"tokens":tok}
    out=Path(req.get("output_path","/root/answer.json")); out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_name(out.name+".tmp"); tmp.write_text(json.dumps(rendered,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); os.replace(tmp,out)
    print(json.dumps({"ok":True,"output_path":str(out),"question_keys":list(rendered),"count":len(rendered)}))
if __name__ == "__main__": main()
