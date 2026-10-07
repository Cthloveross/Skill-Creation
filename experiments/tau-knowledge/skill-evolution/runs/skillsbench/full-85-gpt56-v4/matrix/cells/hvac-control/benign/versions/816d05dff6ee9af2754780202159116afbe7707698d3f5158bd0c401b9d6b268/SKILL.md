---
name: hvac-first-order-identification-pid
version: 1.1.0
description: Execute a supplied HVACSimulator calibration, fit a first-order heating model, tune an anti-windup PI controller, and produce validated calibration, parameter, gain, control-trace, and metric JSON artifacts. Use for room-temperature control tasks with a simulator source and config.
---

# HVAC calibration and bounded PI control

Use this Skill for a thermal-room task that supplies `hvac_simulator.py` exposing an `HVACSimulator` with `reset()`, `step(power)`, `get_dt()`, and `get_setpoint()`. It uses the supplied simulator at runtime rather than assuming plant constants or copying a sensor trace. The packaged entrypoint performs fresh calibration and fresh closed-loop runs, so it is the preferred end-to-end method for this API.

## Entrypoint

`scripts/run_hvac.py` reads one JSON object from stdin and writes JSON to stdout. It imports the public simulator file, then writes all artifacts in `output_dir`:

- `calibration_log.json`
- `estimated_params.json`
- `tuned_gains.json`
- `control_log.json`
- `metrics.json`

Run it from the task workspace (or use absolute paths):

```sh
python3 /app/environment/skills/current/scripts/run_hvac.py <<'EOF'
{"simulator_path":"/root/hvac_simulator.py","config_path":"/root/room_config.json","output_dir":"/root"}
EOF
```

Input fields are `simulator_path` and `config_path` (default `/root/hvac_simulator.py` and `/root/room_config.json`), `output_dir` (default current directory), and optional positive `calibration_power` (default 35, constrained to 0--100), `calibration_duration` (default 150 s), and `control_duration` (default 180 s). Durations shorter than 30 s calibration or 150 s control are rejected. The entrypoint uses standard library dependencies only. If the imported source does not provide this documented API, it fails clearly instead of inventing a plant API.

The entrypoint logs a real reset reading followed by the actual applied command and returned measurement each sample. Calibration uses a constant bounded step and requires no safety trigger; a safety event aborts rather than yielding misleading identification. It fits only the collected response, writes the fit, derives gains from it, resets to a fresh simulator instance, runs PI control, clamps commands to `[0,100]`, and conditionally integrates only when saturation is not worsened. The control log's temperature is the simulator measurement and its power is the command actually sent.

## Artifact meanings and validation

`estimated_params.json` contains positive `K` (degrees C per heater percent), positive `tau` (seconds), fit `r_squared`, and `fitting_error`. The estimator uses least-squares first-order step-response fitting with a grid search over positive time constants. Where a preceding baseline record exists, it uses that record's timestamp as the start of the applied step; this respects simulators that return a measurement after each integration interval.

`tuned_gains.json` uses an IMC-style PI rule for `K/(tau*s+1)` and records `Kp`, `Ki`, `Kd: 0.0`, and the chosen `lambda`. `Kp` produces heater percent per degree C and `Ki` produces heater percent per degree C-second. PI is intentionally used instead of noise-sensitive derivative action.

`metrics.json` is calculated from `control_log.json` and documents its own definitions:

- rise time: first crossing of 90% of initial-to-setpoint change;
- overshoot: peak excursion beyond setpoint divided by initial setpoint change;
- settling time: first point after which all logged temperatures remain within `max(0.1 C, 2% of setpoint)`; using setpoint scale prevents a noise floor from making a small setpoint change unmeasurable;
- steady-state error: absolute error of the mean final 20% of samples (at least five);
- max temperature and control duration: extrema/timing directly from the trace.

For a task with performance targets, compare these measured values—not planned values—to the requested limits. A `null` rise or settling time means the trace did not demonstrate it and must not be reported as a passing numeric result. Re-run with a fresh simulator after a gain or calibration change; do not hand-edit metrics.

For individual post-processing actions, `scripts/hvac_tools.py` receives a JSON request on stdin and writes a result object on stdout. Supported actions are:

```json
{"action":"estimate","calibration_path":"calibration_log.json","output_path":"estimated_params.json"}
{"action":"tune","params_path":"estimated_params.json","dt":0.5,"output_path":"tuned_gains.json"}
{"action":"metrics","control_path":"control_log.json","output_path":"metrics.json"}
{"action":"validate","paths":["calibration_log.json","estimated_params.json","tuned_gains.json","control_log.json","metrics.json"],"setpoint":22.0}
```

`validate` rejects malformed JSON, non-finite values, unordered timestamps, calibration logs with fewer than 20 samples or 30 seconds, non-calibration/control phase labels, a control duration below 150 seconds, inconsistent control errors/setpoints, and any command outside 0--100. Reopen all five output files after an entrypoint run. Also check that the fitted response is credible and that task-specific safety and performance limits are satisfied; structural validity alone is not a claim that the control target passed.

## Failure handling

If the calibration fit is nonpositive or weak, use a fresh reset and a longer/stronger but safe bounded calibration step. If the simulator signals its safety limit, lower the calibration power or retune from a fresh instance; never reuse the heated state. If measured performance misses a requested threshold, modify the run input or tuning method coherently, regenerate the control trace, recompute metrics, and preserve artifacts from the final run only. Never serialize `NaN`, infinity, raw unclamped commands, or invented measurements.
