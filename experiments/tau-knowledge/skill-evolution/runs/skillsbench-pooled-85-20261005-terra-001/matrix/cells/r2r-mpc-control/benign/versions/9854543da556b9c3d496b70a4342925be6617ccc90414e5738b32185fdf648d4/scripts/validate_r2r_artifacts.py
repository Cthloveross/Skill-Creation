#!/usr/bin/env python3
"""Validate declared R2R artifact files. JSON stdin -> JSON stdout."""
import json, math, sys
from pathlib import Path

def bad(msg): raise ValueError(msg)
def number(x, label):
    if not isinstance(x, (int,float)) or isinstance(x, bool) or not math.isfinite(float(x)): bad(label + " must be finite")
    return float(x)
def vector(x, n, label):
    if not isinstance(x, list) or len(x) != n: bad(label + " must have length %d" % n)
    return [number(v, label) for v in x]
def matrix(x, rows, cols, label):
    if not isinstance(x, list) or len(x) != rows: bad(label + " has wrong row count")
    return [vector(row, cols, label) for row in x]
def main(inp):
    root = Path(inp["directory"])
    with open(root/"controller_params.json") as f: p=json.load(f)
    with open(root/"control_log.json") as f: log=json.load(f)
    with open(root/"metrics.json") as f: met=json.load(f)
    n=p.get("horizon_N")
    if not isinstance(n,int) or isinstance(n,bool) or not 3<=n<=30: bad("horizon_N must be integer in [3,30]")
    q=vector(p.get("Q_diag"),12,"Q_diag"); r=vector(p.get("R_diag"),6,"R_diag")
    if min(q)<=0 or min(r)<=0: bad("cost diagonal values must be positive")
    matrix(p.get("K_lqr"),6,12,"K_lqr"); matrix(p.get("A_matrix"),12,12,"A_matrix"); matrix(p.get("B_matrix"),12,6,"B_matrix")
    if log.get("phase")!="control" or not isinstance(log.get("data"),list) or not log["data"]: bad("control log must be nonempty control phase")
    rows=log["data"]; prev=-float("inf")
    ts=[]; tens=[]; refs=[]
    for i,row in enumerate(rows):
        if not isinstance(row,dict): bad("log row is not object")
        t=number(row.get("time"),"time");
        if t<=prev: bad("log times must be strictly ordered")
        prev=t; ts.append(t)
        tens.append(vector(row.get("tensions"),6,"tensions")); vector(row.get("velocities"),6,"velocities")
        vector(row.get("control_inputs"),6,"control_inputs"); refs.append(vector(row.get("references"),12,"references")[:6])
    if ts[-1] < 5.0-1e-9: bad("delivered trace final time must reach 5 seconds")
    flaterr=[abs(tens[i][j]-refs[i][j]) for i in range(len(rows)) for j in range(6)]
    final=[i for i,t in enumerate(ts) if t>=ts[-1]-1.0-1e-12]
    steady=sum(abs(tens[i][j]-refs[i][j]) for i in final for j in range(6))/(len(final)*6)
    mx=max(v for row in tens for v in row); mn=min(v for row in tens for v in row)
    for key in ("steady_state_error","max_tension","min_tension"): number(met.get(key),key)
    if abs(met["steady_state_error"]-steady)>1e-7: bad("steady_state_error does not match final one-second log calculation")
    if abs(met["max_tension"]-mx)>1e-7 or abs(met["min_tension"]-mn)>1e-7: bad("tension extrema do not match log")
    st=met.get("settling_time")
    if st is not None: number(st,"settling_time")
    return {"ok":True,"samples":len(rows),"final_time":ts[-1],"recomputed_steady_state_error":steady,"max_tension":mx,"min_tension":mn}
if __name__=="__main__":
    try: print(json.dumps(main(json.load(sys.stdin)),allow_nan=False))
    except Exception as e:
        print(json.dumps({"ok":False,"error":str(e)})); sys.exit(1)
