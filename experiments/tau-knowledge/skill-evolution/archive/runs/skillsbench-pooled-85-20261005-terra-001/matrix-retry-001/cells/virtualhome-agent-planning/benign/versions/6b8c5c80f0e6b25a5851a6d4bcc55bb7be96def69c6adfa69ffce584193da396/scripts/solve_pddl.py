import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from fd_setup import ensure
from pddl_engine import PDDLError, load, parse, render, validate


def commit(path, plan):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.tmp')
    temporary.write_text(render(plan), encoding='utf8')
    os.replace(temporary, output)


def driver_command(driver, build_profile, plan_file, domain, problem):
    command = [sys.executable, driver] if driver.endswith('.py') else [driver]
    if build_profile:
        command += ['--build', build_profile]
    return command + ['--plan-file', plan_file, '--alias', 'lama-first', domain, problem]


def solve(request):
    try:
        domain, problem = load(request['domain'], request['problem'])
    except Exception as exc:
        return {'ok': False, 'valid': False, 'error': 'PDDL load failed: %s' % exc}

    validation_path = request.get('validate_plan')
    if validation_path:
        try:
            plan = parse(Path(validation_path).read_text(encoding='utf8'))
        except Exception as exc:
            return {'ok': False, 'valid': False, 'error': 'plan read failed: %s' % exc}
        ok, message, _ = validate(domain, problem, plan)
        return {'ok': ok, 'valid': ok, 'actions': len(plan), 'error': None if ok else message}

    output = request.get('plan_output')
    if not output:
        return {'ok': False, 'valid': False, 'error': 'plan_output is required'}
    initially_solved, _, _ = validate(domain, problem, [])
    if initially_solved:
        commit(output, [])
        return {'ok': True, 'valid': True, 'actions': 0, 'plan_output': output}

    driver, build_profile = request.get('fast_downward'), request.get('fast_downward_build')
    if not driver:
        driver, build_profile = ensure(timeout=request.get('planner_setup_timeout_sec', 520))
        if not driver:
            return {'ok': False, 'valid': False, 'error': str(build_profile), 'plan_output': output}

    plan = None
    with tempfile.TemporaryDirectory(prefix='pddl-plan-') as directory:
        base = str(Path(directory) / 'sas_plan')
        process = None
        try:
            process = subprocess.Popen(
                driver_command(driver, build_profile, base, request['domain'], request['problem']),
                start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            process.communicate(timeout=max(1, int(request.get('timeout_sec', 120))))
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            process.communicate()
        except Exception as exc:
            return {'ok': False, 'valid': False, 'error': 'planner launch failed: %s' % exc, 'plan_output': output}

        # Fast Downward may leave several successively improved plans. Prefer
        # the newest readable one, but accept any that independently replays.
        candidates = [Path(base)] + sorted(Path(directory).glob('sas_plan.*'), key=lambda p: p.stat().st_mtime, reverse=True)
        for candidate in candidates:
            if not candidate.is_file() or not candidate.stat().st_size:
                continue
            try:
                proposed = parse(candidate.read_text(encoding='utf8'))
            except PDDLError:
                continue
            ok, _, _ = validate(domain, problem, proposed)
            if ok:
                plan = proposed
                break
    if plan is None:
        return {'ok': False, 'valid': False, 'error': 'planner produced no replay-valid plan', 'plan_output': output}
    commit(output, plan)
    return {'ok': True, 'valid': True, 'actions': len(plan), 'plan_output': output}


def main():
    try:
        print(json.dumps(solve(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({'ok': False, 'valid': False, 'error': str(exc)}))

if __name__ == '__main__':
    main()
