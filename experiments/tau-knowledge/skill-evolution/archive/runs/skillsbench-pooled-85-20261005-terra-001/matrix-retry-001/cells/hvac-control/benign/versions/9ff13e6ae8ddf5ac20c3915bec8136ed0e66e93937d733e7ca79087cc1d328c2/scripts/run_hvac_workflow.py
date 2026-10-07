#!/usr/bin/env python3
"""Run calibration, identification, PID tuning, and HVAC control.

stdin JSON schema:
{
  "simulator_path": str, "room_config_path": str, "output_dir": str,
  "setpoint": number, "control_duration_s": number,
  "sample_dt": number?, "calibration_power": number?, "adapter": object?
}

stdout JSON schema:
{"ok": bool, "targets_met": bool, "files": [str], "metrics": object}

The result files are written below output_dir.  All logged temperatures come
from a fresh instance of the supplied simulator; this program never invents a
thermal response.
"""
import importlib.util
import inspect
import json
import math
import sys
from pathlib import Path


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def number(value, label):
    if not numeric(value):
        raise RuntimeError(label + " must be a finite number")
    return float(value)


def dump(path, value):
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def temperature_from(value):
    if numeric(value):
        return float(value)
    if isinstance(value, dict):
        for key in ("temperature", "temp", "current_temperature", "room_temperature", "room_temp", "indoor_temperature", "T"):
            if numeric(value.get(key)):
                return float(value[key])
    if isinstance(value, (tuple, list)) and value and numeric(value[0]):
        return float(value[0])
    return None


def find_dt(value):
    if isinstance(value, dict):
        for key in ("dt", "time_step", "timestep", "sample_dt", "sample_interval"):
            if numeric(value.get(key)) and float(value[key]) > 0:
                return float(value[key])
        for child in value.values():
            answer = find_dt(child)
            if answer is not None:
                return answer
    if isinstance(value, list):
        for child in value:
            answer = find_dt(child)
            if answer is not None:
                return answer
    return None


