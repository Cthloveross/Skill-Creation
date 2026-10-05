---
name: hvac-calibrate-tune-control
description: Generate calibration, identified thermal-model, controller-tuning, closed-loop trace, and trace-derived metric JSON artifacts for a supplied read-only HVAC Python simulator.
---

# HVAC calibration, identification, and closed-loop control

Use this Skill when the task supplies `/root/hvac_simulator.py` and `/root/room_config.json` and requires the following deliverables in `/root`:

- `calibration_log.json`
- `estimated_params.json`
- `tuned_gains.json`
- `control_log.json`
- `metrics.json`

The supplied simulator and configuration are sealed inputs. Never edit, replace, or write either input file. The workflow writes only deliverables and any optional separate helper files.

## Run

Run `scripts/run_hvac_workflow.py` through the Skill script runner with this JSON stdin:

```json
{}
```

The script reads the simulator and configuration at runtime, uses fresh simulator instances for calibration and controller trials, and writes all five JSON deliverables directly to `/root`. It emits one JSON status object on stdout.

Optional input schema:

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": "/root",
  "setpoint": 22.0,
  "sample_dt": 0.5,
  "control_duration_s": 155.0,
  "calibration_power": 50.0,
  "adapter": {
    "class": "optional simulator class or factory name",
    "temperature_method": "optional zero-argument reader method",
    "temperature_attr": "optional temperature attribute",
    "heater_setter": "optional one-argument actuator setter",
    "step_method": "optional simulation-step method"
  }
}
```

Use adapter fields only after inspecting a nonstandard supplied simulator API. Defaults support common room/HVAC educational APIs including `HVACSimulator`, `get_temperature`, `set_heater_power`, and `step`.

## Method

1. Record a baseline, nonzero heater step, and cooldown. Each record logs the measured temperature and the bounded command applied to the following sample interval.
2. Fit the recorded transitions to `T_next = a*T + b*u + c`, converting the result to the first-order parameters `K = b/(1-a)` and `tau = -dt/log(a)`. Save observed one-step RMSE and R-squared.
3. Derive conservative IMC PI candidates from the fitted model, run a small number of isolated closed-loop trials, and retain the measured candidate with the best trace-derived target score.
4. Clamp every heater command to 0--100 percent and conditionally integrate only when this does not wind up a saturated actuator. Every control record uses `error = setpoint - temperature` exactly.
5. Derive maximum temperature, normalized overshoot, final-20-percent mean absolute steady-state error, 90-percent rise time, and first sustained strict ±0.5 C settling time from the saved control trace.

The stdout object contains `ok`, the written paths, the selected metrics, and `targets_met`. If `targets_met` is false, inspect the generated trace and use the optional adapter only to correct a verified API mismatch; do not alter the public simulator or invent artifacts.
