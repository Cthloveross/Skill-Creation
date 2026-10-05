import json, sys, time
from pathlib import Path
from fd_setup import ensure
from solve_pddl import solve

def resolve(manifest, value):
    p=Path(value)
    return str(p if p.is_absolute() else manifest.parent/p)
def main():
    try:
        request=json.load(sys.stdin); manifest=Path(request.get('problem_json','/app/problem.json'))
        rows=json.loads(manifest.read_text(encoding='utf8'))
        if not isinstance(rows,list) or not rows: raise ValueError('manifest must be a nonempty list')
        specs=[]; results=[None]*len(rows)
        for i,row in enumerate(rows):
            if not isinstance(row,dict) or not all(row.get(k) for k in ('id','domain','problem','plan_output')):
                raise ValueError('manifest row lacks required fields')
            spec=dict(row)
            for key in ('domain','problem','plan_output'): spec[key]=resolve(manifest,row[key])
            specs.append(spec); existing=Path(spec['plan_output'])
            if existing.is_file(): results[i]=solve({'domain':spec['domain'],'problem':spec['problem'],'validate_plan':str(existing)})
        deadline=time.monotonic()+max(1,int(request.get('timeout_sec',595)))
        pending=[i for i,x in enumerate(results) if not x or not x.get('ok')]
        driver=profile=None; setup='all existing plans replay-valid'
        if pending:
            setup_limit=min(int(request.get('planner_setup_timeout_sec',450)),max(1,int(deadline-time.monotonic()-5)))
            driver,profile=ensure(request.get('fast_downward'),setup_limit)
            setup='planner ready' if driver else str(profile)
        for position,index in enumerate(pending):
            left=len(pending)-position; remain=max(1,int(deadline-time.monotonic()))
            # Reserve a small launch window for every later row, but let easy rows
            # return early and leave their unused time for the difficult instances.
            allowance=min(int(request.get('per_task_timeout_sec',45)),max(1,remain-(left-1)*2))
            results[index]=solve(dict(specs[index],fast_downward=driver,fast_downward_build=profile,
                timeout_sec=allowance,fallback_timeout_sec=request.get('fallback_timeout_sec',0))) if driver else {
                'ok':False,'valid':False,'error':setup,'plan_output':specs[index]['plan_output']}
        for i,result in enumerate(results):
            result['id']=rows[i]['id']; result.setdefault('plan_output',specs[i]['plan_output'])
        missing=[x['plan_output'] for x in results if not x.get('ok') or not Path(x['plan_output']).is_file()]
        print(json.dumps({'ok':not missing,'setup':setup,'solved':sum(bool(x.get('ok')) for x in results),
            'total':len(rows),'missing_outputs':missing,'results':results}))
    except Exception as exc:
        print(json.dumps({'ok':False,'error':'manifest processing failed: %s'%exc}))
if __name__=='__main__': main()
