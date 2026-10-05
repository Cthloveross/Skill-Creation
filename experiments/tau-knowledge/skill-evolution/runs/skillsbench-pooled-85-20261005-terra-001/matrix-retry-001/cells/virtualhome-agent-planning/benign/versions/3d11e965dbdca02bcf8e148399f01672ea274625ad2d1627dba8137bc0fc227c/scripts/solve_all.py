#!/usr/bin/env python3
"""Incrementally solve all manifest rows and commit each verified artifact."""
import json,sys,time
from pathlib import Path
from fd_setup import ensure_fast_downward,find_fast_downward,build_for
from solve_pddl import solve

def resolve(m,v):
 p=Path(v);return str(p if p.is_absolute() else m.parent/p)
def existing(s):
 p=Path(s["plan_output"])
 if not p.is_file():return None
 r=solve({"domain":s["domain"],"problem":s["problem"],"validate_plan":str(p)})
 if r.get("ok"):r.update({"plan_output":str(p),"method":"existing replay-valid plan"});return r
 return None
def main():
 try:
  req=json.load(sys.stdin); manifest=Path(req.get("problem_json","/app/problem.json")); rows=json.loads(manifest.read_text(encoding="utf8")); need=("id","domain","problem","plan_output")
  if not isinstance(rows,list) or not rows or any(not isinstance(r,dict) or not all(isinstance(r.get(k),str) and r[k] for k in need) for r in rows):raise ValueError("manifest must be a nonempty array of complete task rows")
  specs=[];results=[]
  for r in rows:
   s=dict(r)
   for k in ("domain","problem","plan_output"):s[k]=resolve(manifest,s[k])
   specs.append(s);results.append(existing(s))
  todo=[i for i,r in enumerate(results) if r is None]; deadline=time.monotonic()+max(1,int(req.get("timeout_sec",590)))
  exe=find_fast_downward(req.get("fast_downward"));setup="not needed"
  if todo and not exe:
   allowed=min(max(1,int(req.get("planner_setup_timeout_sec",260))),max(1,int(deadline-time.monotonic())-45));exe,setup=ensure_fast_downward(req.get("fast_downward"),timeout=allowed)
  elif exe:setup="existing Fast Downward"
  profile=build_for(exe)
  for pos,i in enumerate(todo):
   remain=max(0,int(deadline-time.monotonic())); left=len(todo)-pos
   if not exe:r={"ok":False,"valid":False,"error":setup,"plan_output":specs[i]["plan_output"]}
   elif remain<=0:r={"ok":False,"valid":False,"error":"shared batch timeout expired","plan_output":specs[i]["plan_output"]}
   else:
    # Preserve time for every mandatory output; a plan found before a timeout is retained.
    r=solve(dict(specs[i],fast_downward=exe,fast_downward_build=profile,timeout_sec=max(1,remain//left),no_setup=True))
   r["id"]=rows[i]["id"];results[i]=r
  for i,r in enumerate(results):r["id"]=rows[i]["id"]
  missing=[r["plan_output"] for r in results if not r.get("ok") or not Path(r["plan_output"]).is_file()]
  print(json.dumps({"ok":not missing,"setup":setup,"solved":sum(bool(r.get("ok")) for r in results),"total":len(rows),"missing_outputs":missing,"results":results}))
 except Exception as e:print(json.dumps({"ok":False,"error":"manifest processing failed: %s"%e}))
if __name__=="__main__":main()
