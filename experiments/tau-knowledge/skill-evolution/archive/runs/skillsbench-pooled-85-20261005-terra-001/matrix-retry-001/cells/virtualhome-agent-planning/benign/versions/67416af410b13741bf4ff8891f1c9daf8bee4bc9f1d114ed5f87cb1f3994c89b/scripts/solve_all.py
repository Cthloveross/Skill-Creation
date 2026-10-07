import json,sys,time
from pathlib import Path
from fd_setup import ensure
from solve_pddl import solve

def path(manifest,x):
 p=Path(x);return str(p if p.is_absolute() else manifest.parent/p)
def main():
 try:
  r=json.load(sys.stdin);m=Path(r.get('problem_json','/app/problem.json'));rows=json.loads(m.read_text(encoding='utf8'))
  if not isinstance(rows,list) or not rows:raise ValueError('manifest must be a nonempty list')
  specs=[];results=[]
  for row in rows:
   if not isinstance(row,dict) or not all(row.get(k) for k in ('id','domain','problem','plan_output')):raise ValueError('manifest row lacks required fields')
   s=dict(row);s.update({k:path(m,row[k]) for k in ('domain','problem','plan_output')});specs.append(s);f=Path(s['plan_output'])
   results.append(solve({'domain':s['domain'],'problem':s['problem'],'validate_plan':str(f)}) if f.is_file() else None)
  # Commit inexpensive internal-search solutions before any planner setup can consume the batch budget.
  for i,x in enumerate(results):
   if not x or not x.get('ok'):
    results[i]=solve(dict(specs[i],fallback_only=True,fallback_timeout_sec=r.get('fallback_timeout_sec',3)))
  pending=[i for i,x in enumerate(results) if not x.get('ok')];deadline=time.monotonic()+max(1,int(r.get('timeout_sec',595)));driver=profile=None;setup='all plans solved internally'
  if pending:
   reserve=max(20,5*len(pending));budget=min(int(r.get('planner_setup_timeout_sec',300)),max(1,int(deadline-time.monotonic()-reserve)))
   driver,profile=ensure(r.get('fast_downward'),budget);setup='planner ready' if driver else str(profile)
  for pos,i in enumerate(pending):
   remain=max(1,int(deadline-time.monotonic()));left=len(pending)-pos
   budget=min(int(r.get('per_task_timeout_sec',20)),max(1,remain//left))
   x=solve(dict(specs[i],fast_downward=driver,fast_downward_build=profile,timeout_sec=budget,fallback_timeout_sec=0.05)) if driver else {'ok':False,'valid':False,'error':setup,'plan_output':specs[i]['plan_output']}
   results[i]=x
  for i,x in enumerate(results):x['id']=rows[i]['id'];x.setdefault('plan_output',specs[i]['plan_output'])
  missing=[x['plan_output'] for x in results if not x.get('ok') or not Path(x['plan_output']).is_file()]
  print(json.dumps({'ok':not missing,'setup':setup,'solved':sum(bool(x.get('ok')) for x in results),'total':len(rows),'missing_outputs':missing,'results':results}))
 except Exception as e:print(json.dumps({'ok':False,'error':'manifest processing failed: %s'%e}))
if __name__=='__main__':main()
