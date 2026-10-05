---
name: hvac-calibrate-tune-control
description: Execute a supplied HVAC simulator to perform a real heater-excitation calibration, identify a stable first-order thermal model, tune bounded PI/PID gains, and write trace-derived control artifacts.
---

# HVAC calibration, identification, and control

Use this Skill when an HVAC simulator and room configuration are supplied and the task requires these JSON files in the task work directory:

- `calibration_log.json`
- `estimated_params.json`
- `tuned_gains.json`
- `control_log.json`
- `metrics.json`

The entrypoint uses only the supplied simulator for temperature observations. It creates fresh simulator instances for calibration and each control candidate, clamps heater commands to 0–100%, and selects a model-derived candidate from actual simulated traces.

## Run

Run the script with Python, not as a shell executable. With no standard input it uses the task defaults `/root/hvac_simulator.py`, `/root/room_config.json`, and writes directly to `/root`:

```sh
python3 scripts/run_hvac_workflow.py
```

A JSON request may be supplied on stdin when paths or timing differ:

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "setpoint": 22.0,
  "control_duration_s": 240.0,
  "sample_dt": 0.5,
  "calibration_power": 50.0
}
```

The script reads one JSON object from stdin (or an empty stdin for defaults) and emits one JSON result object on stdout:

```json
{"ok": true, "targets_met": true, "files": ["calibration_log.json", "estimated_params.json", "tuned_gains.json", "control_log.json", "metrics.json"], "metrics": {}}
```

For this task, `output_dir` must be `/root`, because the evaluator reads the artifacts there. Check that `ok`, `targets_met`, and all five names are present after execution.

## Method

1. The script records an 80-second calibration trace with an initial zero-power baseline, a positive step excitation, and a zero-power cooldown. Every row contains the simulator-observed temperature and the applied bounded heater command.
2. It fits the sampled affine first-order relation `T[k+1] = a*T[k] + b*u[k] + c`, converts it to positive process gain `K` and time constant `tau`, and reports in-sample R-squared and RMSE.
3. It derives IMC-style PI gains for several response-time multipliers, adds equilibrium feed-forward estimated from the fitted ambient temperature, and applies conditional anti-windup during each real candidate simulation.
4. It saves the best actual trace at the requested setpoint. All control rows log `error` exactly as `setpoint - temperature`.
5. It computes metrics from the saved trace: overshoot is `max(0, (max_temp - setpoint) / setpoint)`, steady-state error is the final 20% mean absolute error, and settling time is the first time after which all remaining samples are strictly within ±0.5 C.

The script validates finite values, time ordering, durations, actuator limits, trace consistency, and target thresholds before declaring the result successful. If the simulator uses nonconventional names, inspect its public source and pass an `adapter` object with verified `class`, `temperature_method`, `temperature_attr`, `heater_setter`, or `step_method` names. Do not invent records or hand-edit metrics.
