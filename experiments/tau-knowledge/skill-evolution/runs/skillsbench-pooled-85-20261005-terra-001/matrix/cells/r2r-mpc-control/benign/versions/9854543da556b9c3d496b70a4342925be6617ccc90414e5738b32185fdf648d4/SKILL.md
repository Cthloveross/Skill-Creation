---
name: r2r-linear-mpc-artifacts
description: Generate, validate, and document linearized-model MPC artifacts for a six-section roll-to-roll simulator, including a 12-state model, a 5+ second delivered control trace, and trace-derived tension metrics. Use when the simulator source and system configuration are available locally and must not be modified.
---

# Roll-to-roll linear MPC artifact generation

This Skill produces the required `controller_params.json`, `control_log.json`, and
`metrics.json` by operating the supplied simulator as the plant. It does **not**
modify the simulator. The discrete model is obtained by central finite differences
of one actual simulator sample at the declared initial operating point, so the
saved `A_matrix` and `B_matrix` have the simulator's actual discrete-time meaning.

## Prerequisites

* Python 3 and NumPy are available.
* The supplied simulator and `system_config.json` are readable.
* The simulator can be reset, its 12-element state can be read and set for local
  finite-difference experiments, and it can advance one sample from six torques.
* Actuator lower and upper torque limits are known. They must be supplied explicitly
  if the simulator/configuration does not expose them.

The driver includes conservative reflection for common simulator APIs. For a
nonstandard API, provide a small adapter module implementing the protocol in
`references/adapter_protocol.md`. This is preferable to guessing state ordering,
time units, or actuator bounds.

## Runtime input and output

`scripts/r2r_mpc.py` reads one JSON object from stdin and emits one JSON summary to
stdout. Its required inputs are:

```json
{
  "simulator": "/root/r2r_simulator.py",
  "config": "/root/system_config.json",
  "output_dir": "/root/output",
  "duration": 5.0,
  "dt": 0.01,
  "control_min": [-20, -20, -20, -20, -20, -20],
  "control_max": [20, 20, 20, 20, 20, 20]
}
```

Do not assume the example torque limits are correct: use limits stated by the
actual simulator/configuration. `dt`, bounds, and `adapter_module` are optional
when the adapter or simulator exposes them. An optional task schedule is:

```json
{"step_change": {"section": 3, "time": 0.5, "tension": 44.0}}
```

`section` is one-based. The default schedule is the public task's section-3
change to 44 N at 0.5 s. The initial tension reference is obtained from the reset
operating point unless a recognized initial-reference key occurs in the supplied
configuration. Controller settings may be overridden with `horizon_N` (3--30),
`Q_diag` (12 positive values), `R_diag` (6 positive values), `fd_relative_step`,
and `fd_control_step`.

Example execution by an executor:

```bash
python3 scripts/r2r_mpc.py <<'JSON'
{"simulator":"/root/r2r_simulator.py","config":"/root/system_config.json","output_dir":"/root/output","duration":5.0,"control_min":[-20,-20,-20,-20,-20,-20],"control_max":[20,20,20,20,20,20]}
JSON
python3 scripts/validate_r2r_artifacts.py <<'JSON'
{"directory":"/root/output"}
JSON
```

The first command writes all three declared artifacts into `output_dir`. The
second command independently checks their schema, finite values, state/input
ordering, time ordering, duration, and metric consistency. It emits a JSON report
and exits nonzero on an invalid artifact. Read its report before delivering files.

## Control method

1. Reset the plant and establish state ordering `[T1..T6, v1..v6]` and input
   ordering `[u1..u6]`. The reference uses exactly this ordering.
2. At the initial reference point and nominal torque, central-difference the
   one-sample nonlinear transition. This gives discrete `A` and `B`; the driver
   also records their affine one-step residual internally for MPC prediction.
3. Compute a finite-horizon condensed tracking solution at every sample. The
   future reference sequence includes the scheduled change at every point of the
   prediction horizon. Clamp the resulting torques to actual actuator limits.
   A discrete Riccati gain is calculated and saved as `K_lqr`; it is used only as
   a numerical fallback if the online linear solve fails.
4. Log the initial record and every applied sample. The plant, reference, and
   applied (post-clamp) torque are all logged rather than reconstructed later.
5. Compute metrics exclusively from that delivered log. `steady_state_error` is
   the mean absolute tension error across all six sections during the final
   one-second window. `settling_time` is elapsed time from the reference change
   until all remaining samples have every tension error at or below 2 N; it is
   `null` if this did not happen in the trace. `max_tension` and `min_tension`
   are extrema over every logged tension.

If the simulator cannot support repeatable reset/set-state finite differences,
if bounds are unknown, or if a simulation produces nonfinite state values, stop
rather than fabricate model or control artifacts. Supply an adapter that maps the
published simulator API correctly, then rerun.
