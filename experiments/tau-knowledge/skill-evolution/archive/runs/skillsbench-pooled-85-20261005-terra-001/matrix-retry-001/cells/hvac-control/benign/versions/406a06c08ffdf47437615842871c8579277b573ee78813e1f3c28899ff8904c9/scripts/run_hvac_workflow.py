#!/usr/bin/env python3
"""Run a real HVAC calibration and closed-loop experiment.

JSON stdin schema:
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "setpoint": 22.0,
  "control_duration_s": 210.0,
  "sample_dt": 0.5,
  "calibration_power": 50.0,
  "adapter": {"class": "...", "factory": "...", "temperature_method": "...",
              "temperature_attr": "...", "step_method": "...", "time_attr": "..."}
}

The program emits a JSON manifest to stdout and writes the five requested JSON
artifacts to output_dir. It uses only the supplied simulator at runtime.
"""
import importlib.util
import inspect
import json
import math
import sys
from pathlib import Path


def is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def as_num(value, what):
    if not is_num(value):
        raise RuntimeError("simulator returned no finite " + what)
    return float(value)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, indent=2, allow_nan=False)
        handle.write("\n")


def read_dt(value):
    if isinstance(value, dict):
        for key in ("dt", "time_step", "timestep", "sample_time", "sample_interval"):
            if key in value and is_num(value[key]) and float(value[key]) > 0:
                return float(value[key])
        for child in value.values():
            result = read_dt(child)
            if result:
                return result
    if isinstance(value, list):
        for child in value:
            result = read_dt(child)
            if result:
                return result
    return None


def temperature_from(value):
    if is_num(value):
        return float(value)
    if isinstance(value, dict):
        for key in ("temperature", "temp", "current_temperature", "room_temperature", "T"):
            if key in value and is_num(value[key]):
                return float(value[key])
    if isinstance(value, (tuple, list)) and value and is_num(value[0]):
        return float(value[0])
    return None


def load_module(filename):
    spec = importlib.util.spec_from_file_location("task_hvac_simulator", filename)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import supplied simulator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Room:
    def __init__(self, module, config, config_path, dt, adapter):
        self.module = module
        self.config = config
        self.config_path = config_path
        self.dt = dt
        self.adapter = adapter or {}
        self.obj = self._make()
        self.local_time = 0.0
        self._try_reset()
        observed = self._read_time()
        if observed is not None:
            self.local_time = observed
        self.last_temperature = self.temperature()

    def _make(self):
        requested = self.adapter.get("class") or self.adapter.get("factory")
        if requested:
            candidate = getattr(self.module, requested, None)
            if not callable(candidate):
                raise RuntimeError("requested simulator constructor is not callable: " + requested)
            candidates = [candidate]
        else:
            preferred = ("create_simulator", "make_simulator", "HVACSimulator", "RoomSimulator",
                         "ThermalSimulator", "Simulator", "Room", "Environment")
            candidates = []
            for name in preferred:
                value = getattr(self.module, name, None)
                if callable(value):
                    candidates.append(value)
            for name, value in vars(self.module).items():
                if inspect.isclass(value) and value.__module__ == self.module.__name__ and value not in candidates:
                    candidates.append(value)
        if not candidates:
            raise RuntimeError("no simulator factory or class found; supply adapter.class")
        attempts = [(self.config,), (self.config_path,), (), (None,)]
        failures = []
        for constructor in candidates:
            for args in attempts:
                try:
                    return constructor(*args)
                except Exception as exc:
                    failures.append("%s: %s" % (getattr(constructor, "__name__", "factory"), exc))
            try:
                return constructor(**self.config)
            except Exception as exc:
                failures.append("keyword config: %s" % exc)
        raise RuntimeError("could not construct simulator: " + " | ".join(failures[-5:]))

    def _try_reset(self):
        reset = getattr(self.obj, "reset", None)
        if callable(reset):
            try:
                reset()
            except TypeError:
                pass

    def temperature(self):
        names = [self.adapter.get("temperature_method")] if self.adapter.get("temperature_method") else ["get_temperature", "read_temperature", "get_temp", "measure_temperature"]
        for name in names:
            func = getattr(self.obj, name, None) if name else None
            if callable(func):
                answer = temperature_from(func())
                if answer is not None:
                    return answer
        names = [self.adapter.get("temperature_attr")] if self.adapter.get("temperature_attr") else ["temperature", "current_temperature", "room_temperature", "temp", "T"]
        for name in names:
            answer = temperature_from(getattr(self.obj, name, None)) if name else None
            if answer is not None:
                return answer
        answer = temperature_from(getattr(self.obj, "state", None))
        if answer is not None:
            return answer
        raise RuntimeError("cannot read temperature; provide adapter.temperature_method or temperature_attr")

    def _read_time(self):
        names = [self.adapter.get("time_attr")] if self.adapter.get("time_attr") else ["time", "current_time", "simulation_time", "t"]
        for name in names:
            value = getattr(self.obj, name, None) if name else None
            if is_num(value):
                return float(value)
            if callable(value):
                try:
                    value = value()
                    if is_num(value):
                        return float(value)
                except TypeError:
                    pass
        getter = getattr(self.obj, "get_time", None)
        if callable(getter):
            value = getter()
            if is_num(value):
                return float(value)
        return None

    def _call_step(self, function, power):
        try:
            params = list(inspect.signature(function).parameters.values())
        except (TypeError, ValueError):
            return function(power)
        power_names = {"heater_power", "power", "heater", "input_power", "control", "action", "u", "command", "heater_percent"}
        dt_names = {"dt", "time_step", "timestep", "delta_t", "duration"}
        kwargs = {}
        unknown_required = []
        ordinary = []
        for parameter in params:
            if parameter.kind in (parameter.VAR_KEYWORD, parameter.VAR_POSITIONAL):
                continue
            ordinary.append(parameter)
            if parameter.name.lower() in power_names:
                kwargs[parameter.name] = power
            elif parameter.name.lower() in dt_names:
                kwargs[parameter.name] = self.dt
            elif parameter.default is inspect.Parameter.empty:
                unknown_required.append(parameter)
        if unknown_required:
            if len(ordinary) == 1:
                return function(power)
            if len(ordinary) == 2 and ordinary[1].default is inspect.Parameter.empty:
                return function(power, self.dt)
            raise RuntimeError("unsupported required simulator step parameters: " + ", ".join(p.name for p in unknown_required))
        return function(**kwargs)

    def step(self, power):
        power = min(100.0, max(0.0, float(power)))
        names = [self.adapter.get("step_method")] if self.adapter.get("step_method") else ["step", "update", "run_step", "simulate_step", "advance"]
        response = None
        invoked = False
        for name in names:
            function = getattr(self.obj, name, None) if name else None
            if callable(function):
                response = self._call_step(function, power)
                invoked = True
                break
        if not invoked:
            setter = getattr(self.obj, "set_heater_power", None)
            advance = getattr(self.obj, "advance_time", None)
            if not callable(setter) or not callable(advance):
                raise RuntimeError("cannot find simulator step method; provide adapter.step_method")
            setter(power)
            response = self._call_step(advance, 0.0)
        answer = temperature_from(response)
        self.last_temperature = answer if answer is not None else self.temperature()
        observed = self._read_time()
        # Some APIs expose a time member but do not advance it. Preserve strict log ordering.
        if observed is not None and observed > self.local_time + 1e-12:
            self.local_time = observed
        else:
            self.local_time += self.dt
        return self.last_temperature


