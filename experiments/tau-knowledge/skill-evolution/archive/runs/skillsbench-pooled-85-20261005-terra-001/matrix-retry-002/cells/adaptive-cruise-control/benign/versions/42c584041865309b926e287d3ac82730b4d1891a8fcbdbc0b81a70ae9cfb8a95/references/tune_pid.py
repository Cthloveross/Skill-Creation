#!/usr/bin/env python3
"""Deterministically select bounded ACC PID gains from the supplied trace."""
import argparse
from pathlib import Path

import yaml

from simulation import config_with_gains, load_rows, simulate_rows


def set_speed_from(config):
    settings = config.get("acc_settings", {}) if isinstance(config, dict) else {}
    return float(settings.get("set_speed", config.get("set_speed", 30.0)))


def speed_score(trace, rows, target):
    """Favor prompt, non-overshooting behavior in the initial no-lead segment."""
    initial = []
    for sensor, row in zip(rows, trace):
        if sensor["lead_speed"] is not None:
            break
        initial.append(row)
    if not initial:
        return 0.0
    reached = next((row["time"] for row in initial if row["ego_speed"] >= 0.9 * target), None)
    maximum = max(row["ego_speed"] for row in initial)
    tracking = sum((target - row["ego_speed"]) ** 2 for row in initial) / len(initial)
    late_penalty = 100000.0 if reached is None or reached >= 10.0 else 0.0
    overshoot_penalty = 100000.0 * max(0.0, maximum - 1.05 * target) ** 2
    return tracking + late_penalty + overshoot_penalty


def distance_score(trace):
    """Favor low gap-error commands without treating immutable sensor gaps as controllable."""
    follow = [row for row in trace if row["mode"] in ("follow", "emergency")]
    commands = [row["acceleration_cmd"] for row in trace]
    error = sum(row["distance_error"] ** 2 for row in follow) / max(1, len(follow))
    roughness = sum((commands[i] - commands[i - 1]) ** 2 for i in range(1, len(commands))) / max(1, len(commands) - 1)
    return error + 0.02 * roughness


def gains(values):
    return dict(zip(("kp", "ki", "kd"), values))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    rows = load_rows(args.sensor)
    # The no-drag plant needs no integral action; zero derivative avoids initial kick.
    speed_candidates = [(1.0, 0.0, 0.0), (1.5, 0.0, 0.0), (2.0, 0.0, 0.0)]
    distance_candidates = [(0.20, 0.0, 0.0), (0.35, 0.0, 0.0), (0.50, 0.0, 0.0)]
    provisional_distance = gains((0.35, 0.0, 0.0))
    target = set_speed_from(config)
    best_speed_values = min(
        speed_candidates,
        key=lambda candidate: speed_score(
            simulate_rows(rows, config_with_gains(config, {"pid_speed": gains(candidate), "pid_distance": provisional_distance})),
            rows,
            target,
        ),
    )
    best_speed = gains(best_speed_values)
    best_distance_values = min(
        distance_candidates,
        key=lambda candidate: distance_score(
            simulate_rows(rows, config_with_gains(config, {"pid_speed": best_speed, "pid_distance": gains(candidate)}))
        ),
    )
    result = {"pid_speed": best_speed, "pid_distance": gains(best_distance_values)}
    text = yaml.safe_dump(result, sort_keys=False)
    Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
