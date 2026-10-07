import json, sys, time
from pathlib import Path

from fd_setup import ensure
from solve_pddl import solve


def resolve(manifest, value):
    path = Path(value)
    return str(path if path.is_absolute() else manifest.parent / path)


def main():
    try:
        request = json.load(sys.stdin)
        manifest = Path(request.get('problem_json', '/app/problem.json'))
        rows = json.loads(manifest.read_text(encoding='utf8'))
        if not isinstance(rows, list) or not rows:
            raise ValueError('manifest must be a nonempty list')
        specs, results = [], [None] * len(rows)
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or not all(row.get(k) for k in
                                                    ('id', 'domain', 'problem', 'plan_output')):
                raise ValueError('manifest row lacks required fields')
            spec = dict(row)
            for key in ('domain', 'problem', 'plan_output'):
                spec[key] = resolve(manifest, row[key])
            specs.append(spec)
            existing = Path(spec['plan_output'])
            if existing.is_file():
                results[index] = solve({'domain': spec['domain'], 'problem': spec['problem'],
                                        'plan_output': spec['plan_output'],
                                        'validate_plan': str(existing)})
        deadline = time.monotonic() + max(1, int(request.get('timeout_sec', 595)))
        fallback = request.get('fallback_timeout_sec', 1)
        # Small instances can be completed before planner setup. This both avoids
        # needless toolchain work and commits their required artifacts early.
        for index, result in enumerate(results):
            if result and result.get('ok'):
                continue
            if time.monotonic() >= deadline:
                break
            results[index] = solve(dict(specs[index], fallback_timeout_sec=fallback,
                                        fallback_max_expansions=request.get('fallback_max_expansions', 20000),
                                        fallback_max_groundings=request.get('fallback_max_groundings', 100000),
                                        timeout_sec=0))
        pending = [i for i, result in enumerate(results) if not result or not result.get('ok')]
        driver = profile = None
        setup = 'all plans solved or replay-valid without external planner'
        if pending:
            setup_budget = min(int(request.get('planner_setup_timeout_sec', 240)),
                               max(1, int(deadline - time.monotonic() - len(pending))))
            driver, profile = ensure(request.get('fast_downward'), setup_budget)
            setup = 'planner ready' if driver else str(profile)
        for position, index in enumerate(pending):
            remaining_rows = len(pending) - position
            remaining_time = max(1, int(deadline - time.monotonic()))
            # Share remaining time across unsolved rows rather than spending the
            # complete budget on the first difficult instance.
            fair_share = max(2, remaining_time // remaining_rows)
            allowance = min(int(request.get('per_task_timeout_sec', 20)), fair_share)
            if driver:
                results[index] = solve(dict(specs[index], fast_downward=driver,
                                            fast_downward_build=profile, timeout_sec=allowance,
                                            fallback_timeout_sec=0))
            else:
                results[index] = {'ok': False, 'valid': False, 'error': setup,
                                  'plan_output': specs[index]['plan_output']}
        for index, result in enumerate(results):
            if result is None:
                result = {'ok': False, 'valid': False, 'error': 'batch deadline expired',
                          'plan_output': specs[index]['plan_output']}
                results[index] = result
            result['id'] = rows[index]['id']
            result.setdefault('plan_output', specs[index]['plan_output'])
        missing = [result['plan_output'] for result in results
                   if not result.get('ok') or not Path(result['plan_output']).is_file()]
        print(json.dumps({'ok': not missing, 'setup': setup,
                          'solved': sum(bool(r.get('ok')) for r in results),
                          'total': len(rows), 'missing_outputs': missing, 'results': results}))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': 'manifest processing failed: %s' % exc}))


if __name__ == '__main__':
    main()
