#!/usr/bin/env python3
"""HVAC calibration, identification, tuning, and trace generation.

Input: one optional JSON object on stdin. Empty stdin selects /root defaults.
Output: one JSON manifest on stdout. The five deliverables are written beneath
output_dir, which defaults to /root.
"""
import importlib.util
import inspect
import json
import math
import sys
from pathlib import Path


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def num(x, label):
    if not finite(x):
        raise RuntimeError(label + " must be a finite number")
    return float(x)


def clamp(x, low, high):
    return min(high, max(low, float(x)))


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")


def temperature(value):
    if finite(value):
        return float(value)
    if isinstance(value, dict):
        for key in ("temperature", "temp", "current_temperature", "room_temperature", "room_temp", "indoor_temperature", "T"):
            if finite(value.get(key)):
                return float(value[key])
    if isinstance(value, (list, tuple)) and value and finite(value[0]):
        return float(value[0])
    return None


def configured_dt(value):
    if isinstance(value, dict):
        for key in ("dt", "time_step", "timestep", "sample_dt", "sample_interval"):
            if finite(value.get(key)) and float(value[key]) > 0:
                return float(value[key])
        for child in value.values():
            result = configured_dt(child)
            if result is not None:
                return result
    elif isinstance(value, list):
        for child in value:
            result = configured_dt(child)
            if result is not None:
                return result
    return None


