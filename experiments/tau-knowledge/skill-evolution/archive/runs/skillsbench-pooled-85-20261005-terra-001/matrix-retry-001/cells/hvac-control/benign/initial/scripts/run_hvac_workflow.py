#!/usr/bin/env python3
"""Generate HVAC calibration, fit, tuning, control, and metric artifacts.

JSON stdin schema:
{
  "simulator_path": "/root/hvac_simulator.py",       # optional
  "room_config_path": "/root/room_config.json",      # optional
  "output_dir": ".",                                 # optional
  "setpoint": 22.0, "control_duration_s": 180.0,     # optional
  "sample_dt": 0.5, "calibration_power": 40.0,       # optional
  "adapter": {                                        # optional API overrides
    "class": "HVACSimulator", "factory": "create_simulator",
    "temperature_method": "get_temperature", "temperature_attr": "temperature",
    "step_method": "step", "time_attr": "time"
  }
}

The adapter is intentionally limited to names in the supplied module. A step
method is called with a recognized power argument (heater_power/power/etc.) and
with dt when its signature requires or accepts a dt-like argument. This script
writes the five required JSON files and prints a JSON manifest on stdout.
"""
import inspect
import json
import math
import os
import sys
import importlib.util
from pathlib import Path


def finite(x):
    return isinstance(x, (int, float)) and math.isfinite(float(x))


def number(x, label):
    if not finite(x):
        raise RuntimeError("non-finite or missing %s from simulator" % label)
    return float(x)


