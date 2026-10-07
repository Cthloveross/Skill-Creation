#!/usr/bin/env python3
"""End-to-end entrypoint: linearize, design MPC/LQR, simulate, log, metrics.

Writes controller_params.json, control_log.json, metrics.json into --outdir.
Use --diagnose to inspect the detected simulator/config without writing files.

CLI flags (no stdin needed):
  --simulator PATH   (default /root/r2r_simulator.py)
  --config PATH      (default /root/system_config.json)
  --outdir DIR       (default current working directory)
  --t-end SECONDS    (default 6.0, must yield a trace >= 5 s)
  --horizon N        prediction horizon in [3,30] (default 10)
  --qT, --qv, --r    cost weights (tension, velocity, control)
  --diagnose         print detected API/config and exit
"""
import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpc_lib as ml  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulator", default="/root/r2r_simulator.py")
    ap.add_argument("--config", default="/root/system_config.json")
    ap.add_argument("--outdir", default=os.getcwd())
    ap.add_argument("--t-end", type=float, default=6.0)
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--qT", type=float, default=200.0)
    ap.add_argument("--qv", type=float, default=0.1)
    ap.add_argument("--r", type=float, default=0.05)
    ap.add_argument("--diagnose", action="store_true")
    args = ap.parse_args()

    config = ml.load_config(args.config)
    mod = ml.load_module(args.simulator)
    adapter = ml.SimAdapter(mod, args.config, config)
    ref_T, ref_v, refinfo = ml.extract_references(config)
    x_ref = np.concatenate([ref_T, ref_v])
    u_lo, u_hi = ml.extract_u_limits(config)

    if args.diagnose:
        desc = ml.describe_module(mod)
        print("=== MODULE ===")
        print(json.dumps(desc, indent=2))
        print("=== CHOSEN SIM CLASS ===", adapter.cls.__name__)
        print("dt =", adapter.dt)
        print("attr_T=", adapter.attr_T, "attr_v=", adapter.attr_v,
              "attr_t=", adapter.attr_t, "step=", adapter.step_name,
              "reset=", adapter.reset_name)
        print("=== CONFIG ===")
        print(json.dumps(config, indent=2))
        print("ref_tensions=", ref_T.tolist())
        print("ref_velocities=", ref_v.tolist(), refinfo)
        print("u_limits=", (u_lo, u_hi))
        try:
            s = adapter.new()
            x0 = adapter.get_state(s)
            print("initial state from sim =", x0.tolist())
        except Exception as e:  # noqa: BLE001
            print("state read failed:", e)
        return

    horizon = int(max(3, min(30, args.horizon)))

    # 1) linearize around operating point (refine u_ref once)
    u_ref = np.zeros(ml.N_U)
    A, B = ml.linearize_discrete(adapter.step_once, x_ref, u_ref)
    u_ref = ml.estimate_u_ref(A, B, x_ref)
    A, B = ml.linearize_discrete(adapter.step_once, x_ref, u_ref)
    u_ref = ml.estimate_u_ref(A, B, x_ref)

    # 2) weights and feedback
    Q_diag = np.array([args.qT] * ml.N_T + [args.qv] * ml.N_V, float)
    R_diag = np.array([args.r] * ml.N_U, float)
    Q = np.diag(Q_diag)
    R = np.diag(R_diag)
    K, _ = ml.dlqr(A, B, Q, R)
    mpc = ml.build_mpc(A, B, Q, R, horizon)

    # write controller params
    params = {
        "horizon_N": horizon,
        "Q_diag": Q_diag.tolist(),
        "R_diag": R_diag.tolist(),
        "K_lqr": K.tolist(),
        "A_matrix": A.tolist(),
        "B_matrix": B.tolist(),
    }
    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(args.outdir, "controller_params.json"), "w") as f:
        json.dump(params, f, indent=2)

    # 4) run simulation with receding-horizon MPC (LQR fallback)
    s = adapter.new()
    t0 = adapter.get_time(s)
    t = 0.0 if t0 is None else t0
    dt = adapter.dt
    data = []
    n_steps = int(math.ceil(args.t_end / dt)) + 1
    for _ in range(n_steps):
        x = adapter.get_state(s)
        xe = x - x_ref
        try:
            du = ml.mpc_first_move(mpc, xe)
            u = u_ref + du
        except Exception:  # noqa: BLE001
            u = u_ref - K @ xe
        u = ml.clip_u(u, u_lo, u_hi)
        data.append({
            "time": float(t),
            "tensions": x[:ml.N_T].tolist(),
            "velocities": x[ml.N_T:ml.N_X].tolist(),
            "control_inputs": np.asarray(u, float).tolist(),
            "references": x_ref.tolist(),
        })
        adapter.step(s, u)
        tnew = adapter.get_time(s)
        t = (t + dt) if tnew is None else tnew
        if t > args.t_end + dt / 2:
            break

    log = {"phase": "control", "data": data}
    with open(os.path.join(args.outdir, "control_log.json"), "w") as f:
        json.dump(log, f)

    # 5) metrics
    metrics = compute_metrics(data, ref_T)
    with open(os.path.join(args.outdir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    print_summary(params, data, metrics)


def compute_metrics(data, ref_T, band=2.0, ss_window=1.0):
    ref_T = np.asarray(ref_T, float)
    times = np.array([d["time"] for d in data], float)
    Tmat = np.array([d["tensions"] for d in data], float)
    errs = np.mean(np.abs(Tmat - ref_T[None, :]), axis=1)
    # steady state: mean over final ss_window seconds
    tend = times[-1]
    mask = times >= (tend - ss_window)
    ss = float(np.mean(errs[mask])) if mask.any() else float(errs[-1])
    # settling time: earliest time after which err stays within band
    settle = float(tend)
    for i in range(len(errs)):
        if np.all(errs[i:] <= band):
            settle = float(times[i])
            break
    return {
        "steady_state_error": ss,
        "settling_time": settle,
        "max_tension": float(np.max(Tmat)),
        "min_tension": float(np.min(Tmat)),
    }


def print_summary(params, data, metrics):
    A = np.array(params["A_matrix"])
    B = np.array(params["B_matrix"])
    K = np.array(params["K_lqr"])
    print("--- validation ---")
    print("A", A.shape, "B", B.shape, "K", K.shape)
    print("finite A/B/K:", np.all(np.isfinite(A)), np.all(np.isfinite(B)),
          np.all(np.isfinite(K)))
    print("horizon_N", params["horizon_N"], "Q len", len(params["Q_diag"]),
          "R len", len(params["R_diag"]))
    print("trace steps", len(data), "last time", data[-1]["time"] if data else None)
    print("metrics", json.dumps(metrics))
    tgt = {
        "steady_state_error<2.0": metrics["steady_state_error"] < 2.0,
        "settling_time<4.0": metrics["settling_time"] < 4.0,
        "max_tension<50": metrics["max_tension"] < 50.0,
        "min_tension>5": metrics["min_tension"] > 5.0,
    }
    print("targets", json.dumps(tgt))
    if not all(tgt.values()):
        print("WARNING: one or more targets not met; re-tune weights/horizon.")


if __name__ == "__main__":
    main()
