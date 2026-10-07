#!/usr/bin/env python3
"""Orchestrate the full HVAC task against hvac_simulator.py.

Reads an optional JSON config on stdin (all keys optional):
  simulator_path   default /root/hvac_simulator.py
  config_path      default /root/room_config.json
  outdir           default /root
  setpoint         default 22.0
  calib_power      default 50.0
  calib_duration   default 60.0  (seconds, >=30 enforced)
  control_duration default 200.0 (seconds, >=150 enforced)
  dt               default: from room_config else 0.5
  lambda           default: auto from compute_gains
  settle_band      default 0.5
  # interface overrides (strings / bools) when auto-discovery is wrong:
  class_name, step_method, read_method, reset_method,
  temp_attr, time_attr, step_takes_dt, step_returns_temp, init_kwargs(dict)

Writes calibration_log.json, estimated_params.json, tuned_gains.json,
control_log.json, metrics.json and hvac_interface.json into outdir.
Prints a JSON summary to stdout. Exits non-zero if the simulator interface
cannot be resolved.
"""
import importlib.util
import inspect
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hvac_lib import fit_first_order, compute_gains, compute_metrics, PID  # noqa: E402


def load_module(path):
    spec = importlib.util.spec_from_file_location('hvac_simulator_mod', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_config(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _is_tempish(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) \
        and math.isfinite(v) and -50 <= v <= 200


class Plant:
    """Adapter that discovers and wraps the simulator interface."""

    STEP_NAMES = ['step', 'update', 'advance', 'tick', 'simulate', 'simulate_step', 'run_step']
    READ_NAMES = ['read_sensor', 'get_temperature', 'read_temperature', 'read_temp',
                  'measure', 'get_temp', 'sense', 'temperature', 'current_temperature']
    RESET_NAMES = ['reset', 'reset_simulation', 'initialize', 'init_state']
    TEMP_ATTRS = ['temperature', 'temp', 'current_temp', 'T', 'current_temperature']
    TIME_ATTRS = ['time', 't', 'current_time', 'sim_time']

    def __init__(self, mod, cfg_path, room_cfg, ov):
        self.mod = mod
        self.cfg_path = cfg_path
        self.room_cfg = room_cfg
        self.ov = ov
        self.info = {}
        self._last_temp = None
        self._build()

    def _candidate_classes(self):
        classes = [(n, o) for n, o in vars(self.mod).items()
                   if isinstance(o, type) and getattr(o, '__module__', '') == self.mod.__name__]
        if not classes:
            classes = [(n, o) for n, o in vars(self.mod).items() if isinstance(o, type)]

        def score(item):
            n = item[0].lower()
            if 'sim' in n:
                return 0
            if 'hvac' in n or 'room' in n or 'plant' in n or 'thermal' in n:
                return 1
            if 'control' in n:
                return 5
            return 3
        classes.sort(key=score)
        return classes

    def _instantiate(self, cls):
        kwargs = self.ov.get('init_kwargs') or {}
        attempts = [
            lambda: cls(**kwargs) if kwargs else cls(),
            lambda: cls(self.cfg_path),
            lambda: cls(config_path=self.cfg_path),
            lambda: cls(config=self.room_cfg),
            lambda: cls(self.room_cfg),
        ]
        last = None
        for a in attempts:
            try:
                return a()
            except Exception as e:  # noqa: BLE001
                last = e
        raise RuntimeError('could not instantiate %s: %s' % (cls, last))

    def _find_method(self, names):
        for n in names:
            m = getattr(self.obj, n, None)
            if callable(m):
                return n, m
        return None, None

    def _build(self):
        cname = self.ov.get('class_name')
        if cname and hasattr(self.mod, cname):
            cls = getattr(self.mod, cname)
        else:
            cands = self._candidate_classes()
            if not cands:
                raise RuntimeError('no classes found in simulator module')
            self.info['class_candidates'] = [n for n, _ in cands]
            cls = cands[0][1]
        self.cls = cls
        self.info['class_used'] = cls.__name__
        self.obj = self._instantiate(cls)

        # step method
        sname = self.ov.get('step_method')
        if sname:
            self.step_name, self.step_fn = sname, getattr(self.obj, sname)
        else:
            self.step_name, self.step_fn = self._find_method(self.STEP_NAMES)
        if self.step_fn is None:
            self.info['method_candidates'] = [m for m in dir(self.obj) if not m.startswith('_')]
            raise RuntimeError('no step method found; set step_method override')
        self.info['step_method'] = self.step_name

        # read temperature
        self.temp_attr = self.ov.get('temp_attr', '__auto__')
        self.read_name = self.ov.get('read_method')
        self.read_fn = getattr(self.obj, self.read_name) if self.read_name else None
        if self.temp_attr == '__auto__':
            self.temp_attr = None
            for a in self.TEMP_ATTRS:
                if hasattr(self.obj, a) and _is_tempish(getattr(self.obj, a)):
                    self.temp_attr = a
                    break
        if self.read_fn is None and self.ov.get('read_method') is None:
            rn, rf = self._find_method([n for n in self.READ_NAMES])
            # avoid picking an attribute name that is really the temp attribute
            if rf is not None:
                self.read_name, self.read_fn = rn, rf
        self.info['read_method'] = self.read_name
        self.info['temp_attr'] = self.temp_attr

        # reset
        self.reset_name = self.ov.get('reset_method')
        if self.reset_name:
            self.reset_fn = getattr(self.obj, self.reset_name, None)
        else:
            self.reset_name, self.reset_fn = self._find_method(self.RESET_NAMES)
        self.info['reset_method'] = self.reset_name

        # time attr
        self.time_attr = self.ov.get('time_attr', '__auto__')
        if self.time_attr == '__auto__':
            self.time_attr = None
            for a in self.TIME_ATTRS:
                if hasattr(self.obj, a) and isinstance(getattr(self.obj, a), (int, float)):
                    self.time_attr = a
                    break
        self.info['time_attr'] = self.time_attr

        # step signature analysis
        self._analyze_step()

    def _analyze_step(self):
        self.step_takes_dt = self.ov.get('step_takes_dt')
        self.step_returns_temp = self.ov.get('step_returns_temp')
        try:
            sig = inspect.signature(self.step_fn)
            params = [p for p in sig.parameters.values()
                      if p.name != 'self' and p.kind in (p.POSITIONAL_ONLY,
                                                          p.POSITIONAL_OR_KEYWORD)]
        except (ValueError, TypeError):
            params = []
        self._step_params = params
        if self.step_takes_dt is None:
            self.step_takes_dt = any(('dt' in p.name.lower() or 'time' in p.name.lower()
                                      or 'step' in p.name.lower()) for p in params)
        self.info['step_params'] = [p.name for p in params]
        self.info['step_takes_dt'] = self.step_takes_dt

    def reset(self):
        if self.reset_fn is not None:
            try:
                self.reset_fn()
                return
            except Exception:
                pass
        # rebuild as a fallback reset
        try:
            self.obj = self._instantiate(self.cls)
        except Exception:
            pass

    def read_temp(self):
        if self.temp_attr is not None:
            v = getattr(self.obj, self.temp_attr, None)
            if _is_tempish(v):
                self._last_temp = float(v)
                return self._last_temp
        if self.read_fn is not None:
            v = self.read_fn()
            if _is_tempish(v):
                self._last_temp = float(v)
                return self._last_temp
        if self._last_temp is not None:
            return self._last_temp
        return None

    def _call_step(self, power, dt):
        params = self._step_params
        args = []
        used_power = False
        for p in params:
            n = p.name.lower()
            if (not used_power) and ('power' in n or n in ('u', 'p', 'heater',
                                                           'command', 'control',
                                                           'action', 'input')):
                args.append(power)
                used_power = True
            elif 'dt' in n or 'time' in n or 'step' in n:
                args.append(dt)
            elif not used_power:
                args.append(power)
                used_power = True
            else:
                if p.default is inspect.Parameter.empty:
                    args.append(dt if self.step_takes_dt else power)
        if not params:
            # unknown signature: try best-effort
            try:
                return self.step_fn(power, dt) if self.step_takes_dt else self.step_fn(power)
            except TypeError:
                return self.step_fn(power)
        return self.step_fn(*args)

    def step(self, power, dt):
        ret = self._call_step(power, dt)
        if self.step_returns_temp is None:
            self.step_returns_temp = _is_tempish(ret)
            self.info['step_returns_temp'] = self.step_returns_temp
        if _is_tempish(ret):
            self._last_temp = float(ret)
        return ret


def get_dt(ov, room_cfg):
    if ov.get('dt'):
        return float(ov['dt'])
    for k in ('dt', 'timestep', 'time_step', 'sample_time', 'sample_interval'):
        if isinstance(room_cfg, dict) and k in room_cfg:
            try:
                return float(room_cfg[k])
            except Exception:
                pass
    return 0.5


def run_calibration(plant, dt, power, duration):
    plant.reset()
    data = []
    t = 0.0
    temp0 = plant.read_temp()
    if temp0 is None:
        # try a zero-power step to establish a reading
        plant.step(0.0, dt)
        temp0 = plant.read_temp()
    if temp0 is None:
        raise RuntimeError('cannot read temperature from simulator')
    data.append({'time': 0.0, 'temperature': float(temp0), 'heater_power': 0.0})
    min_points = 25
    while t < duration or len(data) < min_points + 1:
        plant.step(power, dt)
        t += dt
        temp = plant.read_temp()
        data.append({'time': round(t, 6), 'temperature': float(temp),
                     'heater_power': float(power)})
        if t > duration and len(data) >= min_points + 1:
            break
        if t > duration * 5:  # safety stop
            break
    return data, float(temp0)


def run_control(plant, dt, setpoint, gains, duration):
    plant.reset()
    pid = PID(gains['Kp'], gains['Ki'], gains['Kd'], 0.0, 100.0)
    data = []
    t = 0.0
    temp = plant.read_temp()
    if temp is None:
        plant.step(0.0, dt)
        temp = plant.read_temp()
    while t < duration:
        temp = plant.read_temp()
        err = setpoint - temp
        out = pid.step(err, dt)
        out = min(100.0, max(0.0, out))
        data.append({'time': round(t, 6), 'temperature': float(temp),
                     'setpoint': float(setpoint), 'heater_power': float(out),
                     'error': float(err)})
        plant.step(out, dt)
        t += dt
    return data


def evaluate_targets(cal, control, metrics):
    cal_span = cal[-1]['time'] - cal[0]['time']
    ctrl_span = control[-1]['time'] - control[0]['time']
    st = metrics['settling_time']
    return {
        'calibration_duration_ok': cal_span >= 30.0,
        'calibration_points_ok': len(cal) >= 20,
        'control_duration_ok': ctrl_span >= 150.0,
        'steady_state_error_ok': metrics['steady_state_error'] < 0.5,
        'settling_time_ok': (st is not None and st < 120.0),
        'overshoot_ok': metrics['overshoot'] < 0.10,
        'max_temp_ok': metrics['max_temp'] < 30.0,
        'calibration_span': cal_span,
        'control_span': ctrl_span,
    }


def main():
    raw = sys.stdin.read().strip() or '{}'
    ov = json.loads(raw)
    sim_path = ov.get('simulator_path', '/root/hvac_simulator.py')
    cfg_path = ov.get('config_path', '/root/room_config.json')
    outdir = ov.get('outdir', '/root')
    setpoint = float(ov.get('setpoint', 22.0))
    calib_power = float(ov.get('calib_power', 50.0))
    calib_duration = max(float(ov.get('calib_duration', 60.0)), 30.0)
    control_duration = max(float(ov.get('control_duration', 200.0)), 150.0)
    settle_band = float(ov.get('settle_band', 0.5))

    room_cfg = load_config(cfg_path)
    dt = get_dt(ov, room_cfg)
    mod = load_module(sim_path)

    try:
        plant = Plant(mod, cfg_path, room_cfg, ov)
    except Exception as e:  # noqa: BLE001
        info = getattr(e, 'args', [''])
        sys.stderr.write('interface discovery failed: %s\n' % e)
        print(json.dumps({'error': 'interface_discovery_failed',
                          'detail': str(e)}))
        sys.exit(2)

    # Phase 1: calibration
    cal_data, ambient = run_calibration(plant, dt, calib_power, calib_duration)
    power_on = [d for d in cal_data if d['heater_power'] and d['heater_power'] > 0]
    cal_log = {'phase': 'calibration', 'heater_power_test': calib_power,
               'data': cal_data}

    # Phase 2: identification
    params = fit_first_order(power_on, power=calib_power, ambient=ambient)

    # Phase 3: tuning
    gains = compute_gains(params['K'], params['tau'], lam=ov.get('lambda'),
                          settling_target=120.0)

    # Phase 4: closed-loop control
    ctrl_data = run_control(plant, dt, setpoint, gains, control_duration)
    ctrl_log = {'phase': 'control', 'setpoint': setpoint, 'data': ctrl_data}
    metrics = compute_metrics(ctrl_data, setpoint, band=settle_band)

    est = {'K': params['K'], 'tau': params['tau'],
           'r_squared': params['r_squared'], 'fitting_error': params['fitting_error'],
           'ambient': params['ambient'], 'T_ss': params['T_ss']}

    def write(name, obj):
        with open(os.path.join(outdir, name), 'w') as f:
            json.dump(obj, f, indent=2)

    write('calibration_log.json', cal_log)
    write('estimated_params.json', est)
    write('tuned_gains.json', gains)
    write('control_log.json', ctrl_log)
    write('metrics.json', metrics)
    write('hvac_interface.json', plant.info)

    checks = evaluate_targets(cal_data, ctrl_data, metrics)
    summary = {
        'dt': dt, 'ambient': ambient, 'params': est, 'gains': gains,
        'metrics': metrics, 'targets': checks, 'interface': plant.info,
        'files': ['calibration_log.json', 'estimated_params.json',
                  'tuned_gains.json', 'control_log.json', 'metrics.json'],
    }
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
