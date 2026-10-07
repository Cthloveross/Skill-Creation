#!/usr/bin/env python3
"""Generate HVAC calibration, identification, control, and metrics artifacts.

Reads one JSON object from stdin and writes JSON artifacts to output_dir.  The
script uses only the Python standard library and never changes the supplied
simulator or room configuration.
"""
import importlib.util
import inspect
import json
import math
import sys
from pathlib import Path


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def number(x, name):
    if not finite(x):
        raise RuntimeError(name + " must be a finite number")
    return float(x)


def clamp(x, lo, hi):
    return max(lo, min(hi, float(x)))


def save(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, allow_nan=False)
        handle.write("\n")


def extract_temperature(value):
    if finite(value):
        return float(value)
    if isinstance(value, dict):
        for key in ("temperature", "temp", "room_temperature", "current_temperature", "T"):
            if finite(value.get(key)):
                return float(value[key])
        for item in value.values():
            found = extract_temperature(item)
            if found is not None:
                return found
    if isinstance(value, (list, tuple)):
        for item in value:
            found = extract_temperature(item)
            if found is not None:
                return found
    return None


def find_dt(value):
    if isinstance(value, dict):
        for key in ("dt", "time_step", "timestep", "sample_dt", "sample_interval"):
            if finite(value.get(key)) and float(value[key]) > 0:
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
    spec = importlib.util.spec_from_file_location("task_hvac_simulator", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load supplied simulator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Plant:
    """Small adapter for common educational room-heating simulator APIs."""
    readers = ("get_temperature", "read_temperature", "measure_temperature",
               "get_current_temperature", "get_temp", "observe", "get_state")
    attributes = ("temperature", "current_temperature", "room_temperature",
                  "room_temp", "indoor_temperature", "temp", "T", "state")
    setters = ("set_heater_power", "set_heater", "set_power", "apply_heater_power",
               "set_input", "set_control", "set_heater_percent")
    steppers = ("step", "update", "advance", "simulate_step", "run_step",
                "advance_time", "update_temperature")
    power_names = {"power", "heater_power", "heater", "heater_level", "input_power",
                   "control", "action", "u", "command", "heater_percent",
                   "power_percent", "heater_power_percent"}
    time_names = {"dt", "time_step", "timestep", "delta_t", "duration", "seconds"}

    def __init__(self, module, config, config_path, dt, adapter):
        self.module = module
        self.config = config
        self.config_path = str(config_path)
        self.dt = dt
        self.adapter = adapter
        self.obj = self._construct()

    def _construct(self):
        requested = self.adapter.get("class")
        constructors = []
        if requested:
            candidate = getattr(self.module, requested, None)
            if not callable(candidate):
                raise RuntimeError("configured adapter class was not found")
            constructors = [candidate]
        else:
            for name in ("HVACSimulator", "RoomSimulator", "ThermalSimulator",
                         "HeatingSimulator", "RoomHeatingSimulator", "Simulator",
                         "create_simulator", "make_simulator"):
                candidate = getattr(self.module, name, None)
                if callable(candidate) and candidate not in constructors:
                    constructors.append(candidate)
            for name, candidate in vars(self.module).items():
                lower = name.lower()
                if (inspect.isclass(candidate) and candidate.__module__ == self.module.__name__
                        and any(word in lower for word in ("hvac", "room", "thermal", "heating", "simulator"))
                        and candidate not in constructors):
                    constructors.append(candidate)
        errors = []
        for maker in constructors:
            for args, kwargs in (((self.config,), {}), ((self.config_path,), {}),
                                 ((), {"config": self.config}),
                                 ((), {"config_path": self.config_path}), ((), {})):
                try:
                    return maker(*args, **kwargs)
                except Exception as exc:
                    errors.append(type(exc).__name__ + ": " + str(exc))
        raise RuntimeError("could not construct HVAC simulator" +
                           (": " + "; ".join(errors[-2:]) if errors else ""))

    @staticmethod
    def params(fn):
        try:
            return [p for p in inspect.signature(fn).parameters.values()
                    if p.kind not in (inspect.Parameter.VAR_POSITIONAL,
                                      inspect.Parameter.VAR_KEYWORD)]
        except (TypeError, ValueError):
            return []

    def method(self, names):
        for name in names:
            candidate = getattr(self.obj, name, None)
            if callable(candidate):
                return candidate
        return None

    def temperature(self):
        requested = self.adapter.get("temperature_method")
        reader = self.method((requested,) if requested else self.readers)
        if reader is not None:
            try:
                answer = extract_temperature(reader())
                if answer is not None:
                    return answer
            except TypeError:
                pass
        requested = self.adapter.get("temperature_attr")
        names = (requested,) if requested else self.attributes
        for name in names:
            answer = extract_temperature(getattr(self.obj, name, None))
            if answer is not None:
                return answer
        raise RuntimeError("unable to read simulator temperature")

    def advance(self, command):
        command = clamp(command, 0.0, 100.0)
        requested = self.adapter.get("step_method")
        step = self.method((requested,) if requested else self.steppers)
        if step is None:
            raise RuntimeError("unable to find simulator step method")
        requested = self.adapter.get("heater_setter")
        setter = self.method((requested,) if requested else self.setters)
        parameters = self.params(step)
        direct_power = any(p.name.lower() in self.power_names for p in parameters)
        if setter is not None and not direct_power:
            try:
                setter(command)
            except TypeError:
                setter(**{self.params(setter)[0].name: command})
        elif setter is None and not direct_power:
            for attr in ("heater_power", "power", "heater", "input_power", "command"):
                if hasattr(self.obj, attr):
                    setattr(self.obj, attr, command)
                    break
        kwargs = {}
        for p in parameters:
            if p.name.lower() in self.power_names:
                kwargs[p.name] = command
            elif p.name.lower() in self.time_names:
                kwargs[p.name] = self.dt
        try:
            if kwargs:
                result = step(**kwargs)
            elif not parameters:
                result = step()
            elif len(parameters) == 1:
                # A setter-based API generally has step(dt); a direct-input API
                # with an unrecognised parameter generally has step(power).
                result = step(self.dt if setter is not None else command)
            else:
                result = step(command, self.dt)
        except TypeError as exc:
            raise RuntimeError("unsupported simulator step signature: " + str(exc))
        observed = extract_temperature(result)
        return self.temperature() if observed is None else observed


def solve3(matrix, rhs):
    work = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda row: abs(work[row][col]))
        if abs(work[pivot][col]) < 1e-12:
            raise RuntimeError("calibration regression is singular")
        work[col], work[pivot] = work[pivot], work[col]
        divisor = work[col][col]
        work[col] = [x / divisor for x in work[col]]
        for row in range(3):
            if row != col:
                scale = work[row][col]
                work[row] = [x - scale * base for x, base in zip(work[row], work[col])]
    return [work[i][3] for i in range(3)]


