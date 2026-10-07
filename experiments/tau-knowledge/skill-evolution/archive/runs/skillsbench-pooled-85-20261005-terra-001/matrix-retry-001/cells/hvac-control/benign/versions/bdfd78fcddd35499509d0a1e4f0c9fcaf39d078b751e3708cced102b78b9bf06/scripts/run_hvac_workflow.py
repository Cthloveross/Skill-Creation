#!/usr/bin/env python3
"""Run an HVAC calibration/identification/control workflow.

Reads one optional JSON object from stdin and emits one JSON status object on
stdout.  On success it writes the five requested JSON documents to output_dir.
Only the Python standard library is used.
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
    return max(low, min(high, float(x)))


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")


def temperature_from(value):
    if finite(value):
        return float(value)
    if isinstance(value, dict):
        for key in ("temperature", "temp", "room_temperature", "current_temperature",
                    "room_temp", "indoor_temperature", "T"):
            if finite(value.get(key)):
                return float(value[key])
        for child in value.values():
            answer = temperature_from(child)
            if answer is not None:
                return answer
    if isinstance(value, (tuple, list)):
        for child in value:
            if finite(child):
                return float(child)
    return None


def config_dt(value):
    if isinstance(value, dict):
        for key in ("dt", "time_step", "timestep", "sample_dt", "sample_interval"):
            if finite(value.get(key)) and float(value[key]) > 0:
                return float(value[key])
        for child in value.values():
            got = config_dt(child)
            if got is not None:
                return got
    if isinstance(value, list):
        for child in value:
            got = config_dt(child)
            if got is not None:
                return got
    return None


def load_module(path):
    spec = importlib.util.spec_from_file_location("task_hvac_simulator", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load simulator module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Plant:
    """Adapter for ordinary educational room/HVAC simulator interfaces."""
    READERS = ("get_temperature", "read_temperature", "measure_temperature",
               "get_current_temperature", "get_temp", "observe", "get_state")
    ATTRS = ("temperature", "current_temperature", "room_temperature", "room_temp",
             "indoor_temperature", "temp", "T", "state")
    SETTERS = ("set_heater_power", "set_heater", "set_power", "apply_heater_power",
               "set_input", "set_control", "set_heater_percent")
    STEPPERS = ("step", "update", "advance", "simulate_step", "run_step",
                "advance_time", "update_temperature")
    POWER_ARGS = {"power", "heater_power", "heater", "heater_level", "input_power",
                  "control", "action", "u", "command", "heater_percent",
                  "power_percent", "heater_power_percent"}
    TIME_ARGS = {"dt", "time_step", "timestep", "delta_t", "duration", "seconds"}

    def __init__(self, module, cfg, cfg_path, dt, adapter):
        self.module = module
        self.cfg = cfg
        self.cfg_path = str(cfg_path)
        self.dt = dt
        self.adapter = adapter
        self.obj = self._construct()

    def _construct(self):
        wanted = self.adapter.get("class")
        makers = []
        if wanted:
            candidate = getattr(self.module, wanted, None)
            if not callable(candidate):
                raise RuntimeError("configured adapter class was not found")
            makers = [candidate]
        else:
            for name in ("HVACSimulator", "RoomSimulator", "ThermalSimulator",
                         "HeatingSimulator", "RoomHeatingSimulator", "Simulator",
                         "create_simulator", "make_simulator"):
                candidate = getattr(self.module, name, None)
                if callable(candidate) and candidate not in makers:
                    makers.append(candidate)
            for name, candidate in vars(self.module).items():
                lower = name.lower()
                if (inspect.isclass(candidate) and candidate.__module__ == self.module.__name__
                        and any(word in lower for word in ("hvac", "room", "thermal", "heating", "simulator"))
                        and candidate not in makers):
                    makers.append(candidate)
        errors = []
        # Both a parsed config object and the config-file path are common public APIs.
        for maker in makers:
            attempts = [((self.cfg,), {}), ((self.cfg_path,), {}),
                        ((), {"config": self.cfg}), ((), {"config_path": self.cfg_path}), ((), {})]
            for args, kwargs in attempts:
                try:
                    return maker(*args, **kwargs)
                except Exception as exc:
                    errors.append(type(exc).__name__ + ": " + str(exc))
        # A stateful module-level API is also supported.
        if any(callable(getattr(self.module, n, None)) for n in self.STEPPERS):
            init = getattr(self.module, "initialize", None) or getattr(self.module, "reset", None)
            if callable(init):
                initialized = False
                for args in ((self.cfg,), (self.cfg_path,), ()):
                    try:
                        init(*args)
                        initialized = True
                        break
                    except TypeError:
                        continue
                if not initialized:
                    raise RuntimeError("could not initialize module-level simulator")
            return self.module
        detail = "; ".join(errors[-3:])
        raise RuntimeError("could not construct HVAC simulator" + (": " + detail if detail else ""))

    @staticmethod
    def parameters(fn):
        try:
            return [p for p in inspect.signature(fn).parameters.values()
                    if p.kind not in (inspect.Parameter.VAR_POSITIONAL,
                                      inspect.Parameter.VAR_KEYWORD)]
        except (TypeError, ValueError):
            return []

    def method(self, names):
        for name in names:
            if name:
                candidate = getattr(self.obj, name, None)
                if callable(candidate):
                    return candidate
        return None

    def temperature(self):
        selected = self.adapter.get("temperature_method")
        reader = self.method((selected,) if selected else self.READERS)
        if reader is not None:
            try:
                answer = temperature_from(reader())
                if answer is not None:
                    return answer
            except TypeError:
                pass
        selected = self.adapter.get("temperature_attr")
        for name in ((selected,) if selected else self.ATTRS):
            answer = temperature_from(getattr(self.obj, name, None))
            if answer is not None:
                return answer
        raise RuntimeError("unable to read a simulator temperature")

    def advance(self, power):
        power = clamp(power, 0.0, 100.0)
        selected = self.adapter.get("step_method")
        step = self.method((selected,) if selected else self.STEPPERS)
        if step is None:
            raise RuntimeError("unable to find a simulator step method")
        selected = self.adapter.get("heater_setter")
        setter = self.method((selected,) if selected else self.SETTERS)
        step_params = self.parameters(step)
        has_direct_power = any(p.name.lower() in self.POWER_ARGS for p in step_params)
        if setter is not None and not has_direct_power:
            setter_params = self.parameters(setter)
            try:
                if setter_params:
                    setter(**{setter_params[0].name: power})
                else:
                    setter(power)
            except TypeError:
                setter(power)
        elif setter is None and not has_direct_power:
            for attr in ("heater_power", "power", "heater", "input_power", "command"):
                if hasattr(self.obj, attr):
                    setattr(self.obj, attr, power)
                    break
        kwargs = {}
        for p in step_params:
            lower = p.name.lower()
            if lower in self.POWER_ARGS:
                kwargs[p.name] = power
            elif lower in self.TIME_ARGS:
                kwargs[p.name] = self.dt
        try:
            if kwargs:
                returned = step(**kwargs)
            elif not step_params:
                returned = step()
            elif len(step_params) == 1:
                returned = step(self.dt if setter is not None else power)
            else:
                returned = step(power, self.dt)
        except TypeError as exc:
            raise RuntimeError("unsupported simulator step signature: " + str(exc))
        observed = temperature_from(returned)
        return self.temperature() if observed is None else observed


def solve3(matrix, rhs):
    work = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda row: abs(work[row][col]))
        if abs(work[pivot][col]) < 1e-12:
            raise RuntimeError("calibration regression is singular")
        work[col], work[pivot] = work[pivot], work[col]
        divisor = work[col][col]
        work[col] = [v / divisor for v in work[col]]
        for row in range(3):
            if row != col:
                scale = work[row][col]
                work[row] = [v - scale * base for v, base in zip(work[row], work[col])]
    return [work[i][3] for i in range(3)]


def identify(rows, dt):
    # Commands are logged with the observation immediately before their interval,
    # therefore u[n] is the physically applied command for T[n] -> T[n+1].
    x = [[r["temperature"], r["heater_power"], 1.0] for r in rows[:-1]]
    y = [r["temperature"] for r in rows[1:]]
    normal = [[sum(row[i] * row[j] for row in x) for j in range(3)] for i in range(3)]
    rhs = [sum(row[i] * target for row, target in zip(x, y)) for i in range(3)]
    a, b, c = solve3(normal, rhs)
    # Thermal systems must be stable.  Bound only numerical edge cases caused by
    # sensor noise, retaining the fitted heater-input scale.
    a = clamp(a, 0.001, 0.9995)
    denominator = 1.0 - a
    k = b / denominator
    if not finite(k) or k <= 0:
        raise RuntimeError("calibration did not identify a positive heater gain")
    predictions = [a * old[0] + b * old[1] + c for old in x]
    sse = sum((actual - pred) ** 2 for actual, pred in zip(y, predictions))
    mean_y = sum(y) / len(y)
    sst = sum((actual - mean_y) ** 2 for actual in y)
    r2 = clamp(1.0 - sse / sst, 0.0, 1.0) if sst > 1e-12 else 0.0
    rmse = math.sqrt(sse / len(y))
    tau = -dt / math.log(a)
    ambient = c / denominator
    if not finite(ambient):
        raise RuntimeError("identified ambient intercept is not finite")
    return {"K": float(k), "tau": float(tau), "r_squared": float(r2),
            "fitting_error": float(rmse), "ambient": float(ambient)}


def gains_for(model, factor):
    lam = clamp(model["tau"] * factor, 1.0, 160.0)
    kp = clamp(model["tau"] / (model["K"] * lam), 1e-6, 300.0)
    return {"Kp": float(kp), "Ki": float(clamp(kp / model["tau"], 1e-8, 30.0)),
            "Kd": 0.0, "lambda": float(lam)}


def run_control(module, cfg, cfg_path, adapter, dt, duration, setpoint, model, gains):
    plant = Plant(module, cfg, cfg_path, dt, adapter)
    # At equilibrium u=(setpoint-ambient)/K.  PI feedback corrects mismatch.
    feedforward = clamp((setpoint - model["ambient"]) / model["K"], 0.0, 95.0)
    integral = 0.0
    now = 0.0
    rows = []
    count = int(math.ceil(duration / dt)) + 1
    for _ in range(count):
        temp = num(plant.temperature(), "control temperature")
        error = setpoint - temp
        candidate_integral = clamp(integral + error * dt, -500.0, 500.0)
        raw = feedforward + gains["Kp"] * error + gains["Ki"] * candidate_integral
        power = clamp(raw, 0.0, 100.0)
        # Conditional anti-windup: retain integral only when it cannot force a
        # saturated command farther in the saturation direction.
        if (abs(raw - power) < 1e-10 or (power <= 0.0 and error > 0.0)
                or (power >= 100.0 and error < 0.0)):
            integral = candidate_integral
        rows.append({"time": float(now), "temperature": float(temp),
                     "setpoint": float(setpoint), "heater_power": float(power),
                     "error": float(setpoint - temp)})
        plant.advance(power)
        now += dt
    return rows


def derive_metrics(rows, setpoint):
    times = [r["time"] for r in rows]
    temps = [r["temperature"] for r in rows]
    initial = temps[0]
    ninety = initial + 0.9 * (setpoint - initial)
    rise_index = next((i for i, temp in enumerate(temps)
                       if (temp >= ninety if setpoint >= initial else temp <= ninety)), len(rows) - 1)
    settle_index = next((i for i in range(len(rows))
                         if all(abs(temp - setpoint) < 0.5 for temp in temps[i:])), len(rows) - 1)
    tail = max(3, int(math.ceil(len(rows) * 0.2)))
    maximum = max(temps)
    return {"rise_time": float(times[rise_index] - times[0]),
            "overshoot": float(max(0.0, (maximum - setpoint) / setpoint)),
            "settling_time": float(times[settle_index] - times[0]),
            "steady_state_error": float(sum(abs(temp - setpoint) for temp in temps[-tail:]) / tail),
            "max_temp": float(maximum)}


def meets_targets(m):
    return (m["steady_state_error"] < 0.5 and m["settling_time"] < 120.0
            and m["overshoot"] < 0.10 and m["max_temp"] < 30.0)


def score(m):
    # Prefer a comfortably compliant actual run, but retain a deterministic best
    # diagnostic candidate if the simulator cannot meet the requested bounds.
    return (100000.0 * max(0.0, m["steady_state_error"] - 0.35)
            + 1000.0 * max(0.0, m["settling_time"] - 100.0)
            + 100000.0 * max(0.0, m["overshoot"] - 0.06)
            + 10000.0 * max(0.0, m["max_temp"] - 27.0)
            + 0.01 * m["settling_time"])


def validate(calibration, model, gains, trace, metrics, setpoint):
    if len(calibration) < 20 or calibration[-1]["time"] - calibration[0]["time"] < 30.0:
        raise RuntimeError("calibration lacks required duration or samples")
    if max(r["heater_power"] for r in calibration) - min(r["heater_power"] for r in calibration) <= 1.0:
        raise RuntimeError("calibration has no deliberate excitation")
    if max(r["temperature"] for r in calibration) - min(r["temperature"] for r in calibration) <= 0.05:
        raise RuntimeError("calibration has no measurable thermal response")
    if model["K"] <= 0 or model["tau"] <= 0 or model["r_squared"] < 0 or model["r_squared"] > 1:
        raise RuntimeError("identified model is not physical")
    if any(not finite(v) or v < 0 for v in gains.values() if v is not gains.get("lambda")) or gains["lambda"] <= 0:
        raise RuntimeError("controller gains are invalid")
    previous = None
    for row in calibration:
        if not all(finite(row[k]) for k in ("time", "temperature", "heater_power")):
            raise RuntimeError("calibration contains non-finite values")
        if not 0 <= row["heater_power"] <= 100:
            raise RuntimeError("calibration command is out of bounds")
    for row in trace:
        if not all(finite(row[k]) for k in ("time", "temperature", "setpoint", "heater_power", "error")):
            raise RuntimeError("control trace contains non-finite values")
        if previous is not None and row["time"] <= previous:
            raise RuntimeError("control times are not strictly ordered")
        previous = row["time"]
        if not 0 <= row["heater_power"] <= 100:
            raise RuntimeError("control command is out of bounds")
        if abs(row["setpoint"] - setpoint) > 1e-9 or abs(row["error"] - (setpoint - row["temperature"])) > 1e-8:
            raise RuntimeError("control trace setpoint/error is inconsistent")
    if trace[-1]["time"] - trace[0]["time"] < 150.0:
        raise RuntimeError("control trace is shorter than 150 seconds")
    recomputed = derive_metrics(trace, setpoint)
    for key in recomputed:
        if abs(recomputed[key] - metrics[key]) > 1e-9:
            raise RuntimeError("metrics were not derived from final control trace")
    if not meets_targets(metrics):
        raise RuntimeError("no tested controller candidate met requested trace targets")


def read_request():
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("stdin must be a JSON object")
    return value


def main(req):
    sim_path = Path(req.get("simulator_path", "/root/hvac_simulator.py"))
    cfg_path = Path(req.get("room_config_path", "/root/room_config.json"))
    outdir = Path(req.get("output_dir", "/root"))
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        raise RuntimeError("room configuration must be a JSON object")
    dt = num(req.get("sample_dt", config_dt(cfg) or 0.5), "sample_dt")
    if dt <= 0:
        raise RuntimeError("sample_dt must be positive")
    setpoint = num(req.get("setpoint", 22.0), "setpoint")
    duration = max(150.0, num(req.get("control_duration_s", 240.0), "control_duration_s"))
    test_power = clamp(num(req.get("calibration_power", 50.0), "calibration_power"), 5.0, 100.0)
    adapter = req.get("adapter", {})
    if not isinstance(adapter, dict):
        raise RuntimeError("adapter must be a JSON object")
    outdir.mkdir(parents=True, exist_ok=True)
    module = load_module(sim_path)

    # Baseline/step/cooldown produces independent temperature and input variation.
    plant = Plant(module, cfg, cfg_path, dt, adapter)
    calibration = []
    now = 0.0
    samples = int(math.ceil(85.0 / dt)) + 1
    baseline_end = int(math.ceil(5.0 / dt))
    heat_end = int(math.ceil(65.0 / dt))
    for i in range(samples):
        command = test_power if baseline_end <= i < heat_end else 0.0
        calibration.append({"time": float(now),
                            "temperature": num(plant.temperature(), "calibration temperature"),
                            "heater_power": float(command)})
        plant.advance(command)
        now += dt
    model = identify(calibration, dt)

    chosen = None
    # Small lambda gives fast response; larger lambda gives conservative damping.
    for factor in (0.06, 0.09, 0.13, 0.18, 0.25, 0.35, 0.50, 0.70, 1.0, 1.5, 2.2, 3.0):
        gains = gains_for(model, factor)
        trace = run_control(module, cfg, cfg_path, adapter, dt, duration, setpoint, model, gains)
        measured = derive_metrics(trace, setpoint)
        candidate = (score(measured), gains, trace, measured)
        if chosen is None or candidate[0] < chosen[0]:
            chosen = candidate
    _, gains, trace, measured = chosen
    validate(calibration, model, gains, trace, measured, setpoint)

    write_json(outdir / "calibration_log.json", {"phase": "calibration", "heater_power_test": test_power,
                                                  "data": calibration})
    write_json(outdir / "estimated_params.json", {key: model[key]
                                                   for key in ("K", "tau", "r_squared", "fitting_error")})
    write_json(outdir / "tuned_gains.json", gains)
    write_json(outdir / "control_log.json", {"phase": "control", "setpoint": setpoint, "data": trace})
    write_json(outdir / "metrics.json", measured)
    return {"ok": True, "targets_met": True,
            "files": ["calibration_log.json", "estimated_params.json", "tuned_gains.json",
                      "control_log.json", "metrics.json"], "metrics": measured}


if __name__ == "__main__":
    try:
        print(json.dumps(main(read_request()), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, allow_nan=False))
        sys.exit(1)
