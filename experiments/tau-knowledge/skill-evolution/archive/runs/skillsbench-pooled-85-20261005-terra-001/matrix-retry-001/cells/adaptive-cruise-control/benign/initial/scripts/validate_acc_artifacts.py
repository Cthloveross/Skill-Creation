#!/usr/bin/env python3
"""Validate a generated ACC result trace.

stdin JSON: {results_path, sensor_path?, expected_rows?, accel_min?, accel_max?}
stdout JSON: {valid, errors, checks}
"""
import csv
import json
import math
import sys
from pathlib import Path


def finite(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def main():
    req = json.load(sys.stdin)
    result_path = Path(req["results_path"])
    errors = []
    expected_header = ["time", "ego_speed", "acceleration_cmd", "mode", "distance_error", "distance", "ttc"]
    with result_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected_header:
            errors.append("CSV header/order does not exactly match the required schema")
        rows = list(reader)
    expected = req.get("expected_rows")
    if expected is None and req.get("sensor_path"):
        with Path(req["sensor_path"]).open(newline="", encoding="utf-8") as handle:
            expected = sum(1 for _ in csv.DictReader(handle))
    if expected is not None and len(rows) != int(expected):
        errors.append(f"row count {len(rows)} differs from expected {expected}")
    amin, amax = float(req.get("accel_min", -8.0)), float(req.get("accel_max", 3.0))
    previous_time = None
    numeric_rows = []
    for index, row in enumerate(rows):
        mode = row.get("mode")
        t, v, a = (finite(row.get(k)) for k in ("time", "ego_speed", "acceleration_cmd"))
        if None in (t, v, a):
            errors.append(f"row {index}: time, ego_speed, and acceleration_cmd must be finite")
            continue
        numeric_rows.append((t, v, a))
        if previous_time is not None and t <= previous_time:
            errors.append(f"row {index}: timestamps are not strictly increasing")
        previous_time = t
        if v < -1e-8:
            errors.append(f"row {index}: ego speed is negative")
        if a < amin - 1e-7 or a > amax + 1e-7:
            errors.append(f"row {index}: acceleration is outside configured limits")
        lead_fields = [row.get("distance_error", ""), row.get("distance", ""), row.get("ttc", "")]
        if mode not in ("cruise", "follow", "emergency"):
            errors.append(f"row {index}: invalid mode {mode!r}")
        elif mode == "cruise" and any(x.strip() for x in lead_fields):
            errors.append(f"row {index}: cruise row has lead-dependent fields")
        elif mode in ("follow", "emergency"):
            if finite(row.get("distance_error")) is None or finite(row.get("distance")) is None:
                errors.append(f"row {index}: lead mode requires finite distance and distance_error")
            if row.get("ttc", "").strip() and finite(row.get("ttc")) is None:
                errors.append(f"row {index}: TTC must be blank or finite")
    for i in range(len(numeric_rows) - 1):
        t, v, a = numeric_rows[i]
        nt, nv, _ = numeric_rows[i + 1]
        dt = nt - t
        expected_v = max(0.0, v + a * dt)
        if abs(nv - expected_v) > 2e-5:
            errors.append(f"rows {i}-{i+1}: ego-speed integration is inconsistent")
            break
    print(json.dumps({"valid": not errors, "errors": errors,
                      "checks": {"rows": len(rows), "header": expected_header,
                                 "acceleration_limits": [amin, amax]}}, allow_nan=False))


if __name__ == "__main__":
    main()
