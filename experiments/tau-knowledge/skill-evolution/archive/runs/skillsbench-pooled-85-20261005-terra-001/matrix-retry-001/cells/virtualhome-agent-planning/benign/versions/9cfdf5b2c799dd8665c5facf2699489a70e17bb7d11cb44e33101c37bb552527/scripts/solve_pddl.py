import json, os, signal, subprocess, sys, tempfile
from pathlib import Path

from fd_setup import ensure
from pddl_engine import PDDLError, load, parse, render, search, validate


def commit(path, plan):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.tmp')
    temporary.write_text(render(plan), encoding='utf8')
    os.replace(str(temporary), str(target))


def command(driver, profile, output, domain, problem):
    cmd = [sys.executable, driver] if driver.endswith('.py') else [driver]
    if profile:
        cmd += ['--build', profile]
    return cmd + ['--plan-file', output, '--alias', 'lama-first', domain, problem]


def solve(request):
    output = request.get('plan_output')
    try:
        domain, problem = load(request['domain'], request['problem'])
    except Exception as exc:
        return {'ok': False, 'valid': False, 'error': 'PDDL load failed: %s' % exc,
                'plan_output': output}
    if request.get('validate_plan'):
        try:
            trial = parse(Path(request['validate_plan']).read_text(encoding='utf8'))
        except Exception as exc:
            return {'ok': False, 'valid': False, 'error': 'plan read failed: %s' % exc,
                    'plan_output': output}
        ok, message, _ = validate(domain, problem, trial)
        return {'ok': ok, 'valid': ok, 'actions': len(trial),
                'error': None if ok else message, 'plan_output': output}
    if not output:
        return {'ok': False, 'valid': False, 'error': 'plan_output is required'}
    initially_solved, _, _ = validate(domain, problem, [])
    if initially_solved:
        commit(output, [])
        return {'ok': True, 'valid': True, 'actions': 0, 'plan_output': output}
    fallback_seconds = float(request.get('fallback_timeout_sec', 0) or 0)
    if fallback_seconds > 0:
        trial = search(domain, problem, fallback_seconds,
                       request.get('fallback_max_expansions', 20000),
                       request.get('fallback_max_groundings', 100000))
        if trial is not None and validate(domain, problem, trial)[0]:
            commit(output, trial)
            return {'ok': True, 'valid': True, 'actions': len(trial),
                    'plan_output': output, 'solver': 'internal'}
    driver, profile = request.get('fast_downward'), request.get('fast_downward_build')
    if not driver:
        driver, profile = ensure(request.get('fast_downward'),
                                 request.get('planner_setup_timeout_sec', 240))
        if not driver:
            return {'ok': False, 'valid': False, 'error': str(profile),
                    'plan_output': output}
    plan = None
    with tempfile.TemporaryDirectory(prefix='airport-plan-') as tempdir:
        base = str(Path(tempdir) / 'sas_plan')
        proc = None
        try:
            proc = subprocess.Popen(
                command(driver, profile, base, request['domain'], request['problem']),
                start_new_session=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True,
            )
            proc.communicate(timeout=max(1, int(request.get('timeout_sec', 20))))
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            proc.communicate()
        except Exception as exc:
            return {'ok': False, 'valid': False, 'error': 'planner launch failed: %s' % exc,
                    'plan_output': output}
        candidates = [Path(base)] + sorted(Path(tempdir).glob('sas_plan.*'),
                                            key=lambda p: p.stat().st_mtime, reverse=True)
        for candidate in candidates:
            if not candidate.is_file() or not candidate.stat().st_size:
                continue
            try:
                trial = parse(candidate.read_text(encoding='utf8'))
            except PDDLError:
                continue
            if validate(domain, problem, trial)[0]:
                plan = trial
                break
    if plan is None:
        return {'ok': False, 'valid': False,
                'error': 'planner produced no replay-valid plan', 'plan_output': output}
    commit(output, plan)
    return {'ok': True, 'valid': True, 'actions': len(plan),
            'plan_output': output, 'solver': 'fast-downward'}


def main():
    try:
        print(json.dumps(solve(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({'ok': False, 'valid': False, 'error': str(exc)}))


if __name__ == '__main__':
    main()
