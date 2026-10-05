#!/usr/bin/env python3
"""Check answer artifact structure and numeric token logs; does not judge facts."""
import ast,json,math,re,sys
from pathlib import Path

def qkeys(path):
    text=Path(path).read_text(encoding="utf-8")
    for load in (json.loads,ast.literal_eval):
        try:
            x=load(text)
            if isinstance(x,dict): return set(map(str,x))
        except Exception: pass
    return set(x.lower() for x in re.findall(r'(?im)^\s*"?(q\d+)"?\s*[:：]',text))
def num(v):
    return (isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>=0) or (isinstance(v,str) and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*",v) is not None)
def main():
    req=json.load(sys.stdin); issues=[]
    try: data=json.loads(Path(req.get("answer_path","/root/answer.json")).read_text(encoding="utf-8"))
    except Exception as e: print(json.dumps({"ok":False,"issues":[f"cannot read valid JSON: {e}"]})); return
    if not isinstance(data,dict): issues.append("top level must be an object")
    else:
        for k,row in data.items():
            if not isinstance(row,dict) or set(row)!={"answer","tokens"}: issues.append(f"{k}: requires exactly answer and tokens")
            else:
                if not isinstance(row["answer"],list): issues.append(f"{k}.answer must be a list")
                if not num(row["tokens"]): issues.append(f"{k}.tokens must be a non-negative numeric count")
        if req.get("questions_path") and qkeys(req["questions_path"])!=set(data): issues.append("question key mismatch")
    print(json.dumps({"ok":not issues,"issues":issues,"keys":list(data) if isinstance(data,dict) else []}))
if __name__ == "__main__": main()