def load_module(path):
    spec = importlib.util.spec_from_file_location("task_hvac_simulator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load simulator_path")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Plant:
    """Small adapter for class-based or module-level teaching simulators."""

    def __init__(self, module, config, config_path, dt, adapter):
        self.module, self.config, self.config_path = module, config, config_path
        self.dt, self.adapter = dt, adapter
        self.obj = self._construct()

    def _construct(self):
        requested = self.adapter.get("class")
        constructors = []
        if requested:
            maker = getattr(self.module, requested, None)
            if not callable(maker):
                raise RuntimeError("adapter class not found: " + str(requested))
            constructors.append(maker)
        else:
            for name in ("HVACSimulator", "RoomSimulator", "ThermalSimulator", "HeatingSimulator", "Simulator", "Room", "create_simulator", "make_simulator"):
                maker = getattr(self.module, name, None)
                if callable(maker) and maker not in constructors:
                    constructors.append(maker)
            for maker in vars(self.module).values():
                if inspect.isclass(maker) and getattr(maker, "__module__", None) == self.module.__name__ and maker not in constructors:
                    constructors.append(maker)
        failures = []
        for maker in constructors:
            # File-path construction is preferred because the supplied config is
            # commonly consumed by the simulator itself.
            attempts = [(self.config_path,), (self.config,), ()]
            if isinstance(self.config, dict):
                attempts.append(None)
            for args in attempts:
                try:
                    return maker(**self.config) if args is None else maker(*args)
                except Exception as exc:
                    failures.append(type(exc).__name__ + ": " + str(exc))
        if any(callable(getattr(self.module, n, None)) for n in ("step", "update", "advance", "simulate_step", "run_step")):
            init = getattr(self.module, "initialize", None) or getattr(self.module, "reset", None)
            if callable(init):
                for args in ((self.config_path,), (self.config,), ()):
                    try:
                        init(*args)
                        break
                    except TypeError:
                        continue
            return self.module
        detail = " | ".join(failures[-3:])
        raise RuntimeError("unable to construct supplied simulator" + (": " + detail if detail else ""))

    def _find(self, names):
        for name in names:
            fn = getattr(self.obj, name, None)
            if callable(fn):
                return fn
        return None

    @staticmethod
    def _parameters(fn):
        try:
            return [p for p in inspect.signature(fn).parameters.values()
                    if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
        except (TypeError, ValueError):
            return []

    def read_temperature(self):
        named = self.adapter.get("temperature_method")
        fn = self._find([named] if named else ["get_temperature", "read_temperature", "get_current_temperature", "get_temp", "measure_temperature", "current_temperature"])
        if fn is not None:
            value = temperature(fn())
            if value is not None:
                return value
        named = self.adapter.get("temperature_attr")
        attrs = [named] if named else ["temperature", "current_temperature", "room_temperature", "room_temp", "indoor_temperature", "temp", "T"]
        for attr in attrs:
            value = temperature(getattr(self.obj, attr, None))
            if value is not None:
                return value
        value = temperature(getattr(self.obj, "state", None))
        if value is not None:
            return value
        raise RuntimeError("cannot read simulator temperature")

    def advance(self, command):
        command = clamp(command, 0.0, 100.0)
        named = self.adapter.get("step_method")
        step = self._find([named] if named else ["step", "update", "advance", "simulate_step", "run_step", "advance_time"])
        if step is None:
            raise RuntimeError("cannot find simulator step method")
        named = self.adapter.get("heater_setter")
        setter = self._find([named] if named else ["set_heater_power", "set_power", "set_heater", "apply_heater_power", "set_input", "set_control"])
        params = self._parameters(step)
        power_names = {"power", "heater_power", "heater", "input_power", "control", "action", "u", "command", "heater_percent", "power_percent", "heater_power_percent"}
        time_names = {"dt", "time_step", "timestep", "delta_t", "duration", "seconds"}
        direct = any(p.name.lower() in power_names for p in params)
        if setter is not None and not direct:
            try:
                setter(command)
            except TypeError:
                p = self._parameters(setter)
                if len(p) != 1:
                    raise RuntimeError("heater setter has unsupported signature")
                setter(**{p[0].name: command})
            kwargs = {p.name: self.dt for p in params if p.name.lower() in time_names}
            required_unknown = [p for p in params if p.default is inspect.Parameter.empty and p.name not in kwargs]
            result = step(self.dt) if required_unknown else step(**kwargs)
        else:
            kwargs = {}
            for p in params:
                if p.name.lower() in power_names:
                    kwargs[p.name] = command
                elif p.name.lower() in time_names:
                    kwargs[p.name] = self.dt
            if kwargs:
                result = step(**kwargs)
            elif not params:
                if setter is None:
                    for attr in ("heater_power", "power", "heater", "input_power", "command"):
                        if hasattr(self.obj, attr):
                            setattr(self.obj, attr, command)
                            break
                result = step()
            else:
                args = [command]
                if len(params) > 1:
                    args.append(self.dt)
                result = step(*args)
        return self.read_temperature() if temperature(result) is None else temperature(result)


def solve3(matrix, rhs):
    a = [list(row) + [value] for row, value in zip(matrix, rhs)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < 1e-10:
            raise ValueError("singular regression")
        a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [v / scale for v in a[col]]
        for row in range(3):
            if row != col:
                scale = a[row][col]
                a[row] = [v - scale * w for v, w in zip(a[row], a[col])]
    return [a[i][3] for i in range(3)]


def identify(rows, dt):
    x = [[r["temperature"], r["heater_power"], 1.0] for r in rows[:-1]]
    y = [r["temperature"] for r in rows[1:]]
    normal = [[sum(row[i] * row[j] for row in x) for j in range(3)] for i in range(3)]
    rhs = [sum(row[i] * value for row, value in zip(x, y)) for i in range(3)]
    try:
        a, b, c = solve3(normal, rhs)
    except ValueError:
        a, b, c = 0.98, 0.01, 0.0
    predictions = [a * row[0] + b * row[1] + c for row in x]
    sse = sum((actual - predicted) ** 2 for actual, predicted in zip(y, predictions))
    mean = sum(y) / len(y)
    sst = sum((actual - mean) ** 2 for actual in y)
    r2 = 0.0 if sst <= 1e-12 else clamp(1.0 - sse / sst, 0.0, 1.0)
    a = clamp(a, 0.001, 0.9995)
    gain = b / (1.0 - a)
    if not finite(gain) or gain <= 1e-5:
        base = min(r["temperature"] for r in rows if r["heater_power"] == 0.0)
        hot = max(r["temperature"] for r in rows if r["heater_power"] > 1.0)
        gain = max(0.0001, (hot - base) / max(1.0, max(r["heater_power"] for r in rows)))
    ambient = c / (1.0 - a)
    if not finite(ambient):
        ambient = rows[0]["temperature"]
    return {"K": float(gain), "tau": float(max(0.1, -dt / math.log(a))),
            "r_squared": float(r2), "fitting_error": float(math.sqrt(sse / len(y))),
            "ambient": float(ambient)}


def make_gains(model, multiplier):
    lam = clamp(model["tau"] * multiplier, 2.0, 80.0)
    kp = clamp(model["tau"] / (max(model["K"], 0.0001) * lam), 0.0001, 300.0)
    return {"Kp": float(kp), "Ki": float(clamp(kp / max(model["tau"], 0.1), 0.000001, 30.0)), "Kd": 0.0, "lambda": float(lam)}


def control_run(module, config, config_path, adapter, dt, duration, setpoint, model, gains):
    plant = Plant(module, config, config_path, dt, adapter)
    feedforward = clamp((setpoint - model["ambient"]) / max(model["K"], 0.0001), 0.0, 90.0)
    integral, now, rows = 0.0, 0.0, []
    count = int(math.ceil(duration / dt)) + 1
    for _ in range(count):
        temp = num(plant.read_temperature(), "control temperature")
        error = setpoint - temp
        proposed_i = clamp(integral + error * dt, -1000.0, 1000.0)
        raw = feedforward + gains["Kp"] * error + gains["Ki"] * proposed_i
        power = clamp(raw, 0.0, 100.0)
        # Conditional integration prevents accumulation that would push farther
        # into an already saturated actuator.
        if abs(raw - power) < 1e-12 or (power <= 0.0 and error > 0.0) or (power >= 100.0 and error < 0.0):
            integral = proposed_i
        rows.append({"time": float(now), "temperature": float(temp), "setpoint": float(setpoint),
                     "heater_power": float(power), "error": float(setpoint - temp)})
        plant.advance(power)
        now += dt
    return rows


def measure(rows, setpoint):
    times = [r["time"] for r in rows]
    temps = [r["temperature"] for r in rows]
    start = temps[0]
    threshold = start + 0.9 * (setpoint - start)
    rise = next((i for i, temp in enumerate(temps) if (temp >= threshold if setpoint >= start else temp <= threshold)), len(rows) - 1)
    settled = next((i for i in range(len(rows)) if all(abs(temp - setpoint) < 0.5 for temp in temps[i:])), len(rows) - 1)
    maximum = max(temps)
    tail = max(3, int(math.ceil(len(temps) * 0.2)))
    return {"rise_time": float(times[rise] - times[0]),
            "overshoot": float(max(0.0, (maximum - setpoint) / setpoint)),
            "settling_time": float(times[settled] - times[0]),
            "steady_state_error": float(sum(abs(temp - setpoint) for temp in temps[-tail:]) / tail),
            "max_temp": float(maximum)}


def meets(m):
    return m["steady_state_error"] < 0.5 and m["settling_time"] < 120.0 and m["overshoot"] < 0.10 and m["max_temp"] < 30.0


def score(m):
    return (10000 * max(0.0, m["steady_state_error"] - 0.35) +
            100 * max(0.0, m["settling_time"] - 105.0) +
            10000 * max(0.0, m["overshoot"] - 0.07) +
            1000 * max(0.0, m["max_temp"] - 28.0) + m["settling_time"] * 0.01)


def request_from_stdin():
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("stdin JSON must be an object")
    return value


def main(request):
    simulator_path = request.get("simulator_path", "/root/hvac_simulator.py")
    config_path = request.get("room_config_path", "/root/room_config.json")
    outdir = Path(request.get("output_dir", "/root"))
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    dt = num(request.get("sample_dt", configured_dt(config) or 0.5), "sample_dt")
    if dt <= 0:
        raise RuntimeError("sample_dt must be positive")
    setpoint = num(request.get("setpoint", 22.0), "setpoint")
    duration = max(150.0, num(request.get("control_duration_s", 240.0), "control_duration_s"))
    calibration_power = clamp(num(request.get("calibration_power", 50.0), "calibration_power"), 2.0, 100.0)
    adapter = request.get("adapter", {})
    if not isinstance(adapter, dict):
        raise RuntimeError("adapter must be an object")
    outdir.mkdir(parents=True, exist_ok=True)
    module = load_module(simulator_path)

    plant = Plant(module, config, config_path, dt, adapter)
    calibration, now = [], 0.0
    # 5 s baseline, 60 s positive excitation, then 15 s cooldown.
    samples = int(math.ceil(80.0 / dt)) + 1
    baseline_end, heat_end = int(math.ceil(5.0 / dt)), int(math.ceil(65.0 / dt))
    for i in range(samples):
        command = calibration_power if baseline_end <= i < heat_end else 0.0
        calibration.append({"time": float(now), "temperature": num(plant.read_temperature(), "calibration temperature"), "heater_power": float(command)})
        plant.advance(command)
        now += dt
    write_json(outdir / "calibration_log.json", {"phase": "calibration", "heater_power_test": float(calibration_power), "data": calibration})

    model = identify(calibration, dt)
    write_json(outdir / "estimated_params.json", {key: model[key] for key in ("K", "tau", "r_squared", "fitting_error")})

    selected = None
    for multiplier in (0.15, 0.22, 0.32, 0.48, 0.70, 1.0, 1.5, 2.0):
        gains = make_gains(model, multiplier)
        trace = control_run(module, config, config_path, adapter, dt, duration, setpoint, model, gains)
        metrics = measure(trace, setpoint)
        candidate = (score(metrics), trace, gains, metrics)
        if selected is None or candidate[0] < selected[0]:
            selected = candidate
        if meets(metrics):
            selected = candidate
            break
    _, trace, gains, metrics = selected
    write_json(outdir / "tuned_gains.json", gains)
    write_json(outdir / "control_log.json", {"phase": "control", "setpoint": float(setpoint), "data": trace})
    write_json(outdir / "metrics.json", metrics)
    return {"ok": True, "targets_met": meets(metrics),
            "files": ["calibration_log.json", "estimated_params.json", "tuned_gains.json", "control_log.json", "metrics.json"],
            "metrics": metrics}


if __name__ == "__main__":
    try:
        print(json.dumps(main(request_from_stdin()), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, allow_nan=False))
        sys.exit(1)
