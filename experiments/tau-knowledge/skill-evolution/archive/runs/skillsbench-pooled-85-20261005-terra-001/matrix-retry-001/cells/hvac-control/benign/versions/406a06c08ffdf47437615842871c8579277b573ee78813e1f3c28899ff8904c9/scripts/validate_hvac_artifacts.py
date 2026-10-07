#!/usr/bin/env python3
"""Validate HVAC deliverables. JSON stdin: output_dir, setpoint, min_control_duration_s."""
import json
import math
import sys
from pathlib import Path


def numeric(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def load(root, name):
    with open(root / name, encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError(name + " is not a JSON object")
    return value


def fail(reason):
    return {"valid": False, "error": reason}


def main(request):
    root = Path(request.get("output_dir", "/root"))
    needed = ["calibration_log.json", "estimated_params.json", "tuned_gains.json", "control_log.json", "metrics.json"]
    if any(not (root / item).is_file() for item in needed):
        return fail("missing required artifact")
    try:
        cal, params, gains, control, reported = [load(root, item) for item in needed]
    except Exception as exc:
        return fail(str(exc))
    if cal.get("phase") != "calibration" or control.get("phase") != "control":
        return fail("incorrect phase")
    crows, rows = cal.get("data"), control.get("data")
    if not isinstance(crows, list) or len(crows) < 20 or not isinstance(rows, list) or len(rows) < 2:
        return fail("insufficient data")
    def check(data, is_control):
        prior = None
        for row in data:
            fields = ["time", "temperature", "heater_power"] + (["setpoint", "error"] if is_control else [])
            if not isinstance(row, dict) or any(key not in row or not numeric(row[key]) for key in fields):
                return "invalid data row"
            if prior is not None and float(row["time"]) <= prior:
                return "non-increasing times"
            prior = float(row["time"])
            if not 0 <= float(row["heater_power"]) <= 100:
                return "heater command outside range"
            if is_control and abs(float(row["error"]) - (float(control["setpoint"]) - float(row["temperature"]))) > 1e-6:
                return "inconsistent control error"
        return None
    problem = check(crows, False) or check(rows, True)
    if problem:
        return fail(problem)
    if float(crows[-1]["time"]) - float(crows[0]["time"]) < 30:
        return fail("short calibration")
    if float(rows[-1]["time"]) - float(rows[0]["time"]) < float(request.get("min_control_duration_s", 150)):
        return fail("short control")
    if not all(numeric(params.get(key)) for key in ("K", "tau", "r_squared", "fitting_error")) or float(params["K"]) <= 0 or float(params["tau"]) <= 0:
        return fail("invalid identified parameters")
    if not all(numeric(gains.get(key)) for key in ("Kp", "Ki", "Kd", "lambda")) or min(float(gains[k]) for k in ("Kp", "Ki", "Kd")) < 0 or float(gains["lambda"]) <= 0:
        return fail("invalid gains")
    sp = float(request.get("setpoint", 22.0))
    temps = [float(row["temperature"]) for row in rows]
    times = [float(row["time"]) for row in rows]
    maximum = max(temps)
    overshoot = max(0.0, (maximum - sp) / sp)
    tail_n = max(3, int(math.ceil(len(rows) * .2)))
    sse = sum(abs(t - sp) for t in temps[-tail_n:]) / tail_n
    settle = next((times[i] - times[0] for i in range(len(temps)) if all(abs(t - sp) < .5 for t in temps[i:])), None)
    for key in ("rise_time", "overshoot", "settling_time", "steady_state_error", "max_temp"):
        if not numeric(reported.get(key)):
            return fail("non-finite metric " + key)
    if abs(float(reported["max_temp"]) - maximum) > .1 or abs(float(reported["overshoot"]) - overshoot) > .01:
        return fail("trace-derived metrics disagree")
    return {"valid": True, "steady_state_error": sse, "settling_time": settle, "overshoot": overshoot, "max_temp": maximum}


if __name__ == "__main__":
    print(json.dumps(main(json.load(sys.stdin)), allow_nan=False))
