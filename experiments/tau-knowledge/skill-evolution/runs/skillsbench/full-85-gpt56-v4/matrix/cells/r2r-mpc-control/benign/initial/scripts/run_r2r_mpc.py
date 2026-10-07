#!/usr/bin/env python3
"""Numerical-model MPC runner. Reads a JSON request from stdin and writes JSON artifacts."""
import importlib.util
import inspect
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

NSTATE, NINPUT = 12, 6


def plain(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, dict):
        return {str(k): plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    return x


def finite(x, name):
    a = np.asarray(x, dtype=float)
    if not np.all(np.isfinite(a)):
        raise ValueError(name + " contains non-finite values")
    return a


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def walk_values(obj, key_hint=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_values(v, str(k).lower())
    elif isinstance(obj, list):
        yield key_hint, obj


def vector_from_config(cfg, words, fallback=None):
    """Find a six-value vector whose key contains one of words, preferring exact hints."""
    found = []
    for key, value in walk_values(cfg):
        if len(value) == 6 and any(w in key for w in words):
            try:
                found.append((key, finite(value, key).reshape(6)))
            except (TypeError, ValueError):
                pass
    if found:
        found.sort(key=lambda p: (0 if any(w == p[0] for w in words) else 1, len(p[0])))
        return found[0][1]
    if fallback is not None:
        return np.asarray(fallback, dtype=float).reshape(6)
    return None


def scalar_from_config(cfg, words, default):
    candidates = []
    def rec(o, prefix=""):
        if isinstance(o, dict):
            for k, v in o.items(): rec(v, (prefix + "." + str(k)).lower())
        elif isinstance(o, (int, float)) and any(w in prefix for w in words):
            candidates.append((prefix, float(o)))
    rec(cfg)
    return candidates[0][1] if candidates else default


def load_module(path):
    spec = importlib.util.spec_from_file_location("supplied_r2r_simulator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import simulator from " + path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def construct_simulator(mod, cfg, cfg_path):
    classes = []
    for name, value in vars(mod).items():
        if inspect.isclass(value) and value.__module__ == mod.__name__:
            score = 0 if "sim" in name.lower() else 1
            classes.append((score, name, value))
    classes.sort(key=lambda x: (x[0], x[1]))
    errors = []
    for _, name, cls in classes:
        for args in ((), (cfg,), (cfg_path,)):
            try:
                ob = cls(*args)
                if callable(getattr(ob, "step", None)):
                    return ob, name
            except Exception as exc:
                errors.append(name + repr(args) + ": " + str(exc))
    raise RuntimeError("no constructible simulator class with step(); attempts: " + " | ".join(errors[-5:]))


def reset(sim):
    fn = getattr(sim, "reset", None)
    if callable(fn):
        return fn()
    return None


def dict_get_case(mapping, names):
    if not isinstance(mapping, dict):
        return None
    lower = {str(k).lower(): v for k, v in mapping.items()}
    for n in names:
        if n in lower:
            return lower[n]
    return None


def observation_state(sim, observation=None):
    """Read [six tensions, six velocities] from a step/reset return or simulator fields."""
    candidates = [observation]
    for attr in ("state", "observation", "obs"):
        if hasattr(sim, attr): candidates.append(getattr(sim, attr))
    ten_names = ("tensions", "tension", "web_tensions", "t")
    vel_names = ("velocities", "velocity", "roller_velocities", "v", "speeds")
    for ob in candidates:
        if isinstance(ob, (tuple, list)) and len(ob) >= 2 and not isinstance(ob[0], (int, float, np.number)):
            t, v = ob[0], ob[1]
        elif isinstance(ob, dict):
            t, v = dict_get_case(ob, ten_names), dict_get_case(ob, vel_names)
        else:
            t = v = None
        if t is not None and v is not None:
            tt, vv = np.asarray(t, dtype=float).reshape(-1), np.asarray(v, dtype=float).reshape(-1)
            if tt.size == 6 and vv.size == 6:
                return np.r_[tt, vv]
    # Attributes are deliberately checked last: a returned observation is usually freshest.
    for tn in ten_names:
        for vn in vel_names:
            if hasattr(sim, tn) and hasattr(sim, vn):
                tt, vv = np.asarray(getattr(sim, tn), dtype=float).reshape(-1), np.asarray(getattr(sim, vn), dtype=float).reshape(-1)
                if tt.size == 6 and vv.size == 6:
                    return np.r_[tt, vv]
    raise RuntimeError("simulator state must expose six tensions and six velocities")


def assign_state(sim, x):
    """Try common public state setters. Returns whether a setter was accepted."""
    x = np.asarray(x, dtype=float).reshape(12)
    for name in ("set_state", "set_initial_state"):
        fn = getattr(sim, name, None)
        if callable(fn):
            for args in ((x,), (x[:6], x[6:])):
                try:
                    fn(*args)
                    return True
                except Exception:
                    pass
    success = False
    for names, value in ((("tensions", "tension", "web_tensions"), x[:6]), (("velocities", "velocity", "roller_velocities", "speeds"), x[6:])):
        for name in names:
            if hasattr(sim, name):
                try:
                    old = getattr(sim, name)
                    setattr(sim, name, np.asarray(value, dtype=getattr(old, "dtype", float)))
                    success = True
                    break
                except Exception:
                    pass
    return success


def step_state(sim, u):
    answer = sim.step(np.asarray(u, dtype=float))
    return observation_state(sim, answer)


def make_transition(module, cfg, cfg_path, x0):
    """Return a fresh one-step transition and whether its state could be set."""
    support = {"writable": True}
    def trans(x, u):
        sim, _ = construct_simulator(module, cfg, cfg_path)
        obs = reset(sim)
        if not assign_state(sim, x):
            support["writable"] = False
        # Even for a read-only plant, this yields the real reset transition.
        return step_state(sim, u)
    # Probe once now so the caller can select the true accessible operating point.
    sim, _ = construct_simulator(module, cfg, cfg_path)
    obs = reset(sim)
    baseline = observation_state(sim, obs)
    assign_state(sim, x0)
    try:
        actual = observation_state(sim)
    except Exception:
        actual = baseline
    return trans, support, baseline, actual


def numerical_model(trans, xop, uop, eps_x=1e-4, eps_u=1e-4):
    xop, uop = finite(xop, "operating state"), finite(uop, "operating action")
    f0 = trans(xop, uop)
    A = np.empty((12, 12)); B = np.empty((12, 6))
    for j in range(12):
        h = eps_x * max(1.0, abs(xop[j]))
        d = np.zeros(12); d[j] = h
        A[:, j] = (trans(xop + d, uop) - trans(xop - d, uop)) / (2.0 * h)
    for j in range(6):
        h = eps_u * max(1.0, abs(uop[j]))
        d = np.zeros(6); d[j] = h
        B[:, j] = (trans(xop, uop + d) - trans(xop, uop - d)) / (2.0 * h)
    return finite(A, "A"), finite(B, "B"), finite(f0, "f0")


def terminal_lqr(A, B, Q, R):
    P = Q.copy()
    for _ in range(2000):
        H = R + B.T @ P @ B
        K = np.linalg.solve(H, B.T @ P @ A)
        new = Q + A.T @ P @ A - A.T @ P @ B @ K
        new = (new + new.T) / 2.0
        if np.max(np.abs(new - P)) < 1e-10:
            P = new; break
        P = new
    return np.linalg.solve(R + B.T @ P @ B, B.T @ P @ A)


def tracking_action(A, B, Q, R, x, refs, ueq):
    """Finite-horizon affine dynamic programming for an absolute-state reference sequence."""
    P = Q.copy(); p = -Q @ refs[-1]
    c = B @ ueq
    first_F = first_g = None
    for k in range(len(refs) - 1, -1, -1):
        H = R + B.T @ P @ B
        G = B.T @ P @ A
        h = B.T @ (P @ c + p)
        F = -np.linalg.solve(H, G)
        g = -np.linalg.solve(H, h)
        if k == 0:
            first_F, first_g = F, g
        Pold, pold = P, p
        P = Q + A.T @ Pold @ A - G.T @ np.linalg.solve(H, G)
        p = -Q @ refs[k] + A.T @ (Pold @ c + pold) - G.T @ np.linalg.solve(H, h)
        P = (P + P.T) / 2.0
    return ueq + first_F @ x + first_g


def validate(params, log, duration):
    if not (3 <= params["horizon_N"] <= 30): raise ValueError("horizon outside [3,30]")
    if np.asarray(params["A_matrix"]).shape != (12,12): raise ValueError("A shape")
    if np.asarray(params["B_matrix"]).shape != (12,6): raise ValueError("B shape")
    if np.asarray(params["K_lqr"]).shape != (6,12): raise ValueError("K shape")
    if len(params["Q_diag"]) != 12 or min(params["Q_diag"]) <= 0: raise ValueError("invalid Q")
    if len(params["R_diag"]) != 6 or min(params["R_diag"]) <= 0: raise ValueError("invalid R")
    data = log["data"]
    if not data or data[-1]["time"] < duration - 1e-9 or data[-1]["time"] < 5.0: raise ValueError("log does not span required duration")
    for row in data:
        if any(len(row[k]) != 6 for k in ("tensions", "velocities", "control_inputs")) or len(row["references"]) != 12:
            raise ValueError("bad log row shape")
        finite(row["tensions"] + row["velocities"] + row["control_inputs"] + row["references"], "log")


def main(request):
    sim_path = request.get("simulator_path", "/root/r2r_simulator.py")
    cfg_path = request.get("config_path", "/root/system_config.json")
    outdir = Path(request.get("output_dir", ".")); outdir.mkdir(parents=True, exist_ok=True)
    duration = float(request.get("duration", 5.1)); horizon = int(request.get("horizon_N", 12))
    if duration < 5.0: raise ValueError("duration must be at least 5 seconds")
    if not 3 <= horizon <= 30: raise ValueError("horizon_N must be in [3,30]")
    cfg, module = load_json(cfg_path), load_module(sim_path)
    probe, clsname = construct_simulator(module, cfg, cfg_path)
    initial_obs = reset(probe); initial_x = observation_state(probe, initial_obs)
    tref = vector_from_config(cfg, ("reference_tensions", "tension_references", "target_tensions", "tension_setpoints"), initial_x[:6])
    vref = vector_from_config(cfg, ("reference_velocities", "velocity_references", "target_velocities", "velocity_setpoints"), initial_x[6:])
    r0 = np.r_[tref, vref]
    ueq = vector_from_config(cfg, ("equilibrium_torque", "initial_torque", "initial_control", "nominal_torque"), np.zeros(6))
    dt = scalar_from_config(cfg, ("time_step", "timestep", ".dt"), getattr(probe, "dt", 0.01))
    if not (math.isfinite(dt) and dt > 0): raise ValueError("simulator timestep is invalid")
    max_u = vector_from_config(cfg, ("max_torque", "torque_limit", "motor_limit", "actuator_limit"), None)
    if max_u is None:
        attr = getattr(probe, "max_torque", getattr(probe, "torque_limit", 20.0))
        max_u = np.full(6, float(np.max(np.abs(np.asarray(attr, dtype=float)))))
    max_u = np.abs(max_u); min_u = -max_u
    transition, writable, reset_x, actual_x = make_transition(module, cfg, cfg_path, r0)
    xop = r0 if writable["writable"] else reset_x
    A, B, f0 = numerical_model(transition, xop, ueq)
    Qdiag = np.asarray(request.get("Q_diag", [120.0]*6 + [1.0]*6), dtype=float)
    Rdiag = np.asarray(request.get("R_diag", [0.08]*6), dtype=float)
    if Qdiag.shape != (12,) or Rdiag.shape != (6,) or np.min(Qdiag) <= 0 or np.min(Rdiag) <= 0: raise ValueError("positive Q_diag(12) and R_diag(6) required")
    Q, R = np.diag(Qdiag), np.diag(Rdiag)
    K = terminal_lqr(A, B, Q, R)
    change_time = float(request.get("change_time", 0.5)); section = int(request.get("change_section", 3)) - 1
    change_value = float(request.get("change_tension", 44.0))
    if not 0 <= section < 6: raise ValueError("change_section must be 1..6")
    sim, _ = construct_simulator(module, cfg, cfg_path); obs = reset(sim); x = observation_state(sim, obs)
    rows = []; count = int(math.ceil(duration / dt))
    def ref_at(t):
        r = r0.copy()
        if t >= change_time: r[section] = change_value
        return r
    for k in range(count):
        t0 = k * dt
        refs = [ref_at(t0 + (j + 1) * dt) for j in range(horizon)]
        u = tracking_action(A, B, Q, R, x, refs, ueq)
        u = np.minimum(np.maximum(finite(u, "action"), min_u), max_u)
        x = step_state(sim, u)
        tlog = (k + 1) * dt
        rows.append({"time": float(tlog), "tensions": plain(x[:6]), "velocities": plain(x[6:]), "control_inputs": plain(u), "references": plain(ref_at(tlog))})
    params = {"horizon_N": horizon, "Q_diag": plain(Qdiag), "R_diag": plain(Rdiag), "K_lqr": plain(K), "A_matrix": plain(A), "B_matrix": plain(B)}
    log = {"phase": "control", "data": rows}
    final = [r for r in rows if r["time"] >= rows[-1]["time"] - 1.0]
    errors = np.asarray([np.abs(np.asarray(r["tensions"]) - np.asarray(r["references"][:6])) for r in final])
    allerr = np.asarray([np.abs(np.asarray(r["tensions"]) - np.asarray(r["references"][:6])) for r in rows])
    start = next((i for i,r in enumerate(rows) if r["time"] >= change_time), 0)
    settling = None
    for i in range(start, len(rows)):
        if np.all(allerr[i:] <= 2.0):
            settling = float(rows[i]["time"] - change_time); break
    tensions = np.asarray([r["tensions"] for r in rows], dtype=float)
    metrics = {"steady_state_error": float(np.mean(errors)), "settling_time": settling, "max_tension": float(np.max(tensions)), "min_tension": float(np.min(tensions))}
    validate(params, log, duration)
    for filename, obj in (("controller_params.json", params), ("control_log.json", log), ("metrics.json", metrics)):
        with open(outdir / filename, "w", encoding="utf-8") as f: json.dump(obj, f, indent=2, allow_nan=False)
    # A small local linear prediction check, reported rather than placed in required schemas.
    local_residual = float(np.max(np.abs(f0 - (A @ xop + B @ ueq))))
    return {"status": "ok", "simulator_class": clsname, "dt": float(dt), "steps": len(rows), "linearization_state_writable": bool(writable["writable"]), "local_affine_residual": local_residual, "metrics": metrics, "output_dir": str(outdir)}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        print(json.dumps(main(request), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        sys.exit(2)
