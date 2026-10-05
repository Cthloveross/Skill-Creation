#!/usr/bin/env python3
"""Create HVAC calibration, identification, tuning, and control artifacts.

Input: optional JSON object on stdin. Output: JSON status object on stdout.
The requested artifacts are written under output_dir (default /root).
"""
import importlib.util
import inspect
import json
import math
import sys
from pathlib import Path


def isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def number(v, label):
    if not isnum(v):
        raise RuntimeError(label + " is not a finite number")
    return float(v)


def clip(v, lo, hi):
    return max(lo, min(hi, float(v)))


def dump(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, allow_nan=False)
        handle.write("\n")


def extract_temperature(value):
    if isnum(value):
        return float(value)
    if isinstance(value, dict):
        for key in ("temperature", "temp", "room_temperature", "current_temperature",
                    "indoor_temperature", "room_temp", "T"):
            if isnum(value.get(key)):
                return float(value[key])
        for nested in value.values():
            if isinstance(nested, dict):
                result = extract_temperature(nested)
                if result is not None:
                    return result
    if isinstance(value, (tuple, list)) and value and isnum(value[0]):
        return float(value[0])
    return None


def find_dt(value):
    if isinstance(value, dict):
        for key in ("sample_dt", "time_step", "timestep", "dt", "sample_interval"):
            if isnum(value.get(key)) and float(value[key]) > 0:
                return float(value[key])
        for child in value.values():
            ans = find_dt(child)
            if ans:
                return ans
    if isinstance(value, list):
        for child in value:
            ans = find_dt(child)
            if ans:
                return ans
    return None