def identify(rows, dt):
    x = [[row["temperature"], row["heater_power"], 1.0] for row in rows[:-1]]
    y = [row["temperature"] for row in rows[1:]]
    normal = [[sum(row[i] * row[j] for row in x) for j in range(3)] for i in range(3)]
    rhs = [sum(row[i] * target for row, target in zip(x, y)) for i in range(3)]
    a, b, c = solve3(normal, rhs)
    a = clamp(a, 0.001, 0.9995)
    k = b / (1.0 - a)
    if not finite(k) or k <= 0:
        raise RuntimeError("calibration did not identify a positive heater gain")
    prediction = [a * old[0] + b * old[1] + c for old in x]
    sse = sum((actual - fitted) ** 2 for actual, fitted in zip(y, prediction))
    mean = sum(y) / len(y)
    sst = sum((actual - mean) ** 2 for actual in y)
    return {
        "K": float(k),
        "tau": float(-dt / math.log(a)),
        "r_squared": float(clamp(1.0 - sse / sst, 0.0, 1.0) if sst > 1e-12 else 0.0),
        "fitting_error": float(math.sqrt(sse / len(y))),
        "ambient": float(c / (1.0 - a)),
    }


def make_gains(model, factor):
    lam = clamp(model["tau"] * factor, 1.0, 160.0)
    kp = clamp(model["tau"] / (model["K"] * lam), 1e-6, 250.0)
    return {"Kp": float(kp), "Ki": float(clamp(kp / model["tau"], 1e-8, 20.0)),
            "Kd": 0.0, "lambda": float(lam)}


