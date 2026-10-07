---
name: hvac-calibrate-tune-control
description: Generate verified HVAC calibration, first-order identification, bounded feedback-control, and trace-derived JSON artifacts using a supplied Python room simulator.
---

# HVAC calibration, identification, and feedback control

Use this Skill when `/root/hvac_simulator.py` and `/root/room_config.json` are supplied and the task requires these artifacts directly in `/root`:

- `calibration_log.json`
- `estimated_params.json`
- `tuned_gains.json`
- `control_log.json`
- `metrics.json`

Run `scripts/run_hvac_workflow.py` using the Skill script runner, with `{}` as JSON stdin. Do **not** assume that the packaged `scripts` directory exists below `/root`; the entrypoint itself uses absolute default paths for supplied task files and writes the deliverables to `/root`.

```json
{}
```

The optional request schema is:

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "setpoint": 22.0,
  "sample_dt": 0.5,
  "control_duration_s": 240.0,
  "calibration_power": 50.0,
  "adapter": {
    "class": "optional verified simulator class name",
    "temperature_method": "optional verified reader",
    "temperature_attr": "optional verified temperature attribute",
    "heater_setter": "optional verified power setter",
    "step_method": "optional verified step method"
  }
}
```

The script emits one JSON status object on stdout. `ok: true` means all artifacts were written and reopened validation passed. Any `ok: false` result is a workflow failure: inspect the public simulator source, provide only verified adapter names if needed, and rerun before completing the task.

## Method

1. Construct fresh simulator instances from the supplied configuration. Record an 85-second calibration with an initial zero-power baseline, a bounded positive heater step, and a zero-power cooldown. Samples contain actual simulator temperature observations and the applied 0--100% command.
2. Estimate the discrete affine transition `T[n+1] = a*T[n] + b*u[n] + c` from adjacent calibration samples. Convert it to first-order heater gain `K=b/(1-a)` and `tau=-dt/log(a)`. The saved fit statistics are calculated from these recorded transitions.
3. Generate model-derived IMC/PI gain candidates. Run every candidate against a fresh actual simulator, use bounded commands and conditional anti-windup, and select only from measured closed-loop traces.
4. Save the selected 22.0 C control trace. Each record logs finite ordered time, observed temperature, setpoint, bounded applied heater power, and exactly `error = setpoint - temperature`.
5. Recompute all metrics from the final saved trace. Steady-state error is final-20%-sample mean absolute error; settling is the first point after which all remaining samples are strictly within ±0.5 C; overshoot and maximum temperature are taken from the same trace.

The script refuses to report success unless calibration coverage/excitation, model/gain physicality, artifact schemas, actuator bounds, time ordering, model-fit quality, 150-second control duration, error consistency, and requested trace targets validate.