def load_module(path):
    spec = importlib.util.spec_from_file_location("supplied_hvac_simulator", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load simulator_path")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Plant:
    """Runtime adapter for common small educational HVAC simulator interfaces."""

    TEMP_METHODS = ("get_temperature", "read_temperature", "measure_temperature",
                    "get_current_temperature", "get_temp", "observe", "get_state")
    TEMP_ATTRS = ("temperature", "current_temperature", "room_temperature",
                  "room_temp", "indoor_temperature", "temp", "T", "state")
    SETTERS = ("set_heater_power", "set_heater", "set_power", "apply_heater_power",
               "set_input", "set_control", "set_heater_percent")
    STEPPERS = ("step", "update", "advance", "simulate_step", "run_step",
                "advance_time", "update_temperature")
    POWER_NAMES = {"power", "heater_power", "heater", "heater_level", "input_power",
                   "control", "action", "u", "command", "heater_percent",
                   "power_percent", "heater_power_percent"}
    TIME_NAMES = {"dt", "time_step", "timestep", "delta_t", "duration", "seconds"}

    def __init__(self, module, config, config_path, dt, adapter):
        self.module, self.config, self.config_path, self.dt = module, config, str(config_path), dt
        self.adapter = adapter
        self.obj = self._new_object()

    def _new_object(self):
        requested = self.adapter.get("class")
        choices = []
        if requested:
            candidate = getattr(self.module, requested, None)
            if not callable(candidate):
                raise RuntimeError("adapter class was not found")
            choices = [candidate]
        else:
            preferred = ("HVACSimulator", "RoomSimulator", "ThermalSimulator",
                         "HeatingSimulator", "RoomHeatingSimulator", "Simulator",
                         "create_simulator", "make_simulator")
            for name in preferred:
                candidate = getattr(self.module, name, None)
                if callable(candidate):
                    choices.append(candidate)
            # Include only clearly simulator-related classes; do not accidentally
            # instantiate PID/helper classes merely because they are public.
            for name, candidate in vars(self.module).items():
                low = name.lower()
                if (inspect.isclass(candidate) and candidate.__module__ == self.module.__name__
                        and any(word in low for word in ("simulator", "thermal", "room", "hvac"))
                        and candidate not in choices):
                    choices.append(candidate)
        errors = []
        for maker in choices:
            for args, kwargs in (((self.config_path,), {}), ((self.config,), {}),
                                 ((), {"config": self.config}), ((), {"config_path": self.config_path}),
                                 ((), {})):
                try:
                    return maker(*args, **kwargs)
                except Exception as exc:
                    errors.append(type(exc).__name__ + ": " + str(exc))
        # A module can itself implement stateful initialize/read/step functions.
        if any(callable(getattr(self.module, name, None)) for name in self.STEPPERS):
            reset = getattr(self.module, "initialize", None) or getattr(self.module, "reset", None)
            if callable(reset):
                initialized = False
                for args in ((self.config_path,), (self.config,), ()):
                    try:
                        reset(*args)
                        initialized = True
                        break
                    except TypeError:
                        pass
                if not initialized:
                    raise RuntimeError("unable to initialize module-level simulator")
            return self.module
        tail = "; ".join(errors[-3:])
        raise RuntimeError("could not construct a simulator instance" + (": " + tail if tail else ""))

    @staticmethod
    def params(fn):
        try:
            return [p for p in inspect.signature(fn).parameters.values()
                    if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
        except (ValueError, TypeError):
            return []

    def callable_named(self, names):
        for name in names:
            if not name:
                continue
            candidate = getattr(self.obj, name, None)
            if callable(candidate):
                return candidate
        return None

    def temperature(self):
        configured = self.adapter.get("temperature_method")
        fn = self.callable_named((configured,) if configured else self.TEMP_METHODS)
        if fn:
            try:
                result = extract_temperature(fn())
                if result is not None:
                    return result
            except TypeError:
                pass
        configured = self.adapter.get("temperature_attr")
        names = (configured,) if configured else self.TEMP_ATTRS
        for name in names:
            result = extract_temperature(getattr(self.obj, name, None))
            if result is not None:
                return result
        raise RuntimeError("unable to read temperature from simulator")

    def advance(self, command):
        command = clip(command, 0.0, 100.0)
        configured = self.adapter.get("step_method")
        step = self.callable_named((configured,) if configured else self.STEPPERS)
        if step is None:
            raise RuntimeError("unable to find simulator step method")
        configured = self.adapter.get("heater_setter")
        setter = self.callable_named((configured,) if configured else self.SETTERS)
        parameters = self.params(step)
        direct_power = any(p.name.lower() in self.POWER_NAMES for p in parameters)
        if setter is not None and not direct_power:
            sp = self.params(setter)
            try:
                if sp:
                    setter(**{sp[0].name: command})
                else:
                    setter(command)
            except TypeError:
                setter(command)
        elif setter is None and not direct_power:
            for attr in ("heater_power", "power", "heater", "input_power", "command"):
                if hasattr(self.obj, attr):
                    setattr(self.obj, attr, command)
                    break
        kwargs = {}
        for p in parameters:
            low = p.name.lower()
            if low in self.POWER_NAMES:
                kwargs[p.name] = command
            elif low in self.TIME_NAMES:
                kwargs[p.name] = self.dt
        try:
            if kwargs:
                returned = step(**kwargs)
            elif not parameters:
                returned = step()
            elif len(parameters) == 1:
                # An otherwise unnamed one-argument step convention is normally dt
                # when a setter was used, and power when no setter exists.
                returned = step(self.dt if setter is not None else command)
            else:
                returned = step(command, self.dt)
        except TypeError as exc:
            raise RuntimeError("unsupported simulator step signature: " + str(exc))
        observed = extract_temperature(returned)
        return self.temperature() if observed is None else observed


def solve3(matrix, rhs):
    work = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda row: abs(work[row][col]))
        if abs(work[pivot][col]) < 1e-10:
            raise ValueError("singular normal matrix")
        work[col], work[pivot] = work[pivot], work[col]
        scale = work[col][col]
        work[col] = [x / scale for x in work[col]]
        for row in range(3):
            if row != col:
                scale = work[row][col]
                work[row] = [x - scale * y for x, y in zip(work[row], work[col])]
    return [work[i][3] for i in range(3)]


def identify(rows, dt):
    x = [[r["temperature"], r["heater_power"], 1.0] for r in rows[:-1]]
    y = [r["temperature"] for r in rows[1:]]
    normal = [[sum(row[i] * row[j] for row in x) for j in range(3)] for i in range(3)]
    rhs = [sum(row[i] * target for row, target in zip(x, y)) for i in range(3)]
    try:
        a, b, c = solve3(normal, rhs)
    except ValueError:
        # A valid fallback still derives scale from the observed excited response.
        a, b, c = 0.98, 0.0, rows[0]["temperature"] * 0.02
    predicted = [a * row[0] + b * row[1] + c for row in x]
    sse = sum((actual - estimate) ** 2 for actual, estimate in zip(y, predicted))
    mean = sum(y) / len(y)
    sst = sum((actual - mean) ** 2 for actual in y)
    r2 = clip(1.0 - sse / sst, 0.0, 1.0) if sst > 1e-12 else 0.0
    stable_a = clip(a, 0.001, 0.9995)
    gain = b / (1.0 - stable_a)
    if not isnum(gain) or gain <= 1e-6:
        baseline = sum(r["temperature"] for r in rows[:max(1, len(rows)//16)]) / max(1, len(rows)//16)
        excited = max(r["temperature"] for r in rows if r["heater_power"] > 1.0)
        peak_power = max(r["heater_power"] for r in rows)
        gain = max(1e-4, (excited - baseline) / max(peak_power, 1.0))
    ambient = c / (1.0 - stable_a)
    if not isnum(ambient):
        ambient = rows[0]["temperature"]
    return {"K": float(gain), "tau": float(max(0.1, -dt / math.log(stable_a))),
            "r_squared": float(r2), "fitting_error": float(math.sqrt(sse / len(y))),
            "ambient": float(ambient)}


def gains_for(model, factor):
    lam = clip(model["tau"] * factor, 1.5, 100.0)
    kp = clip(model["tau"] / (max(model["K"], 1e-4) * lam), 1e-5, 250.0)
    return {"Kp": float(kp), "Ki": float(clip(kp / max(model["tau"], 0.1), 1e-7, 20.0)),
            "Kd": 0.0, "lambda": float(lam)}


def run_control(module, config, config_path, adapter, dt, duration, setpoint, model, gains):
    plant = Plant(module, config, config_path, dt, adapter)
    feedforward = clip((setpoint - model["ambient"]) / max(model["K"], 1e-4), 0.0, 95.0)
    integral, now, rows = 0.0, 0.0, []
    samples = int(math.ceil(duration / dt)) + 1
    for _ in range(samples):
        temp = number(plant.temperature(), "control temperature")
        error = setpoint - temp
        trial_i = clip(integral + error * dt, -500.0, 500.0)
        raw = feedforward + gains["Kp"] * error + gains["Ki"] * trial_i
        power = clip(raw, 0.0, 100.0)
        # Conditional integration prevents windup while saturation pushes away
        # from the direction in which the error asks the controller to move.
        if abs(raw - power) < 1e-10 or (power == 0.0 and error > 0.0) or (power == 100.0 and error < 0.0):
            integral = trial_i
        rows.append({"time": float(now), "temperature": float(temp), "setpoint": float(setpoint),
                     "heater_power": float(power), "error": float(setpoint - temp)})
        plant.advance(power)
        now += dt
    return rows


def metrics(rows, setpoint):
    times = [r["time"] for r in rows]
    temps = [r["temperature"] for r in rows]
    initial = temps[0]
    level = initial + 0.9 * (setpoint - initial)
    rise_i = next((i for i, t in enumerate(temps) if (t >= level if setpoint >= initial else t <= level)), len(rows)-1)
    settle_i = next((i for i in range(len(rows)) if all(abs(t-setpoint) < 0.5 for t in temps[i:])), len(rows)-1)
    tail = max(3, int(math.ceil(len(rows) * 0.2)))
    maximum = max(temps)
    return {"rise_time": float(times[rise_i] - times[0]),
            "overshoot": float(max(0.0, (maximum-setpoint) / setpoint)),
            "settling_time": float(times[settle_i] - times[0]),
            "steady_state_error": float(sum(abs(t-setpoint) for t in temps[-tail:]) / tail),
            "max_temp": float(maximum)}


def target_ok(m):
    return (m["steady_state_error"] < 0.5 and m["settling_time"] < 120.0
            and m["overshoot"] < 0.10 and m["max_temp"] < 30.0)


def candidate_score(m):
    return (10000 * max(0.0, m["steady_state_error"] - 0.35)
            + 150 * max(0.0, m["settling_time"] - 105.0)
            + 10000 * max(0.0, m["overshoot"] - 0.07)
            + 1000 * max(0.0, m["max_temp"] - 28.0) + 0.01 * m["settling_time"])


def validate(calibration, model, gains, trace, m, setpoint):
    if len(calibration) < 20 or calibration[-1]["time"] - calibration[0]["time"] < 30:
        raise RuntimeError("calibration coverage validation failed")
    if max(r["heater_power"] for r in calibration) - min(r["heater_power"] for r in calibration) <= 1:
        raise RuntimeError("calibration excitation validation failed")
    for doc in (model, gains, m):
        if not all(isnum(v) for v in doc.values()):
            raise RuntimeError("non-finite derived value")
    if model["K"] <= 0 or model["tau"] <= 0 or gains["lambda"] <= 0:
        raise RuntimeError("nonphysical identified/tuned value")
    previous = None
    for row in calibration + trace:
        if not all(isnum(row[k]) for k in row):
            raise RuntimeError("non-finite trace value")
        if not 0 <= row["heater_power"] <= 100:
            raise RuntimeError("unbounded heater command")
    for row in trace:
        if previous is not None and row["time"] <= previous:
            raise RuntimeError("control time is not strictly ordered")
        previous = row["time"]
        if abs(row["error"] - (row["setpoint"] - row["temperature"])) > 1e-8:
            raise RuntimeError("inconsistent logged control error")
        if abs(row["setpoint"] - setpoint) > 1e-9:
            raise RuntimeError("inconsistent setpoint")
    if trace[-1]["time"] - trace[0]["time"] < 150:
        raise RuntimeError("control duration validation failed")


def request():
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("stdin must contain a JSON object")
    return value


def main(req):
    simulator_path = req.get("simulator_path", "/root/hvac_simulator.py")
    config_path = req.get("room_config_path", "/root/room_config.json")
    outdir = Path(req.get("output_dir", "/root"))
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise RuntimeError("room configuration must be a JSON object")
    dt = number(req.get("sample_dt", find_dt(config) or 0.5), "sample_dt")
    if dt <= 0:
        raise RuntimeError("sample_dt must be positive")
    setpoint = number(req.get("setpoint", 22.0), "setpoint")
    duration = max(150.0, number(req.get("control_duration_s", 240.0), "control_duration_s"))
    power = clip(number(req.get("calibration_power", 50.0), "calibration_power"), 2.0, 100.0)
    adapter = req.get("adapter", {})
    if not isinstance(adapter, dict):
        raise RuntimeError("adapter must be an object")
    outdir.mkdir(parents=True, exist_ok=True)
    module = load_module(simulator_path)

    plant = Plant(module, config, config_path, dt, adapter)
    calibration, now = [], 0.0
    count = int(math.ceil(80.0/dt)) + 1
    baseline_end, heat_end = int(math.ceil(5.0/dt)), int(math.ceil(65.0/dt))
    for i in range(count):
        command = power if baseline_end <= i < heat_end else 0.0
        calibration.append({"time": float(now), "temperature": number(plant.temperature(), "calibration temperature"),
                            "heater_power": float(command)})
        plant.advance(command)
        now += dt
    model = identify(calibration, dt)

    selected = None
    for factor in (0.10, 0.15, 0.22, 0.32, 0.48, 0.70, 1.0, 1.5, 2.0, 3.0):
        gains = gains_for(model, factor)
        trace = run_control(module, config, config_path, adapter, dt, duration, setpoint, model, gains)
        measured = metrics(trace, setpoint)
        item = (candidate_score(measured), trace, gains, measured)
        if selected is None or item[0] < selected[0]:
            selected = item
        if target_ok(measured):
            selected = item
            break
    _, trace, gains, measured = selected
    validate(calibration, model, gains, trace, measured, setpoint)

    dump(outdir / "calibration_log.json", {"phase": "calibration", "heater_power_test": power, "data": calibration})
    dump(outdir / "estimated_params.json", {k: model[k] for k in ("K", "tau", "r_squared", "fitting_error")})
    dump(outdir / "tuned_gains.json", gains)
    dump(outdir / "control_log.json", {"phase": "control", "setpoint": setpoint, "data": trace})
    dump(outdir / "metrics.json", measured)
    return {"ok": True, "targets_met": target_ok(measured),
            "files": ["calibration_log.json", "estimated_params.json", "tuned_gains.json", "control_log.json", "metrics.json"],
            "metrics": measured}


if __name__ == "__main__":
    try:
        print(json.dumps(main(request()), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, allow_nan=False))
        sys.exit(1)
