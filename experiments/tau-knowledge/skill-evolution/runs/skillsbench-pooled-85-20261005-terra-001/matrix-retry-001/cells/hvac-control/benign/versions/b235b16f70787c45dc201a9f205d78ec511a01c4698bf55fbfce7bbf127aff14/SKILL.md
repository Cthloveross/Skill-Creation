---
name: hvac-calibrate-tune-control
description: Run a supplied read-only HVAC simulator to create calibration, identified-model, PID tuning, closed-loop control, and trace-derived metric JSON artifacts.
---

# HVAC calibration and control workflow

Use this Skill when `/root/hvac_simulator.py` and `/root/room_config.json` are supplied and the task requires these files directly under `/root`:

- `calibration_log.json`
- `estimated_params.json`
- `tuned_gains.json`
- `control_log.json`
- `metrics.json`

The simulator and room configuration are immutable task inputs. Do not edit, replace, or copy over either file. This Skill creates only the requested output artifacts.

## Run

Run `scripts/run_hvac_workflow.py` using the Skill script runner with JSON stdin:

```json
{}
```

The script reads the supplied simulator and room configuration at runtime. It uses a fresh simulator for calibration and a fresh simulator for the final closed-loop run. It deliberately performs only one final control run rather than multiple long trial runs, so it can complete when a simulator advances in real time.

Optional stdin schema:

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "setpoint": 22.0,
  "sample_dt": 0.5,
  "calibration_power": 50.0,
  "control_duration_s": 155.0,
  "adapter": {
    "class": "optional simulator class/factory name",
    "temperature_method": "optional zero-argument temperature reader",
    "temperature_attr": "optional temperature attribute",
    "heater_setter": "optional one-argument heater setter",
    "step_method": "optional simulation step method"
  }
}
```

The default adapter discovers common educational simulator interfaces such as `HVACSimulator`, `get_temperature`, `set_heater_power`, and `step`. Supply adapter overrides only after inspecting a nonstandard simulator API; do not modify the supplied source to make it fit an adapter.

## Generated artifact semantics

1. The calibration trace includes baseline, a repeated nonzero heater test level, and cooldown. It has more than 20 strictly ordered samples and spans more than 30 seconds.
2. A discrete first-order transition model is fit from the calibration records:
   `T[k+1] = a*T[k] + b*u[k] + c`. The reported continuous parameters are `K=b/(1-a)` and `tau=-dt/log(a)`. The fitting error is one-step RMSE and R-squared is calculated from the same transitions.
3. Model-derived IMC PI gains with feedforward are used in the single closed-loop run. Commands are always clamped to 0--100 percent, and conditional integration prevents windup at either clamp.
4. Every control row records the command applied for the following interval and has `error` exactly equal to `setpoint - temperature`.
5. Metrics are recomputed from the saved control trace: maximum temperature, normalized overshoot, final-20%-of-trace mean absolute steady-state error, 90% rise time, and the first point after which all remaining samples are strictly within ±0.5 C.

The script emits one JSON status object on stdout with `ok`, generated paths, selected gains, metrics, and `targets_met`. It exits nonzero on an unsupported simulator interface or invalid simulator data rather than fabricating artifacts.
