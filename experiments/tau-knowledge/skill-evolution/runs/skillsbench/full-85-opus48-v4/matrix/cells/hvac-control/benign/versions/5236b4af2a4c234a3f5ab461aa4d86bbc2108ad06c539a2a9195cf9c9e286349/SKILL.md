---
name: hvac-first-order-pid-control
description: >
  End-to-end workflow for the HVAC temperature-control task that drives
  hvac_simulator.py: run a step calibration, identify a first-order (K, tau)
  thermal model, compute PI(D) gains by lambda/IMC tuning, run a clamped
  anti-windup closed-loop controller to a setpoint (default 22.0 C), and
  emit calibration_log.json, estimated_params.json, tuned_gains.json,
  control_log.json and metrics.json. Use this whenever the task asks to
  calibrate a room, estimate parameters, tune a controller and run
  closed-loop control against a provided simulator while meeting
  steady-state-error / settling-time / overshoot / duration / max-temp targets.
---

# HVAC first-order identification + PID control

## What the public task requires
The opening asks you to, in order, produce five JSON artifacts in the work
directory (default `/root`):

1. `calibration_log.json` – a calibration experiment of **>=30 s** of data with
   **>=20 data points** at a constant test power.
2. `estimated_params.json` – first-order model fit `{K, tau, r_squared, fitting_error}`.
3. `tuned_gains.json` – `{Kp, Ki, Kd, lambda}` derived from the estimated model.
4. `control_log.json` – closed-loop trace driving the room to the setpoint
   (default 22.0 C), **>=150 s** of control data.
5. `metrics.json` – `{rise_time, overshoot, settling_time, steady_state_error, max_temp}`
   computed from the delivered control trace.

Targets (verify, do not assume): steady_state_error < 0.5 C, settling_time < 120 s,
overshoot < 10% (0.10 fraction), control duration >= 150 s, max_temp < 30 C.
Constraints: initial temperature ~18.0 C (+/-2 C sensor noise), heater power
clamped to 0-100%.

The simulator is the *plant*: ego/room temperature must be produced by stepping
`hvac_simulator.py`, never fabricated. Fit the model from the recorded
calibration response rather than assuming nominal dynamics, and compute metrics
from the actually delivered control trace.

## Method
**Model.** A room with heat loss is approximated by a stable first-order plant.
Under a constant heater power `u` the step response is
`T(t) = T_ss - (T_ss - T0) * exp(-t/tau)`, with steady-state gain
`K = (T_ss - ambient) / u` (degrees C per % power) and time constant `tau` (s).

**Calibration.** Read the baseline (zero-power) temperature, then apply a
constant test power (default 50%) and record `time, temperature, heater_power`
for at least 30 s / 20 points.

**Identification.** Fit `K, tau` from the power-on portion by searching `tau`
and solving the 2-parameter linear least squares for the asymptote and amplitude
(`scripts/hvac_lib.py: fit_first_order`). Report `r_squared` and RMS
`fitting_error`. `ambient` is the pre-heat baseline reading.

**Tuning.** IMC / lambda PI tuning for a first-order plant:
`Kp = tau / (|K| * lambda)`, `Ki = 1 / (|K| * lambda)`, `Kd = 0`, where the
closed-loop time constant `lambda` is chosen so the ~5*lambda settling stays
under the settling target with margin (`scripts/hvac_lib.py: compute_gains`).
Smaller `lambda` is faster but risks saturation overshoot; larger is slower and
smoother. `lambda` is a tunable knob — adjust it from simulator experiments.

**Closed loop.** Discrete PID with integral clamping / conditional integration
anti-windup, output clamped to [0,100]%. Ego/room temperature comes from the
simulator step, integrated from the initial condition.

**Metrics (explicit definitions).** Relative to the first control sample:
rise_time = first time temperature reaches 90% of the step; overshoot =
`max(0,(max_temp-setpoint))/(setpoint-initial)`; settling_time = first time after
which `|T-setpoint| <= band` for all later samples (band defaults to 0.5 C to
match the steady-state target); steady_state_error = `|mean(last 20%) - setpoint|`;
max_temp = max temperature in the trace.

## How the executor uses this Skill
1. **Inspect the simulator first.** `cat /root/hvac_simulator.py` and
   `cat /root/room_config.json`. Identify the class name, how to construct it,
   how to read the current temperature (method or attribute), how to advance one
   step (method, whether it takes a power and/or dt, whether it returns the new
   temperature), any reset method, and the timestep `dt`.
2. **Run the orchestrator.** `scripts/run_hvac.py` auto-discovers that interface
   and performs all four phases, writing the five JSON files. It accepts a JSON
   config on stdin (all keys optional) to override anything the auto-discovery
   gets wrong. Example:
   ```
   echo '{}' | python3 /app/environment/skills/current/scripts/run_hvac.py
   ```
   or with overrides after reading the simulator:
   ```
   echo '{"setpoint":22.0,"calib_power":50.0,"calib_duration":60,
          "control_duration":200,"dt":0.5,"lambda":12,
          "step_method":"step","step_takes_dt":false,
          "step_returns_temp":true,"read_method":"get_temperature",
          "reset_method":"reset","temp_attr":null}' \
     | python3 /app/environment/skills/current/scripts/run_hvac.py
   ```
   It prints a JSON summary (resolved interface, params, gains, metrics,
   per-target pass/fail) and also writes `hvac_interface.json` for debugging the
   discovered API. If discovery fails it reports the candidate names it saw;
   set the matching override keys and rerun.
3. **Validate.** `scripts/validate_outputs.py` reopens all five artifacts and
   checks they are finite, time-ordered, long enough (>=30s/20pts calibration,
   >=150s control), internally consistent, and whether each target is met:
   ```
   echo '{"dir":"/root","setpoint":22.0}' | python3 .../scripts/validate_outputs.py
   ```
4. **Tune if a target fails.** If overshoot/settling fails, change `lambda`
   (increase to reduce overshoot, decrease to speed up) and/or extend
   `control_duration`; rerun `run_hvac.py` then `validate_outputs.py`. If the
   fit is poor (`r_squared` low) increase `calib_duration` or adjust
   `calib_power` so the response is well excited but stays below max_temp.

## Standalone helpers (stdin JSON -> stdout JSON)
- `scripts/fit_first_order.py`: in `{"data":[{time,temperature,heater_power}...],
  "power":<opt>,"ambient":<opt>}` -> out `{K,tau,r_squared,fitting_error,T_ss,T0,ambient,power}`.
- `scripts/compute_gains.py`: in `{K,tau,"lambda":<opt>,"settling_target":<opt>}`
  -> out `{Kp,Ki,Kd,lambda}`.
- `scripts/compute_metrics.py`: in `{"data":[{time,temperature...}...],"setpoint":22.0,
  "band":<opt>,"ss_frac":<opt>}` -> out the metrics object.

## Failure handling
- If the simulator interface cannot be discovered, `run_hvac.py` exits non-zero
  with the inspected class/method candidates; supply explicit overrides.
- If calibration shows no temperature rise under test power, raise `calib_power`
  (still <=100) and re-run; a near-zero `K` makes gains blow up and is reported.
- Never copy the simulator's recorded temperature as the controlled output; the
  control trace must come from integrating the controller's commands through the
  simulator. Do not hardcode instance-specific numbers into the scripts.

See `references/method.md` for the derivations and tuning rationale.
