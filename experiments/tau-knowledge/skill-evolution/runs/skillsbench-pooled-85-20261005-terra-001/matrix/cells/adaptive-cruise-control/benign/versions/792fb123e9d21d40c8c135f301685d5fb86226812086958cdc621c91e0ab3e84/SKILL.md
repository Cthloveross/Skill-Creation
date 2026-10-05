---
name: adaptive-cruise-control-simulation
description: Build, tune, run, and validate a discrete-time Adaptive Cruise Control (ACC) simulation from a YAML vehicle/ACC configuration and timestamped sensor CSV. Use when deliverables must include PID and ACC Python modules, runtime-loaded gain YAML, an aligned simulation CSV, and an ACC performance report.
---

# Adaptive Cruise Control Simulation

This Skill materializes a self-contained ACC project and runs it against the supplied public input files. The project implements separate PID speed and gap controllers, mode priority (`emergency`, `follow`, `cruise`), time-headway spacing, TTC-triggered emergency braking, acceleration saturation, controller reset on mode changes, and Euler longitudinal dynamics.

## Inputs

- A YAML configuration such as `/root/vehicle_params.yaml`. Configuration names may be nested; common names including `acc_settings.set_speed`, `time_headway`, `min_gap`, acceleration limits, and emergency TTC threshold are recognized. Public task defaults are used only if a setting is absent.
- A CSV such as `/root/sensor_data.csv` with `time`, `ego_speed`, `lead_speed`, and `distance` columns. Blank lead fields mean no lead vehicle.

The recorded ego speed is used only as the initial condition. Subsequent ego speeds are integrated from ACC commands. On a no-lead to lead transition, the sensor distance initializes the simulated gap; while the lead persists, gap is propagated from lead-relative velocity.

## Procedure

1. Materialize the project into the task work directory:

   ```bash
   python /path/to/skill/scripts/materialize_acc_project.py <<'JSON'
   {"destination":"/root"}
   JSON
   ```

   This writes `pid_controller.py`, `acc_system.py`, `simulation.py`, and `tune_acc.py` without modifying either input file.

2. Tune gains into the required runtime configuration. Tuning is deliberately separate from simulation; `simulation.py` never auto-tunes.

   ```bash
   cd /root
   python tune_acc.py --config vehicle_params.yaml --sensor sensor_data.csv --output tuning_results.yaml
   ```

   The tuner makes a deterministic bounded search. All emitted `kp` values are strictly between 0 and 10 and `ki`/`kd` values are in `[0, 5)`.

3. Run the final 150-second simulation and report:

   ```bash
   python simulation.py --config vehicle_params.yaml --gains tuning_results.yaml \
     --sensor sensor_data.csv --output simulation_results.csv --report acc_report.md \
     --expected-rows 1501
   ```

## Produced artifact semantics

`simulation_results.csv` has exactly this column order:

`time,ego_speed,acceleration_cmd,mode,distance_error,distance,ttc`

A row logs the current state and command before its Euler update. Cruise rows leave distance-related fields blank. TTC is blank unless a lead exists and the simulated ego vehicle is closing on it. `distance_error` is `safe_gap - actual_gap`; positive means too close. The follow controller negates its PID output so positive gap error commands braking. Every command is clamped to the configured physical interval and speed is clamped nonnegative.

The report includes the requested System design, PID tuning methodology and final gains, and Simulation results and performance metrics sections. Metrics are trace-derived: first 90%-set-speed crossing, maximum speed overshoot, final-window speed error, final-window distance error when lead data exists, minimum lead gap, and duration/row count.

## Validation and failure handling

`simulation.py` rejects malformed/missing columns, non-increasing time, nonpositive timestep, missing gains, invalid gain ranges, non-finite numeric values, and (when `--expected-rows 1501` is supplied) an input row count other than 1501. It reopens the written CSV and verifies header, row count, time alignment, finite required values, allowed modes, acceleration limits, nonnegative speed, and blank-field semantics before writing the report. A target miss is reported as a metric status, not concealed or fabricated; the data-driven lead scenario can make all targets infeasible.

Do not replace the runtime gains with hard-coded values in `simulation.py`, do not copy the sensor ego-speed trajectory after initialization, and do not report TTC for non-closing traffic.
