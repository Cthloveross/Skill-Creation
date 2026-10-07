---
name: roll-to-roll-mpc-artifacts
description: Build validated controller_params.json, control_log.json, and metrics.json for a six-section roll-to-roll simulator using numerical local linearization and constrained finite-horizon tracking control. Use when a supplied Python simulator and JSON system configuration define the plant.
---

# Roll-to-roll MPC artifacts

Use this Skill for the supplied simulator without modifying it. The entrypoint imports the simulator at runtime, obtains the state in the fixed order `[T1..T6, v1..v6]`, numerically linearizes one simulator time step about the initial reference operating point, and writes all required deliverables.

## Runtime interface

Run from the directory containing the supplied simulator and configuration. The script consumes one JSON object on standard input and emits a JSON run summary on standard output.

```sh
python /app/environment/skills/current/scripts/run_r2r_mpc.py <<'JSON'
{
  "simulator_path": "/root/r2r_simulator.py",
  "config_path": "/root/system_config.json",
  "output_dir": "/root",
  "duration": 5.1,
  "change_time": 0.5,
  "change_section": 3,
  "change_tension": 44.0,
  "horizon_N": 12
}
JSON
```

Input fields are optional except paths when they differ from the defaults. `change_section` is one-based. `duration` must be at least 5 seconds and `horizon_N` must be in `[3,30]`.

The entrypoint:

1. Reads reference tensions, timestep, and actuator limits from the supplied configuration when available.
2. Imports and instantiates a class exposing `reset()` and `step(action)` from the supplied simulator. It supports common dictionary/attribute observations containing `tensions` and `velocities`.
3. Forms the requested initial reference state, tries to set it on a freshly reset simulator, and estimates discrete `A_matrix` and `B_matrix` with centered finite differences through the real one-step dynamics. If the simulator deliberately exposes no writable state, it explicitly falls back to the reset operating state and records that fact in the stdout summary; this is not silently presented as a reference-point linearization.
4. Computes a finite-horizon quadratic tracking action at every step. The future reference sequence is constructed over the full prediction horizon, including the scheduled section-3 change. Saturation is applied before `step`, so `control_inputs` records the actual requested bounded motor torques. A Riccati terminal LQR gain is also saved as `K_lqr`.
5. Logs simulator-delivered tensions and velocities after every action, with the reference state and applied control used for that timestep.
6. Calculates metrics from that delivered log. Steady-state error is the mean absolute tension error in the final one-second window. Settling time is the first post-change time after which every tension remains within 2 N of its logged reference; it is `null` if no such time exists.

## Expected artifacts and validation

The selected `output_dir` receives:

- `controller_params.json`: horizon, strictly positive 12-state and 6-input weights, a 6x12 LQR gain, and 12x12/12x6 discrete matrices.
- `control_log.json`: `phase: "control"` and one entry per actual simulator step with six tensions, six velocities, six controls, and twelve references.
- `metrics.json`: numeric steady-state error, settling time (or JSON null when unsettled), maximum tension, and minimum tension.

The script validates matrix dimensions, finite numeric contents, positive cost weights, log shape, and a span of at least five seconds before reporting success. It also reports a one-step local finite-difference consistency residual in its summary. Inspect a non-success summary rather than fabricating output: unsupported simulator construction, missing state observations, or an invalid configuration must be corrected with a narrow adapter update while preserving the state ordering and artifact schemas.

The output metrics must be judged against the task limits from the delivered trace: mean steady-state tension error below 2 N, settling time below 4 seconds, maximum tension below 50 N, and minimum tension above 5 N. If tuning is necessary, vary `horizon_N`, `Q_diag`, `R_diag`, or actuator bounds through repeated simulator runs; do not alter the supplied simulator or hard-code a run's logged values.