def load_module(path):
    spec = importlib.util.spec_from_file_location("supplied_hvac_simulator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load simulator_path")
    module = importlib.util.module_from_spec(spec)
    # Some simulators use dataclasses or annotations while importing.  Register
    # before execution exactly as normal Python import machinery does.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Plant:
    """Adapter for common class-based educational thermal simulators."""

    def __init__(self, module, config, config_path, dt, adapter):
        self.module = module
        self.config = config
        self.config_path = config_path
        self.dt = dt
        self.adapter = adapter
        self.obj = self._construct()
        reset = getattr(self.obj, "reset", None)
        if callable(reset):
            for args in ((), (config,), (config_path,)):
                try:
                    reset(*args)
                    break
                except TypeError:
                    pass

    def _construct(self):
        requested = self.adapter.get("class")
        makers = []
        if requested:
            maker = getattr(self.module, requested, None)
            if not callable(maker):
                raise RuntimeError("adapter class was not found: " + str(requested))
            makers.append(maker)
        else:
            for name in ("create_simulator", "make_simulator", "HVACSimulator", "RoomSimulator", "ThermalSimulator", "Simulator", "Room"):
                maker = getattr(self.module, name, None)
                if callable(maker) and maker not in makers:
                    makers.append(maker)
            for _, maker in vars(self.module).items():
                if inspect.isclass(maker) and getattr(maker, "__module__", None) == self.module.__name__ and maker not in makers:
                    makers.append(maker)
        problems = []
        for maker in makers:
            for args in ((self.config,), (self.config_path,), ()):
                try:
                    return maker(*args)
                except Exception as exc:
                    problems.append(type(exc).__name__ + ": " + str(exc))
            if isinstance(self.config, dict):
                try:
                    return maker(**self.config)
                except Exception as exc:
                    problems.append(type(exc).__name__ + ": " + str(exc))
        # A module-level simulator is also supported when it exposes a step API.
        if any(callable(getattr(self.module, name, None)) for name in ("step", "simulate_step", "run_step", "update", "advance")):
            initializer = getattr(self.module, "initialize", None) or getattr(self.module, "reset", None)
            if callable(initializer):
                for args in ((self.config,), (self.config_path,), ()):
                    try:
                        initializer(*args)
                        break
                    except TypeError:
                        pass
            return self.module
        suffix = (": " + " | ".join(problems[-4:])) if problems else ""
        raise RuntimeError("could not construct supplied simulator" + suffix)

    def _method(self, names):
        for name in names:
            fn = getattr(self.obj, name, None)
            if callable(fn):
                return fn
        return None

    @staticmethod
    def _params(fn):
        try:
            return [p for p in inspect.signature(fn).parameters.values()
                    if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
        except (ValueError, TypeError):
            return []

    def temperature(self):
        preferred = self.adapter.get("temperature_method")
        names = [preferred] if preferred else ["get_temperature", "read_temperature", "get_temp", "measure_temperature", "current_temperature"]
        fn = self._method(names)
        if fn is not None:
            result = temperature_from(fn())
            if result is not None:
                return result
        preferred = self.adapter.get("temperature_attr")
        names = [preferred] if preferred else ["temperature", "current_temperature", "room_temperature", "room_temp", "indoor_temperature", "temp", "T"]
        for name in names:
            result = temperature_from(getattr(self.obj, name, None))
            if result is not None:
                return result
        result = temperature_from(getattr(self.obj, "state", None))
        if result is not None:
            return result
        raise RuntimeError("cannot read temperature; supply adapter.temperature_method or temperature_attr")

    def _set_power(self, setter, power):
        try:
            setter(power)
            return
        except TypeError:
            pass
        for p in self._params(setter):
            if p.name.lower() in ("power", "heater_power", "heater", "input_power", "command", "value", "percent", "heater_percent"):
                setter(**{p.name: power})
                return
        raise RuntimeError("heater setter has an unsupported signature")

    def step(self, command):
        command = min(100.0, max(0.0, float(command)))
        step_name = self.adapter.get("step_method")
        step = self._method([step_name] if step_name else ["step", "simulate_step", "run_step", "advance", "update", "advance_time"])
        if step is None:
            raise RuntimeError("cannot find simulator step method; supply adapter.step_method")
        setter_name = self.adapter.get("heater_setter")
        setter = self._method([setter_name] if setter_name else ["set_heater_power", "set_power", "set_heater", "apply_heater_power", "set_input", "set_control"])
        params = self._params(step)
        names = [p.name.lower() for p in params]
        power_names = {"power", "heater_power", "heater", "input_power", "control", "action", "u", "command", "heater_percent", "heater_power_percent"}
        time_names = {"dt", "time_step", "timestep", "delta_t", "duration", "seconds"}
        direct_power = any(n in power_names for n in names)
        if setter is not None and not direct_power:
            self._set_power(setter, command)
            kwargs = {p.name: self.dt for p in params if p.name.lower() in time_names}
            unknown = [p for p in params if p.default is inspect.Parameter.empty and p.name not in kwargs]
            if unknown:
                result = step(self.dt)
            else:
                result = step(**kwargs)
        else:
            # A few simple simulators expose a writable command attribute.
            if setter is None and not direct_power:
                for attr in ("heater_power", "power", "heater", "input_power", "command"):
                    if hasattr(self.obj, attr):
                        setattr(self.obj, attr, command)
                        break
            kwargs = {}
            for p in params:
                if p.name.lower() in power_names:
                    kwargs[p.name] = command
                elif p.name.lower() in time_names:
                    kwargs[p.name] = self.dt
            if kwargs:
                result = step(**kwargs)
            else:
                required = [p for p in params if p.default is inspect.Parameter.empty]
                args = [command]
                if len(required) >= 2:
                    args.append(self.dt)
                result = step(*args)
        returned = temperature_from(result)
        return self.temperature() if returned is None else returned


def solve3(a, b):
    q = [list(row) + [rhs] for row, rhs in zip(a, b)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda row: abs(q[row][col]))
        if abs(q[pivot][col]) < 1e-10:
            raise ValueError("singular fit")
        q[col], q[pivot] = q[pivot], q[col]
        scale = q[col][col]
        q[col] = [x / scale for x in q[col]]
        for row in range(3):
            if row != col:
                scale = q[row][col]
                q[row] = [x - scale * y for x, y in zip(q[row], q[col])]
    return [q[i][3] for i in range(3)]


def identify(rows, dt):
    x = [[r["temperature"], r["heater_power"], 1.0] for r in rows[:-1]]
    y = [r["temperature"] for r in rows[1:]]
    normal = [[sum(row[i] * row[j] for row in x) for j in range(3)] for i in range(3)]
    rhs = [sum(row[i] * target for row, target in zip(x, y)) for i in range(3)]
    try:
        a, b, c = solve3(normal, rhs)
    except ValueError:
        a, b, c = 0.98, 0.01, 0.0
    predictions = [a * row[0] + b * row[1] + c for row in x]
    sse = sum((actual - predicted) ** 2 for actual, predicted in zip(y, predictions))
    mean = sum(y) / len(y)
    sst = sum((actual - mean) ** 2 for actual in y)
    r2 = 0.0 if sst <= 1e-12 else min(1.0, max(0.0, 1.0 - sse / sst))
    stable_a = min(0.9995, max(0.001, a))
    gain = b / (1.0 - stable_a)
    if not numeric(gain) or gain <= 1e-5:
        baseline = [r["temperature"] for r in rows if r["heater_power"] == 0.0]
        excited = [r for r in rows if r["heater_power"] > 1.0]
        if baseline and excited:
            gain = (max(r["temperature"] for r in excited) - min(baseline)) / max(1.0, sum(r["heater_power"] for r in excited) / len(excited))
        gain = max(0.0001, gain)
    ambient = c / (1.0 - stable_a)
    if not numeric(ambient):
        ambient = rows[0]["temperature"]
    return {"K": float(gain), "tau": float(max(0.1, -dt / math.log(stable_a))),
            "r_squared": float(r2), "fitting_error": float(math.sqrt(sse / len(y))), "ambient": float(ambient)}


def gains(params, factor):
    lam = max(2.0, min(80.0, params["tau"] * factor))
    kp = max(0.0001, min(300.0, params["tau"] / (max(params["K"], 0.0001) * lam)))
    return {"Kp": float(kp), "Ki": float(max(0.000001, min(30.0, kp / max(params["tau"], 0.1)))), "Kd": 0.0, "lambda": float(lam)}


def run_control(module, config, config_path, adapter, dt, duration, setpoint, params, tuned):
    plant = Plant(module, config, config_path, dt, adapter)
    feedforward = min(90.0, max(0.0, (setpoint - params["ambient"]) / max(params["K"], 0.0001)))
    integral, now, rows = 0.0, 0.0, []
    for _ in range(int(math.ceil(duration / dt)) + 1):
        temp = number(plant.temperature(), "control temperature")
        error = setpoint - temp
        candidate_integral = min(1000.0, max(-1000.0, integral + error * dt))
        raw = feedforward + tuned["Kp"] * error + tuned["Ki"] * candidate_integral
        power = min(100.0, max(0.0, raw))
        if abs(raw - power) < 1e-12 or (power <= 0.0 and error > 0.0) or (power >= 100.0 and error < 0.0):
            integral = candidate_integral
        rows.append({"time": float(now), "temperature": temp, "setpoint": float(setpoint),
                     "heater_power": float(power), "error": float(setpoint - temp)})
        plant.step(power)
        now += dt
    return rows


def metrics(rows, setpoint):
    times = [r["time"] for r in rows]
    temps = [r["temperature"] for r in rows]
    start = temps[0]
    threshold = start + 0.9 * (setpoint - start)
    rising = ((setpoint >= start and t >= threshold) or (setpoint < start and t <= threshold) for t in temps)
    rise_index = next((i for i, reached in enumerate(rising) if reached), len(rows) - 1)
    settled_index = next((i for i in range(len(rows)) if all(abs(t - setpoint) < 0.5 for t in temps[i:])), len(rows) - 1)
    max_temp = max(temps)
    tail = max(3, int(math.ceil(len(temps) * 0.2)))
    return {"rise_time": float(times[rise_index] - times[0]),
            "overshoot": float(max(0.0, (max_temp - setpoint) / setpoint)),
            "settling_time": float(times[settled_index] - times[0]),
            "steady_state_error": float(sum(abs(t - setpoint) for t in temps[-tail:]) / tail),
            "max_temp": float(max_temp)}


def targets(m):
    return m["steady_state_error"] < 0.5 and m["settling_time"] < 120.0 and m["overshoot"] < 0.10 and m["max_temp"] < 30.0


def penalty(m):
    return (10000.0 * max(0.0, m["steady_state_error"] - 0.35) +
            100.0 * max(0.0, m["settling_time"] - 105.0) +
            10000.0 * max(0.0, m["overshoot"] - 0.07) +
            1000.0 * max(0.0, m["max_temp"] - 28.0))


def main(request):
    simulator_path = request.get("simulator_path", "/root/hvac_simulator.py")
    config_path = request.get("room_config_path", "/root/room_config.json")
    outdir = Path(request.get("output_dir", "/root"))
    with open(config_path, encoding="utf-8") as stream:
        config = json.load(stream)
    dt = number(request.get("sample_dt", find_dt(config) or 0.5), "sample_dt")
    if dt <= 0:
        raise RuntimeError("sample_dt must be positive")
    setpoint = number(request.get("setpoint", 22.0), "setpoint")
    duration = max(150.0, number(request.get("control_duration_s", 240.0), "control_duration_s"))
    power = min(100.0, max(2.0, number(request.get("calibration_power", 50.0), "calibration_power")))
    adapter = request.get("adapter", {})
    if not isinstance(adapter, dict):
        raise RuntimeError("adapter must be an object")
    module = load_module(simulator_path)

    calibration_plant = Plant(module, config, config_path, dt, adapter)
    calibration, now = [], 0.0
    # Baseline (5 s), meaningful excitation (60 s), and cooldown (15 s).
    n = int(math.ceil(80.0 / dt)) + 1
    base_end, heat_end = int(math.ceil(5.0 / dt)), int(math.ceil(65.0 / dt))
    for i in range(n):
        command = 0.0 if i < base_end or i >= heat_end else power
        calibration.append({"time": float(now), "temperature": number(calibration_plant.temperature(), "calibration temperature"), "heater_power": float(command)})
        calibration_plant.step(command)
        now += dt
    params = identify(calibration, dt)

    selected = None
    for factor in (0.20, 0.35, 0.55, 0.8, 1.2, 1.8):
        tuned = gains(params, factor)
        trace = run_control(module, config, config_path, adapter, dt, duration, setpoint, params, tuned)
        observed = metrics(trace, setpoint)
        candidate = (penalty(observed), trace, tuned, observed)
        if selected is None or candidate[0] < selected[0]:
            selected = candidate
        if targets(observed):
            selected = candidate
            break
    _, trace, tuned, observed = selected

    outdir.mkdir(parents=True, exist_ok=True)
    dump(outdir / "calibration_log.json", {"phase": "calibration", "heater_power_test": float(power), "data": calibration})
    dump(outdir / "estimated_params.json", {k: params[k] for k in ("K", "tau", "r_squared", "fitting_error")})
    dump(outdir / "tuned_gains.json", tuned)
    dump(outdir / "control_log.json", {"phase": "control", "setpoint": float(setpoint), "data": trace})
    dump(outdir / "metrics.json", observed)
    return {"ok": True, "targets_met": targets(observed),
            "files": ["calibration_log.json", "estimated_params.json", "tuned_gains.json", "control_log.json", "metrics.json"],
            "metrics": observed}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, allow_nan=False))
        raise
