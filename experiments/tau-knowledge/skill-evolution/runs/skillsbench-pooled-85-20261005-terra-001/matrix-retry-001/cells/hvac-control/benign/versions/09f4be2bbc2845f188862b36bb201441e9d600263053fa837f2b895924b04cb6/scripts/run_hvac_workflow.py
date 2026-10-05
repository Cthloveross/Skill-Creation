#!/usr/bin/env python3
"""Execute HVAC calibration, identification, tuning, and control.

Input JSON keys:
  simulator_path (str), room_config_path (str), output_dir (str), setpoint
  (number), control_duration_s (number), sample_dt (optional positive number),
  calibration_power (optional 2..100), adapter (optional object).

Output JSON: {ok, files, targets_met, metrics}.  The five result files are
written below output_dir.  The implementation only logs observations obtained
by advancing fresh instances of the supplied simulator.
"""
import importlib.util
import inspect
import json
import math
import sys
from pathlib import Path


def is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def as_float(value, label):
    if not is_num(value):
        raise RuntimeError(label + " must be a finite number")
    return float(value)


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def extract_temperature(value):
    if is_num(value):
        return float(value)
    if isinstance(value, dict):
        for key in ("temperature", "temp", "current_temperature", "room_temperature", "room_temp", "indoor_temperature", "T"):
            if is_num(value.get(key)):
                return float(value[key])
    if isinstance(value, (list, tuple)) and value and is_num(value[0]):
        return float(value[0])
    return None


def configured_dt(value):
    if isinstance(value, dict):
        for key in ("dt", "time_step", "timestep", "sample_dt", "sample_interval"):
            if is_num(value.get(key)) and float(value[key]) > 0:
                return float(value[key])
        for child in value.values():
            answer = configured_dt(child)
            if answer is not None:
                return answer
    elif isinstance(value, list):
        for child in value:
            answer = configured_dt(child)
            if answer is not None:
                return answer
    return None


