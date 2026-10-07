#!/usr/bin/env python3
"""Standard-library artifact analysis for first-order HVAC control workflows.

Read one JSON object from stdin and write one JSON object to stdout. See SKILL.md
for action schemas. Errors are emitted as {"ok": false, "error": ...} and exit 2.
"""
import json
import math
import sys
from pathlib import Path


def finite_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("%s must be a finite number" % field)
    return float(value)


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_result(obj, output_path=None):
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, allow_nan=False)
            fh.write("\n")
    print(json.dumps({"ok": True, "result": obj}, allow_nan=False))


def records(doc, kind):
    data = doc.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("%s data must be a nonempty list" % kind)
    answer = []
    last_t = None
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            raise ValueError("%s data[%d] must be an object" % (kind, i))
        t = finite_number(row.get("time"), "data[%d].time" % i)
        temp = finite_number(row.get("temperature"), "data[%d].temperature" % i)
        if last_t is not None and t <= last_t:
            raise ValueError("%s times must be strictly increasing" % kind)
        last_t = t
        answer.append((t, temp, row))
    return answer


def estimate(calibration):
    rows = records(calibration, "calibration")
    if len(rows) < 20:
        raise ValueError("calibration requires at least 20 records")
    if rows[-1][0] - rows[0][0] < 30.0:
        raise ValueError("calibration duration must be at least 30 seconds")
    powers = [finite_number(r.get("heater_power"), "heater_power") for _, _, r in rows]
    positive = max(powers)
    if positive <= 0:
        raise ValueError("calibration needs a positive heater-power step")
    # Define onset as first sample at the largest sustained applied power. The
    # pre-step average is the measured baseline when it exists.
    onset = next(i for i, p in enumerate(powers) if abs(p - positive) <= 1e-9)
    pretemps = [rows[i][1] for i in range(onset)] or [rows[0][1]]
    baseline = sum(pretemps) / len(pretemps)
    sample = [(t - rows[onset][0], temp) for t, temp, r in rows[onset:]
              if abs(finite_number(r.get("heater_power"), "heater_power") - positive) <= 1e-9]
    if len(sample) < 8 or sample[-1][0] <= 0:
        raise ValueError("need sustained constant-power samples after the step")
    duration = sample[-1][0]
    best = None
    # Search logarithmically-ish over a broad physically positive range. For a
    # fixed tau, the least-squares coefficient B is the response asymptote.
    lo = max(0.05, duration / 200.0)
    hi = max(lo * 2.0, duration * 8.0)
    for j in range(360):
        frac = j / 359.0
        tau = lo * (hi / lo) ** frac
        qs = [1.0 - math.exp(-t / tau) for t, _ in sample]
        ys = [temp - baseline for _, temp in sample]
        denom = sum(q * q for q in qs)
        if denom <= 0:
            continue
        b = sum(q * y for q, y in zip(qs, ys)) / denom
        predicted = [baseline + b * q for q in qs]
        sse = sum((temp - pred) ** 2 for (_, temp), pred in zip(sample, predicted))
        if best is None or sse < best[0]:
            best = (sse, tau, b, predicted)
    if best is None or best[2] <= 0:
        raise ValueError("fit did not find a positive heating response")
    sse, tau, response, predicted = best
    observed = [temp for _, temp in sample]
    mean = sum(observed) / len(observed)
    sst = sum((temp - mean) ** 2 for temp in observed)
    r2 = 1.0 - sse / sst if sst > 1e-12 else 0.0
    rmse = math.sqrt(sse / len(sample))
    return {
        "K": response / positive,
        "tau": tau,
        "r_squared": r2,
        "fitting_error": rmse,
        "fit_method": "least-squares first-order step response, grid searched tau",
        "heater_power_step": positive,
        "baseline_temperature": baseline,
        "samples_fit": len(sample),
    }


def tune(params, dt):
    k = finite_number(params.get("K"), "K")
    tau = finite_number(params.get("tau"), "tau")
    dt = finite_number(dt, "dt")
    if k <= 0 or tau <= 0 or dt <= 0:
        raise ValueError("K, tau, and dt must be positive")
    # Conservative IMC PI for G=K/(tau*s+1), with lambda no faster than both
    # several samples and a fraction of the observed plant time constant.
    lam = max(4.0 * dt, min(2.0 * tau, max(0.5 * tau, 10.0 * dt)))
    kp = tau / (k * lam)
    ki = kp / tau
    return {
        "Kp": kp,
        "Ki": ki,
        "Kd": 0.0,
        "lambda": lam,
        "tuning_method": "conservative IMC PI; output is heater percent",
        "integral_limit_recommendation": 100.0 / max(ki, 1e-12),
    }