def run_control(module, config, config_path, adapter, dt, duration, setpoint, model, gains):
    plant = Plant(module, config, config_path, dt, adapter)
    feedforward = clamp((setpoint - model["ambient"]) / model["K"], 0.0, 95.0)
    integral = 0.0
    rows = []
    now = 0.0
    for _ in range(int(math.ceil(duration / dt)) + 1):
        temp = number(plant.temperature(), "control temperature")
        error = setpoint - temp
        proposed_integral = clamp(integral + error * dt, -400.0, 400.0)
        raw = feedforward + gains["Kp"] * error + gains["Ki"] * proposed_integral
        command = clamp(raw, 0.0, 100.0)
        if abs(raw - command) < 1e-12 or (command == 0.0 and error > 0.0) or (command == 100.0 and error < 0.0):
            integral = proposed_integral
        rows.append({"time": float(now), "temperature": float(temp), "setpoint": float(setpoint),
                     "heater_power": float(command), "error": float(setpoint - temp)})
        plant.advance(command)
        now += dt
    return rows


def metrics_for(rows, setpoint):
    times = [row["time"] for row in rows]
    temps = [row["temperature"] for row in rows]
    threshold = temps[0] + 0.9 * (setpoint - temps[0])
    rise = next((i for i, temp in enumerate(temps) if temp >= threshold), len(rows) - 1)
    settle = next((i for i in range(len(rows)) if all(abs(temp - setpoint) < 0.5 for temp in temps[i:])), len(rows) - 1)
    tail = max(3, int(math.ceil(0.2 * len(rows))))
    maximum = max(temps)
    return {"rise_time": float(times[rise] - times[0]),
            "overshoot": float(max(0.0, (maximum - setpoint) / setpoint)),
            "settling_time": float(times[settle] - times[0]),
            "steady_state_error": float(sum(abs(t - setpoint) for t in temps[-tail:]) / tail),
            "max_temp": float(maximum)}


def target_ok(m):
    return (m["steady_state_error"] < 0.5 and m["settling_time"] < 120.0 and
            m["overshoot"] < 0.10 and m["max_temp"] < 30.0)


def candidate_score(m):
    return (100000.0 * max(0.0, m["steady_state_error"] - 0.35) +
            2000.0 * max(0.0, m["settling_time"] - 105.0) +
            100000.0 * max(0.0, m["overshoot"] - 0.06) +
            20000.0 * max(0.0, m["max_temp"] - 27.0) + m["settling_time"] * 0.01)


def validate(calibration, model, gains, trace, measured, setpoint):
    if len(calibration) < 20 or calibration[-1]["time"] - calibration[0]["time"] < 30.0:
        raise RuntimeError("calibration lacks required coverage")
    if max(r["heater_power"] for r in calibration) - min(r["heater_power"] for r in calibration) <= 1.0:
        raise RuntimeError("calibration lacks heater excitation")
    if max(r["temperature"] for r in calibration) - min(r["temperature"] for r in calibration) <= 0.05:
        raise RuntimeError("calibration lacks measurable response")
    if model["K"] <= 0 or model["tau"] <= 0 or not 0 <= model["r_squared"] <= 1 or model["fitting_error"] < 0:
        raise RuntimeError("identified parameters are invalid")
    if any(not finite(gains[key]) or gains[key] < 0 for key in ("Kp", "Ki", "Kd")) or gains["lambda"] <= 0:
        raise RuntimeError("controller gains are invalid")
    last = None
    for row in trace:
        if any(not finite(row[k]) for k in ("time", "temperature", "setpoint", "heater_power", "error")):
            raise RuntimeError("control trace has non-finite values")
        if last is not None and row["time"] <= last:
            raise RuntimeError("control time is not strictly ordered")
        last = row["time"]
        if not 0 <= row["heater_power"] <= 100 or abs(row["setpoint"] - setpoint) > 1e-9:
            raise RuntimeError("control trace violates command or setpoint contract")
        if abs(row["error"] - (setpoint - row["temperature"])) > 1e-8:
            raise RuntimeError("control error is inconsistent")
    if trace[-1]["time"] - trace[0]["time"] < 150.0:
        raise RuntimeError("control trace is too short")
    recomputed = metrics_for(trace, setpoint)
    if any(abs(recomputed[key] - measured[key]) > 1e-9 for key in recomputed):
        raise RuntimeError("metrics were not derived from final trace")
    if not target_ok(measured):
        raise RuntimeError("tested controller candidates did not meet requested targets")


