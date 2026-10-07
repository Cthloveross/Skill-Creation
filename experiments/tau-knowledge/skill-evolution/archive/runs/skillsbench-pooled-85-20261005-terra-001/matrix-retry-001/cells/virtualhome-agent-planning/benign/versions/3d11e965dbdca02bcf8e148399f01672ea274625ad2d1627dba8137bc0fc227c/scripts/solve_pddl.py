#!/usr/bin/env python3
import json,os,signal,subprocess,sys,tempfile
from pathlib import Path
from fd_setup import ensure_fast_downward,build_for
from pddl_engine import PDDLError,load,parse_plan_text,render,validate

def command(exe,build,domain,problem,out):
 p=[sys.executable,exe] if exe.lower().endswith(".py") else [exe]
 if build: p += ["--build",build]
 return p+["--alias","lama-first",domain,problem,"--plan-file",out]
def run(domain,problem,exe,build,seconds):
 with tempfile.TemporaryDirectory(prefix="airport-plan-") as folder:
  target=str(Path(folder)/"plan")
  try:
   q=subprocess.Popen(command(exe,build,domain,problem,target),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
   try: out,err=q.communicate(timeout=max(1,int(seconds)))
   except subprocess.TimeoutExpired:
    try: os.killpg(q.pid,signal.SIGTERM)
    except OSError:q.terminate()
    try: out,err=q.communicate(timeout=4)
    except subprocess.TimeoutExpired:
     try:os.killpg(q.pid,signal.SIGKILL)
     except OSError:q.kill()
     out,err=q.communicate()
  except OSError as e:return None,"planner invocation failed: %s"%e
  for f in [Path(target)]+sorted(Path(folder).glob("plan.*"),key=lambda x:x.stat().st_mtime,reverse=True):
   if f.is_file() and f.stat().st_size:
    try:return parse_plan_text(f.read_text(encoding="utf8")),"Fast Downward lama-first"
    except PDDLError as e:return None,"planner plan parse failure: %s"%e
  return None,"planner produced no plan: "+((err or out or "").strip()[-600:])
def solve(x):
 if not isinstance(x.get("domain"),str) or not isinstance(x.get("problem"),str):return {"ok":False,"valid":False,"error":"domain and problem are required"}
 try:d,p=load(x["domain"],x["problem"])
 except (OSError,PDDLError) as e:return {"ok":False,"valid":False,"error":"PDDL load failed: %s"%e}
 if x.get("validate_plan"):
  try:plan=parse_plan_text(Path(x["validate_plan"]).read_text(encoding="utf8"))
  except (OSError,PDDLError) as e:return {"ok":False,"valid":False,"error":"plan read failed: %s"%e}
  ok,why,_=validate(d,p,plan);return {"ok":ok,"valid":ok,"actions":len(plan),"error":None if ok else why}
 exe=x.get("fast_downward"); note=None
 if not exe and not x.get("no_setup"):exe,note=ensure_fast_downward(timeout=int(x.get("planner_setup_timeout_sec",260)))
 if not exe:return {"ok":False,"valid":False,"error":note or "Fast Downward unavailable"}
 plan,method=run(x["domain"],x["problem"],exe,x.get("fast_downward_build",build_for(exe)),x.get("timeout_sec",20))
 if plan is None:return {"ok":False,"valid":False,"error":method}
 ok,why,_=validate(d,p,plan)
 if not ok:return {"ok":False,"valid":False,"error":"external plan rejected: "+why}
 out=x.get("plan_output")
 if not isinstance(out,str) or not out:return {"ok":False,"valid":False,"error":"plan_output is required"}
 try:
  z=Path(out);z.parent.mkdir(parents=True,exist_ok=True);tmp=z.with_name(z.name+".tmp");tmp.write_text(render(plan),encoding="utf8");os.replace(tmp,z)
 except OSError as e:return {"ok":False,"valid":False,"error":"cannot write plan: %s"%e}
 return {"ok":True,"valid":True,"actions":len(plan),"method":method,"plan_output":out}
def main():
 try:print(json.dumps(solve(json.load(sys.stdin))))
 except Exception as e:print(json.dumps({"ok":False,"valid":False,"error":"unexpected solver error: %s"%e}))
if __name__=="__main__":main()