def import_simulator(path):
    spec = importlib.util.spec_from_file_location("task_hvac_simulator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to import simulator_path")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Plant:
    """Small adapter for conventional educational HVAC simulator APIs."""

    def __init__(self, module, config, config_path, dt, adapter):
        self.module = module
        self.config = config
        self.config_path = config_path
        self.dt = dt
        self.adapter = adapter or {}
        self.obj = self._construct()
        reset = getattr(self.obj, "reset", None)
        if callable(reset):
            for args in ((), (self.config,), (self.config_path,)):
                try:
                    reset(*args)
                    break
                except TypeError:
                    continue

    def _construct(self):
        requested = self.adapter.get("class") or self.adapter.get("factory")
        candidates = []
        if requested:
            maker = getattr(self.module, requested, None)
            if not callable(maker):
                raise RuntimeError("adapter constructor was not found: " + str(requested))
            candidates.append(maker)
        else:
            for name in ("create_simulator", "make_simulator", "HVACSimulator", "RoomSimulator", "ThermalSimulator", "Simulator", "Room"):
                maker = getattr(self.module, name, None)
                if callable(maker):
                    candidates.append(maker)
            for _, maker in vars(self.module).items():
                if inspect.isclass(maker) and getattr(maker, "__module__", None) == self.module.__name__ and maker not in candidates:
                    candidates.append(maker)
        errors = []
        for maker in candidates:
            for args in ((self.config,), (self.config_path,), ()):
                try:
                    return maker(*args)
                except Exception as exc:
                    errors.append(type(exc).__name__ + ": " + str(exc))
            if isinstance(self.config, dict):
                try:
                    return maker(**self.config)
                except Exception as exc:
                    errors.append(type(exc).__name__ + ": " + str(exc))
        # Permit a deliberately module-level teaching simulator as well.
        if any(callable(getattr(self.module, name, None)) for name in ("step", "update", "run_step", "advance", "simulate_step")):
            initializer = getattr(self.module, "initialize", None) or getattr(self.module, "reset", None)
            if callable(initializer):
                for args in ((self.config,), (self.config_path,), ()):
                    try:
                        initializer(*args)
                        break
                    except TypeError:
                        continue
            return self.module
        detail = " | ".join(errors[-5:])
        raise RuntimeError("could not construct supplied simulator" + (": " + detail if detail else ""))

    def _method(self, names):
        for name in names:
            fn = getattr(self.obj, name, None)
            if callable(fn):
                return fn
        return None

    def temperature(self):
        names = [self.adapter["temperature_method"]] if self.adapter.get("temperature_method") else [
            "get_temperature", "read_temperature", "get_temp", "measure_temperature", "current_temperature"
        ]
        fn = self._method(names)
        if fn is not None:
            answer = extract_temperature(fn())
            if answer is not None:
                return answer
        names = [self.adapter["temperature_attr"]] if self.adapter.get("temperature_attr") else [
            "temperature", "current_temperature", "room_temperature", "room_temp", "indoor_temperature", "temp", "T"
        ]
        for name in names:
            answer = extract_temperature(getattr(self.obj, name, None))
            if answer is not None:
                return answer
        answer = extract_temperature(getattr(self.obj, "state", None))
        if answer is not None:
            return answer
        raise RuntimeError("cannot read temperature; provide adapter.temperature_method or temperature_attr")

    @staticmethod
    def _parameters(fn):
        try:
            return [p for p in inspect.signature(fn).parameters.values()
                    if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
        except (ValueError, TypeError):
            return []

    def _call_setter(self, setter, power):
        params = self._parameters(setter)
        if not params:
            return setter(power)
        try:
            return setter(power)
        except TypeError:
            names = {"heater_power", "power", "heater", "input_power", "command", "value", "percent", "heater_percent", "heater_power_percent"}
            for p in params:
                if p.name.lower() in names:
                    return setter(**{p.name: power})
            raise

    def step(self, power):
        power = min(100.0, max(0.0, float(power)))
        step_names = [self.adapter["step_method"]] if self.adapter.get("step_method") else [
            "step", "simulate_step", "run_step", "advance", "update", "advance_time"
        ]
        fn = self._method(step_names)
        setter_names = [self.adapter["heater_setter"]] if self.adapter.get("heater_setter") else [
            "set_heater_power", "set_power", "set_heater", "apply_heater_power", "set_input", "set_control"
        ]
        setter = self._method(setter_names)
        if fn is None:
            raise RuntimeError("cannot find a simulator step method; provide adapter.step_method")

        params = self._parameters(fn)
        names = [p.name.lower() for p in params]
        power_names = {"heater_power", "power", "heater", "input_power", "control", "action", "u", "command", "heater_percent", "heater_power_percent"}
        time_names = {"dt", "time_step", "timestep", "delta_t", "duration", "seconds"}
        has_power = any(name in power_names for name in names)

        # APIs such as set_heater_power(power); update(dt) must set the command
        # before advancing.  This also avoids mistaking update(dt) for update(power).
        if setter is not None and not has_power:
            self._call_setter(setter, power)
            kwargs = {p.name: self.dt for p in params if p.name.lower() in time_names}
            required_unknown = [p for p in params if p.default is inspect.Parameter.empty and p.name not in kwargs]
            result = fn(*([self.dt] if required_unknown else []), **kwargs)
        else:
            kwargs = {}
            for p in params:
                if p.name.lower() in power_names:
                    kwargs[p.name] = power
                elif p.name.lower() in time_names:
                    kwargs[p.name] = self.dt
            if kwargs:
                result = fn(**kwargs)
            else:
                # Conventional unknown positional API is step(power[, dt]).
                required = [p for p in params if p.default is inspect.Parameter.empty]
                args = [power]
                if len(required) >= 2:
                    args.append(self.dt)
                result = fn(*args)
        answer = extract_temperature(result)
        return self.temperature() if answer is None else answer


def solve_3x3(matrix, rhs):
    augmented = [list(row) + [value] for row, value in zip(matrix, rhs)]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("singular regression")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(3):
            if row != column:
                scale = augmented[row][column]
                augmented[row] = [value - scale * pivot_value for value, pivot_value in zip(augmented[row], augmented[column])]
    return [augmented[i][3] for i in range(3)]


def identify(rows, dt):
    x = [[row["temperature"], row["heater_power"], 1.0] for row in rows[:-1]]
    y = [row["temperature"] for row in rows[1:]]
    normal = [[sum(row[i] * row[j] for row in x) for j in range(3)] for i in range(3)]
    rhs = [sum(row[i] * target for row, target in zip(x, y)) for i in range(3)]
    try:
        a, b, c = solve_3x3(normal, rhs)
    except ValueError:
        a, b, c = 0.98, 0.001, 0.0
    predicted = [a * row[0] + b * row[1] + c for row in x]
    sse = sum((actual - estimate) ** 2 for actual, estimate in zip(y, predicted))
    mean = sum(y) / len(y)
    sst = sum((actual - mean) ** 2 for actual in y)
    r_squared = 0.0 if sst <= 1e-12 else max(0.0, min(1.0, 1.0 - sse / sst))
    rmse = math.sqrt(sse / len(y))
    stable_a = min(0.9995, max(0.001, a))
    gain = b / (1.0 - stable_a)
    if not is_num(gain) or gain <= 1e-6:
        off = [r["temperature"] for r in rows if r["heater_power"] <= 0.0]
        on = [r for r in rows if r["heater_power"] > 1.0]
        if off and on:
            gain = max(0.0001, (max(r["temperature"] for r in on) - min(off)) / max(1.0, sum(r["heater_power"] for r in on) / len(on)))
        else:
            gain = 0.01
    ambient = c / (1.0 - stable_a)
    if not is_num(ambient):
        ambient = rows[0]["temperature"]
    return {
        "K": float(gain), "tau": float(max(0.1, -dt / math.log(stable_a))),
        "r_squared": float(r_squared), "fitting_error": float(rmse), "ambient": float(ambient)
    }


def calculate_metrics(rows, setpoint):
    times = [row["time"] for row in rows]
    temperatures = [row["temperature"] for row in rows]
    initial, difference = temperatures[0], setpoint - temperatures[0]
    level = initial + 0.9 * difference
    rise = next((time - times[0] for time, temp in zip(times, temperatures)
                 if (difference >= 0 and temp >= level) or (difference < 0 and temp <= level)), times[-1] - times[0])
    settling = next((times[i] - times[0] for i in range(len(temperatures))
                     if all(abs(temp - setpoint) < 0.5 for temp in temperatures[i:])), times[-1] - times[0])
    tail_count = max(3, int(math.ceil(len(temperatures) * 0.2)))
    maximum = max(temperatures)
    return {
        "rise_time": float(rise),
        "overshoot": float(max(0.0, (maximum - setpoint) / setpoint)),
        "settling_time": float(settling),
        "steady_state_error": float(sum(abs(temp - setpoint) for temp in temperatures[-tail_count:]) / tail_count),
        "max_temp": float(maximum),
    }


def gains_for(params, speed_factor):
    lam = max(3.0, min(60.0, params["tau"] / 3.0 * speed_factor))
    kp = params["tau"] / (max(params["K"], 0.0001) * lam)
    kp = max(0.0001, min(250.0, kp))
    return {"Kp": float(kp), "Ki": float(max(0.000001, min(25.0, kp / max(params["tau"], 0.1)))), "Kd": 0.0, "lambda": float(lam)}


def control_run(module, config, config_path, adapter, dt, duration, setpoint, params, gains):
    plant = Plant(module, config, config_path, dt, adapter)
    feedforward = min(90.0, max(0.0, (setpoint - params["ambient"]) / max(params["K"], 0.0001)))
    integral, time, rows = 0.0, 0.0, []
    count = int(math.ceil(duration / dt)) + 1
    for _ in range(count):
        temperature = as_float(plant.temperature(), "control temperature")
        error = setpoint - temperature
        proposed_integral = max(-1000.0, min(1000.0, integral + error * dt))
        raw = feedforward + gains["Kp"] * error + gains["Ki"] * proposed_integral
        command = min(100.0, max(0.0, raw))
        # Conditional integration allows recovery away from either saturation.
        if abs(raw - command) < 1e-12 or (command <= 0.0 and error > 0.0) or (command >= 100.0 and error < 0.0):
            integral = proposed_integral
        rows.append({"time": float(time), "temperature": temperature, "setpoint": float(setpoint),
                     "heater_power": float(command), "error": float(setpoint - temperature)})
        plant.step(command)
        time += dt
    return rows


def meets_targets(metrics):
    return (metrics["steady_state_error"] < 0.5 and metrics["settling_time"] < 120.0 and
            metrics["overshoot"] < 0.10 and metrics["max_temp"] < 30.0)


def score(metrics):
    return (max(0.0, metrics["steady_state_error"] - 0.35) * 1000.0 +
            max(0.0, metrics["settling_time"] - 100.0) * 10.0 +
            max(0.0, metrics["overshoot"] - 0.07) * 1000.0 +
            max(0.0, metrics["max_temp"] - 28.0) * 100.0)


def main(request):
    config_path = request.get("room_config_path", "/root/room_config.json")
    simulator_path = request.get("simulator_path", "/root/hvac_simulator.py")
    output_dir = Path(request.get("output_dir", "/root"))
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    dt = float(request.get("sample_dt", configured_dt(config) or 0.5))
    if not is_num(dt) or dt <= 0:
        raise RuntimeError("sample_dt must be positive")
    setpoint = float(request.get("setpoint", 22.0))
    duration = max(150.0, float(request.get("control_duration_s", 240.0)))
    calibration_power = min(100.0, max(2.0, float(request.get("calibration_power", 50.0))))
    adapter = request.get("adapter", {})
    if not isinstance(adapter, dict):
        raise RuntimeError("adapter must be an object")
    module = import_simulator(simulator_path)

    calibration_plant = Plant(module, config, config_path, dt, adapter)
    calibration, time = [], 0.0
    count = int(math.ceil(70.0 / dt)) + 1
    baseline_end = int(math.ceil(5.0 / dt))
    step_end = int(math.ceil(55.0 / dt))
    for index in range(count):
        command = 0.0 if index < baseline_end or index >= step_end else calibration_power
        calibration.append({"time": float(time), "temperature": as_float(calibration_plant.temperature(), "calibration temperature"), "heater_power": float(command)})
        calibration_plant.step(command)
        time += dt
    params = identify(calibration, dt)

    # Retain the safest successful model-derived response, or the best observed
    # candidate if the physical configuration cannot meet the requested targets.
    selected_rows = selected_gains = selected_metrics = None
    for factor in (0.50, 0.75, 1.0, 1.5, 2.0):
        gains = gains_for(params, factor)
        rows = control_run(module, config, config_path, adapter, dt, duration, setpoint, params, gains)
        observed = calculate_metrics(rows, setpoint)
        if selected_metrics is None or score(observed) < score(selected_metrics):
            selected_rows, selected_gains, selected_metrics = rows, gains, observed
        if meets_targets(observed):
            selected_rows, selected_gains, selected_metrics = rows, gains, observed
            break

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "calibration_log.json", {"phase": "calibration", "heater_power_test": calibration_power, "data": calibration})
    write_json(output_dir / "estimated_params.json", {key: params[key] for key in ("K", "tau", "r_squared", "fitting_error")})
    write_json(output_dir / "tuned_gains.json", selected_gains)
    write_json(output_dir / "control_log.json", {"phase": "control", "setpoint": setpoint, "data": selected_rows})
    write_json(output_dir / "metrics.json", selected_metrics)
    return {"ok": True, "targets_met": meets_targets(selected_metrics),
            "files": ["calibration_log.json", "estimated_params.json", "tuned_gains.json", "control_log.json", "metrics.json"],
            "metrics": selected_metrics}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, allow_nan=False))
        raise
