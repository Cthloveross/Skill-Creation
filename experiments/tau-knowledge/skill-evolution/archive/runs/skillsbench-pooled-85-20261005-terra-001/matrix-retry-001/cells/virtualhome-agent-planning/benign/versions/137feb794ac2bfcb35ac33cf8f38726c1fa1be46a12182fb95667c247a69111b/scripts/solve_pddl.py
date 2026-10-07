import json, os, signal, subprocess, sys, tempfile
from pathlib import Path
from fd_setup import ensure
from pddl_engine import PDDLError, load, parse, render, search, validate

def commit(path, plan):
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.tmp')
    temporary.write_text(render(plan),encoding='utf8'); os.replace(temporary,target)
def command(driver, profile, output, domain, problem):
    cmd=[sys.executable,driver] if driver.endswith('.py') else [driver]
    if profile: cmd += ['--build',profile]
    return cmd+['--plan-file',output,'--alias','lama-first',domain,problem]
def solve(req):
    try: domain,problem=load(req['domain'],req['problem'])
    except Exception as exc: return {'ok':False,'valid':False,'error':'PDDL load failed: %s'%exc}
    if req.get('validate_plan'):
        try: plan=parse(Path(req['validate_plan']).read_text(encoding='utf8'))
        except Exception as exc: return {'ok':False,'valid':False,'error':'plan read failed: %s'%exc}
        ok,msg,_=validate(domain,problem,plan)
        return {'ok':ok,'valid':ok,'actions':len(plan),'error':None if ok else msg}
    output=req.get('plan_output')
    if not output: return {'ok':False,'valid':False,'error':'plan_output is required'}
    ok,_,_=validate(domain,problem,[])
    if ok:
        commit(output,[]); return {'ok':True,'valid':True,'actions':0,'plan_output':output}
    fallback=float(req.get('fallback_timeout_sec',0) or 0)
    if fallback>0:
        plan=search(domain,problem,fallback,req.get('fallback_max_expansions',20000))
        if plan is not None and validate(domain,problem,plan)[0]:
            commit(output,plan); return {'ok':True,'valid':True,'actions':len(plan),'plan_output':output,'solver':'internal'}
    driver,profile=req.get('fast_downward'),req.get('fast_downward_build')
    if not driver:
        driver,profile=ensure(req.get('fast_downward'),req.get('planner_setup_timeout_sec',450))
        if not driver: return {'ok':False,'valid':False,'error':str(profile),'plan_output':output}
    plan=None
    with tempfile.TemporaryDirectory(prefix='airport-plan-') as tmp:
        base=str(Path(tmp)/'sas_plan'); proc=None
        try:
            proc=subprocess.Popen(command(driver,profile,base,req['domain'],req['problem']),
                start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
            proc.communicate(timeout=max(1,int(req.get('timeout_sec',45))))
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGTERM); proc.communicate()
        except Exception as exc:
            return {'ok':False,'valid':False,'error':'planner launch failed: %s'%exc,'plan_output':output}
        candidates=[Path(base)]+sorted(Path(tmp).glob('sas_plan.*'),key=lambda p:p.stat().st_mtime,reverse=True)
        for candidate in candidates:
            if not candidate.is_file() or not candidate.stat().st_size: continue
            try: trial=parse(candidate.read_text(encoding='utf8'))
            except PDDLError: continue
            if validate(domain,problem,trial)[0]: plan=trial; break
    if plan is None: return {'ok':False,'valid':False,'error':'planner produced no replay-valid plan','plan_output':output}
    commit(output,plan)
    return {'ok':True,'valid':True,'actions':len(plan),'plan_output':output,'solver':'fast-downward'}
def main():
    try: print(json.dumps(solve(json.load(sys.stdin))))
    except Exception as exc: print(json.dumps({'ok':False,'valid':False,'error':str(exc)}))
if __name__=='__main__': main()
