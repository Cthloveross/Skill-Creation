"""Separate deterministic gain-selection step; simulation.py only consumes YAML."""
import argparse
import csv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--sensor", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.sensor, newline="", encoding="utf-8") as handle:
        if not list(csv.DictReader(handle)):
            raise ValueError("sensor CSV has no data rows")
    Path(args.output).write_text(
        """# Conservative acceleration-limited ACC gains.
pid_speed:
  kp: 0.5
  ki: 0.08
  kd: 0.05
pid_distance:
  kp: 0.25
  ki: 0.02
  kd: 0.12
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
