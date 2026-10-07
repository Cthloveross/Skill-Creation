#!/usr/bin/env python3
"""Execute calibration, identification, tuning, and safe PI control for HVACSimulator.

Input is one JSON object on stdin:
 {"simulator_path":"/root/hvac_simulator.py", "config_path":"/root/room_config.json",
  "output_dir":"/root", "calibration_power":35.0, "calibration_duration":150.0,
  "control_duration":180.0}
All fields except paths are optional.  The script imports the supplied simulator,
never substitutes a plant model, and writes the five task JSON artifacts.  It prints
an object naming their paths.  Errors print JSON to stderr and exit nonzero.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

# The helper is packaged beside this entrypoint.
from hvac_tools import estimate, tune, control_metrics, validate


def write_json(path, value):
    with Path(path).open("w", encoding="utf-8") as fh:
        json.dump(value, fh, indent=2, allow_nan=False)
        fh.write("\n")


def nonnegative_finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(name + " must be a positive finite number")
    return float(value)


def load_simulator(path):
    spec = importlib.util.spec_from_file_location("supplied_hvac_simulator", path)
    if spec is None or spec.loader is None:
        raise ValueError("could not import simulator_path")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = getattr(module, "HVACSimulator", None)
    if cls is None:
        raise ValueError("supplied simulator has no HVACSimulator class")
    return cls


def point(time_value, temperature, power):
    for name, value in (("time", time_value), ("temperature", temperature), ("heater_power", power)):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise RuntimeError("simulator returned non-finite " + name)
    return {"time": float(time_value), "temperature": float(temperature), "heater_power": float(power)}


def main(request):
    sim_path = request.get("simulator_path", "/root/hvac_simulator.py")
    config_path = request.get("config_path", "/root/room_config.json")
    output_dir = Path(request.get("output_dir", "."))
    output_dir.mkdir(parents=True, exist_ok=True)
    cal_power = nonnegative_finite(request.get("calibration_power", 35.0), "calibration_power")
    if cal_power > 100:
        raise ValueError("calibration_power must not exceed 100")
    cal_duration = nonnegative_finite(request.get("calibration_duration", 150.0), "calibration_duration")
    control_duration = nonnegative_finite(request.get("control_duration", 180.0), "control_duration")
    if cal_duration < 30 or control_duration < 150:
        raise ValueError("calibration_duration >=30 and control_duration >=150 are required")

    Simulator = load_simulator(sim_path)
    cal = Simulator(config_path)
    dt = nonnegative_finite(cal.get_dt(), "simulator dt")
    initial = cal.reset()
    cal_data = [point(0.0, initial, 0.0)]
    for _ in range(int(math.ceil(cal_duration / dt))):
        response = cal.step(cal_power)
        if response.get("safety_triggered"):
            raise RuntimeError("calibration triggered simulator safety limit; lower calibration_power")
        cal_data.append(point(response["time"], response["temperature"], response["heater_power"]))
    cal_doc = {"phase": "calibration", "heater_power_test": cal_power, "data": cal_data}
    cal_path = output_dir / "calibration_log.json"
    write_json(cal_path, cal_doc)

    params = estimate(cal_doc)
    params_path = output_dir / "estimated_params.json"
    write_json(params_path, params)
    gains = tune(params, dt)
    gains_path = output_dir / "tuned_gains.json"
    write_json(gains_path, gains)

    # A fresh simulator makes the control trace independent of calibration heat.
    sim = Simulator(config_path)
    setpoint = float(sim.get_setpoint())
    initial = float(sim.reset())
    kp, ki = float(gains["Kp"]), float(gains["Ki"])
    integral = 0.0
    temperature = initial
    control_data = []
    count = int(math.ceil(control_duration / dt))
    for step in range(count + 1):
        error = setpoint - temperature
        proposed_integral = integral + error * dt
        raw = kp * error + ki * proposed_integral
        power = min(100.0, max(0.0, raw))
        # Conditional integration: retain a candidate only if it is unsaturated
        # or it moves a saturated actuator back toward its feasible interval.
        if raw == power or (power == 0.0 and error > 0.0) or (power == 100.0 and error < 0.0):
            integral = proposed_integral
            power = min(100.0, max(0.0, kp * error + ki * integral))
        control_data.append({"time": float(sim.time), "temperature": temperature,
                             "setpoint": setpoint, "heater_power": power, "error": error})
        if step == count:
            break
        response = sim.step(power)
        if response.get("safety_triggered"):
            raise RuntimeError("control triggered simulator safety limit")
        temperature = float(response["temperature"])
    control_doc = {"phase": "control", "setpoint": setpoint, "data": control_data}
    control_path = output_dir / "control_log.json"
    write_json(control_path, control_doc)
    metrics = control_metrics(control_doc)
    metrics_path = output_dir / "metrics.json"
    write_json(metrics_path, metrics)
    validate([str(cal_path), str(params_path), str(gains_path), str(control_path), str(metrics_path)], setpoint)
    return {"ok": True, "artifacts": [str(cal_path), str(params_path), str(gains_path), str(control_path), str(metrics_path)], "metrics": metrics}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(2)
