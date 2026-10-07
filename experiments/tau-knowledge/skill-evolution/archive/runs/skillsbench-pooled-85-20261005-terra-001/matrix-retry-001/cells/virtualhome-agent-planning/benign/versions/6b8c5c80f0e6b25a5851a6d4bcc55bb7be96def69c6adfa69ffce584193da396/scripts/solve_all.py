import json
import sys
import time
from pathlib import Path

from fd_setup import ensure
from solve_pddl import solve


def resolved(manifest, value):
    path = Path(value)
    return str(path if path.is_absolute() else manifest.parent / path)


def main():
    try:
        request = json.load(sys.stdin)
        manifest = Path(request.get('problem_json', '/app/problem.json'))
        rows = json.loads(manifest.read_text(encoding='utf8'))
        if not isinstance(rows, list) or not rows:
            raise ValueError('manifest must contain at least one task')
        specs, results = [], []
        for row in rows:
            if not isinstance(row, dict) or not all(row.get(key) for key in ('id', 'domain', 'problem', 'plan_output')):
                raise ValueError('manifest row lacks id, domain, problem, or plan_output')
            spec = dict(row)
            for key in ('domain', 'problem', 'plan_output'):
                spec[key] = resolved(manifest, row[key])
            specs.append(spec)
            existing = Path(spec['plan_output'])
            results.append(solve({'domain': spec['domain'], 'problem': spec['problem'], 'validate_plan': str(existing)}) if existing.is_file() else None)

        pending = [index for index, result in enumerate(results) if not result or not result.get('ok')]
        deadline = time.monotonic() + max(1, int(request.get('timeout_sec', 595)))
        driver = profile = None
        setup_status = 'all existing plans replayed successfully'
        if pending:
            setup_limit = min(int(request.get('planner_setup_timeout_sec', 520)), max(1, int(deadline - time.monotonic() - 5)))
            driver, profile = ensure(request.get('fast_downward'), timeout=setup_limit)
            setup_status = 'planner ready' if driver else str(profile)

        for position, index in enumerate(pending):
            remaining = max(1, int(deadline - time.monotonic()))
            later = len(pending) - position - 1
            # Keep a small opportunity for every later row while giving each
            # current task the configured normal solve budget.
            budget = min(int(request.get('per_task_timeout_sec', 120)), max(1, remaining - 2 * later))
            if driver:
                result = solve(dict(specs[index], fast_downward=driver, fast_downward_build=profile, timeout_sec=budget))
            else:
                result = {'ok': False, 'valid': False, 'error': setup_status, 'plan_output': specs[index]['plan_output']}
            result['id'] = rows[index]['id']
            results[index] = result

        for index, result in enumerate(results):
            result['id'] = rows[index]['id']
            result.setdefault('plan_output', specs[index]['plan_output'])
        missing = [result['plan_output'] for result in results if not result.get('ok') or not Path(result['plan_output']).is_file()]
        print(json.dumps({
            'ok': not missing,
            'setup': setup_status,
            'solved': sum(bool(result.get('ok')) for result in results),
            'total': len(rows),
            'missing_outputs': missing,
            'results': results,
        }))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': 'manifest processing failed: %s' % exc}))

if __name__ == '__main__':
    main()