def request_from_stdin():
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("stdin must be a JSON object")
    return value


def main(req):
    sim_path = Path(req.get("simulator_path", "/root/hvac_simulator.py"))
    config_path = Path(req.get("room_config_path", "/root/room_config.json"))
    output_dir = Path(req.get("output_dir", "/root"))
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise RuntimeError("room configuration must be a JSON object")
    dt = number(req.get("sample_dt", find_dt(config) or 0.5), "sample_dt")
    if dt <= 0:
        raise RuntimeError("sample_dt must be positive")
    setpoint = number(req.get("setpoint", 22.0), "setpoint")
    duration = max(150.0, number(req.get("control_duration_s", 180.0), "control_duration_s"))
    test_power = clamp(number(req.get("calibration_power", 50.0), "calibration_power"), 5.0, 100.0)
    adapter = req.get("adapter", {})
    if not isinstance(adapter, dict):
        raise RuntimeError("adapter must be a JSON object")
    output_dir.mkdir(parents=True, exist_ok=True)
    module = load_module(sim_path)

    # Fresh calibration: 5 s baseline, 50 s heater step, then cooldown.
    calibration_plant = Plant(module, config, config_path, dt, adapter)
    calibration = []
    now = 0.0
    sample_count = int(math.ceil(70.0 / dt)) + 1
    baseline_end = int(math.ceil(5.0 / dt))
    heat_end = int(math.ceil(55.0 / dt))
    for index in range(sample_count):
        command = test_power if baseline_end <= index < heat_end else 0.0
        calibration.append({"time": float(now),
                            "temperature": number(calibration_plant.temperature(), "calibration temperature"),
                            "heater_power": float(command)})
        calibration_plant.advance(command)
        now += dt
    model = identify(calibration, dt)

    # Write completed calibration products before executing control trials so a
    # later simulator failure cannot erase completed experimental evidence.
    save(output_dir / "calibration_log.json", {"phase": "calibration", "heater_power_test": test_power,
                                                "data": calibration})
    save(output_dir / "estimated_params.json", {key: model[key]
                                                  for key in ("K", "tau", "r_squared", "fitting_error")})

    best = None
    # Two measured candidates balance robustness with completion time. Both are
    # model-derived and each uses an isolated, fresh simulator instance.
    for factor in (0.5, 1.0):
        gains = make_gains(model, factor)
        trace = run_control(module, config, config_path, adapter, dt, duration, setpoint, model, gains)
        measured = metrics_for(trace, setpoint)
        candidate = (candidate_score(measured), gains, trace, measured)
        if best is None or candidate[0] < best[0]:
            best = candidate
    _, gains, trace, measured = best

    # Save the actual chosen trial before final reopening-style validation.
    save(output_dir / "tuned_gains.json", gains)
    save(output_dir / "control_log.json", {"phase": "control", "setpoint": setpoint, "data": trace})
    save(output_dir / "metrics.json", measured)
    validate(calibration, model, gains, trace, measured, setpoint)
    return {"ok": True, "targets_met": True,
            "files": ["calibration_log.json", "estimated_params.json", "tuned_gains.json",
                      "control_log.json", "metrics.json"], "metrics": measured}


if __name__ == "__main__":
    try:
        print(json.dumps(main(request_from_stdin()), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, allow_nan=False))
        sys.exit(1)