def solve_3x3(matrix, vector):
    aug = [list(row) + [target] for row, target in zip(matrix, vector)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise RuntimeError("calibration regression is singular")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        divisor = aug[col][col]
        aug[col] = [x / divisor for x in aug[col]]
        for row in range(3):
            if row != col:
                factor = aug[row][col]
                aug[row] = [x - factor * y for x, y in zip(aug[row], aug[col])]
    return [aug[i][3] for i in range(3)]


def identify(rows):
    x = []
    y = []
    intervals = []
    for left, right in zip(rows[:-1], rows[1:]):
        x.append([float(left["temperature"]), float(left["heater_power"]), 1.0])
        y.append(float(right["temperature"]))
        intervals.append(float(right["time"]) - float(left["time"]))
    normal = [[sum(row[i] * row[j] for row in x) for j in range(3)] for i in range(3)]
    target = [sum(row[i] * actual for row, actual in zip(x, y)) for i in range(3)]
    try:
        a, b, c = solve_3x3(normal, target)
    except RuntimeError:
        a, b, c = 0.98, 0.001, 0.0
    dt = sorted(intervals)[len(intervals) // 2]
    if not is_num(dt) or dt <= 0:
        dt = 0.5
    predicted = [a * row[0] + b * row[1] + c for row in x]
    sse = sum((actual - estimate) ** 2 for actual, estimate in zip(y, predicted))
    mean = sum(y) / len(y)
    sst = sum((actual - mean) ** 2 for actual in y)
    r2 = 0.0 if sst <= 1e-12 else max(0.0, min(1.0, 1.0 - sse / sst))
    rmse = math.sqrt(max(0.0, sse / len(y)))
    a_safe = min(0.9995, max(0.001, a))
    tau = -dt / math.log(a_safe)
    k = b / (1.0 - a_safe)
    ambient = c / (1.0 - a_safe)
    # Enforce a positive heater gain using measured baseline/step contrast if noisy OLS is invalid.
    if not is_num(k) or k <= 1e-7:
        off = [r["temperature"] for r in rows if float(r["heater_power"]) < 1e-9]
        on = [r["temperature"] for r in rows if float(r["heater_power"]) > 1.0]
        powers = [r["heater_power"] for r in rows if float(r["heater_power"]) > 1.0]
        contrast = max(0.01, (sum(on) / len(on) - sum(off) / len(off)) if on and off else 0.01)
        k = contrast / (sum(powers) / len(powers) if powers else 50.0)
    if not is_num(ambient):
        ambient = float(rows[0]["temperature"])
    return {"K": float(k), "tau": float(max(0.1, tau)), "r_squared": float(r2),
            "fitting_error": float(rmse), "ambient_temperature": float(ambient)}


def gains_for(params):
    k = max(1e-5, float(params["K"]))
    tau = max(0.5, float(params["tau"]))
    lam = max(4.0, min(20.0, tau / 3.0))
    kp = max(0.01, min(60.0, tau / (k * lam)))
    ki = max(0.0001, min(10.0, kp / tau))
    return {"Kp": float(kp), "Ki": float(ki), "Kd": 0.0, "lambda": float(lam)}


def measure_metrics(rows, setpoint):
    times = [float(r["time"]) for r in rows]
    temps = [float(r["temperature"]) for r in rows]
    start = times[0]
    delta = setpoint - temps[0]
    threshold = temps[0] + 0.9 * delta
    rise = 0.0 if abs(delta) < 1e-12 else None
    if rise is None:
        for time, temp in zip(times, temps):
            if (delta > 0 and temp >= threshold) or (delta < 0 and temp <= threshold):
                rise = time - start
                break
    # Public artifacts require finite metric values. A full control run must settle.
    if rise is None:
        rise = times[-1] - start
    settling = None
    for i in range(len(temps)):
        if all(abs(temp - setpoint) < 0.5 for temp in temps[i:]):
            settling = times[i] - start
            break
    if settling is None:
        settling = times[-1] - start
    count = max(3, int(math.ceil(len(rows) * 0.2)))
    tail_error = sum(abs(temp - setpoint) for temp in temps[-count:]) / count
    maximum = max(temps)
    return {"rise_time": float(rise), "overshoot": float(max(0.0, (maximum - setpoint) / setpoint)),
            "settling_time": float(settling), "steady_state_error": float(tail_error), "max_temp": float(maximum)}


def main(request):
    simulator_path = request.get("simulator_path", "/root/hvac_simulator.py")
    config_path = request.get("room_config_path", "/root/room_config.json")
    output_dir = Path(request.get("output_dir", "/root"))
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    dt = float(request.get("sample_dt", read_dt(config) or 0.5))
    if not is_num(dt) or dt <= 0:
        raise RuntimeError("sample_dt must be positive")
    module = load_module(simulator_path)
    adapter = request.get("adapter", {})
    calibration_room = Room(module, config, config_path, dt, adapter)
    power_test = min(100.0, max(2.0, float(request.get("calibration_power", 50.0))))
    calibration = []
    # 5 s baseline + 45 s heater step + 15 s cooldown: >= 65 s and >20 points.
    counts = [max(1, int(math.ceil(seconds / dt))) for seconds in (5.0, 45.0, 15.0)]
    for index in range(sum(counts)):
        temp = calibration_room.temperature()
        command = 0.0 if index < counts[0] or index >= counts[0] + counts[1] else power_test
        calibration.append({"time": calibration_room.local_time, "temperature": temp, "heater_power": command})
        calibration_room.step(command)
    calibration.append({"time": calibration_room.local_time, "temperature": calibration_room.temperature(), "heater_power": 0.0})
    params = identify(calibration)
    tuned = gains_for(params)
    setpoint = float(request.get("setpoint", 22.0))
    duration = max(150.0, float(request.get("control_duration_s", 210.0)))
    control_room = Room(module, config, config_path, dt, adapter)
    steps = int(math.ceil(duration / dt)) + 1
    integral = 0.0
    previous_error = None
    feedforward = min(100.0, max(0.0, (setpoint - params["ambient_temperature"]) / max(params["K"], 1e-5)))
    control = []
    for _ in range(steps):
        temp = control_room.temperature()
        error = setpoint - temp
        candidate = max(-100.0, min(100.0, integral + error * dt))
        derivative = 0.0 if previous_error is None else (error - previous_error) / dt
        requested_power = feedforward + tuned["Kp"] * error + tuned["Ki"] * candidate + tuned["Kd"] * derivative
        command = min(100.0, max(0.0, requested_power))
        # Conditional integration: do not wind up while a saturated command would move farther out.
        if command == requested_power or (command <= 0.0 and error > 0.0) or (command >= 100.0 and error < 0.0):
            integral = candidate
        control.append({"time": control_room.local_time, "temperature": temp, "setpoint": setpoint,
                        "heater_power": command, "error": error})
        previous_error = error
        control_room.step(command)
    metric_doc = measure_metrics(control, setpoint)
    write_json(output_dir / "calibration_log.json", {"phase": "calibration", "heater_power_test": power_test, "data": calibration})
    write_json(output_dir / "estimated_params.json", {key: params[key] for key in ("K", "tau", "r_squared", "fitting_error")})
    write_json(output_dir / "tuned_gains.json", tuned)
    write_json(output_dir / "control_log.json", {"phase": "control", "setpoint": setpoint, "data": control})
    write_json(output_dir / "metrics.json", metric_doc)
    return {"ok": True, "output_dir": str(output_dir), "files": ["calibration_log.json", "estimated_params.json", "tuned_gains.json", "control_log.json", "metrics.json"], "metrics": metric_doc}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, allow_nan=False))
        raise
