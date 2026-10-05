---
name: hvac-calibrate-tune-control
description: Generate and validate calibration, first-order thermal-identification, PID-gain, closed-loop-control, and trace-derived metric JSON artifacts for the supplied HVAC simulator. Use for tasks requiring calibration_log.json, estimated_params.json, tuned_gains.json, control_log.json, and metrics.json in /root.
---

# HVAC calibration and control workflow

Use this Skill when a supplied Python room/HVAC simulator must be calibrated and controlled at a specified temperature setpoint. The workflow runs the real simulator, records its observations, fits a constrained first-order model, derives bounded PI/PID gains, and computes metrics solely from the emitted control trace.

## Required execution

Run `scripts/run_hvac_workflow.py` through the runtime's packaged-script interface with JSON stdin. **Use `/root` as `output_dir`**, because the task verifier reads the five deliverables directly from `/root`.

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "setpoint": 22.0,
  "control_duration_s": 210.0
}
```

The script receives one JSON object on stdin and emits a JSON manifest on stdout. On success, confirm its `ok` field is true. It writes:

* `/root/calibration_log.json`
* `/root/estimated_params.json`
* `/root/tuned_gains.json`
* `/root/control_log.json`
* `/root/metrics.json`

Do not merely run the script with its default relative output directory: that can place artifacts outside the verifier's required location.

## Method

The script constructs a fresh simulator for calibration and a separate fresh simulator for the closed-loop run, so calibration heating does not contaminate the control initial condition. Calibration records a zero-power baseline, a bounded heater step, and a cooldown at a fixed cadence. It always records more than 20 ordered samples spanning more than 30 seconds, with deliberate 0-to-positive-power excitation.

It fits the data to the discrete first-order relation `T[k+1] = a*T[k] + b*u[k] + c`, converts it into positive continuous-time gain `K` and time constant `tau`, and reports fit quality. A physically constrained fallback is used only when noisy regression produces an invalid heating gain. Tuning uses an IMC-inspired PI design, with an equilibrium heater feed-forward term, conditional-integration anti-windup, and strict 0--100% command clamping.

Control rows describe the simulated temperature before the logged heater command is applied. Every row contains finite `time`, `temperature`, `setpoint`, `heater_power`, and `error`; error is exactly `setpoint - temperature`.

`metrics.json` is recomputed from `control_log.json`: rise time is the first 90% response crossing, overshoot is `max(0, max_temperature - setpoint) / setpoint`, settling time is the first point after which all samples remain strictly within 0.5 C, steady-state error is the mean absolute error over the final 20% of samples (at least 30 seconds), and max_temp is the trace maximum.

## Simulator compatibility and failures

The adapter supports common Python simulator APIs: factories/classes such as `HVACSimulator`, `RoomSimulator`, or `create_simulator`; temperature methods/attributes such as `get_temperature` or `temperature`; and step methods such as `step`, `update`, or `run_step`. It passes a room-config dictionary, config path, keyword-expanded configuration, or no arguments as appropriate.

If the supplied simulator uses nonstandard names, pass an `adapter` mapping in the input, for example:

```json
{
  "output_dir": "/root",
  "adapter": {
    "class": "MyRoom",
    "temperature_attr": "current_temperature",
    "step_method": "advance",
    "time_attr": "simulation_time"
  }
}
```

If the workflow reports a simulator API error, inspect only the supplied simulator and provide names that it actually exposes; never invent observations or hand-edit output artifacts.

## Validation

After successful generation, run `scripts/validate_hvac_artifacts.py` with:

```json
{"output_dir":"/root","setpoint":22.0,"min_control_duration_s":150.0}
```

It emits a JSON report with `valid: true` only when all required artifacts exist, are valid and internally consistent, have ordered finite data, meet calibration/control duration and actuator constraints, and their metrics match the saved control trace. If validation fails, correct the invocation or API adapter and rerun the complete workflow to `/root`.
