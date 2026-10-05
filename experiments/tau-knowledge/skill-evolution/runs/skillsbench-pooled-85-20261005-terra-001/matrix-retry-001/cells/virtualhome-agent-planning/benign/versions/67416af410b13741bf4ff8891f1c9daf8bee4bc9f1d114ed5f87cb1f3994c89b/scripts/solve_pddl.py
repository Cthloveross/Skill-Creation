import json,os,signal,subprocess,sys,tempfile
from pathlib import Path
from fd_setup import ensure
from pddl_engine import PDDLError,load,parse,render,validate,search

def commit(path,plan):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.tmp');tmp.write_text(render(plan),encoding='utf8');os.replace(tmp,p)
def command(driver,profile,plan,domain,problem):
 c=[sys.executable,driver] if driver.endswith('.py') else [driver]
 if profile:c+=['--build',profile]
 return c+['--plan-file',plan,'--alias','lama-first',domain,problem]
def solve(r):
 try:d,p=load(r['domain'],r['problem'])
 except Exception as e:return {'ok':False,'valid':False,'error':'PDDL load failed: %s'%e}
 if r.get('validate_plan'):
  try:z=parse(Path(r['validate_plan']).read_text(encoding='utf8'))
  except Exception as e:return {'ok':False,'valid':False,'error':'plan read failed: %s'%e}
  ok,msg,_=validate(d,p,z);return {'ok':ok,'valid':ok,'actions':len(z),'error':None if ok else msg}
 out=r.get('plan_output')
 if not out:return {'ok':False,'valid':False,'error':'plan_output is required'}
 ok,_,_=validate(d,p,[])
 if ok:commit(out,[]);return {'ok':True,'valid':True,'actions':0,'plan_output':out}
 z=search(d,p,r.get('fallback_timeout_sec',3),r.get('fallback_max_expansions',100000))
 if z is not None:
  ok,msg,_=validate(d,p,z)
  if ok:commit(out,z);return {'ok':True,'valid':True,'actions':len(z),'plan_output':out,'solver':'internal'}
 if r.get('fallback_only'):return {'ok':False,'valid':False,'error':'internal search found no plan within budget','plan_output':out}
 driver,profile=r.get('fast_downward'),r.get('fast_downward_build')
 if not driver:
  driver,profile=ensure(timeout=r.get('planner_setup_timeout_sec',300))
  if not driver:return {'ok':False,'valid':False,'error':str(profile),'plan_output':out}
 plan=None
 with tempfile.TemporaryDirectory(prefix='pddl-plan-') as td:
  base=str(Path(td)/'sas_plan');proc=None
  try:
   proc=subprocess.Popen(command(driver,profile,base,r['domain'],r['problem']),start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
   proc.communicate(timeout=max(1,int(r.get('timeout_sec',20))))
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGTERM);proc.communicate()
  except Exception as e:return {'ok':False,'valid':False,'error':'planner launch failed: %s'%e,'plan_output':out}
  for f in [Path(base)]+sorted(Path(td).glob('sas_plan.*'),key=lambda x:x.stat().st_mtime,reverse=True):
   if not f.is_file() or not f.stat().st_size:continue
   try:z=parse(f.read_text(encoding='utf8'))
   except PDDLError:continue
   if validate(d,p,z)[0]:plan=z;break
 if plan is None:return {'ok':False,'valid':False,'error':'planner produced no replay-valid plan','plan_output':out}
 commit(out,plan);return {'ok':True,'valid':True,'actions':len(plan),'plan_output':out,'solver':'fast-downward'}
def main():
 try:print(json.dumps(solve(json.load(sys.stdin))))
 except Exception as e:print(json.dumps({'ok':False,'valid':False,'error':str(e)}))
if __name__=='__main__':main()
