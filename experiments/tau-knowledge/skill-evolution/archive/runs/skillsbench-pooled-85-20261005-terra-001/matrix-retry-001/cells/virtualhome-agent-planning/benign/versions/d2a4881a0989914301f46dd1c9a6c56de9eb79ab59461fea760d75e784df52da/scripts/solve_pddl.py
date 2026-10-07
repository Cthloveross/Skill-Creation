import json,os,signal,subprocess,sys,tempfile
from pathlib import Path
from fd_setup import ensure,profile
from pddl_engine import *
def commit(path,plan):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_name(p.name+'.tmp');q.write_text(render(plan));os.replace(q,p)
def solve(r):
 try:d,p=load(r['domain'],r['problem'])
 except Exception as e:return {'ok':False,'valid':False,'error':'PDDL load failed: %s'%e}
 if r.get('validate_plan'):
  try:plan=parse(Path(r['validate_plan']).read_text())
  except Exception as e:return {'ok':False,'valid':False,'error':'plan read failed: %s'%e}
  ok,msg,_=validate(d,p,plan);return {'ok':ok,'valid':ok,'actions':len(plan),'error':None if ok else msg}
 out=r.get('plan_output')
 if not out:return {'ok':False,'valid':False,'error':'plan_output required'}
 ok,_,_=validate(d,p,[])
 if ok:commit(out,[]);return {'ok':True,'valid':True,'actions':0,'plan_output':out}
 driver=r.get('fast_downward'); prof=r.get('fast_downward_build')
 if not driver:
  driver,prof=ensure(timeout=r.get('planner_setup_timeout_sec',360))
  if not driver:return {'ok':False,'valid':False,'error':str(prof),'plan_output':out}
 with tempfile.TemporaryDirectory() as td:
  f=str(Path(td)/'sas_plan');cmd=([sys.executable,driver] if driver.endswith('.py') else [driver])+((['--build',prof]) if prof else [])+['--plan-file',f,'--alias','lama-first',r['domain'],r['problem']]
  try:
   x=subprocess.Popen(cmd,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True);x.communicate(timeout=max(1,int(r.get('timeout_sec',120))))
  except subprocess.TimeoutExpired:
   os.killpg(x.pid,signal.SIGTERM);x.communicate()
  files=[Path(f)]+sorted(Path(td).glob('sas_plan.*'),reverse=True)
  plan=None
  for q in files:
   if q.is_file() and q.stat().st_size:
    try:plan=parse(q.read_text());break
    except PDDLError:pass
 if plan is None:return {'ok':False,'valid':False,'error':'planner produced no readable plan','plan_output':out}
 ok,msg,_=validate(d,p,plan)
 if not ok:return {'ok':False,'valid':False,'error':'external plan rejected: '+msg,'plan_output':out}
 commit(out,plan);return {'ok':True,'valid':True,'actions':len(plan),'plan_output':out}
def main():
 try:print(json.dumps(solve(json.load(sys.stdin))))
 except Exception as e:print(json.dumps({'ok':False,'valid':False,'error':str(e)}))
if __name__=='__main__':main()
