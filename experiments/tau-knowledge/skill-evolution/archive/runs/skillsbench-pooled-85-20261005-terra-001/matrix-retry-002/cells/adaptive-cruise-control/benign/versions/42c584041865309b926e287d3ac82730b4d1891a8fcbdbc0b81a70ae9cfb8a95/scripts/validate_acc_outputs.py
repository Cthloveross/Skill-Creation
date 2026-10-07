#!/usr/bin/env python3
"""Validate ACC result and tuning files.
stdin: {results_csv, tuning_yaml, required_rows}
stdout: {valid, errors, rows, modes}
"""
import csv
import json
import math
import sys
from pathlib import Path

import yaml

COLUMNS = ["time", "ego_speed", "acceleration_cmd", "mode", "distance_error", "distance", "ttc"]


def finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def main():
    request = json.load(sys.stdin)
    errors = []
    modes = {}
    rows = 0
    previous_time = None
    try:
        with open(request["results_csv"], newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != COLUMNS:
                errors.append("result CSV columns must be exactly " + ",".join(COLUMNS))
            for line, row in enumerate(reader, 2):
                rows += 1
                if None in row:
                    errors.append(f"row {line}: malformed column count")
                    continue
                for key in ("time", "ego_speed", "acceleration_cmd"):
                    if not finite(row[key]):
                        errors.append(f"row {line}: {key} must be finite")
                if finite(row["time"]):
                    now = float(row["time"])
                    if previous_time is not None and now <= previous_time:
                        errors.append(f"row {line}: time is not strictly increasing")
                    previous_time = now
                if finite(row["ego_speed"]) and float(row["ego_speed"]) < 0:
                    errors.append(f"row {line}: negative ego speed")
                if finite(row["acceleration_cmd"]) and not -8.000001 <= float(row["acceleration_cmd"]) <= 3.000001:
                    errors.append(f"row {line}: acceleration outside stated physical bounds")
                mode = row["mode"]
                modes[mode] = modes.get(mode, 0) + 1
                if mode not in {"cruise", "follow", "emergency"}:
                    errors.append(f"row {line}: invalid mode")
                lead_values = (row["distance_error"], row["distance"], row["ttc"])
                if mode == "cruise" and any(value.strip() for value in lead_values):
                    errors.append(f"row {line}: cruise lead fields must be blank")
                if mode in {"follow", "emergency"}:
                    if not row["distance_error"].strip() or not row["distance"].strip():
                        errors.append(f"row {line}: lead mode needs distance fields")
                    for key in ("distance_error", "distance", "ttc"):
                        if row[key].strip() and not finite(row[key]):
                            errors.append(f"row {line}: {key} must be finite or blank")
    except Exception as exc:
        errors.append("unable to read result CSV: " + str(exc))

    if rows != int(request.get("required_rows", 1501)):
        errors.append(f"expected {request.get('required_rows', 1501)} data rows, found {rows}")

    try:
        data = yaml.safe_load(Path(request["tuning_yaml"]).read_text(encoding="utf-8"))
        for section in ("pid_speed", "pid_distance"):
            if not isinstance(data, dict) or not isinstance(data.get(section), dict):
                errors.append("missing tuning section " + section)
                continue
            for key in ("kp", "ki", "kd"):
                value = data[section].get(key)
                if not finite(value):
                    errors.append(f"{section}.{key} must be finite")
                    continue
                value = float(value)
                if key == "kp" and not 0 < value < 10:
                    errors.append(f"{section}.kp outside (0,10)")
                if key in {"ki", "kd"} and not 0 <= value < 5:
                    errors.append(f"{section}.{key} outside [0,5)")
    except Exception as exc:
        errors.append("unable to read tuning YAML: " + str(exc))

    print(json.dumps({"valid": not errors, "errors": errors, "rows": rows, "modes": modes}, sort_keys=True))


if __name__ == "__main__":
    main()
