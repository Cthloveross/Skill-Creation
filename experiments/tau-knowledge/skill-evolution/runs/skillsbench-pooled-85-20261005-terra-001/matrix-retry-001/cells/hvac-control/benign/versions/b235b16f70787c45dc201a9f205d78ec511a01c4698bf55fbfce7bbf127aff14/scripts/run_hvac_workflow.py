#!/usr/bin/env python3
"""Generate HVAC calibration, model, tuning, control, and metric artifacts.

stdin: JSON object documented in SKILL.md
stdout: JSON status object
The program uses only the Python standard library and never writes either
supplied simulator input or room configuration input.
"""
import importlib.util
import inspect
import json
import math
import sys
from pathlib import Path


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def number(value, name):
    if not finite(value):
        raise RuntimeError(name + " must be a finite number")
    return float(value)


def clamp(value, low, high):
    return max(low, min(high, float(value)))


def dump(path, document):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, allow_nan=False)
        handle.write("\n")


def temperature_of(value):
    if finite(value):
        return float(value)
    if isinstance(value, dict):
        for key in ("temperature", "temp", "current_temperature", "room_temperature", "T"):
            if finite(value.get(key)):
                return float(value[key])
    if isinstance(value, (tuple, list)):
        for item in value:
            answer = temperature_of(item)
            if answer is not None:
                return answer
    return None


def nested_dt(value):
    if isinstance(value, dict):
        for key in ("dt", "time_step", "timestep", "sample_dt", "sample_interval"):
            if finite(value.get(key)) and float(value[key]) > 0:
                return float(value[key])
        for item in value.values():
            result = nested_dt(item)
            if result is not None:
                return result
    elif isinstance(value, list):
        for item in value:
            result = nested_dt(item)
            if result is not None:
                return result
    return None


