#!/usr/bin/env python3
"""Run and validate an ACC simulation. Simulation never performs gain tuning."""
import argparse
import csv
import math
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from acc_system import AdaptiveCruiseControl

HEADER = ["time", "ego_speed", "acceleration_cmd", "mode", "distance_error", "distance", "ttc"]


def _scalar(text):
    text = text.strip().strip("\"'")
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    if text.lower() in ("null", "none", "~", ""):
        return None
    try:
        return float(text) if any(x in text.lower() for x in (".", "e")) else int(text)
    except ValueError:
        return text


def load_yaml(path):
    """Load ordinary nested mapping YAML; use PyYAML when it is available."""
    text = Path(path).read_text(encoding="utf-8")
    if yaml is not None:
        loaded = yaml.safe_load(text)
        if not isinstance(loaded, dict):
            raise ValueError("YAML root must be a mapping")
        return loaded
    root, stack = {}, [(-1, root)]
    for raw in text.splitlines():
        clean = raw.split("#", 1)[0].rstrip()
        if not clean.strip() or ":" not in clean:
            continue
        indent = len(clean) - len(clean.lstrip(" "))
        key, value = clean.strip().split(":", 1)
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if value.strip() == "":
            child = {}
            parent[key.strip()] = child
            stack.append((indent, child))
        else:
            parent[key.strip()] = _scalar(value)
    return root


def _finite_optional(value):
    if value is None or str(value).strip() == "":
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def read_sensor(path, expected_rows=None):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = ("time", "ego_speed", "lead_speed", "distance")
        if reader.fieldnames is None or any(key not in reader.fieldnames for key in required):
            raise ValueError("sensor CSV requires time, ego_speed, lead_speed, distance columns")
        rows = []
        previous = None
        for source in reader:
            time = _finite_optional(source.get("time"))
            ego = _finite_optional(source.get("ego_speed"))
            if time is None or ego is None:
                raise ValueError("time and ego_speed must be finite on every sensor row")
            if previous is not None and time <= previous:
                raise ValueError("sensor times must be strictly increasing")
            previous = time
            rows.append({
                "time": time,
                "initial_ego": max(0.0, ego),
                "lead_speed": _finite_optional(source.get("lead_speed")),
                "sensor_distance": _finite_optional(source.get("distance")),
            })
    if not rows:
        raise ValueError("sensor CSV has no data rows")
    if expected_rows is not None and len(rows) != expected_rows:
        raise ValueError("expected %d sensor rows, got %d" % (expected_rows, len(rows)))
    return rows


def combine_config(config, gains):
    combined = dict(config)
    combined["pid_gains"] = gains
    return combined


def simulate_rows(sensor_rows, config, gains):
    """Return output rows using sensor ego speed only at time zero.

    Lead distance is an exogenous sensor observation at every sample.  The
    simulation controls and integrates only the ego vehicle state.
    """
    acc = AdaptiveCruiseControl(combine_config(config, gains))
    ego = sensor_rows[0]["initial_ego"]
    output = []
    fallback_dt = 0.1
    for index, source in enumerate(sensor_rows):
        dt = fallback_dt if index == 0 else source["time"] - sensor_rows[index - 1]["time"]
        if dt <= 0.0:
            raise ValueError("nonpositive timestep")
        lead = source["lead_speed"]
        observed_gap = source["sensor_distance"]
        has_lead = lead is not None and observed_gap is not None
        command, mode, error = acc.compute(
            ego,
            lead if has_lead else None,
            observed_gap if has_lead else None,
            dt,
        )
        output.append({
            "time": source["time"],
            "ego_speed": ego,
            "acceleration_cmd": command,
            "mode": mode,
            "distance_error": error,
            "distance": observed_gap if has_lead else None,
            "ttc": acc.ttc if has_lead else None,
        })
        # Explicit Euler: log/control at current time, then propagate ego state.
        ego = max(0.0, ego + command * dt)
    return output


def metrics(rows, set_speed):
    speeds = [r["ego_speed"] for r in rows]
    threshold = 0.9 * set_speed
    rise = next((r["time"] - rows[0]["time"] for r in rows if r["ego_speed"] >= threshold), None)
    overshoot = max(0.0, (max(speeds) - set_speed) / set_speed * 100.0) if set_speed else 0.0
    tail_start = rows[-1]["time"] - 10.0
    tail = [r for r in rows if r["time"] >= tail_start]
    speed_sse = sum(abs(r["ego_speed"] - set_speed) for r in tail) / len(tail)
    gap_rows = [r for r in rows if r["distance"] is not None]
    tail_gaps = [r for r in tail if r["distance_error"] is not None]
    return {
        "duration_s": rows[-1]["time"] - rows[0]["time"],
        "row_count": len(rows),
        "speed_rise_time_s": rise,
        "speed_overshoot_percent": overshoot,
        "speed_steady_state_error_mps": speed_sse,
        "distance_steady_state_error_m": None if not tail_gaps else sum(abs(r["distance_error"]) for r in tail_gaps) / len(tail_gaps),
        "minimum_distance_m": None if not gap_rows else min(r["distance"] for r in gap_rows),
    }


def _fmt(value):
    return "" if value is None else ("%.10g" % value)


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _fmt(row[key]) for key in HEADER})


