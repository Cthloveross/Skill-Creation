---
name: hvac-calibrate-tune-control
description: Generate and validate calibration, identified-model, PID-tuning, bounded closed-loop HVAC, and trace-derived metric JSON artifacts for a supplied room-heating simulator.
---

# HVAC calibration, tuning, and control

Use this Skill for a task that supplies an HVAC simulator and room configuration and requires these files in the task work directory:

- `calibration_log.json`
- `estimated_params.json`
- `tuned_gains.json`
- `control_log.json`
- `metrics.json`

## Run the workflow

Run `scripts/run_hvac_workflow.py` with the executor's packaged-script runner. It receives one JSON object on stdin and emits one JSON manifest on stdout. For the supplied task files, use:

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "setpoint": 22.0,
  "control_duration_s": 240.0
}
```

The script imports and executes the supplied simulator; it does not synthesize a thermal trace. It supports common simulator constructors, temperature accessors, direct `step(power, dt)` APIs, and separate heater-setter plus time-advance APIs. If it reports an unsupported API, inspect the supplied simulator source and pass an `adapter` with its verified names:

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "adapter": {
    "class": "HVACSimulator",
    "temperature_method": "get_temperature",
    "step_method": "step",
    "heater_setter": "set_heater_power"
  }
}
```

`output_dir` must be `/root` when the evaluator reads `/root/*.json`. Check the returned manifest has `"ok": true`, all five names in `files`, and `"targets_met": true` before considering the task complete.

## Method

1. The workflow records a 70-second experiment at a fixed cadence, including a zero-power baseline, positive bounded heater step, and cooldown. Every calibration record is measured before applying its logged command.
2. It identifies a stable first-order discrete model from the measured transitions and converts it to positive process gain `K` and time constant `tau`. It reports regression R-squared and RMSE from the calibration observations.
3. It derives PI-compatible IMC-style gains from that model, then evaluates several model-derived response-speed choices in fresh simulator runs. The best safe, settled trace is retained. Heater commands are always clamped to 0--100%, and conditional integration prevents windup during saturation.
4. It runs at least 150 seconds of closed-loop control at the requested setpoint. Each saved error is calculated directly as `setpoint - temperature`.
5. It computes metrics only from the delivered control trace. Overshoot is fractional `(max_temp - setpoint) / setpoint`, floored at zero. Settling is the first time after which all saved samples remain strictly within ±0.5 C. Steady-state error is mean absolute error over the final 20% of samples.

## Artifacts and validation

`calibration_log.json` contains `phase: "calibration"`, `heater_power_test`, and finite, time-ordered `data` records with `time`, `temperature`, and `heater_power`.

`estimated_params.json` contains finite positive `K` and `tau`, an `r_squared` in `[0, 1]`, and nonnegative `fitting_error`. `tuned_gains.json` contains finite nonnegative `Kp`, `Ki`, `Kd`, plus positive `lambda`.

`control_log.json` contains `phase: "control"`, a 22.0 setpoint, and finite, strictly ordered rows with `time`, `temperature`, `setpoint`, bounded `heater_power`, and exact `error`. `metrics.json` contains finite `rise_time`, `overshoot`, `settling_time`, `steady_state_error`, and `max_temp` computed from that control file.

If targets are not met, do not hand-edit measurements. Use the manifest diagnostics, verify the simulator adapter and configuration, then rerun the complete workflow with a longer `control_duration_s` or an explicitly supported `sample_dt`.
