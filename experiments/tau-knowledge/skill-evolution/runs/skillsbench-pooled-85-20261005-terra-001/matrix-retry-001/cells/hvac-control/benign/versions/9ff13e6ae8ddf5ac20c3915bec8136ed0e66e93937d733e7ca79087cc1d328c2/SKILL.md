---
name: hvac-calibrate-tune-control
description: Run a supplied HVAC room simulator to create calibration, first-order model identification, PID tuning, bounded closed-loop temperature-control, and trace-derived JSON deliverables.
---

# HVAC calibration, tuning, and control

Use this Skill when a task provides an HVAC simulator plus room configuration and requires these deliverables in its work directory:

- `calibration_log.json`
- `estimated_params.json`
- `tuned_gains.json`
- `control_log.json`
- `metrics.json`

## Execute

Run the packaged Python entrypoint from the task environment. It reads one JSON object from standard input and writes a result manifest to standard output; the five required artifacts are written directly under `output_dir`.

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "setpoint": 22.0,
  "control_duration_s": 240.0
}
```

For example, invoke `scripts/run_hvac_workflow.py` with the executor's packaged-script runner, supplying the JSON above on stdin. Do not stop after inspecting the manifest: confirm that it reports `ok: true`, `targets_met: true`, and all five expected artifact names. The evaluator reads `/root`, so `output_dir` must be `/root` for this task.

The optional inputs are:

- `sample_dt`: positive logging/control period in seconds. By default, the workflow uses a positive timestep found in the room configuration, otherwise `0.5`.
- `calibration_power`: heater step percentage, clamped to `2..100`; defaults to `50`.
- `adapter`: names for a nonstandard simulator API. Supported keys are `class`, `temperature_method`, `temperature_attr`, `step_method`, and `heater_setter`.

For a simulator with conventional `HVACSimulator`, `get_temperature`, `set_heater_power`, and `step` or `update` methods, no adapter is needed. If source inspection establishes different names, supply only verified names, for example:

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "adapter": {
    "class": "HVACSimulator",
    "temperature_method": "get_temperature",
    "heater_setter": "set_heater_power",
    "step_method": "update"
  }
}
```

## Workflow

1. Instantiate a fresh simulator and record an 80-second calibration experiment. It includes a zero-power baseline, a bounded positive heater step, and a cooldown, with time, observed temperature, and actually applied heater command at every sample.
2. Fit a discrete first-order affine response from consecutive calibration observations. Convert it to finite positive process gain `K` and time constant `tau`; report in-sample R-squared and RMSE as `fitting_error`.
3. Derive PI/PID-compatible IMC-style candidate gains from the fitted model. Evaluate several model-derived response speeds in fresh simulator instances, using bounded commands, feed-forward from the fitted equilibrium, and conditional integral anti-windup.
4. Save the safest best candidate's real closed-loop trace, at the requested 22 C setpoint, for no less than 150 seconds.
5. Derive all reported performance values from the saved trace. Overshoot is `max(0, (max_temp - setpoint) / setpoint)`. Settling time is the first logged time after which every remaining sample lies strictly within ±0.5 C. Steady-state error is the final 20% mean absolute error.

## Output contract and checks

The script validates finite numbers, increasing time, heater bounds, exact logged error (`setpoint - temperature`), trace duration, and the requested limits before reporting success. `metrics.json` is calculated from `control_log.json`, not from nominal model behavior.

If the manifest reports an unsupported simulator interface or targets are not met, inspect the actual supplied simulator/configuration, correct an adapter only where necessary, and rerun the entire workflow. Do not fabricate or hand-edit measurement records or metrics.
