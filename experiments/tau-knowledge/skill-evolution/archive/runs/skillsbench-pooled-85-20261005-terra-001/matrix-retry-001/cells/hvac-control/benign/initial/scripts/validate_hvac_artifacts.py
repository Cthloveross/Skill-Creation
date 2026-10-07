#!/usr/bin/env python3
"""Validate the five HVAC deliverables. JSON stdin: output_dir, setpoint, min_control_duration_s."""
import json
import math
import sys
from pathlib import Path


def fail(message):
    return {"valid": False, "error": message}


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def load(root, name):
    with open(root / name, encoding="utf-8") as f:
        return json.load(f)


def close(a, b, tol=1e-7):
    return abs(float(a) - float(b)) <= tol


def recompute(data, sp):
    times = [float(x["time"]) for x in data]
    temps = [float(x["temperature"]) for x in data]
    initial, start = temps[0], times[0]
    delta = sp - initial
    rise = None
    if abs(delta) < 1e-9:
        rise = 0.0
    else:
        threshold = initial + .9 * delta
        for t, temp in zip(times, temps):
            if (delta > 0 and temp >= threshold) or (delta < 0 and temp <= threshold):
                rise = t - start; break
    settle = None
    for i in range(len(data)):
        if all(abs(x - sp) <= .5 for x in temps[i:]):
            settle = times[i] - start; break
    window = max(start, times[-1] - max(30.0, .2 * (times[-1] - start)))
    tail = [abs(float(x["error"])) for x in data if float(x["time"]) >= window]
    return {"rise_time": rise, "overshoot": max(0., max(temps)-sp)/max(abs(delta), 1e-9),
            "settling_time": settle, "steady_state_error": sum(tail)/len(tail), "max_temp": max(temps)}


def main(request):
    root = Path(request.get("output_dir", "."))
    required = ["calibration_log.json", "estimated_params.json", "tuned_gains.json", "control_log.json", "metrics.json"]
    if any(not (root / x).is_file() for x in required):
        return fail("one or more required artifact files are missing")
    cal, params, gains, control, reported = [load(root, x) for x in required]
    if cal.get("phase") != "calibration" or control.get("phase") != "control":
        return fail("incorrect phase field")
    cal_data, data = cal.get("data"), control.get("data")
    if not isinstance(cal_data, list) or not isinstance(data, list) or len(cal_data) < 20 or len(data) < 2:
        return fail("insufficient calibration or control data")
    def check_rows(rows, control_rows=False):
        last = None
        for row in rows:
            keys = ["time", "temperature", "heater_power"]
            if control_rows: keys += ["setpoint", "error"]
            if not all(k in row and finite(row[k]) for k in keys):
                return "record has missing/non-finite required fields"
            if last is not None and float(row["time"]) <= last:
                return "record times are not strictly increasing"
            last = float(row["time"])
            if not 0 <= float(row["heater_power"]) <= 100:
                return "heater power outside [0,100]"
            if control_rows and not close(row["error"], float(control.get("setpoint")) - float(row["temperature"])):
                return "control error is inconsistent with temperature/setpoint"
        return None
    issue = check_rows(cal_data) or check_rows(data, True)
    if issue: return fail(issue)
    if float(cal_data[-1]["time"]) - float(cal_data[0]["time"]) < 30.0:
        return fail("calibration duration is below 30 seconds")
    minimum = float(request.get("min_control_duration_s", 150.0))
    if float(data[-1]["time"]) - float(data[0]["time"]) < minimum:
        return fail("control duration is below requested minimum")
    if not all(k in params and finite(params[k]) for k in ("K", "tau", "r_squared", "fitting_error")):
        return fail("estimated parameters are incomplete or non-finite")
    if not all(k in gains and finite(gains[k]) for k in ("Kp", "Ki", "Kd", "lambda")):
        return fail("tuned gains are incomplete or non-finite")
    sp = float(request.get("setpoint", control.get("setpoint", 22.0)))
    computed = recompute(data, sp)
    for key, value in computed.items():
        actual = reported.get(key)
        if value is None:
            if actual is not None: return fail("metric %s should be null" % key)
        elif not finite(actual) or not close(actual, value, 1e-6):
            return fail("metric %s does not match trace" % key)
    return {"valid": True, "calibration_points": len(cal_data), "control_points": len(data), "metrics": computed}


if __name__ == "__main__":
    print(json.dumps(main(json.load(sys.stdin)), allow_nan=False))
