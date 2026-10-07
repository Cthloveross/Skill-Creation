#!/usr/bin/env python3
"""Solve a small explicitly specified linear system from JSON stdin."""
import json, math, sys

def emit(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, allow_nan=False)); raise SystemExit(code)
def numeric(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(float(x))
def main():
    try: data=json.load(sys.stdin)
    except Exception as e: emit({"ok":False,"error":"stdin must contain JSON","detail":str(e)},1)
    if not isinstance(data,dict): emit({"ok":False,"error":"input must be an object"},1)
    names=data.get("variables"); equations=data.get("equations"); tol=data.get("tolerance",1e-12)
    if not isinstance(names,list) or not names or not all(isinstance(x,str) and x for x in names) or len(set(names))!=len(names): emit({"ok":False,"error":"variables must be unique nonempty names"},1)
    if not isinstance(equations,list) or not equations: emit({"ok":False,"error":"equations must be a nonempty array"},1)
    if not numeric(tol) or tol<=0: emit({"ok":False,"error":"tolerance must be positive and finite"},1)
    eps=float(tol); index={x:i for i,x in enumerate(names)}; a=[]
    for n,e in enumerate(equations):
        if not isinstance(e,dict) or not isinstance(e.get("coefficients"),dict) or not numeric(e.get("rhs")): emit({"ok":False,"error":"each equation needs coefficients and numeric rhs","equation":n},1)
        row=[0.0]*len(names)+[float(e["rhs"])]
        for key,x in e["coefficients"].items():
            if key not in index or not numeric(x): emit({"ok":False,"error":"unknown variable or nonnumeric coefficient","equation":n,"variable":key},1)
            row[index[key]]=float(x)
        a.append(row)
    piv=[]; r=0; width=len(names)
    for col in range(width):
        candidates=list(range(r,len(a)))
        if not candidates: break
        q=max(candidates,key=lambda i:abs(a[i][col]))
        if abs(a[q][col])<=eps: continue
        a[r],a[q]=a[q],a[r]; d=a[r][col]; a[r]=[x/d for x in a[r]]
        for i in range(len(a)):
            if i!=r and abs(a[i][col])>eps:
                f=a[i][col]; a[i]=[x-f*y for x,y in zip(a[i],a[r])]
        piv.append(col); r+=1
    if any(all(abs(x)<=eps for x in row[:width]) and abs(row[width])>eps for row in a): emit({"ok":False,"error":"system is inconsistent; no solution"},1)
    if len(piv)<width: emit({"ok":False,"error":"system is underdetermined; no unique solution","free_variables":[names[i] for i in range(width) if i not in piv]},1)
    answer=[0.0]*width
    for i,col in enumerate(piv): answer[col]=0.0 if abs(a[i][width])<=eps else a[i][width]
    residuals=[sum(float(e["coefficients"].get(n,0))*answer[i] for i,n in enumerate(names))-float(e["rhs"]) for e in equations]
    emit({"ok":True,"solution":dict(zip(names,answer)),"residuals":residuals})
if __name__=="__main__": main()
