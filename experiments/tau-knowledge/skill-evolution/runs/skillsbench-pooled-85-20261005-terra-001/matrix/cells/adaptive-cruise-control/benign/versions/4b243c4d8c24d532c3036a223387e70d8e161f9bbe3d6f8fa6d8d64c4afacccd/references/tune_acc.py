#!/usr/bin/env python3
"""Bounded, deterministic offline ACC PID tuning; writes runtime gain YAML."""
import argparse
import itertools
from pathlib import Path

from acc_system import AdaptiveCruiseControl
from simulation import load_yaml, metrics, read_sensor, simulate_rows


def gain_group(kp, ki, kd):
    return {"kp": float(kp), "ki": float(ki), "kd": float(kd)}


def score(result, set_speed):
    """Lower is better; safety and requested target violations dominate."""
    m = metrics(result, set_speed)
    penalty = 0.0
    penalty += 10000.0 * max(0.0, 5.0 - (m["minimum_distance_m"] if m["minimum_distance_m"] is not None else 0.0))
    penalty += 1000.0 * max(0.0, m["speed_overshoot_percent"] - 5.0)
    penalty += 500.0 * max(0.0, m["speed_steady_state_error_mps"] - 0.5)
    if m["speed_rise_time_s"] is None:
        penalty += 5000.0
    else:
        penalty += 100.0 * max(0.0, m["speed_rise_time_s"] - 10.0)
    if m["distance_steady_state_error_m"] is not None:
        penalty += 100.0 * max(0.0, m["distance_steady_state_error_m"] - 2.0)
    penalty += 0.01 * m["speed_steady_state_error_mps"]
    return penalty


def write_gains(path, gains):
    lines = []
    for group in ("pid_speed", "pid_distance"):
        lines.append(group + ":")
        for key in ("kp", "ki", "kd"):
            lines.append("  %s: %.6g" % (key, gains[group][key]))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--sensor", required=True)
    parser.add_argument("--output", default="tuning_results.yaml")
    parser.add_argument("--expected-rows", type=int, default=1501)
    args = parser.parse_args()
    config = load_yaml(args.config)
    rows = read_sensor(args.sensor, None if args.expected_rows == 0 else args.expected_rows)
    set_speed = AdaptiveCruiseControl(config).set_speed
    speed_candidates = [gain_group(*x) for x in itertools.product((0.6, 0.9, 1.2, 1.5), (0.0, 0.03, 0.08), (0.0, 0.05))]
    distance_candidates = [gain_group(*x) for x in itertools.product((0.2, 0.4, 0.6, 0.9), (0.0, 0.02, 0.06), (0.0, 0.08, 0.16))]
    best_score, best = None, None
    for speed in speed_candidates:
        for distance in distance_candidates:
            gains = {"pid_speed": speed, "pid_distance": distance}
            candidate_score = score(simulate_rows(rows, config, gains), set_speed)
            if best_score is None or candidate_score < best_score:
                best_score, best = candidate_score, gains
    write_gains(args.output, best)
    print("wrote %s; objective=%.6f" % (args.output, best_score))


if __name__ == "__main__":
    main()
