---
name: hvac-calibrate-tune-control
description: Run a reproducible calibration, first-order thermal identification, IMC/PI tuning, and bounded closed-loop temperature-control experiment against a supplied Python HVAC simulator. Use when the required deliverables are calibration_log.json, estimated_params.json, tuned_gains.json, control_log.json, and metrics.json.
---

# HVAC calibration and closed-loop control

This Skill creates the five required runtime artifacts from the actual supplied simulator; it never substitutes recorded sensor temperatures for the simulated controlled trajectory.

## Preconditions

* The simulator and room configuration must be readable at runtime. Defaults are `/root/hvac_simulator.py` and `/root/room_config.json`.
* The simulator must expose a constructible simulator/room/environment class (or `create_simulator`) with a readable temperature and a one-step advancement method. The included adapter recognizes common names such as `step`, `update`, `get_temperature`, `temperature`, and `current_temperature`.
* If its API is unusual, inspect the supplied simulator first and supply the optional `adapter` mapping described in `scripts/run_hvac_workflow.py`'s module documentation. Do not fabricate observations or alter simulator physics.

## End-to-end execution

Run `scripts/run_hvac_workflow.py` once with JSON on stdin. It writes all deliverables into `output_dir` and emits a JSON manifest on stdout. For example:

```json
{
  "simulator_path": "/root/hvac_simulator.py",
  "room_config_path": "/root/room_config.json",
  "output_dir": ".",
  "setpoint": 22.0,
  "control_duration_s": 180.0
}
```

The calibration has an initial zero-power baseline, a bounded deliberate heater step, and a zero-power cooldown. Its duration is at least 65 s by default and it records at least 20 samples. The script estimates the discrete ARX thermal model

`T[k+1] = a*T[k] + b*u[k] + c`

and reports `tau=-dt/log(a)` and steady-state gain `K=b/(1-a)`. It then derives conservative IMC/PI gains from the fitted gain and time constant, includes an estimated ambient feed-forward term, clamps heater output to `[0,100]`, and uses conditional-integration anti-windup.

The generated control trace lasts at least 150 s by default. Each row is the controller state before its stated heater command is integrated. The controller temperature is always read from the simulator after the prior applied command.

## Verify output

After generation, run `scripts/validate_hvac_artifacts.py` with:

```json
{"output_dir": ".", "setpoint": 22.0, "min_control_duration_s": 150.0}
```

It emits `{ "valid": true, ... }` only if all five files exist, all records are finite and time ordered, control errors agree with the logged temperatures, heater commands obey 0--100%, calibration meets the 30 s/20-point requirement, and the reported metrics recompute from the delivered control trace under the documented definitions.

`metrics.json` definitions are: rise time is first 90%-of-initial-error crossing; overshoot is positive peak excess normalized by the initial setpoint change; settling time is the earliest time after which every remaining sample lies within ±0.5 C; steady-state error is the mean absolute error over the final max(30 s, 20%) window; and max_temp is the trace maximum. A missing threshold crossing is represented as JSON `null`, rather than a made-up value.

If validation fails, correct the simulator adapter or runtime configuration and regenerate all artifacts from a clean output directory. Do not hand-edit metrics, parameters, or trace values.
