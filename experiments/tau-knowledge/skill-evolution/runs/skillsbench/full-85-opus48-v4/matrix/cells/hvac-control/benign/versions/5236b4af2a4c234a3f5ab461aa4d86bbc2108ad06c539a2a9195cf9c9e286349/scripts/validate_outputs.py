#!/usr/bin/env python3
"""Reopen the five artifacts and validate structure, finiteness, ordering,
lengths and target compliance.

stdin JSON: {"dir":"/root","setpoint":22.0,"band":0.5}
stdout JSON: {ok: bool, checks: {...}, metrics_recomputed: {...}, problems: [...]}
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hvac_lib import compute_metrics  # noqa: E402


def load(d, name):
    with open(os.path.join(d, name)) as f:
        return json.load(f)


def finite_ordered(rows, keys):
    times = []
    for r in rows:
        for k in keys:
            if k in r and r[k] is not None:
                v = r[k]
                if not (isinstance(v, (int, float)) and math.isfinite(v)):
                    return False, 'non-finite %s' % k
        if 'time' in r:
            times.append(r['time'])
    for i in range(1, len(times)):
        if times[i] < times[i - 1]:
            return False, 'time not non-decreasing'
    return True, ''


def main():
    raw = sys.stdin.read().strip() or '{}'
    cfg = json.loads(raw)
    d = cfg.get('dir', '/root')
    setpoint = float(cfg.get('setpoint', 22.0))
    band = float(cfg.get('band', 0.5))
    problems = []
    checks = {}

    try:
        cal = load(d, 'calibration_log.json')
        est = load(d, 'estimated_params.json')
        gains = load(d, 'tuned_gains.json')
        ctrl = load(d, 'control_log.json')
        metrics = load(d, 'metrics.json')
    except Exception as e:  # noqa: BLE001
        print(json.dumps({'ok': False, 'problems': ['missing/invalid file: %s' % e]}))
        return

    cal_rows = cal.get('data', [])
    ctrl_rows = ctrl.get('data', [])

    checks['calibration_points>=20'] = len(cal_rows) >= 20
    cal_span = (cal_rows[-1]['time'] - cal_rows[0]['time']) if cal_rows else 0
    checks['calibration_duration>=30s'] = cal_span >= 30.0
    ok, msg = finite_ordered(cal_rows, ['time', 'temperature', 'heater_power'])
    checks['calibration_finite_ordered'] = ok
    if not ok:
        problems.append('calibration: ' + msg)

    ctrl_span = (ctrl_rows[-1]['time'] - ctrl_rows[0]['time']) if ctrl_rows else 0
    checks['control_duration>=150s'] = ctrl_span >= 150.0
    ok, msg = finite_ordered(ctrl_rows, ['time', 'temperature', 'setpoint',
                                         'heater_power', 'error'])
    checks['control_finite_ordered'] = ok
    if not ok:
        problems.append('control: ' + msg)

    # heater power range
    pr_ok = all(0.0 - 1e-6 <= r.get('heater_power', 0) <= 100.0 + 1e-6
                for r in ctrl_rows)
    checks['heater_power_in_0_100'] = pr_ok

    for k in ('K', 'tau', 'r_squared', 'fitting_error'):
        if k not in est:
            problems.append('estimated_params missing %s' % k)
    for k in ('Kp', 'Ki', 'Kd', 'lambda'):
        if k not in gains:
            problems.append('tuned_gains missing %s' % k)

    # recompute metrics from the delivered control trace and cross-check
    recomputed = None
    if ctrl_rows:
        recomputed = compute_metrics(ctrl_rows, setpoint, band=band)
        for k in ('rise_time', 'overshoot', 'settling_time',
                  'steady_state_error', 'max_temp'):
            if k not in metrics:
                problems.append('metrics missing %s' % k)

    # target compliance (recomputed, authoritative)
    if recomputed:
        st = recomputed['settling_time']
        checks['steady_state_error<0.5'] = recomputed['steady_state_error'] < 0.5
        checks['settling_time<120'] = (st is not None and st < 120.0)
        checks['overshoot<0.10'] = recomputed['overshoot'] < 0.10
        checks['max_temp<30'] = recomputed['max_temp'] < 30.0

    ok = all(v for v in checks.values()) and not problems
    print(json.dumps({'ok': bool(ok), 'checks': checks,
                      'metrics_recomputed': recomputed,
                      'problems': problems}, indent=2))


if __name__ == '__main__':
    main()