def control_metrics(control):
    rows = records(control, "control")
    sp = finite_number(control.get("setpoint"), "setpoint")
    values = [temp for _, temp, _ in rows]
    times = [t for t, _, _ in rows]
    initial = values[0]
    change = sp - initial
    mag = abs(change)
    if mag < 1e-9:
        rise = 0.0
        overshoot = 0.0
    else:
        threshold = initial + 0.9 * change
        hit = next((t for t, temp in zip(times, values)
                    if (temp >= threshold if change > 0 else temp <= threshold)), None)
        rise = None if hit is None else hit - times[0]
        excursion = max(values) - sp if change > 0 else sp - min(values)
        overshoot = max(0.0, excursion) / mag
    band = max(0.1, 0.02 * max(mag, 1e-12))
    settle = None
    for i in range(len(rows)):
        if all(abs(temp - sp) <= band for temp in values[i:]):
            settle = times[i] - times[0]
            break
    tail_count = min(len(values), max(5, int(math.ceil(len(values) * 0.2))))
    tail_mean = sum(values[-tail_count:]) / tail_count
    return {
        "rise_time": rise,
        "overshoot": overshoot,
        "settling_time": settle,
        "steady_state_error": abs(sp - tail_mean),
        "max_temp": max(values),
        "control_duration": times[-1] - times[0],
        "definitions": {
            "rise_time": "first 90% initial-to-setpoint crossing, seconds",
            "overshoot": "peak beyond setpoint divided by initial setpoint change",
            "settling_time": "first time all remaining samples lie within max(0.1 C, 2% initial-change) of setpoint, seconds",
            "steady_state_error": "absolute error of mean final 20% (at least 5) samples, C",
        },
    }


def validate(paths, setpoint=None):
    results = {}
    for path in paths:
        doc = load_json(path)
        name = Path(path).name
        if name == "calibration_log.json":
            rr = records(doc, "calibration")
            if len(rr) < 20 or rr[-1][0] - rr[0][0] < 30:
                raise ValueError("calibration count/duration requirement failed")
            for _, _, row in rr:
                p = finite_number(row.get("heater_power"), "heater_power")
                if p < 0 or p > 100:
                    raise ValueError("calibration heater_power outside [0,100]")
        elif name == "control_log.json":
            rr = records(doc, "control")
            logged_sp = finite_number(doc.get("setpoint"), "control setpoint")
            if setpoint is not None and abs(logged_sp - finite_number(setpoint, "setpoint")) > 1e-9:
                raise ValueError("control setpoint differs from requested setpoint")
            for _, _, row in rr:
                if abs(finite_number(row.get("setpoint"), "row setpoint") - logged_sp) > 1e-9:
                    raise ValueError("control row setpoint inconsistent with document")
                if abs(finite_number(row.get("error"), "error") - (logged_sp - finite_number(row.get("temperature"), "temperature"))) > 1e-6:
                    raise ValueError("control error inconsistent with temperature")
                p = finite_number(row.get("heater_power"), "heater_power")
                if p < 0 or p > 100:
                    raise ValueError("control heater_power outside [0,100]")
        else:
            # Recursively reject non-finite numeric values in other JSON files.
            def walk(x):
                if isinstance(x, float) and not math.isfinite(x):
                    raise ValueError("non-finite number in " + name)
                if isinstance(x, dict):
                    for v in x.values(): walk(v)
                elif isinstance(x, list):
                    for v in x: walk(v)
            walk(doc)
        results[name] = "valid"
    return {"validated": results}


def main():
    request = json.load(sys.stdin)
    action = request.get("action")
    if action == "estimate":
        result = estimate(load_json(request["calibration_path"]))
    elif action == "tune":
        result = tune(load_json(request["params_path"]), request["dt"])
    elif action == "metrics":
        result = control_metrics(load_json(request["control_path"]))
    elif action == "validate":
        paths = request.get("paths")
        if not isinstance(paths, list) or not paths:
            raise ValueError("validate requires a nonempty paths list")
        result = validate(paths, request.get("setpoint"))
    else:
        raise ValueError("action must be estimate, tune, metrics, or validate")
    dump_result(result, request.get("output_path"))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