def validate_output(path, sensor_rows, min_accel, max_accel):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != HEADER:
            raise ValueError("output header/order is incorrect")
        rows = list(reader)
    if len(rows) != len(sensor_rows):
        raise ValueError("output row count does not align with sensor input")
    for expected, row in zip(sensor_rows, rows):
        if abs(float(row["time"]) - expected["time"]) > 1e-8:
            raise ValueError("output time does not align with sensor time")
        if row["mode"] not in ("cruise", "follow", "emergency"):
            raise ValueError("invalid output mode")
        speed, command = float(row["ego_speed"]), float(row["acceleration_cmd"])
        if not (math.isfinite(speed) and math.isfinite(command) and speed >= 0.0 and min_accel - 1e-8 <= command <= max_accel + 1e-8):
            raise ValueError("invalid speed or acceleration in output")
        has_lead = expected["lead_speed"] is not None and expected["sensor_distance"] is not None
        if not has_lead:
            if row["mode"] != "cruise" or any(row[x] != "" for x in ("distance_error", "distance", "ttc")):
                raise ValueError("cruise rows must have blank lead fields")
        else:
            if abs(float(row["distance"]) - expected["sensor_distance"]) > 1e-6:
                raise ValueError("output distance must match sensor observation")
            if row["distance_error"] == "":
                raise ValueError("lead row lacks distance error")
        if row["ttc"] != "" and float(row["ttc"]) <= 0.0:
            raise ValueError("reported TTC must be positive")


def write_report(path, config, gains, result_metrics):
    acc = AdaptiveCruiseControl(combine_config(config, gains))

    def value(v, unit=""):
        return "not applicable" if v is None else "%.3f%s" % (v, unit)

    checks = [
        ("Speed rise time < 10 s", result_metrics["speed_rise_time_s"] is not None and result_metrics["speed_rise_time_s"] < 10.0),
        ("Speed overshoot < 5%", result_metrics["speed_overshoot_percent"] < 5.0),
        ("Speed steady-state error < 0.5 m/s", result_metrics["speed_steady_state_error_mps"] < 0.5),
        ("Distance steady-state error < 2 m", result_metrics["distance_steady_state_error_m"] is not None and result_metrics["distance_steady_state_error_m"] < 2.0),
        ("Minimum distance > 5 m", result_metrics["minimum_distance_m"] is not None and result_metrics["minimum_distance_m"] > 5.0),
    ]
    lines = [
        "# Adaptive Cruise Control Report", "", "## System design", "",
        "The simulator uses mutually exclusive cruise, follow, and emergency modes. Cruise tracks the configured set speed with a speed PID. Follow uses a separate gap PID and the constant-time-headway target `gap = headway × simulated ego speed + minimum gap`. Each detected lead gap is taken from its current sensor observation. Emergency mode has priority whenever closing TTC is below its configured threshold and commands maximum braking. Safety features include physical command saturation, nonnegative speed, bounded/reset PID state on mode transitions, and omission of TTC unless the ego vehicle is closing.",
        "", "## PID tuning methodology and final gains", "",
        "A deterministic bounded candidate search was run on the supplied lead-vehicle trace. Candidates were scored from trace-derived safety and tracking violations; the selected gains are loaded at runtime by `simulation.py` rather than embedded in it.",
        "", "```yaml", "pid_speed:",
    ]
    for key in ("kp", "ki", "kd"):
        lines.append("  %s: %s" % (key, gains["pid_speed"][key]))
    lines.append("pid_distance:")
    for key in ("kp", "ki", "kd"):
        lines.append("  %s: %s" % (key, gains["pid_distance"][key]))
    lines += ["```", "", "## Simulation results and performance metrics", "", "| Metric | Value | Target status |", "|---|---:|---|"]
    mapping = [
        ("Speed rise time", value(result_metrics["speed_rise_time_s"], " s"), checks[0][1]),
        ("Speed overshoot", value(result_metrics["speed_overshoot_percent"], "%"), checks[1][1]),
        ("Speed steady-state error", value(result_metrics["speed_steady_state_error_mps"], " m/s"), checks[2][1]),
        ("Distance steady-state error", value(result_metrics["distance_steady_state_error_m"], " m"), checks[3][1]),
        ("Minimum distance", value(result_metrics["minimum_distance_m"], " m"), checks[4][1]),
        ("Duration", value(result_metrics["duration_s"], " s"), result_metrics["duration_s"] >= 150.0),
        ("Output rows", str(result_metrics["row_count"]), result_metrics["row_count"] == 1501),
    ]
    for label, measured, passed in mapping:
        lines.append("| %s | %s | %s |" % (label, measured, "PASS" if passed else "NOT MET"))
    lines += ["", "A `NOT MET` status is an observed property of this input trace and selected controller, not a substituted claim of compliance."]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _check_gains(gains):
    for group in ("pid_speed", "pid_distance"):
        if group not in gains or not isinstance(gains[group], dict):
            raise ValueError("missing %s gains" % group)
        for key in ("kp", "ki", "kd"):
            value = float(gains[group].get(key))
            if not math.isfinite(value) or not (0.0 < value < 10.0 if key == "kp" else 0.0 <= value < 5.0):
                raise ValueError("invalid %s.%s gain" % (group, key))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--gains", required=True)
    parser.add_argument("--sensor", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--expected-rows", type=int, default=1501, help="0 disables row-count enforcement")
    args = parser.parse_args()
    config, gains = load_yaml(args.config), load_yaml(args.gains)
    _check_gains(gains)
    source = read_sensor(args.sensor, None if args.expected_rows == 0 else args.expected_rows)
    result = simulate_rows(source, config, gains)
    write_csv(args.output, result)
    controller = AdaptiveCruiseControl(combine_config(config, gains))
    validate_output(args.output, source, controller.min_accel, controller.max_accel)
    write_report(args.report, config, gains, metrics(result, controller.set_speed))


if __name__ == "__main__":
    main()
