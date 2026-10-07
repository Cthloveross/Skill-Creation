---
name: r2r-mpc-tension-control
description: >-
  Build, run, and validate a model-based (LQR/MPC) tension controller for a
  coupled multi-section Roll-to-Roll (R2R) web-handling simulator. Use when a
  task supplies an r2r_simulator.py plus a system_config.json and asks you to
  (1) derive a linearized discrete state-space model around the reference
  operating point, (2) design an MPC / finite-horizon tracking controller with
  an LQR fallback, (3) run it through the UNMODIFIED simulator for >=5 s, and
  (4) emit controller_params.json, control_log.json, and metrics.json meeting
  steady-state-error / settling-time / max-tension / min-tension targets.
---

# R2R MPC Tension Control

## What this Skill produces

Three JSON artifacts (written to the working directory, normally `/root`):

- `controller_params.json` — `horizon_N` (int in [3,30]), `Q_diag` (12 positive
  floats), `R_diag` (6 positive floats), `K_lqr` (6x12), `A_matrix` (12x12),
  `B_matrix` (12x6). A/B are the **discrete** linearized model built with the
  simulator's own sample interval.
- `control_log.json` — `{"phase":"control","data":[...]}`, one entry per step,
  spanning at least 5 s. Each entry has `time`, `tensions` (6), `velocities`
  (6), `control_inputs` (6 motor torques), `references` (12 = [T1..T6_ref,
  v1..v6_ref]).
- `metrics.json` — `steady_state_error`, `settling_time`, `max_tension`,
  `min_tension`, computed from the delivered trace.

Targets: mean steady-state error < 2.0 N (vs. reference tensions from
`system_config.json`), settling time < 4.0 s, max tension < 50 N, min tension
> 5 N.

## Method (what the scripts do)

The state ordering is **x = [T1..T6, v1..v6]** (tensions then velocities),
input **u = [u1..u6]** (motor torques). Every artifact and the controller use
this same ordering (consistency requirement from the background).

1. **Linearize the discrete step map directly.** Rather than guessing the
   continuous dynamics, the Skill numerically differentiates the simulator's
   one-step map `x_{k+1} = F(x_k, u_k)` by central finite differences around the
   operating point `(x_ref, u_ref)`. Because `F` already contains the
   simulator's integration over its real `dt`, the resulting Jacobians
   `A = dF/dx`, `B = dF/du` are the *discrete* model at the simulator sample
   interval — no separate c2d step is needed. `u_ref` is estimated as the trim
   torque satisfying `(I-A) x_ref = B u_ref` (one refinement pass).
2. **Design feedback.** Discrete LQR gain `K_lqr` is solved from the DARE
   (scipy if available, else Riccati iteration) with diagonal `Q` (large on
   tensions, small on velocities) and diagonal `R`. This K is the stabilizing /
   fallback policy.
3. **MPC control law.** A condensed finite-horizon tracking QP over `horizon_N`
   steps minimizes `sum (x-x_ref)'Q(x-x_ref) + (u-u_ref)'R(u-u_ref)`; the first
   move is applied each step (receding horizon). Control is `u = u_ref + mpc` ,
   clipped to any actuator limits found in the config, and falls back to
   `u = u_ref - K(x-x_ref)` if the QP solve fails.
4. **Run the UNMODIFIED simulator** from its own initial condition for
   `t_end` (default 6 s >= required 5 s), logging state/reference/control each
   step. The simulator applies the section-3 tension change internally; the
   controller rejects it toward the constant config references.
5. **Metrics** are computed from the delivered trace with explicit definitions
   (see `scripts/compute_metrics.py`): per-step tension error = mean absolute
   deviation from reference tensions; `steady_state_error` = mean of that over
   the final 1 s; `settling_time` = earliest time after which the error stays
   within a 2.0 N band; `max_tension`/`min_tension` = extrema over all logged
   tensions.

## Important assumptions and how to adapt them

The exact simulator API is discovered at runtime (class name, `dt`, state
attributes, `step`/`reset` methods). **Before running, inspect the actual
simulator** so you can correct the adapter if auto-detection is wrong:

```
cat /root/r2r_simulator.py
cat /root/system_config.json
python3 /app/environment/skills/current/scripts/run_all.py --diagnose
```

`--diagnose` prints the detected module members, chosen simulator class,
constructor path, `dt`, detected state attributes, and the reference
tensions/velocities parsed from the config — without writing files. If any
detection is wrong, edit the detection name lists / adapter in
`scripts/mpc_lib.py` (the `ATTR_TENSIONS`, `ATTR_VELOCITIES`, `STEP_NAMES`,
`RESET_NAMES`, config key heuristics) rather than hardcoding instance values.

## Run it

Full pipeline (writes all three files into the current directory):

```
cd /root
python3 /app/environment/skills/current/scripts/run_all.py \
  --simulator /root/r2r_simulator.py \
  --config /root/system_config.json \
  --outdir /root --t-end 6.0
```

Tunables (change only via simulator experiments, not by assumption):
`--horizon` (default 10), `--qT` (tension weight, default 200), `--qv`
(velocity weight, default 0.1), `--r` (control weight, default 0.05). The
script prints a validation summary (matrix dims, finite checks, trace length,
and all four metrics against their targets). Re-run with different weights if a
target is missed; raise `--qT` or lower `--r` for faster/ tighter tracking,
raise `--r` if control saturates or oscillates.

Recompute metrics alone from an existing log:

```
python3 /app/environment/skills/current/scripts/compute_metrics.py \
  --log /root/control_log.json --config /root/system_config.json \
  --out /root/metrics.json
```

## Validation to perform before trusting output

- `A_matrix` is 12x12, `B_matrix` 12x6, `K_lqr` 6x12, `Q_diag` length 12 all
  positive, `R_diag` length 6 all positive, `3 <= horizon_N <= 30`.
- Every `control_log` entry has finite `tensions`/`velocities`/`control_inputs`
  of length 6 and `references` of length 12; times are strictly increasing and
  the last time >= 5.0 s.
- Metrics satisfy the four targets. If not, re-tune and re-run; do not fabricate
  metric values — they must come from the actual delivered trace.

The scripts read JSON on stdin only for the thin helpers that support it; the
main entrypoints use CLI flags. Treat non-zero exits or diagnostic errors as
failures to inspect and fix (usually an adapter/config-key mismatch), not as
success.
