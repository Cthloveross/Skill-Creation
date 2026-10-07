#!/usr/bin/env python3
"""Run runtime-tuned ACC and write the required CSV and Markdown report."""
import argparse
import csv
import math
import statistics
from pathlib import Path

import yaml

from acc_system import AdaptiveCruiseControl

FIELDS = ["time", "ego_speed", "acceleration_cmd", "mode", "distance_error", "distance", "ttc"]


def number(value):
    if value is None or str(value).strip() == "":
        return None
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("non-finite sensor value")
    return value


def load_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        needed = ("time", "ego_speed", "lead_speed", "distance")
        if not reader.fieldnames or any(name not in reader.fieldnames for name in needed):
            raise ValueError("sensor CSV lacks required columns")
        rows = []
        last_time = None
        for line, raw in enumerate(reader, 2):
            current_time = number(raw["time"])
            if current_time is None or (last_time is not None and current_time <= last_time):
                raise ValueError("invalid timestamp at sensor row " + str(line))
            lead_speed = number(raw["lead_speed"])
            distance = number(raw["distance"])
            if (lead_speed is None) != (distance is None):
                raise ValueError("incomplete lead observation at sensor row " + str(line))
            if distance is not None and distance < 0:
                raise ValueError("negative lead distance at sensor row " + str(line))
            rows.append({"time": current_time, "lead_speed": lead_speed, "distance": distance})
            last_time = current_time
    if not rows:
        raise ValueError("sensor CSV has no data rows")
    return rows


def config_with_gains(config, gains):
    merged = dict(config)
    merged["_pid_gains"] = gains
    return merged


def simulate_rows(rows, config):
    controller = AdaptiveCruiseControl(config)
    vehicle = config.get("vehicle", {}) if isinstance(config, dict) else {}
    initial_speed = config.get("initial_speed", vehicle.get("initial_speed", 0.0))
    ego_speed = max(0.0, float(initial_speed))
    trace = []
    for index, sensor in enumerate(rows):
        if index + 1 < len(rows):
            dt = rows[index + 1]["time"] - sensor["time"]
        elif index:
            dt = sensor["time"] - rows[index - 1]["time"]
        else:
            dt = 0.1
        if dt <= 0:
            raise ValueError("non-positive dt")
        command, mode, distance_error = controller.compute(
            ego_speed, sensor["lead_speed"], sensor["distance"], dt
        )
        # These are precisely the state values used in the TTC calculation.
        ttc = controller.last_ttc
        trace.append({
            "time": sensor["time"],
            "ego_speed": ego_speed,
            "acceleration_cmd": command,
            "mode": mode,
            "distance_error": distance_error,
            "distance": sensor["distance"] if mode != "cruise" else None,
            "ttc": ttc,
        })
        ego_speed = max(0.0, ego_speed + command * dt)
    return trace


def fmt(value):
    # Precision is deliberately sufficient for TTC recomputation from CSV fields.
    return "" if value is None else format(float(value), ".12f")


def report(trace, controller, output_path):
    cruise = [row for row in trace if row["mode"] == "cruise"]
    lead_rows = [row for row in trace if row["mode"] != "cruise"]
    rise = next((row["time"] for row in cruise if row["ego_speed"] >= 0.9 * controller.set_speed), None)
    overshoot = (max((row["ego_speed"] for row in cruise), default=controller.set_speed) - controller.set_speed) / controller.set_speed * 100.0
    cruise_tail = cruise[-100:]
    speed_error = statistics.fmean(abs(row["ego_speed"] - controller.set_speed) for row in cruise_tail) if cruise_tail else None
    follow_tail = lead_rows[-100:]
    distance_error = statistics.fmean(abs(row["distance_error"]) for row in follow_tail) if follow_tail else None
    gaps = [row["distance"] for row in lead_rows if row["distance"] is not None]
    display = lambda value: "N/A" if value is None else f"{value:.3f}"
    lines = [
        "# ACC Simulation Report",
        "",
        "## System design",
        "",
        "The ACC uses mutually exclusive cruise, follow, and TTC-priority emergency modes. Cruise uses a speed PID. Follow uses a separate distance PID and the constant-time-headway policy `d_safe = 1.5 * ego_speed + 10.0` unless configuration overrides those values. Safety features include acceleration saturation, nonnegative speed, mode-transition PID reset, blank undefined TTC values, and maximum configured braking in emergency mode.",
        "",
        "## PID tuning methodology and final gains",
        "",
        f"A deterministic bounded candidate evaluation selected speed PID gains kp={controller.speed_pid.kp:.6g}, ki={controller.speed_pid.ki:.6g}, kd={controller.speed_pid.kd:.6g}, and distance PID gains kp={controller.distance_pid.kp:.6g}, ki={controller.distance_pid.ki:.6g}, kd={controller.distance_pid.kd:.6g}. The speed candidates penalize a rise later than 10 s and overshoot above 5%; integral-free speed candidates prevent windup in the specified drag-free Euler plant. These gains are loaded from `tuning_results.yaml` at runtime.",
        "",
        "## Simulation results and performance metrics",
        "",
        f"Records: {len(trace)}; duration: {trace[-1]['time'] - trace[0]['time']:.3f} s.",
        f"Cruise rise time to 90%: {display(rise)} s (target <10 s).",
        f"Cruise overshoot: {overshoot:.3f}% (target <5%).",
        f"Cruise tail mean absolute speed error: {display(speed_error)} m/s (target <0.5 m/s).",
        f"Follow tail mean absolute distance error: {display(distance_error)} m (target <2 m).",
        f"Minimum observed lead distance: {display(min(gaps) if gaps else None)} m (target >5 m).",
        "Observed distance is supplied sensor data; a value below the target is reported as a data/safety finding rather than altered by the simulator.",
    ]
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--tuning", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    rows = load_rows(args.sensor)
    base_config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    gains = yaml.safe_load(Path(args.tuning).read_text(encoding="utf-8")) or {}
    if not all(section in gains for section in ("pid_speed", "pid_distance")):
        raise ValueError("tuning file missing PID sections")
    config = config_with_gains(base_config, gains)
    trace = simulate_rows(rows, config)

    with open(args.output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in trace:
            writer.writerow({key: row[key] if key == "mode" else fmt(row[key]) for key in FIELDS})
    report(trace, AdaptiveCruiseControl(config), args.report)


if __name__ == "__main__":
    main()
