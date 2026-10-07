---
name: hvac-calibrate-tune-control
description: Run a supplied Python HVAC simulator to collect a real heater-excitation calibration, identify a first-order thermal model, tune a bounded feedback controller, and generate the five JSON HVAC control deliverables.
---

# HVAC calibration, identification, and control

Use this Skill for a supplied HVAC simulator and room configuration when the required deliverables are:

- `calibration_log.json`
- `estimated_params.json`
- `tuned_gains.json`
- `control_log.json`
- `metrics.json`

Invoke the packaged entrypoint **through the Skill script runner**, rather than assuming that `scripts/` exists beneath `/root`. Send `{}` on stdin to use the task defaults:

```json
{}
```

The default input paths are `/root/hvac_simulator.py` and `/root/room_config.json`; output files are written directly to `/root`. The script accepts this optional JSON request schema:

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "setpoint": 22.0,
  "sample_dt": 0.5,
  "calibration_power": 50.0,
  "control_duration_s": 240.0,
  "adapter": {}
}
```

It emits one JSON object to stdout. On success it includes `ok: true`, `targets_met`, the five written filenames, and the trace-derived metrics. A false `ok` is an execution failure and must be repaired before claiming the task complete.

## Workflow

1. Load the supplied simulator and configuration, create a fresh plant, and record an 80-second calibration with a zero-power baseline, a bounded positive step, and cooldown. The recorded temperatures are observations from the simulator; commands are always clamped to 0--100%.
2. Fit a sampled affine first-order model from adjacent calibration records. Save positive gain `K`, positive time constant `tau`, coefficient of determination `r_squared`, and RMSE `fitting_error`.
3. Derive several IMC-style PI candidates from that identified model. Each candidate is run on a fresh simulator instance with feed-forward, clamping, and conditional anti-windup. Select using measurements calculated from the actual candidate trace, not assumed nominal dynamics.
4. Save the selected gains and a closed-loop trace at a 22.0 C setpoint. Every control record contains finite, strictly ordered time, observed temperature, bounded applied power, and `error` computed exactly as `setpoint - temperature`.
5. Derive metrics from the saved trace. Overshoot is `max(0, (max_temp - setpoint) / setpoint)`; settling time is the first sample after which every remaining sample is within the strict ±0.5 C band; steady-state error is mean absolute error over the final 20% of samples.

The entrypoint validates artifact shape, finite numerical values, calibration coverage and excitation, actuator bounds, trace duration, error consistency, and the required performance limits before reporting `targets_met`.

## Simulator compatibility

The entrypoint introspects common class- and module-level simulator APIs, including common temperature reader, heater setter, and time-step names. If the supplied source uses uncommon names, pass only names verified by inspecting that public source:

```json
{
  "adapter": {
    "class": "VerifiedSimulatorClass",
    "temperature_method": "verified_temperature_reader",
    "temperature_attr": "verified_temperature_attribute",
    "heater_setter": "verified_heater_setter",
    "step_method": "verified_step_method"
  }
}
```

Do not hand-author trace rows or metrics: all five deliverables must result from the supplied simulator and the delivered control trace.
