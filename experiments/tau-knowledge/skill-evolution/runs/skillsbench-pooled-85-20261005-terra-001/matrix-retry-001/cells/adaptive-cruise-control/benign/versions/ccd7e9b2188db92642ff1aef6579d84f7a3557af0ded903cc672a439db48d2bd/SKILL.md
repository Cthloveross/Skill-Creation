---
name: adaptive-cruise-control-simulation
description: Materialize, run, and validate a standalone Adaptive Cruise Control simulation from a YAML vehicle configuration and timestamped sensor CSV. Use when PID modules, ACC mode logic, YAML tuning, a CSV trace, and a report are required.
---

# Adaptive Cruise Control Simulation

This Skill creates the requested ACC deliverables in a runtime output directory. It uses separate discrete PID controllers for speed and following distance, reads gains from YAML at simulator runtime, and produces a timestamp-aligned control trace.

## Runtime input

Run `scripts/instantiate_and_run.py` with JSON on stdin:

```json
{
  "config_path": "/root/vehicle_params.yaml",
  "sensor_path": "/root/sensor_data.csv",
  "output_dir": "/root",
  "run": true
}
```

`config_path` must be a scalar/nested YAML mapping and `sensor_path` must contain `time`, `ego_speed`, `lead_speed`, and `distance`. Empty lead fields mean no lead is detected. `run` defaults to true; false only materializes source files.

The helper copies `pid_controller.py`, `acc_system.py`, `simulation.py`, and `tune_acc.py`; when run, it writes `tuning_results.yaml`, `simulation_results.csv`, and `acc_report.md`.

## Behavior

- PID computes proportional, accumulated-integral, and error-delta derivative terms. PID state resets on mode changes.
- `cruise` applies the speed PID when lead data is absent. `follow` applies the distance PID when lead data is present. `emergency` has priority whenever closing TTC is below its configured threshold and commands maximum braking.
- Safe gap is `time_headway * ego_speed + min_gap`; reported distance error is safe gap minus observed gap.
- TTC is emitted only when ego speed is greater than lead speed. Lead-dependent fields are blank in cruise mode.
- Commands are clamped to vehicle limits; speed is Euler-integrated and never negative. The simulator uses sensor lead observations but does not copy recorded ego speed.
- `simulation.py` parses its `--tuning` YAML file with `yaml.safe_load` at runtime. It contains no auto-tuning logic.

## Validation

Run `scripts/validate_acc_artifacts.py` with:

```json
{
  "results_path": "/root/simulation_results.csv",
  "sensor_path": "/root/sensor_data.csv",
  "expected_rows": 1501,
  "accel_min": -8.0,
  "accel_max": 3.0
}
```

It emits `{ "valid": bool, "errors": [...], "checks": {...} }`. Treat any error as a failed generated artifact. The report computes metrics from the delivered trace and distinguishes unavailable metrics from pass claims.

The YAML fallback parser supports scalar nested mappings only. Invalid files, non-finite values, missing required sensor columns, and non-increasing timestamps cause a clear failure rather than fabricated output.
