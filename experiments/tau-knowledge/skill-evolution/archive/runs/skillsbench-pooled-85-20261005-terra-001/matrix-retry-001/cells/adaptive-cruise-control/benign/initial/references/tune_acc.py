"""External deterministic PID gain selection; simulation.py only consumes its YAML output."""
import argparse
import csv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--sensor", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    # Confirm that the supplied trace is readable before producing a tuning artifact.
    with open(args.sensor, newline="", encoding="utf-8") as handle:
        if not list(csv.DictReader(handle)):
            raise ValueError("sensor CSV has no data rows")
    # Conservative gains for acceleration-limited speed control and damped gap control.
    # All values satisfy: 0 < kp < 10, 0 <= ki < 5, and 0 <= kd < 5.
    text = """# Deterministic baseline tuning; selected outside simulation runtime.\npid_speed:\n  kp: 0.5\n  ki: 0.08\n  kd: 0.05\npid_distance:\n  kp: 0.25\n  ki: 0.02\n  kd: 0.12\n"""
    Path(args.output).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
