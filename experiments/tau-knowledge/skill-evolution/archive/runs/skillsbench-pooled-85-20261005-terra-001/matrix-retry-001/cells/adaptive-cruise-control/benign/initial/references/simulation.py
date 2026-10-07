"""Standalone ACC simulator. Usage: python simulation.py --config X --sensor Y --tuning Z --output O"""
import argparse
import csv
import math
from pathlib import Path
from acc_system import AdaptiveCruiseControl, _find


def scalar(value):
    value = value.strip().strip("\"'")
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return float(value) if any(c in value for c in ".eE") else int(value)
    except ValueError:
        return value


def load_yaml(path):
    """Read scalar nested YAML mappings; intentionally no list/anchor support."""
    root, stack = {}, [(-1, root)]
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip() or ":" not in line:
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, value = line.strip().split(":", 1)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value.strip() == "":
            child = {}
            parent[key.strip()] = child
            stack.append((indent, child))
        else:
            parent[key.strip()] = scalar(value)
    return root


def finite_cell(row, key):
    raw = row.get(key, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except ValueError:
        return None


def fmt(value):
    return "" if value is None else f"{value:.6f}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--sensor", required=True)
    parser.add_argument("--tuning", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    config = load_yaml(args.config)
    config.update(load_yaml(args.tuning))
    with open(args.sensor, newline="", encoding="utf-8") as handle:
        input_rows = list(csv.DictReader(handle))
    required = {"time", "ego_speed", "lead_speed", "distance"}
    if not input_rows or not required.issubset(input_rows[0]):
        raise ValueError("sensor CSV must contain time, ego_speed, lead_speed, distance")
    controller = AdaptiveCruiseControl(config)
    ego_speed = max(0.0, float(_find(config, ("initial_speed", "initial_ego_speed"), 0.0)))
    previous_time = None
    output = []
    for index, sensor in enumerate(input_rows):
        time = finite_cell(sensor, "time")
        if time is None:
            raise ValueError(f"non-finite time at sensor row {index}")
        if previous_time is not None and time <= previous_time:
            raise ValueError("sensor timestamps must be strictly increasing")
        dt = float(_find(config, ("dt", "timestep", "time_step"), 0.1)) if previous_time is None else time - previous_time
        lead_speed, distance = finite_cell(sensor, "lead_speed"), finite_cell(sensor, "distance")
        if lead_speed is None or distance is None:
            lead_speed, distance = None, None
        command, mode, distance_error = controller.compute(ego_speed, lead_speed, distance, dt)
        ttc = None
        if lead_speed is not None and ego_speed > lead_speed:
            ttc = distance / (ego_speed - lead_speed)
        output.append({"time": fmt(time), "ego_speed": fmt(ego_speed), "acceleration_cmd": fmt(command),
                       "mode": mode, "distance_error": fmt(distance_error), "distance": fmt(distance), "ttc": fmt(ttc)})
        ego_speed = max(0.0, ego_speed + command * dt)
        previous_time = time
    names = ["time", "ego_speed", "acceleration_cmd", "mode", "distance_error", "distance", "ttc"]
    with open(args.output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(output)


if __name__ == "__main__":
    main()
