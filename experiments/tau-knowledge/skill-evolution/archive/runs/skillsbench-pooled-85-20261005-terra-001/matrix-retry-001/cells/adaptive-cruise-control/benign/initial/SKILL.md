---
name: adaptive-cruise-control-simulation
description: Build, run, and validate a file-based Adaptive Cruise Control (ACC) simulation from a YAML vehicle configuration and timestamped sensor CSV. Use when the deliverables include PID and ACC Python modules, tuned gains, a result trace, and a performance report.
---

# Adaptive Cruise Control Simulation

This Skill materializes a standalone ACC project and executes it against runtime-supplied inputs. It implements discrete PID control, cruise/follow/emergency mode priority, time-headway gap policy, TTC safety braking, acceleration and non-negative-speed limits, and CSV/report validation.

## Inputs

The instantiation helper reads JSON from stdin:

```json
{
  "config_path": "/root/vehicle_params.yaml",
  "sensor_path": "/root/sensor_data.csv",
  "output_dir": "/root",
  "run": true
}
```

- `config_path` is a YAML mapping containing ACC and vehicle settings. Nested mappings are supported. Common setting names such as `set_speed`, `time_headway`, `min_gap`/`min_distance`, `emergency_ttc_threshold`, `max_acceleration`, `max_deceleration`, `min_acceleration`, `dt`, and `initial_speed` are recognized.
- `sensor_path` is a CSV with `time`, `ego_speed`, `lead_speed`, and `distance`. The recorded ego speed is not reused after initialization; the generated trajectory is integrated from the configured initial speed (default 0 m/s).
- `output_dir` receives all requested task artifacts.
- `run` defaults to `true`. Set it to false only to materialize the source project without executing it.

Run `scripts/instantiate_and_run.py` through the Skill runtime. It copies the supplied project templates, runs `tune_acc.py` to create `tuning_results.yaml`, then runs `simulation.py` to create `simulation_results.csv`, and finally writes `acc_report.md`.

The generated project contains:

- `pid_controller.py` — `PIDController(kp, ki, kd)`, `reset()`, and `compute(error, dt)`.
- `acc_system.py` — `AdaptiveCruiseControl(config)` and `compute(ego_speed, lead_speed, distance, dt)` returning `(acceleration_cmd, mode, distance_error)`.
- `tune_acc.py` — a separate gain-selection step. `simulation.py` never embeds tuning and always loads `tuning_results.yaml` at runtime.
- `simulation.py` — standalone runtime simulation command.
- `tuning_results.yaml`, `simulation_results.csv`, and `acc_report.md`.

## Control semantics

1. A detected lead requires finite lead speed and distance. Missing lead data selects `cruise` and leaves all lead-dependent result fields blank.
2. For a detected lead, TTC is defined only for positive closing speed. `emergency` has highest priority when TTC is below the configured threshold; it commands maximum configured braking.
3. Otherwise `follow` uses `safe_gap = time_headway * ego_speed + min_gap`. The reported distance error is `safe_gap - measured_gap`, so a positive error means the vehicle is too close. The distance PID output is negated to obtain an acceleration command.
4. `cruise` uses the speed PID. In follow mode, positive acceleration is additionally capped by a speed-setpoint ceiling, so following cannot drive the vehicle above the configured set speed.
5. On a mode transition both controller states are reset. Commands are clamped to configured physical acceleration limits and Euler integration clamps speed at zero.
6. Each output row reports the state before its command is integrated, at exactly the corresponding input timestamp. Lead measurements are treated as current sensor observations; they are never inferred from recorded ego speed.

## Verify the result

After materialization, validate the actual generated files with `scripts/validate_acc_artifacts.py`. Its JSON input is:

```json
{
  "results_path": "/root/simulation_results.csv",
  "sensor_path": "/root/sensor_data.csv",
  "expected_rows": 1501,
  "accel_min": -8.0,
  "accel_max": 3.0
}
```

It emits JSON with `valid`, `errors`, and computed checks. It verifies the exact result header, row count, ordered finite timestamps, valid modes, blank/defined lead fields, acceleration limits, and Euler consistency between adjacent ego-speed rows. Treat any nonempty `errors` list as a failed artifact that must be corrected and regenerated.

The generated Markdown report explicitly states its metric windows and reports numeric metrics only when the applicable cruise/follow samples exist. Do not claim a target passes merely because the trace was produced; inspect the report and validator output.

## Limitations and handling

The supplied YAML reader intentionally supports the scalar nested-mapping format used for vehicle parameter files; YAML lists, anchors, and multiline scalars are unsupported. If configuration uses those features, normalize it to scalar mappings before running. The sensor CSV must have the four named columns and monotonically increasing finite timestamps. Invalid or missing mandatory files cause the helper to emit a JSON error rather than silently fabricate an output.
