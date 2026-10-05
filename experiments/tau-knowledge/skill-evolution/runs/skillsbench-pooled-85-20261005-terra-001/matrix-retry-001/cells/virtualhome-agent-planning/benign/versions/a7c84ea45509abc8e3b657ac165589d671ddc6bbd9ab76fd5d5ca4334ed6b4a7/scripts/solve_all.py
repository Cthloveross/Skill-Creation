#!/usr/bin/env python3
"""Incremental full-manifest planner: preserve valid artifacts and solve the rest."""
import json, sys, time
from pathlib import Path
from fd_setup import ensure_fast_downward, find_fast_downward
from solve_pddl import solve

def _resolve(manifest,value):
    p=Path(value); return str(p if p.is_absolute() else manifest.parent/p)

def _existing(spec):
    p=Path(spec["plan_output"])
    if not p.is_file(): return None
    r=solve({"domain":spec["domain"],"problem":spec["problem"],"validate_plan":str(p)})
    if r.get("ok"):
        r.update({"plan_output":str(p),"method":"existing replay-valid plan"}); return r
    return None

def main():
    try:
        request=json.load(sys.stdin); manifest=Path(request.get("problem_json","/app/problem.json"))
        rows=json.loads(manifest.read_text(encoding="utf-8")); needed=("id","domain","problem","plan_output")
        if not isinstance(rows,list) or not rows or any(not isinstance(x,dict) or not all(isinstance(x.get(k),str) and x[k] for k in needed) for x in rows):
            raise ValueError("manifest must be a nonempty array of complete task rows")
        specs=[]; results=[None]*len(rows)
        for i,row in enumerate(rows):
            s=dict(row)
            for k in ("domain","problem","plan_output"): s[k]=_resolve(manifest,s[k])
            specs.append(s); results[i]=_existing(s)
        unresolved=[i for i,r in enumerate(results) if r is None]
        total=max(1,int(request.get("timeout_sec",590))); deadline=time.monotonic()+total
        setup="not needed"
        exe=find_fast_downward(request.get("fast_downward"))
        if unresolved and not exe:
            setup_budget=min(max(1,int(request.get("planner_setup_timeout_sec",330))),max(1,int(deadline-time.monotonic())-30))
            exe,setup=ensure_fast_downward(request.get("fast_downward"),timeout=setup_budget)
        elif exe: setup="existing Fast Downward"
        for ordinal,i in enumerate(unresolved):
            s=specs[i]; left=len(unresolved)-ordinal; remaining=max(0,int(deadline-time.monotonic()))
            if not exe: r={"ok":False,"valid":False,"error":setup,"plan_output":s["plan_output"]}
            elif remaining<=0: r={"ok":False,"valid":False,"error":"shared batch timeout expired","plan_output":s["plan_output"]}
            else:
                # Equal allocation prevents early hard instances from suppressing required later files.
                slice_seconds=max(1,remaining//left)
                r=solve(dict(s,fast_downward=exe,timeout_sec=slice_seconds))
            r["id"]=rows[i]["id"]; results[i]=r
        for i,r in enumerate(results):
            r["id"]=rows[i]["id"]
        missing=[r["plan_output"] for r in results if not r.get("ok") or not Path(r["plan_output"]).is_file()]
        print(json.dumps({"ok":not missing,"setup":setup,"solved":sum(bool(r.get("ok")) for r in results),"total":len(rows),"missing_outputs":missing,"results":results}))
    except Exception as e: print(json.dumps({"ok":False,"error":"manifest processing failed: %s"%e}))
if __name__=="__main__":main()
