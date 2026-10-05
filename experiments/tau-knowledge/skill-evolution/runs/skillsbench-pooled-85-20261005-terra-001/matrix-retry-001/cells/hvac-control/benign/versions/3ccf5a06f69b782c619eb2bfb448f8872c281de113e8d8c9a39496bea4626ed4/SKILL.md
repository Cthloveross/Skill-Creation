---
name: hvac-calibrate-tune-control
description: Run the supplied HVAC simulator to create calibration, first-order parameter-estimation, controller-tuning, closed-loop control, and trace-derived metric artifacts required for a 22 C room-temperature-control task.
---

# HVAC calibration and control

Use this Skill when `/root/hvac_simulator.py` and `/root/room_config.json` are supplied and the required deliverables are `calibration_log.json`, `estimated_params.json`, `tuned_gains.json`, `control_log.json`, and `metrics.json`.

## Required execution

Invoke the packaged script **through the runtime's skill-script interface** (do not enter `scripts/run_hvac_workflow.py` as a bare shell command). Pass this JSON object:

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "setpoint": 22.0,
  "control_duration_s": 240.0
}
```

The `/root` output directory is mandatory because the task verifier reads the five JSON files directly there. The script writes all five artifacts only from observations obtained by running a fresh supplied simulator for calibration and another fresh supplied simulator for control. Its stdout is a JSON manifest; require `"ok": true` before considering the task complete.

## Workflow implemented by the script

1. Record a 70-second calibration experiment at fixed sample cadence: a zero-power baseline, a bounded positive heater step, then cooldown. This produces more than 20 strictly ordered records with genuine heater excitation.
2. Fit the logged transitions to `T[k+1] = a*T[k] + b*u[k] + c`, converting the stable discrete model to positive first-order `K` and `tau`. Report regression `r_squared` and RMSE fitting error.
3. Derive finite nonnegative PI/PID-compatible gains using the identified first-order model and a positive IMC-style lambda.
4. Run a bounded PI control experiment at the requested setpoint. Commands are clamped to 0--100%, the integral state is conditionally updated to avoid windup, and every logged error is computed exactly as `setpoint - temperature`.
5. Derive all metrics from the saved control samples. Overshoot is fractional overshoot `(max_temp-setpoint)/setpoint`, clipped at zero. Settling is the first sample after which all remaining values are strictly inside ±0.5 C. Steady-state error is the mean absolute error over the final 20% of the trace.

The runtime adapter supports normal simulator classes/factories and common temperature/step method names. If the supplied API is nonstandard, provide only names verified in the supplied source via `adapter`, for example:

```json
{
  "output_dir": "/root",
  "adapter": {
    "class": "MySimulator",
    "temperature_method": "read_temperature",
    "step_method": "advance"
  }
}
```

## Output schemas

`calibration_log.json` is an object with `phase: "calibration"`, bounded `heater_power_test`, and `data` rows containing finite `time`, `temperature`, and `heater_power`.

`estimated_params.json` contains finite `K`, `tau`, `r_squared`, and `fitting_error`. `tuned_gains.json` contains finite nonnegative `Kp`, `Ki`, `Kd` and positive `lambda`.

`control_log.json` is an object with `phase: "control"`, `setpoint`, and rows containing finite `time`, `temperature`, `setpoint`, `heater_power`, and `error`. `metrics.json` contains finite `rise_time`, `overshoot`, `settling_time`, `steady_state_error`, and `max_temp`.

If the script reports an API or construction error, inspect the supplied simulator source, correct the adapter names or supplied paths, and rerun the complete workflow. Do not fabricate or hand-edit experiment records.
