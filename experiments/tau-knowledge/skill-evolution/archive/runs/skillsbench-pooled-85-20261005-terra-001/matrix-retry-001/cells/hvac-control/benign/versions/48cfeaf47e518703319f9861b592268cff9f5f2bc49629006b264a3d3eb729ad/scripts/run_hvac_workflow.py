#!/usr/bin/env python3
"""Runtime HVAC calibration and control artifact generator.

Input: one JSON object on stdin (see SKILL.md).
Output: one JSON status object on stdout.
The program uses only Python's standard library and does not modify task inputs.
"""
import importlib.util
import inspect
import json
import math
import sys
from pathlib import Path


def isnum(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def num(x, label):
    if not isnum(x):
        raise RuntimeError(label + " must be a finite number")
    return float(x)


def clip(x, low, high):
    return max(low, min(high, float(x)))


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")


def temperature_from(value):
    if isnum(value):
        return float(value)
    if isinstance(value, dict):
        for key in ("temperature", "temp", "room_temperature", "current_temperature", "T"):
            if isnum(value.get(key)):
                return float(value[key])
    if isinstance(value, (list, tuple)):
        for item in value:
            answer = temperature_from(item)
            if answer is not None:
                return answer
    return None


def configured_dt(value):
    if isinstance(value, dict):
        for key in ("dt", "time_step", "timestep", "sample_dt", "sample_interval"):
            if isnum(value.get(key)) and float(value[key]) > 0:
                return float(value[key])
        for item in value.values():
            answer = configured_dt(item)
            if answer is not None:
                return answer
    if isinstance(value, list):
        for item in value:
            answer = configured_dt(item)
            if answer is not None:
                return answer
    return None


def load_simulator(path):
    spec = importlib.util.spec_from_file_location("supplied_hvac_simulator", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the supplied HVAC simulator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Plant:
    """Adapter for ordinary discrete HVAC/room simulator interfaces."""
    READER_NAMES = ("get_temperature", "read_temperature", "measure_temperature",
                    "get_current_temperature", "get_temp", "observe", "get_state")
    ATTR_NAMES = ("temperature", "current_temperature", "room_temperature",
                  "room_temp", "indoor_temperature", "temp", "T", "state")
    SETTER_NAMES = ("set_heater_power", "set_heater", "set_power", "apply_heater_power",
                    "set_input", "set_control", "set_heater_percent")
    STEP_NAMES = ("step", "update", "advance", "simulate_step", "run_step",
                  "advance_time", "update_temperature")

    def __init__(self, module, config, config_path, dt, adapter):
        self.module = module
        self.config = config
        self.config_path = str(config_path)
        self.dt = dt
        self.adapter = adapter
        self.obj = self._construct()

    def _candidates(self):
        requested = self.adapter.get("class")
        if requested:
            maker = getattr(self.module, requested, None)
            if not callable(maker):
                raise RuntimeError("configured simulator class/factory is unavailable")
            return [maker]
        result = []
        preferred = ("HVACSimulator", "RoomSimulator", "ThermalSimulator",
                     "HeatingSimulator", "RoomHeatingSimulator", "Simulator",
                     "Room", "HVAC", "create_simulator", "make_simulator")
        for name in preferred:
            candidate = getattr(self.module, name, None)
            if callable(candidate) and candidate not in result:
                result.append(candidate)
        for candidate in vars(self.module).values():
            if (inspect.isclass(candidate) and candidate.__module__ == self.module.__name__
                    and candidate not in result):
                result.append(candidate)
        return result

    def _construct(self):
        errors = []
        attempts = [((self.config,), {}), ((self.config_path,), {}),
                    ((), {"config": self.config}), ((), {"config_path": self.config_path}),
                    ((), {})]
        if isinstance(self.config, dict):
            attempts.insert(4, ((), dict(self.config)))
        for maker in self._candidates():
            for args, kwargs in attempts:
                try:
                    return maker(*args, **kwargs)
                except Exception as exc:
                    errors.append(type(exc).__name__ + ": " + str(exc))
        detail = "; ".join(errors[-3:])
        raise RuntimeError("could not construct an HVAC simulator" + (": " + detail if detail else ""))

    @staticmethod
    def parameters(fn):
        try:
            return [p for p in inspect.signature(fn).parameters.values()
                    if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)]
        except (TypeError, ValueError):
            return []

    def _method(self, names):
        for name in names:
            if not name:
                continue
            fn = getattr(self.obj, name, None)
            if callable(fn):
                return fn
        return None

    def temperature(self):
        requested = self.adapter.get("temperature_method")
        reader = self._method((requested,) if requested else self.READER_NAMES)
        if reader is not None:
            try:
                answer = temperature_from(reader())
                if answer is not None:
                    return answer
            except TypeError:
                pass
        requested = self.adapter.get("temperature_attr")
        names = (requested,) if requested else self.ATTR_NAMES
        for name in names:
            answer = temperature_from(getattr(self.obj, name, None))
            if answer is not None:
                return answer
        raise RuntimeError("simulator has no readable temperature")

    def advance(self, command):
        command = clip(command, 0.0, 100.0)
        requested = self.adapter.get("step_method")
        step = self._method((requested,) if requested else self.STEP_NAMES)
        if step is None:
            raise RuntimeError("simulator has no supported step method")
        requested = self.adapter.get("heater_setter")
        setter = self._method((requested,) if requested else self.SETTER_NAMES)
        params = self.parameters(step)
        names = [p.name.lower() for p in params]
        power_positions = [i for i, name in enumerate(names)
                           if name in ("power", "heater_power", "heater", "input_power", "control", "action", "u", "command")
                           or "power" in name or "heater" in name]
        time_positions = [i for i, name in enumerate(names)
                          if name in ("dt", "time_step", "timestep", "delta_t", "duration", "seconds")
                          or "time" in name or "duration" in name]
        direct_power = bool(power_positions)
        if setter is not None and not direct_power:
            try:
                setter(command)
            except TypeError:
                sp = self.parameters(setter)
                if not sp:
                    raise RuntimeError("heater setter does not accept a command")
                setter(**{sp[0].name: command})
        elif setter is None and not direct_power:
            for attr in ("heater_power", "power", "heater", "input_power", "command"):
                if hasattr(self.obj, attr):
                    setattr(self.obj, attr, command)
                    break
        kwargs = {}
        for p in params:
            name = p.name.lower()
            if name in names and (name in ("power", "heater_power", "heater", "input_power", "control", "action", "u", "command") or "power" in name or "heater" in name):
                kwargs[p.name] = command
            elif name in ("dt", "time_step", "timestep", "delta_t", "duration", "seconds") or "time" in name or "duration" in name:
                kwargs[p.name] = self.dt
        try:
            if kwargs:
                result = step(**kwargs)
            elif not params:
                result = step()
            elif len(params) == 1:
                result = step(command if direct_power else self.dt)
            else:
                result = step(command, self.dt)
        except TypeError as exc:
            raise RuntimeError("unsupported simulator step signature: " + str(exc))
        return temperature_from(result)


def solve3(matrix, rhs):
    a = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise RuntimeError("calibration transition fit is singular")
        a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [v / scale for v in a[col]]
        for row in range(3):
            if row != col:
                scale = a[row][col]
                a[row] = [v - scale * q for v, q in zip(a[row], a[col])]
    return [a[i][3] for i in range(3)]


def identify(rows, dt):
    x = [[r["temperature"], r["heater_power"], 1.0] for r in rows[:-1]]
    y = [r["temperature"] for r in rows[1:]]
    normal = [[sum(row[i] * row[j] for row in x) for j in range(3)] for i in range(3)]
    rhs = [sum(row[i] * target for row, target in zip(x, y)) for i in range(3)]
    raw_a, raw_b, raw_c = solve3(normal, rhs)
    # Noise can push a near-unit stable pole just outside its physical range.
    a = clip(raw_a, 0.002, 0.999)
    b = raw_b
    k = b / (1.0 - a)
    if not isnum(k) or k <= 0:
        raise RuntimeError("calibration did not establish positive heater gain")
    predicted = [a * old[0] + b * old[1] + raw_c for old in x]
    sse = sum((actual - pred) ** 2 for actual, pred in zip(y, predicted))
    mean_y = sum(y) / len(y)
    sst = sum((actual - mean_y) ** 2 for actual in y)
    return {"K": float(k), "tau": float(-dt / math.log(a)),
            "r_squared": float(clip(1.0 - sse / sst, 0.0, 1.0) if sst > 1e-12 else 0.0),
            "fitting_error": float(math.sqrt(sse / len(y))),
            "ambient": float(raw_c / (1.0 - a))}


def gains_from(model, factor):
    lam = clip(model["tau"] * factor, 0.75, 180.0)
    kp = clip(model["tau"] / (model["K"] * lam), 1e-5, 200.0)
    return {"Kp": float(kp), "Ki": float(clip(kp / model["tau"], 1e-7, 15.0)),
            "Kd": 0.0, "lambda": float(lam)}


def control_trial(module, config, config_path, adapter, dt, duration, setpoint, model, gains):
    plant = Plant(module, config, config_path, dt, adapter)
    feedforward = clip((setpoint - model["ambient"]) / model["K"], 0.0, 95.0)
    integral = 0.0
    data, time = [], 0.0
    steps = int(math.ceil(duration / dt)) + 1
    for _ in range(steps):
        temp = num(plant.temperature(), "control temperature")
        error = setpoint - temp
        candidate_integral = clip(integral + error * dt, -300.0, 300.0)
        raw = feedforward + gains["Kp"] * error + gains["Ki"] * candidate_integral
        command = clip(raw, 0.0, 100.0)
        # Integrate while unsaturated, or only when the error moves a saturated
        # output back toward its permitted range.
        if abs(raw - command) < 1e-12 or (command <= 0.0 and error > 0.0) or (command >= 100.0 and error < 0.0):
            integral = candidate_integral
        data.append({"time": float(time), "temperature": float(temp), "setpoint": float(setpoint),
                     "heater_power": float(command), "error": float(error)})
        plant.advance(command)
        time += dt
    return data


def derive_metrics(rows, setpoint):
    ts = [r["time"] for r in rows]
    temps = [r["temperature"] for r in rows]
    rise_threshold = temps[0] + 0.9 * (setpoint - temps[0])
    rise_index = next((i for i, v in enumerate(temps) if v >= rise_threshold), len(rows) - 1)
    settle_index = next((i for i in range(len(rows)) if all(abs(v - setpoint) < 0.5 for v in temps[i:])), len(rows) - 1)
    tail = max(3, int(math.ceil(len(rows) * 0.2)))
    maximum = max(temps)
    return {"rise_time": float(ts[rise_index] - ts[0]),
            "overshoot": float(max(0.0, (maximum - setpoint) / setpoint)),
            "settling_time": float(ts[settle_index] - ts[0]),
            "steady_state_error": float(sum(abs(v - setpoint) for v in temps[-tail:]) / tail),
            "max_temp": float(maximum)}


def target_ok(m):
    return (m["steady_state_error"] < 0.5 and m["settling_time"] < 120.0 and
            m["overshoot"] < 0.10 and m["max_temp"] < 30.0)


def score(m):
    return (10000 * max(0.0, m["steady_state_error"] - 0.35) +
            100 * max(0.0, m["settling_time"] - 105.0) +
            10000 * max(0.0, m["overshoot"] - 0.06) +
            1000 * max(0.0, m["max_temp"] - 27.0) + 0.01 * m["settling_time"])


def request():
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
    output = Path(req.get("output_dir", "/root"))
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    if not isinstance(config, dict):
        raise RuntimeError("room configuration must be a JSON object")
    dt = num(req.get("sample_dt", configured_dt(config) or 0.5), "sample_dt")
    if dt <= 0:
        raise RuntimeError("sample_dt must be positive")
    setpoint = num(req.get("setpoint", 22.0), "setpoint")
    duration = max(150.0, num(req.get("control_duration_s", 155.0), "control_duration_s"))
    test_power = clip(num(req.get("calibration_power", 50.0), "calibration_power"), 5.0, 100.0)
    adapter = req.get("adapter", {})
    if not isinstance(adapter, dict):
        raise RuntimeError("adapter must be a JSON object")
    output.mkdir(parents=True, exist_ok=True)
    module = load_simulator(sim_path)

    # 5 s baseline, 45 s energized response, 15 s cooldown: enough samples,
    # duration, and excitation while retaining a completion-friendly run time.
    plant = Plant(module, config, config_path, dt, adapter)
    calibration, time = [], 0.0
    n = int(math.ceil(65.0 / dt)) + 1
    baseline = int(math.ceil(5.0 / dt))
    heating_end = int(math.ceil(50.0 / dt))
    for i in range(n):
        command = test_power if baseline <= i < heating_end else 0.0
        calibration.append({"time": float(time), "temperature": num(plant.temperature(), "calibration temperature"),
                            "heater_power": float(command)})
        plant.advance(command)
        time += dt
    model = identify(calibration, dt)
    write_json(output / "calibration_log.json", {"phase": "calibration", "heater_power_test": float(test_power), "data": calibration})
    write_json(output / "estimated_params.json", {k: model[k] for k in ("K", "tau", "r_squared", "fitting_error")})

    best = None
    # These are all model-derived IMC time constants. Fresh instances prevent
    # one trial's temperature state from contaminating another candidate.
    for factor in (0.25, 0.5, 1.0):
        gains = gains_from(model, factor)
        trace = control_trial(module, config, config_path, adapter, dt, duration, setpoint, model, gains)
        metrics = derive_metrics(trace, setpoint)
        candidate = (score(metrics), gains, trace, metrics)
        if best is None or candidate[0] < best[0]:
            best = candidate
    _, gains, trace, metrics = best
    write_json(output / "tuned_gains.json", gains)
    write_json(output / "control_log.json", {"phase": "control", "setpoint": float(setpoint), "data": trace})
    write_json(output / "metrics.json", metrics)
    return {"ok": True, "targets_met": target_ok(metrics),
            "files": [str(output / name) for name in ("calibration_log.json", "estimated_params.json", "tuned_gains.json", "control_log.json", "metrics.json")],
            "metrics": metrics}


if __name__ == "__main__":
    try:
        print(json.dumps(main(request()), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, allow_nan=False))
        sys.exit(1)