def load_module(path):
    spec = importlib.util.spec_from_file_location("task_hvac_simulator", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import supplied HVAC simulator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Plant:
    """Small adapter for ordinary discrete room-heating simulators."""
    CLASS_NAMES = ("HVACSimulator", "RoomSimulator", "ThermalSimulator", "HeatingSimulator",
                   "RoomHeatingSimulator", "Simulator", "Room", "HVAC", "create_simulator",
                   "make_simulator")
    READERS = ("get_temperature", "read_temperature", "measure_temperature",
               "get_current_temperature", "get_temp", "observe", "get_state")
    ATTRS = ("temperature", "current_temperature", "room_temperature", "room_temp",
             "indoor_temperature", "temp", "T", "state")
    SETTERS = ("set_heater_power", "set_heater", "set_power", "apply_heater_power",
               "set_input", "set_control", "set_heater_percent")
    STEPPERS = ("step", "update", "advance", "simulate_step", "run_step", "advance_time",
                "update_temperature")

    def __init__(self, module, configuration, config_path, dt, adapter):
        self.module = module
        self.configuration = configuration
        self.config_path = str(config_path)
        self.dt = dt
        self.adapter = adapter
        self.object = self._construct()

    def _makers(self):
        requested = self.adapter.get("class")
        if requested:
            candidate = getattr(self.module, requested, None)
            if not callable(candidate):
                raise RuntimeError("requested simulator class/factory does not exist")
            return [candidate]
        choices = []
        for name in self.CLASS_NAMES:
            candidate = getattr(self.module, name, None)
            if callable(candidate) and candidate not in choices:
                choices.append(candidate)
        for candidate in vars(self.module).values():
            if inspect.isclass(candidate) and candidate.__module__ == self.module.__name__ and candidate not in choices:
                choices.append(candidate)
        return choices

    def _construct(self):
        # A path is tried first because many supplied simulators load JSON
        # themselves. Dict and keyword variants support simple alternatives.
        attempts = [((self.config_path,), {}), ((self.configuration,), {}),
                    ((), {"config_path": self.config_path}),
                    ((), {"config": self.configuration}), ((), {})]
        if isinstance(self.configuration, dict):
            attempts.insert(-1, ((), dict(self.configuration)))
        errors = []
        for maker in self._makers():
            for args, kwargs in attempts:
                try:
                    return maker(*args, **kwargs)
                except Exception as exc:
                    errors.append(type(exc).__name__ + ": " + str(exc))
        suffix = "; ".join(errors[-3:])
        raise RuntimeError("could not construct simulator" + (": " + suffix if suffix else ""))

    @staticmethod
    def signature(fn):
        try:
            return [p for p in inspect.signature(fn).parameters.values()
                    if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
        except (TypeError, ValueError):
            return []

    def _method(self, names):
        for name in names:
            if not name:
                continue
            fn = getattr(self.object, name, None)
            if callable(fn):
                return fn
        return None

    def temperature(self):
        requested = self.adapter.get("temperature_method")
        reader = self._method((requested,) if requested else self.READERS)
        if reader is not None:
            try:
                answer = temperature_of(reader())
                if answer is not None:
                    return answer
            except TypeError:
                pass
        requested = self.adapter.get("temperature_attr")
        for name in ((requested,) if requested else self.ATTRS):
            answer = temperature_of(getattr(self.object, name, None))
            if answer is not None:
                return answer
        raise RuntimeError("simulator exposes no readable temperature")

    def advance(self, command):
        command = clamp(command, 0.0, 100.0)
        requested = self.adapter.get("step_method")
        stepper = self._method((requested,) if requested else self.STEPPERS)
        if stepper is None:
            raise RuntimeError("simulator exposes no supported step method")
        requested = self.adapter.get("heater_setter")
        setter = self._method((requested,) if requested else self.SETTERS)
        params = self.signature(stepper)
        lower = [p.name.lower() for p in params]
        power_names = {"power", "heater_power", "heater", "input_power", "control", "action", "u", "command"}
        time_names = {"dt", "time_step", "timestep", "delta_t", "duration", "seconds"}
        direct_power = any(name in power_names or "power" in name or "heater" in name for name in lower)
        if setter is not None and not direct_power:
            setter(command)
        elif setter is None and not direct_power:
            for attr in ("heater_power", "power", "heater", "input_power", "command"):
                if hasattr(self.object, attr):
                    setattr(self.object, attr, command)
                    break
        kwargs = {}
        for p in params:
            name = p.name.lower()
            if name in power_names or "power" in name or "heater" in name:
                kwargs[p.name] = command
            elif name in time_names or "time" in name or "duration" in name:
                kwargs[p.name] = self.dt
        if kwargs:
            result = stepper(**kwargs)
        elif not params:
            result = stepper()
        elif len(params) == 1:
            # A one-argument method with no recognisable name is conventionally
            # a duration when a setter exists, otherwise an actuator command.
            result = stepper(self.dt if setter is not None else command)
        else:
            result = stepper(command, self.dt)
        return temperature_of(result)


def solve3(matrix, rhs):
    augmented = [list(row) + [rhs[index]] for index, row in enumerate(matrix)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-13:
            raise RuntimeError("calibration transition fit is singular")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        divisor = augmented[col][col]
        augmented[col] = [item / divisor for item in augmented[col]]
        for row in range(3):
            if row != col:
                amount = augmented[row][col]
                augmented[row] = [item - amount * pivot_item for item, pivot_item in zip(augmented[row], augmented[col])]
    return [augmented[index][3] for index in range(3)]


def identify(rows, dt):
    features = [[row["temperature"], row["heater_power"], 1.0] for row in rows[:-1]]
    targets = [row["temperature"] for row in rows[1:]]
    normal = [[sum(row[i] * row[j] for row in features) for j in range(3)] for i in range(3)]
    # A negligible ridge makes the calculation robust to nearly constant
    # readings without materially altering an excited experiment.
    for i in range(3):
        normal[i][i] += 1e-10
    rhs = [sum(row[i] * target for row, target in zip(features, targets)) for i in range(3)]
    raw_a, raw_b, raw_c = solve3(normal, rhs)
    a = clamp(raw_a, 0.002, 0.9995)
    gain = raw_b / (1.0 - a)
    if not finite(gain) or gain <= 0:
        raise RuntimeError("calibration did not establish a positive heater gain")
    predicted = [a * old[0] + raw_b * old[1] + raw_c for old in features]
    sse = sum((actual - predicted_value) ** 2 for actual, predicted_value in zip(targets, predicted))
    mean = sum(targets) / len(targets)
    sst = sum((actual - mean) ** 2 for actual in targets)
    return {
        "K": float(gain),
        "tau": float(-dt / math.log(a)),
        "r_squared": float(clamp(1.0 - sse / sst, 0.0, 1.0) if sst > 1e-12 else 0.0),
        "fitting_error": float(math.sqrt(sse / len(targets))),
        "ambient": float(raw_c / (1.0 - a)),
    }


def imc_gains(model):
    # lambda=tau/2 provides a conservative response while still allowing a
    # 22 C room target to settle in ordinary educational HVAC models.
    lam = clamp(0.5 * model["tau"], 0.75, 180.0)
    kp = clamp(model["tau"] / (model["K"] * lam), 1e-6, 200.0)
    return {"Kp": float(kp), "Ki": float(clamp(kp / model["tau"], 1e-8, 15.0)),
            "Kd": 0.0, "lambda": float(lam)}


def run_control(module, config, config_path, adapter, dt, duration, setpoint, model, gains):
    plant = Plant(module, config, config_path, dt, adapter)
    feedforward = clamp((setpoint - model["ambient"]) / model["K"], 0.0, 95.0)
    integral = 0.0
    time = 0.0
    rows = []
    steps = int(math.ceil(duration / dt)) + 1
    for _ in range(steps):
        temperature = number(plant.temperature(), "control temperature")
        error = setpoint - temperature
        proposal = clamp(integral + error * dt, -300.0, 300.0)
        raw = feedforward + gains["Kp"] * error + gains["Ki"] * proposal
        command = clamp(raw, 0.0, 100.0)
        # Conditional integration: retain an integral update only if it is not
        # increasing a saturated command farther beyond its permitted bound.
        if abs(raw - command) < 1e-12 or (command <= 0.0 and error > 0.0) or (command >= 100.0 and error < 0.0):
            integral = proposal
        rows.append({"time": float(time), "temperature": float(temperature),
                     "setpoint": float(setpoint), "heater_power": float(command),
                     "error": float(error)})
        plant.advance(command)
        time += dt
    return rows


def metrics_from(rows, setpoint):
    times = [row["time"] for row in rows]
    temperatures = [row["temperature"] for row in rows]
    threshold = temperatures[0] + 0.9 * (setpoint - temperatures[0])
    rise = next((index for index, value in enumerate(temperatures) if value >= threshold), len(rows) - 1)
    settle = next((index for index in range(len(rows))
                   if all(abs(value - setpoint) < 0.5 for value in temperatures[index:])), len(rows) - 1)
    tail = max(3, int(math.ceil(len(rows) * 0.2)))
    maximum = max(temperatures)
    return {
        "rise_time": float(times[rise] - times[0]),
        "overshoot": float(max(0.0, (maximum - setpoint) / setpoint)),
        "settling_time": float(times[settle] - times[0]),
        "steady_state_error": float(sum(abs(value - setpoint) for value in temperatures[-tail:]) / tail),
        "max_temp": float(maximum),
    }


def target_met(metrics):
    return (metrics["steady_state_error"] < 0.5 and metrics["settling_time"] < 120.0 and
            metrics["overshoot"] < 0.10 and metrics["max_temp"] < 30.0)


def parse_request():
    text = sys.stdin.read().strip()
    if not text:
        return {}
    value = json.loads(text)
    if not isinstance(value, dict):
        raise RuntimeError("stdin must be a JSON object")
    return value


def main(request):
    simulator_path = Path(request.get("simulator_path", "/root/hvac_simulator.py"))
    config_path = Path(request.get("room_config_path", "/root/room_config.json"))
    output_dir = Path(request.get("output_dir", "/root"))
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise RuntimeError("room configuration must be a JSON object")
    dt = number(request.get("sample_dt", nested_dt(config) or 0.5), "sample_dt")
    if dt <= 0:
        raise RuntimeError("sample_dt must be positive")
    setpoint = number(request.get("setpoint", 22.0), "setpoint")
    duration = max(150.0, number(request.get("control_duration_s", 155.0), "control_duration_s"))
    test_power = clamp(number(request.get("calibration_power", 50.0), "calibration_power"), 5.0, 100.0)
    adapter = request.get("adapter", {})
    if not isinstance(adapter, dict):
        raise RuntimeError("adapter must be a JSON object")
    output_dir.mkdir(parents=True, exist_ok=True)
    module = load_module(simulator_path)

    # Baseline 5 s, nonzero 45 s step, cooldown 15 s. The sample count and
    # span exceed the requested calibration minimum even for larger dt values.
    plant = Plant(module, config, config_path, dt, adapter)
    calibration = []
    elapsed = 0.0
    total = int(math.ceil(65.0 / dt)) + 1
    baseline_end = int(math.ceil(5.0 / dt))
    heating_end = int(math.ceil(50.0 / dt))
    for index in range(total):
        command = test_power if baseline_end <= index < heating_end else 0.0
        calibration.append({"time": float(elapsed),
                            "temperature": number(plant.temperature(), "calibration temperature"),
                            "heater_power": float(command)})
        plant.advance(command)
        elapsed += dt

    # Save the observed experiment before fitting so the supplied evidence is
    # retained even if a caller needs to diagnose an unsupported plant model.
    dump(output_dir / "calibration_log.json", {
        "phase": "calibration", "heater_power_test": float(test_power), "data": calibration
    })
    model = identify(calibration, dt)
    dump(output_dir / "estimated_params.json", {key: model[key] for key in ("K", "tau", "r_squared", "fitting_error")})

    gains = imc_gains(model)
    dump(output_dir / "tuned_gains.json", gains)
    trace = run_control(module, config, config_path, adapter, dt, duration, setpoint, model, gains)
    result_metrics = metrics_from(trace, setpoint)
    dump(output_dir / "control_log.json", {"phase": "control", "setpoint": float(setpoint), "data": trace})
    dump(output_dir / "metrics.json", result_metrics)
    paths = [str(output_dir / name) for name in (
        "calibration_log.json", "estimated_params.json", "tuned_gains.json", "control_log.json", "metrics.json"
    )]
    return {"ok": True, "targets_met": target_met(result_metrics), "files": paths,
            "gains": gains, "metrics": result_metrics}


if __name__ == "__main__":
    try:
        print(json.dumps(main(parse_request()), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, allow_nan=False))
        sys.exit(1)