def dump(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")


def load_module(path):
    spec = importlib.util.spec_from_file_location("supplied_hvac_simulator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import simulator: %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def recursive_dt(value):
    if isinstance(value, dict):
        for key in ("dt", "time_step", "timestep", "sample_time", "sample_interval"):
            if key in value and finite(value[key]) and float(value[key]) > 0:
                return float(value[key])
        for child in value.values():
            ans = recursive_dt(child)
            if ans is not None:
                return ans
    elif isinstance(value, list):
        for child in value:
            ans = recursive_dt(child)
            if ans is not None:
                return ans
    return None


def scalar_temperature(value):
    if finite(value):
        return float(value)
    if isinstance(value, dict):
        for key in ("temperature", "temp", "current_temperature", "room_temperature", "T"):
            if key in value and finite(value[key]):
                return float(value[key])
    if isinstance(value, (tuple, list)) and value and finite(value[0]):
        return float(value[0])
    return None


class SimulatorAdapter:
    def __init__(self, module, config_path, config, dt, override):
        self.module = module
        self.config = config
        self.dt = dt
        self.override = override or {}
        self.obj = self._construct(config_path)
        self.temperature_method = self.override.get("temperature_method")
        self.temperature_attr = self.override.get("temperature_attr")
        self.step_method = self.override.get("step_method")
        self.time_attr = self.override.get("time_attr")
        self.local_time = 0.0
        # Reset only if it is explicitly a normal zero-argument lifecycle call.
        reset = getattr(self.obj, "reset", None)
        if callable(reset):
            try:
                result = reset()
                t = scalar_temperature(result)
                if t is not None:
                    self._last_temperature = t
            except TypeError:
                pass
        self._last_temperature = self.temperature()
        observed = self.time()
        if observed is not None:
            self.local_time = observed

    def _construct(self, config_path):
        candidates = []
        factory_name = self.override.get("factory")
        if factory_name:
            candidates.append(getattr(self.module, factory_name))
        else:
            for name, item in vars(self.module).items():
                if callable(item) and ("simulator" in name.lower() or name.lower() in ("room", "environment", "hvac")):
                    candidates.append(item)
        class_name = self.override.get("class")
        if class_name:
            candidates = [getattr(self.module, class_name)]
        if not candidates:
            raise RuntimeError("no simulator class/factory found; provide adapter.class or adapter.factory")
        attempts = [(self.config,), (config_path,), ()]
        errors = []
        for constructor in candidates:
            for args in attempts:
                try:
                    return constructor(*args)
                except Exception as exc:
                    errors.append("%s%r: %s" % (getattr(constructor, "__name__", "factory"), args, exc))
        raise RuntimeError("could not construct supplied simulator: " + " | ".join(errors[-6:]))

    def temperature(self):
        methods = [self.temperature_method] if self.temperature_method else ["get_temperature", "read_temperature", "get_temp"]
        for name in methods:
            if not name:
                continue
            fn = getattr(self.obj, name, None)
            if callable(fn):
                value = scalar_temperature(fn())
                if value is not None:
                    return value
        attrs = [self.temperature_attr] if self.temperature_attr else ["temperature", "current_temperature", "room_temperature", "temp", "T"]
        for name in attrs:
            if name and hasattr(self.obj, name):
                value = scalar_temperature(getattr(self.obj, name))
                if value is not None:
                    return value
        state = getattr(self.obj, "state", None)
        value = scalar_temperature(state)
        if value is not None:
            return value
        raise RuntimeError("cannot read simulator temperature; supply temperature_method or temperature_attr")

    def time(self):
        attrs = [self.time_attr] if self.time_attr else ["time", "current_time", "t", "simulation_time"]
        for name in attrs:
            if name and hasattr(self.obj, name) and finite(getattr(self.obj, name)):
                return float(getattr(self.obj, name))
        for name in ("get_time", "time"):
            fn = getattr(self.obj, name, None)
            if callable(fn):
                try:
                    value = fn()
                    if finite(value):
                        return float(value)
                except TypeError:
                    pass
        return None

    def _call_step(self, fn, power):
        try:
            sig = inspect.signature(fn)
            parameters = list(sig.parameters.values())
        except (TypeError, ValueError):
            return fn(power)
        kwargs = {}
        positional = []
        power_names = {"heater_power", "power", "heater", "input_power", "control", "action", "u", "command"}
        dt_names = {"dt", "time_step", "timestep", "delta_t", "duration"}
        required_unknown = []
        for p in parameters:
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                continue
            if p.name.lower() in power_names:
                kwargs[p.name] = power
            elif p.name.lower() in dt_names:
                kwargs[p.name] = self.dt
            elif p.default is inspect.Parameter.empty:
                required_unknown.append(p.name)
        if required_unknown:
            # A usual single required positional control argument may have an unfamiliar name.
            if len(parameters) == 1:
                positional = [power]
            else:
                raise RuntimeError("unsupported required step parameters: %s" % required_unknown)
        return fn(*positional, **kwargs)

    def step(self, power):
        power = min(100.0, max(0.0, float(power)))
        names = [self.step_method] if self.step_method else ["step", "update", "simulate_step", "run_step", "advance"]
        response = None
        for name in names:
            if not name:
                continue
            fn = getattr(self.obj, name, None)
            if callable(fn):
                response = self._call_step(fn, power)
                break
        else:
            setter = getattr(self.obj, "set_heater_power", None)
            advancer = getattr(self.obj, "advance_time", None) or getattr(self.obj, "advance", None)
            if not callable(setter) or not callable(advancer):
                raise RuntimeError("cannot find simulator step method; provide adapter.step_method")
            setter(power)
            response = self._call_step(advancer, 0.0)
        response_temp = scalar_temperature(response)
        self._last_temperature = response_temp if response_temp is not None else self.temperature()
        observed = self.time()
        if observed is None:
            self.local_time += self.dt
        else:
            self.local_time = observed
        return self._last_temperature


def least_squares(rows, y):
    n = len(rows)
    m = len(rows[0])
    a = [[0.0] * (m + 1) for _ in range(m)]
    for row, target in zip(rows, y):
        for i in range(m):
            a[i][m] += row[i] * target
            for j in range(m):
                a[i][j] += row[i] * row[j]
    for col in range(m):
        pivot = max(range(col, m), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise RuntimeError("calibration is not sufficiently exciting to fit thermal model")
        a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [x / scale for x in a[col]]
        for r in range(m):
            if r == col:
                continue
            scale = a[r][col]
            a[r] = [a[r][j] - scale * a[col][j] for j in range(m + 1)]
    return [a[i][m] for i in range(m)]


def estimate(records, dt):
    x, y = [], []
    for left, right in zip(records[:-1], records[1:]):
        x.append([float(left["temperature"]), float(left["heater_power"]), 1.0])
        y.append(float(right["temperature"]))
    a, b, c = least_squares(x, y)
    # Sensor noise may make a marginally stable fit appear outside its physical range.
    a_physical = min(0.9999, max(0.001, a))
    tau = -dt / math.log(a_physical)
    denom = 1.0 - a_physical
    k = b / denom
    ambient = c / denom
    predictions = [a * row[0] + b * row[1] + c for row in x]
    mean_y = sum(y) / len(y)
    sse = sum((actual - predicted) ** 2 for actual, predicted in zip(y, predictions))
    sst = sum((actual - mean_y) ** 2 for actual in y)
    r2 = 1.0 - sse / sst if sst > 1e-12 else 0.0
    return {
        "K": k, "tau": tau, "r_squared": r2,
        "fitting_error": math.sqrt(sse / len(y)),
        "ambient_temperature": ambient,
        "discrete_a": a, "discrete_b": b, "sample_dt": dt,
    }


def tune(params):
    k = float(params["K"])
    tau = max(0.5, float(params["tau"]))
    # Positive heater-to-temperature gain is required for this heating controller.
    if not math.isfinite(k) or k <= 1e-7:
        raise RuntimeError("identified heater gain is nonpositive; calibration cannot tune a heating controller")
    lam = min(20.0, max(8.0, tau / 4.0))
    kp = min(30.0, max(0.05, tau / (k * lam)))
    ki = kp / tau
    return {"Kp": kp, "Ki": ki, "Kd": 0.0, "lambda": lam}


def metrics(data, setpoint):
    times = [float(r["time"]) for r in data]
    temps = [float(r["temperature"]) for r in data]
    start, initial = times[0], temps[0]
    change = setpoint - initial
    rise = None
    if abs(change) < 1e-9:
        rise = 0.0
    else:
        threshold = initial + 0.9 * change
        for t, temp in zip(times, temps):
            if (change > 0 and temp >= threshold) or (change < 0 and temp <= threshold):
                rise = t - start
                break
    band = 0.5
    settling = None
    for i in range(len(data)):
        if all(abs(temp - setpoint) <= band for temp in temps[i:]):
            settling = times[i] - start
            break
    window_start = max(start, times[-1] - max(30.0, 0.2 * (times[-1] - start)))
    tail = [abs(r["error"]) for r in data if float(r["time"]) >= window_start]
    overshoot = max(0.0, max(temps) - setpoint) / max(abs(change), 1e-9)
    return {"rise_time": rise, "overshoot": overshoot, "settling_time": settling,
            "steady_state_error": sum(tail) / len(tail), "max_temp": max(temps)}


def main(request):
    sim_path = request.get("simulator_path", "/root/hvac_simulator.py")
    cfg_path = request.get("room_config_path", "/root/room_config.json")
    output_dir = Path(request.get("output_dir", "."))
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, encoding="utf-8") as f:
        config = json.load(f)
    requested_dt = float(request.get("sample_dt", recursive_dt(config) or 0.5))
    if not finite(requested_dt) or requested_dt <= 0:
        raise RuntimeError("sample_dt must be positive")
    sim = SimulatorAdapter(load_module(sim_path), cfg_path, config, requested_dt, request.get("adapter", {}))
    dt = requested_dt
    start_time = sim.local_time
    calibration_power = min(100.0, max(1.0, float(request.get("calibration_power", 40.0))))
    # 5 s baseline, up to 40 s excitation (safety cutout at 24 C), then 20 s cooldown.
    calibration = []
    n_baseline, n_step, n_cool = [max(1, int(math.ceil(v / dt))) for v in (5.0, 40.0, 20.0)]
    for i in range(n_baseline + n_step + n_cool):
        temperature = sim.temperature()
        if i < n_baseline:
            power = 0.0
        elif i < n_baseline + n_step and temperature < 24.0:
            power = calibration_power
        else:
            power = 0.0
        calibration.append({"time": sim.local_time, "temperature": temperature, "heater_power": power})
        sim.step(power)
    # Add a final state so each applied calibration command has a successor in the fit.
    calibration.append({"time": sim.local_time, "temperature": sim.temperature(), "heater_power": 0.0})
    calibration_doc = {"phase": "calibration", "heater_power_test": calibration_power, "data": calibration}
    params = estimate(calibration, dt)
    gains = tune(params)
    setpoint = float(request.get("setpoint", 22.0))
    duration = max(150.0, float(request.get("control_duration_s", 180.0)))
    steps = max(2, int(math.ceil(duration / dt)))
    integral = 0.0
    previous_error = None
    ambient = float(params["ambient_temperature"])
    ff = (setpoint - ambient) / float(params["K"])
    control = []
    for _ in range(steps + 1):
        temp = sim.temperature()
        error = setpoint - temp
        candidate = integral + error * dt
        derivative = 0.0 if previous_error is None else (error - previous_error) / dt
        raw_candidate = ff + gains["Kp"] * error + gains["Ki"] * candidate + gains["Kd"] * derivative
        command = min(100.0, max(0.0, raw_candidate))
        # Conditional integration prevents windup while retaining integral action out of saturation.
        if command == raw_candidate or (command <= 0.0 and error > 0.0) or (command >= 100.0 and error < 0.0):
            integral = candidate
        raw = ff + gains["Kp"] * error + gains["Ki"] * integral + gains["Kd"] * derivative
        command = min(100.0, max(0.0, raw))
        control.append({"time": sim.local_time, "temperature": temp, "setpoint": setpoint,
                        "heater_power": command, "error": error})
        previous_error = error
        sim.step(command)
    control_doc = {"phase": "control", "setpoint": setpoint, "data": control}
    metric_doc = metrics(control, setpoint)
    dump(output_dir / "calibration_log.json", calibration_doc)
    dump(output_dir / "estimated_params.json", {k: params[k] for k in ("K", "tau", "r_squared", "fitting_error")})
    dump(output_dir / "tuned_gains.json", gains)
    dump(output_dir / "control_log.json", control_doc)
    dump(output_dir / "metrics.json", metric_doc)
    return {"output_dir": str(output_dir), "files": ["calibration_log.json", "estimated_params.json", "tuned_gains.json", "control_log.json", "metrics.json"], "metrics": metric_doc}


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
        print(json.dumps(result, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise
