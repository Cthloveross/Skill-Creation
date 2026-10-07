---
name: hvac-first-order-identification-pid
version: 1.0.0
description: Calibrate a supplied room-heating simulator, fit a first-order thermal response, derive bounded PI/PID gains, execute a safe closed-loop run, and create validated JSON evidence and trace metrics. Use for HVAC/room temperature-control tasks requiring calibration and controller artifacts.
---

# HVAC first-order identification and bounded control

Use this Skill when a task supplies a thermal simulator and requires calibration evidence, fitted parameters, controller tuning, a closed-loop trace, and performance metrics. The simulator API is intentionally treated as an external dependency: inspect its source and configuration before writing the small runtime driver that calls it. Do not assume a class, method, reset behavior, or integration ordering from this Skill.

## Required runtime inputs and outputs

The normal task input is a Python simulator source file plus its room/configuration JSON. The workflow writes these JSON files in the task working directory:

- `calibration_log.json`
- `estimated_params.json`
- `tuned_gains.json`
- `control_log.json`
- `metrics.json`

The packaged tool is `scripts/hvac_tools.py`. It reads one JSON object from stdin and emits one JSON result object to stdout. It uses only the Python standard library.

### Tool input schema

All actions accept an optional `output_path`, which receives the result as formatted JSON.

```json
{"action":"estimate", "calibration_path":"calibration_log.json", "output_path":"estimated_params.json"}
{"action":"tune", "params_path":"estimated_params.json", "dt":0.5, "output_path":"tuned_gains.json"}
{"action":"metrics", "control_path":"control_log.json", "output_path":"metrics.json"}
{"action":"validate", "paths":["calibration_log.json","estimated_params.json","tuned_gains.json","control_log.json","metrics.json"], "setpoint":22.0}
```

`estimate` expects a calibration object with a `data` list of records containing finite `time`, `temperature`, and `heater_power` values. It fits a no-dead-time first-order step response by a deterministic grid search over time constants. `tune` derives conservative IMC-style PI gains using the fitted gain and time constant. `metrics` calculates all values from the delivered control trace, not from a planned trajectory. `validate` raises an error (and emits an error JSON object) if required structure, ordering, finiteness, or physical command limits are violated.

## End-to-end procedure

1. **Inspect the simulator first.** Read the simulator source and config. Identify how to create/reset a room, obtain its initial measured temperature, apply a heater command, advance exactly one time increment, and read the resulting temperature. Also identify the simulator time step and whether its reading contains measurement noise. Use its native API rather than replacing the plant with an invented equation.

2. **Write a short runtime driver in the task workspace.** The driver is task output support code, not a replacement simulator. It should load the supplied config, make a fresh simulator instance for calibration and another fresh instance for control, and serialize only ordinary JSON numbers. Keep controller state in the driver.

3. **Collect meaningful calibration data.** Starting from the simulator's actual initial temperature, log an initial zero-power observation, then apply a fixed nonzero step that stays within 0--100 percent. Log current simulator time, measured temperature, and applied heater power at every simulator sample. Run at least 30 seconds and retain at least 20 records. If the first step would make the temperature unsafe, lower the step and repeat from a fresh reset. Do not fabricate observations or reuse a control trajectory as calibration.

   Write this shape (additional finite fields are acceptable):

   ```json
   {"phase":"calibration","heater_power_test":50.0,"data":[
     {"time":0.0,"temperature":18.0,"heater_power":0.0}
   ]}
   ```

   Then estimate with, for example:

   ```sh
   python3 /app/environment/skills/current/scripts/hvac_tools.py <<'EOF'
   {"action":"estimate","calibration_path":"calibration_log.json","output_path":"estimated_params.json"}
   EOF
   ```

   Check that the fitted `K` and `tau` are positive, `r_squared` is finite, and the fit error is credible relative to observed temperature variation. If not, improve the excitation duration/amplitude and recollect from a reset simulator; do not hand-edit fitted values.

4. **Derive the gains from the fit.** Supply the actual simulator `dt` to `tune` and write `tuned_gains.json`. The included rule models `K` in degrees C per heater-percent and returns `Kp` in percent per degree C and `Ki` in percent per degree C-second. It chooses an intentionally conservative closed-loop time constant (`lambda`) from `tau` and the sample interval. Retain `Kd: 0.0` unless a measured-noise-aware derivative design is specifically needed; derivative action on noisy temperature measurements is usually counterproductive.

5. **Run closed-loop control for the requested duration (never shorter than 150 s when that is the requirement).** At each sample:

   - read the current simulated temperature;
   - calculate `error = setpoint - temperature`;
   - calculate an unsaturated PI/PID command from the current error and controller state;
   - clamp the **applied** heater power to `[0, 100]`;
   - prevent integral windup. A reliable conditional-integration rule is: only accept the candidate integral when unsaturated, or when its sign would move an already saturated command back toward range. An equivalent back-calculation method is acceptable;
   - apply the clamped command to the simulator and advance exactly one simulator step;
   - log the timestamp corresponding to the state used for the command, temperature, setpoint, clamped heater power, and error.

   Preserve simulator-provided time rather than assuming a nominal clock. Make all rows chronological. A valid base shape is:

   ```json
   {"phase":"control","setpoint":22.0,"data":[
     {"time":0.0,"temperature":18.0,"setpoint":22.0,"heater_power":0.0,"error":4.0}
   ]}
   ```

   The logged `heater_power` must be the command actually sent to the simulator, not the raw command. Never copy a recorded sensor temperature as the simulated controlled trajectory.

6. **Compute metrics from `control_log.json`.** Run the `metrics` action. Definitions used by the tool are documented in its output under `definitions`:

   - `rise_time`: first time reaching 90% of the initial-to-setpoint change;
   - `overshoot`: maximum amount above setpoint divided by the magnitude of that initial change, floored at zero;
   - `settling_time`: first time after which every remaining sample stays within a 2% initial-change band (with a 0.1 C minimum band) around setpoint; `null` if it never settles;
   - `steady_state_error`: absolute difference between setpoint and the mean of the final 20% of samples (at least five samples when available);
   - `max_temp`: largest logged temperature.

   Use the task's requested thresholds to assess results. If performance misses a target, change the calibration experiment or gain selection coherently and rerun a fresh closed-loop simulation; retain artifacts from the final matching run only.

7. **Validate and reopen all files.** Use `validate` after writing all five artifacts. It checks JSON structure, finite values, strictly increasing time, minimum calibration coverage/count, phase/setpoint consistency, control duration, and command range. Also manually inspect the reported metrics against the task limits and ensure no output reports a temperature above the safety limit. Validation does not claim a target was met merely because fields exist.

## Failure handling

- If the simulator lacks a documented reset, create a new instance for each trial rather than silently carrying heated state into the next run.
- If calibration is too noisy or has no sustained power step, do not fit it. Increase excitation signal-to-noise while respecting temperature safety and collect a new trace.
- If no settling time can be calculated, emit JSON `null`, not a fabricated number, and tune/re-run.
- If a sensor value, clock value, or command is non-finite, stop that run and diagnose the simulator/driver; do not serialize `NaN` or infinity.
- If a requested API operation is unavailable, report that incompatibility clearly rather than guessing an API or generating synthetic logs.
