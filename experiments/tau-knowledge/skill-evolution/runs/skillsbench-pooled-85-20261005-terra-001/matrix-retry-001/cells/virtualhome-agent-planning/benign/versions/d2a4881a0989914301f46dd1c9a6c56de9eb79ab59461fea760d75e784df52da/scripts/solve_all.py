import json,sys,time
from pathlib import Path
from fd_setup import ensure
from solve_pddl import solve
def path(m,x):
 p=Path(x);return str(p if p.is_absolute() else m.parent/p)
def main():
 try:
  r=json.load(sys.stdin);m=Path(r.get('problem_json','/app/problem.json'));rows=json.loads(m.read_text());end=time.monotonic()+int(r.get('timeout_sec',590)); specs=[];results=[]
  for row in rows:
   if not all(row.get(k) for k in ('id','domain','problem','plan_output')):raise ValueError('bad manifest row')
   s={k:(path(m,row[k]) if k in ('domain','problem','plan_output') else row[k]) for k in row};specs.append(s)
   old=Path(s['plan_output'])
   results.append(solve({'domain':s['domain'],'problem':s['problem'],'validate_plan':str(old)}) if old.is_file() else None)
  todo=[i for i,x in enumerate(results) if not x or not x.get('ok')];driver=prof=None;setup='all retained'
  if todo:
   driver,prof=ensure(r.get('fast_downward'),timeout=min(int(r.get('planner_setup_timeout_sec',360)),max(1,int(end-time.monotonic()-20)));setup='ready' if driver else str(prof)
  # Reserve a short attempt for every later row, but prioritize early missing artifacts.
  for pos,i in enumerate(todo):
   left=max(1,int(end-time.monotonic()));later=len(todo)-pos-1;budget=min(int(r.get('per_task_timeout_sec',120)),max(5,left-5*later))
   z={'ok':False,'valid':False,'error':setup,'plan_output':specs[i]['plan_output']} if not driver else solve(dict(specs[i],fast_downward=driver,fast_downward_build=prof,timeout_sec=budget))
   z['id']=rows[i]['id'];results[i]=z
  for i,z in enumerate(results):z['id']=rows[i]['id'];z.setdefault('plan_output',specs[i]['plan_output'])
  missing=[z['plan_output'] for z in results if not z.get('ok') or not Path(z['plan_output']).is_file()]
  print(json.dumps({'ok':not missing,'setup':setup,'solved':sum(bool(z.get('ok')) for z in results),'total':len(rows),'missing_outputs':missing,'results':results}))
 except Exception as e:print(json.dumps({'ok':False,'error':'manifest processing failed: %s'%e}))
if __name__=='__main__':main()
