#!/usr/bin/env python3
"""Validate a generated ACC trace.
stdin: {results_path, sensor_path?, expected_rows?, accel_min?, accel_max?}
stdout: {valid, errors, checks}
"""
import csv
import json
import math
import sys
from pathlib import Path


def finite(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def main():
    request = json.load(sys.stdin)
    expected_header = ["time", "ego_speed", "acceleration_cmd", "mode", "distance_error", "distance", "ttc"]
    errors = []
    with Path(request["results_path"]).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected_header:
            errors.append("CSV header/order does not match required schema")
        rows = list(reader)
    expected_rows = request.get("expected_rows")
    if expected_rows is None and request.get("sensor_path"):
        with Path(request["sensor_path"]).open(newline="", encoding="utf-8") as handle:
            expected_rows = sum(1 for _ in csv.DictReader(handle))
    if expected_rows is not None and len(rows) != int(expected_rows):
        errors.append(f"row count {len(rows)} differs from expected {expected_rows}")
    amin, amax = float(request.get("accel_min", -8.0)), float(request.get("accel_max", 3.0))
    prior = None
    numeric = []
    for index, row in enumerate(rows):
        time, speed, accel = (finite(row.get(key)) for key in ("time", "ego_speed", "acceleration_cmd"))
        if None in (time, speed, accel):
            errors.append(f"row {index}: time, ego_speed, acceleration_cmd must be finite")
            continue
        if prior is not None and time <= prior:
            errors.append(f"row {index}: time is not strictly increasing")
        prior = time
        numeric.append((time, speed, accel))
        if speed < 0 or not amin - 1e-8 <= accel <= amax + 1e-8:
            errors.append(f"row {index}: physical limit violation")
        mode = row.get("mode")
        fields = [row.get(key, "") for key in ("distance_error", "distance", "ttc")]
        if mode not in ("cruise", "follow", "emergency"):
            errors.append(f"row {index}: invalid mode")
        elif mode == "cruise" and any(value.strip() for value in fields):
            errors.append(f"row {index}: cruise has lead fields")
        elif mode != "cruise" and (finite(row.get("distance_error")) is None or finite(row.get("distance")) is None):
            errors.append(f"row {index}: lead mode lacks distance fields")
    for index in range(len(numeric) - 1):
        time, speed, accel = numeric[index]
        next_time, next_speed, _ = numeric[index + 1]
        if abs(next_speed - max(0.0, speed + accel * (next_time - time))) > 2e-5:
            errors.append(f"rows {index}-{index + 1}: Euler integration mismatch")
            break
    print(json.dumps({"valid": not errors, "errors": errors,
                      "checks": {"rows": len(rows), "header": expected_header,
                                 "acceleration_limits": [amin, amax]}}, allow_nan=False))


if __name__ == "__main__":
    main()
