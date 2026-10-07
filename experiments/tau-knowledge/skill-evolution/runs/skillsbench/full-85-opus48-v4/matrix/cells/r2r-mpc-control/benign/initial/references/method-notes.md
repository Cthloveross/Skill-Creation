# Method notes for R2R MPC tension control

## State / input convention (keep consistent everywhere)
- x = [T1..T6, v1..v6]  (12 states: 6 tensions, then 6 velocities)
- u = [u1..u6]          (6 motor torques)
- references = [T1_ref..T6_ref, v1_ref..v6_ref] (12)
- The A/B matrices, K_lqr, Q_diag, R_diag, the control loop, and the log
  entries all use this ordering. Mismatched ordering is the most common
  failure and silently degrades tracking.

## Why discrete-map linearization
The simulator advances state over its own `dt`. Numerically differentiating the
one-step map F(x,u) with central differences yields the DISCRETE A=dF/dx and
B=dF/du directly at the simulator sample interval, so no separate continuous
discretization is required. Verify `dt` with `--diagnose`; if the simulator
hides dt, set it from the config or the known value and re-run.

## Operating point
Linearize at the reference operating point (reference tensions + velocities).
The trim torque u_ref solves (I - A) x_ref = B u_ref by least squares; it is
the feedforward that holds the plant at the reference and is essential for low
steady-state error. The control applied is u = u_ref + MPC_move (or the LQR
fallback u = u_ref - K (x - x_ref)).

## Tuning guidance (do it via simulator experiments)
- Larger tension weight qT or smaller control weight r => tighter/faster
  tracking, lower steady-state error, but more control effort and risk of
  overshoot (watch max_tension < 50 N).
- Larger r or smaller qT => smoother control, slower settling.
- horizon_N must stay in [3,30]; longer horizons improve prediction of the
  coupled response at the cost of compute.
- If tensions dip (min_tension <= 5 N) during the transient, reduce aggressive
  deceleration by raising r or lowering qT, or add actuator clipping limits.

## Metrics (explicit definitions)
- per-step error = mean absolute deviation of the 6 tensions from the
  reference tensions parsed from system_config.json.
- steady_state_error = mean per-step error over the final 1 second of the
  trace (must be < 2.0 N).
- settling_time = earliest time after which the per-step error stays within a
  2.0 N band for the rest of the trace (must be < 4.0 s).
- max_tension / min_tension = global extrema of all logged tensions
  (must be < 50 N and > 5 N).

## Adapting the simulator adapter
If `--diagnose` shows wrong state attributes or no step method, edit the NAME
lists at the top of scripts/mpc_lib.py (ATTR_TENSIONS, ATTR_VELOCITIES,
STEP_NAMES, RESET_NAMES) and the config key heuristics in extract_references /
extract_u_limits. Never hardcode the instance's numeric answers; only adapt the
API/key detection so the pipeline reads the real inputs at runtime.
