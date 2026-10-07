#!/usr/bin/env python3
"""Generate required HVAC artifacts from a supplied simulator.

stdin JSON: simulator_path, room_config_path, output_dir, setpoint,
control_duration_s, sample_dt, calibration_power, and optional adapter.
stdout JSON: {ok, files, metrics} on success.  Files are written to output_dir.
"""
import importlib.util
import inspect
import json
import math
import sys
from pathlib import Path


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def finite(x, label):
    if not num(x):
        raise RuntimeError("non-finite " + label)
    return float(x)


def dump(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")


def extract_temp(value):
    if num(value):
        return float(value)
    if isinstance(value, dict):
        for k in ("temperature", "temp", "current_temperature", "room_temperature", "T"):
            if num(value.get(k)):
                return float(value[k])
    if isinstance(value, (tuple, list)) and value and num(value[0]):
        return float(value[0])
    return None


def config_dt(x):
    if isinstance(x, dict):
        for k in ("dt", "time_step", "timestep", "sample_dt", "sample_interval"):
            if num(x.get(k)) and float(x[k]) > 0:
                return float(x[k])
        for v in x.values():
            got = config_dt(v)
            if got is not None:
                return got
    if isinstance(x, list):
        for v in x:
            got = config_dt(v)
            if got is not None:
                return got
    return None


def load_module(path):
    spec = importlib.util.spec_from_file_location("provided_hvac_simulator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import simulator_path")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Simulator:
    def __init__(self, mod, cfg, cfg_path, dt, adapter):
        self.mod, self.cfg, self.cfg_path, self.dt = mod, cfg, cfg_path, dt
        self.adapter = adapter or {}
        self.obj = self.construct()
        reset = getattr(self.obj, "reset", None)
        if callable(reset):
            try:
                reset()
            except TypeError:
                pass

    def construct(self):
        requested = self.adapter.get("class") or self.adapter.get("factory")
        candidates = []
        if requested:
            thing = getattr(self.mod, requested, None)
            if not callable(thing):
                raise RuntimeError("adapter constructor does not exist: " + str(requested))
            candidates = [thing]
        else:
            for name in ("create_simulator", "make_simulator", "HVACSimulator", "RoomSimulator", "ThermalSimulator", "Simulator", "Room"):
                thing = getattr(self.mod, name, None)
                if callable(thing):
                    candidates.append(thing)
            for _, thing in vars(self.mod).items():
                if inspect.isclass(thing) and thing.__module__ == self.mod.__name__ and thing not in candidates:
                    candidates.append(thing)
        errors = []
        for maker in candidates:
            for args in ((self.cfg,), (self.cfg_path,), ()):
                try:
                    return maker(*args)
                except Exception as exc:
                    errors.append(str(exc))
            try:
                return maker(**self.cfg)
            except Exception as exc:
                errors.append(str(exc))
        # A small number of supplied simulators use module-level state/functions.
        if any(callable(getattr(self.mod, n, None)) for n in ("step", "update", "run_step", "advance")):
            init = getattr(self.mod, "initialize", None) or getattr(self.mod, "reset", None)
            if callable(init):
                try:
                    init(self.cfg)
                except TypeError:
                    init()
            return self.mod
        raise RuntimeError("could not construct supplied simulator: " + " | ".join(errors[-4:]))

    def temperature(self):
        names = ([self.adapter["temperature_method"]] if self.adapter.get("temperature_method") else
                 ["get_temperature", "read_temperature", "get_temp", "measure_temperature"])
        for name in names:
            fn = getattr(self.obj, name, None)
            if callable(fn):
                value = extract_temp(fn())
                if value is not None:
                    return value
        names = ([self.adapter["temperature_attr"]] if self.adapter.get("temperature_attr") else
                 ["temperature", "current_temperature", "room_temperature", "temp", "T"])
        for name in names:
            value = extract_temp(getattr(self.obj, name, None))
            if value is not None:
                return value
        value = extract_temp(getattr(self.obj, "state", None))
        if value is not None:
            return value
        raise RuntimeError("cannot read temperature; supply adapter temperature_method or temperature_attr")

    def step(self, power):
        power = min(100.0, max(0.0, float(power)))
        names = ([self.adapter["step_method"]] if self.adapter.get("step_method") else
                 ["step", "update", "run_step", "simulate_step", "advance"])
        fn = next((getattr(self.obj, n, None) for n in names if callable(getattr(self.obj, n, None))), None)
        if fn is None:
            setter, advance = getattr(self.obj, "set_heater_power", None), getattr(self.obj, "advance_time", None)
            if not callable(setter) or not callable(advance):
                raise RuntimeError("cannot find simulator step method; supply adapter.step_method")
            setter(power)
            fn = advance
            power = None
        try:
            ps = list(inspect.signature(fn).parameters.values())
        except (TypeError, ValueError):
            answer = fn(power if power is not None else self.dt)
        else:
            kw, positional = {}, []
            pnames = {"heater_power", "power", "heater", "input_power", "control", "action", "u", "command", "heater_percent"}
            dnames = {"dt", "time_step", "timestep", "delta_t", "duration"}
            for p in ps:
                if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                    continue
                if p.name.lower() in pnames and power is not None:
                    kw[p.name] = power
                elif p.name.lower() in dnames:
                    kw[p.name] = self.dt
                elif p.default is inspect.Parameter.empty:
                    positional.append(p)
            if positional:
                # Unknown one/two-argument APIs conventionally mean (power[, dt]).
                args = ([] if power is None else [power]) + ([self.dt] if len(positional) > 1 else [])
                answer = fn(*args)
            else:
                answer = fn(**kw)
        return extract_temp(answer) if extract_temp(answer) is not None else self.temperature()


def solve3(a, b):
    q = [list(r) + [v] for r, v in zip(a, b)]
    for c in range(3):
        p = max(range(c, 3), key=lambda r: abs(q[r][c]))
        if abs(q[p][c]) < 1e-12:
            raise ValueError("singular fit")
        q[c], q[p] = q[p], q[c]
        z = q[c][c]
        q[c] = [v / z for v in q[c]]
        for r in range(3):
            if r != c:
                z = q[r][c]
                q[r] = [v - z*w for v, w in zip(q[r], q[c])]
    return [q[i][3] for i in range(3)]


def identify(rows, dt):
    x = [[r["temperature"], r["heater_power"], 1.0] for r in rows[:-1]]
    y = [r["temperature"] for r in rows[1:]]
    normal = [[sum(row[i]*row[j] for row in x) for j in range(3)] for i in range(3)]
    rhs = [sum(row[i]*v for row, v in zip(x, y)) for i in range(3)]
    try:
        a, b, c = solve3(normal, rhs)
    except ValueError:
        a, b, c = 0.98, 0.02, 0.0
    pred = [a*r[0] + b*r[1] + c for r in x]
    sse = sum((u-v)**2 for u, v in zip(y, pred))
    mean = sum(y)/len(y)
    sst = sum((v-mean)**2 for v in y)
    r2 = 0.0 if sst <= 1e-12 else max(0.0, min(1.0, 1.0-sse/sst))
    rmse = math.sqrt(sse/len(y))
    aa = min(.9995, max(.001, a))
    K, tau = b/(1-aa), -dt/math.log(aa)
    if not num(K) or K <= 1e-6:
        off = [r["temperature"] for r in rows if r["heater_power"] == 0]
        on = [r["temperature"] for r in rows if r["heater_power"] > 1]
        p = [r["heater_power"] for r in rows if r["heater_power"] > 1]
        K = max(.0001, (max(on)-min(off))/max(1.0, sum(p)/len(p))) if on and off else .01
    ambient = c/(1-aa)
    if not num(ambient):
        ambient = rows[0]["temperature"]
    return {"K": float(K), "tau": float(max(.1, tau)), "r_squared": float(r2), "fitting_error": float(rmse), "ambient": float(ambient)}


def metrics(rows, sp):
    ts, tv = [r["time"] for r in rows], [r["temperature"] for r in rows]
    delta, threshold = sp-tv[0], tv[0] + .9*(sp-tv[0])
    rise = next((t-ts[0] for t, v in zip(ts, tv) if (delta >= 0 and v >= threshold) or (delta < 0 and v <= threshold)), ts[-1]-ts[0])
    settle = next((ts[i]-ts[0] for i in range(len(tv)) if all(abs(v-sp) < .5 for v in tv[i:]), ts[-1]-ts[0])
    n = max(3, int(math.ceil(len(tv)*.2)))
    mx = max(tv)
    return {"rise_time": float(rise), "overshoot": float(max(0., (mx-sp)/sp)), "settling_time": float(settle), "steady_state_error": float(sum(abs(v-sp) for v in tv[-n:])/n), "max_temp": float(mx)}


def main(req):
    cfgpath, out = req.get("room_config_path", "/root/room_config.json"), Path(req.get("output_dir", "/root"))
    with open(cfgpath, encoding="utf-8") as f: cfg = json.load(f)
    dt = float(req.get("sample_dt", config_dt(cfg) or .5))
    if not num(dt) or dt <= 0: raise RuntimeError("sample_dt must be positive")
    mod, adapter = load_module(req.get("simulator_path", "/root/hvac_simulator.py")), req.get("adapter", {})
    power = min(100., max(2., float(req.get("calibration_power", 50.))))
    room, cal, t = Simulator(mod, cfg, cfgpath, dt, adapter), [], 0.
    for i in range(int(math.ceil(70./dt))+1):
        u = 0. if i < math.ceil(5./dt) or i >= math.ceil(55./dt) else power
        cal.append({"time": t, "temperature": finite(room.temperature(), "calibration temperature"), "heater_power": u})
        room.step(u); t += dt
    par = identify(cal, dt)
    lam = max(5., min(25., par["tau"]/3.))
    kp = max(.01, min(25., par["tau"]/(max(par["K"], .0001)*lam)))
    gains = {"Kp": float(kp), "Ki": float(max(.0001, min(2., kp/max(par["tau"], .5)))), "Kd": 0., "lambda": float(lam)}
    sp, duration = float(req.get("setpoint", 22.)), max(150., float(req.get("control_duration_s", 240.)))
    room, control, t, integ, old = Simulator(mod, cfg, cfgpath, dt, adapter), [], 0., 0., None
    ff = min(85., max(0., (sp-par["ambient"])/max(par["K"], .0001)))
    for _ in range(int(math.ceil(duration/dt))+1):
        temp, err = finite(room.temperature(), "control temperature"), 0.
        err = sp-temp
        trial = max(-100., min(100., integ + err*dt))
        raw = ff + gains["Kp"]*err + gains["Ki"]*trial
        u = min(100., max(0., raw))
        if u == raw or (u == 0. and err > 0.) or (u == 100. and err < 0.): integ = trial
        control.append({"time": t, "temperature": temp, "setpoint": sp, "heater_power": u, "error": sp-temp})
        old = err; room.step(u); t += dt
    met = metrics(control, sp)
    out.mkdir(parents=True, exist_ok=True)
    dump(out/"calibration_log.json", {"phase":"calibration", "heater_power_test":power, "data":cal})
    dump(out/"estimated_params.json", {k:par[k] for k in ("K","tau","r_squared","fitting_error")})
    dump(out/"tuned_gains.json", gains)
    dump(out/"control_log.json", {"phase":"control", "setpoint":sp, "data":control})
    dump(out/"metrics.json", met)
    return {"ok":True, "files":["calibration_log.json","estimated_params.json","tuned_gains.json","control_log.json","metrics.json"], "metrics":met}

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok":False, "error":str(exc)}))
        raise
