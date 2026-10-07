---
name: hvac-calibrate-tune-control
description: Run a bounded HVAC calibration, identify a first-order thermal model, tune a PI/PID controller, and write validated trace-derived JSON deliverables using a supplied read-only Python HVAC simulator.
---

# HVAC calibration, identification, and control

Use this Skill when `/root/hvac_simulator.py` and `/root/room_config.json` are supplied and the task requires these files directly in `/root`:

- `calibration_log.json`
- `estimated_params.json`
- `tuned_gains.json`
- `control_log.json`
- `metrics.json`

The simulator and configuration are immutable public inputs. Do not edit, replace, or write either file.

Run `scripts/run_hvac_workflow.py` with the Skill script runner. Send `{}` on stdin for the default task paths and a 22.0 C setpoint:

```json
{}
```

Optional JSON input schema:

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "setpoint": 22.0,
  "sample_dt": 0.5,
  "control_duration_s": 180.0,
  "calibration_power": 50.0,
  "adapter": {
    "class": "optional verified simulator class name",
    "temperature_method": "optional verified temperature reader",
    "temperature_attr": "optional verified temperature attribute",
    "heater_setter": "optional verified heater setter",
    "step_method": "optional verified step method"
  }
}
```

The script emits one JSON status object on stdout. A successful result has `ok: true` and lists the five written files. An `ok: false` result means no completion claim should be made; correct only the supplied adapter information when the simulator has a nonstandard public API, then rerun.

## Workflow

1. Use a fresh simulator instance for a 70-second baseline/positive-step/cooldown calibration. The calibration log contains the actual measured temperature, ordered simulation time, and the command applied over each following interval.
2. Fit the affine discrete transition `T[n+1] = a*T[n] + b*u[n] + c` by least squares. Convert it to `K=b/(1-a)` and `tau=-dt/log(a)`, and save transition RMSE and R-squared from the recorded calibration observations.
3. Derive two conservative IMC/PI candidates from the fitted model and execute them on fresh simulator instances. This intentionally uses only a small fixed number of actual trials so the complete workflow remains within the task time budget. Select the best measured compliant trace.
4. Log every closed-loop sample at a 22.0 C setpoint with a clamped 0--100% heater command and conditional anti-windup. The logged error is computed exactly as `setpoint - temperature`.
5. Derive all reported metrics from the selected saved trace: 90% rise time, normalized overshoot, final-20% mean absolute steady-state error, maximum temperature, and first sustained strict ±0.5 C settling time.

Before reporting success, the workflow checks finite values, strict ordering, calibration excitation and duration, positive fitted thermal parameters, command limits, at least 150 seconds of control data, trace/model consistency, and the requested performance limits.
