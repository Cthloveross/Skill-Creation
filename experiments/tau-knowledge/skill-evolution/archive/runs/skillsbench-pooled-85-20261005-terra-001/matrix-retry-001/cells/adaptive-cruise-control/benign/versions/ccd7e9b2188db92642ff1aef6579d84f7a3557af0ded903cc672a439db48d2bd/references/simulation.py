"""Standalone ACC simulator.
Usage: python simulation.py --config vehicle_params.yaml --sensor sensor_data.csv
       --tuning tuning_results.yaml --output simulation_results.csv
"""
import argparse
import csv
import math
from pathlib import Path

try:
    import yaml
except ImportError:  # A scalar mapping fallback remains available for restricted runtimes.
    yaml = None

from acc_system import AdaptiveCruiseControl, _find


def _scalar(value):
    value = value.strip().strip("\"'")
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return float(value) if any(ch in value for ch in ".eE") else int(value)
    except ValueError:
        return value


def _simple_yaml(text):
    root, stack = {}, [(-1, root)]
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip() or ":" not in line:
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, value = line.strip().split(":", 1)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value.strip():
            parent[key.strip()] = _scalar(value)
        else:
            child = {}
            parent[key.strip()] = child
            stack.append((indent, child))
    return root


def load_yaml(path):
    """Load runtime YAML; PyYAML safe_load is preferred over the scalar fallback."""
    text = Path(path).read_text(encoding="utf-8")
    if yaml is not None:
        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            return loaded
        raise ValueError("YAML root must be a mapping")
    return _simple_yaml(text)


def finite_cell(row, key):
    raw = row.get(key, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def fmt(value):
    """Preserve sufficient precision for TTC recomputation from CSV fields."""
    return "" if value is None else format(float(value), ".15g")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--sensor", required=True)
    parser.add_argument("--tuning", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config = load_yaml(args.config)
    tuning = load_yaml(args.tuning)
    config.update(tuning)
    with open(args.sensor, newline="", encoding="utf-8") as handle:
        sensor_rows = list(csv.DictReader(handle))
    required = {"time", "ego_speed", "lead_speed", "distance"}
    if not sensor_rows or not required.issubset(sensor_rows[0]):
        raise ValueError("sensor CSV must contain time, ego_speed, lead_speed, distance")

    controller = AdaptiveCruiseControl(config)
    ego_speed = max(0.0, float(_find(config, ("initial_speed", "initial_ego_speed"), 0.0)))
    nominal_dt = float(_find(config, ("dt", "timestep", "time_step"), 0.1))
    previous_time = None
    output = []
    for index, sensor in enumerate(sensor_rows):
        time = finite_cell(sensor, "time")
        if time is None:
            raise ValueError(f"non-finite time at sensor row {index}")
        if previous_time is not None and time <= previous_time:
            raise ValueError("sensor timestamps must be strictly increasing")
        dt = nominal_dt if previous_time is None else time - previous_time
        lead_speed = finite_cell(sensor, "lead_speed")
        distance = finite_cell(sensor, "distance")
        if lead_speed is None or distance is None:
            lead_speed, distance = None, None

        command, mode, distance_error = controller.compute(ego_speed, lead_speed, distance, dt)
        ttc = None
        if lead_speed is not None and ego_speed > lead_speed:
            ttc = distance / (ego_speed - lead_speed)
        output.append({
            "time": fmt(time), "ego_speed": fmt(ego_speed),
            "acceleration_cmd": fmt(command), "mode": mode,
            "distance_error": fmt(distance_error), "distance": fmt(distance), "ttc": fmt(ttc),
        })
        ego_speed = max(0.0, ego_speed + command * dt)
        previous_time = time

    names = ["time", "ego_speed", "acceleration_cmd", "mode", "distance_error", "distance", "ttc"]
    with open(args.output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(output)


if __name__ == "__main__":
    main()
