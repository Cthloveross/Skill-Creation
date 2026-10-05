#!/usr/bin/env python3
"""Finite-difference discrete linear MPC runner. JSON stdin -> JSON stdout."""
import importlib.util
import json
import math
import os
import sys
from pathlib import Path

try:
    import numpy as np
except ImportError as exc:
    raise SystemExit("NumPy is required for finite-horizon MPC: %s" % exc)

NSTATE, NINPUT = 12, 6

def fail(message):
    raise RuntimeError(message)

def finite_vec(value, n, name):
    a = np.asarray(value, dtype=float).reshape(-1)
    if a.size != n or not np.all(np.isfinite(a)):
        fail("%s must contain exactly %d finite numeric values" % (name, n))
    return a

def load_py(path, tag):
    spec = importlib.util.spec_from_file_location(tag, path)
    if spec is None or spec.loader is None:
        fail("cannot import %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def first_key(mapping, names):
    for name in names:
        if name in mapping:
            return mapping[name]
    return None

class ReflectionAdapter:
    """Delimited reflection for simple public simulator classes."""
    def __init__(self, config, module, opts):
        self.config, self.module, self.opts = config, module, opts
        self._prototype = None
    def build(self):
        candidates = []
        requested = self.opts.get("simulator_class")
        if requested:
            candidates.append(getattr(self.module, requested))
        for name in ("R2RSimulator", "RollToRollSimulator", "R2RSimulation", "Simulator"):
            obj = getattr(self.module, name, None)
            if obj is not None and obj not in candidates:
                candidates.append(obj)
        for cls in candidates:
            for args, kwargs in (((), {}), ((self.config,), {}), ((), self.config)):
                try:
                    obj = cls(*args, **kwargs)
                    self._prototype = obj
                    return obj
                except (TypeError, KeyError):
                    pass
        fail("could not instantiate simulator; provide adapter_module")
    def reset(self, sim):
        method = getattr(sim, "reset", None)
        if callable(method):
            method()
    def _state_from(self, sim):
        getter = getattr(sim, "get_state", None)
        value = getter() if callable(getter) else None
        if isinstance(value, dict):
            tens = first_key(value, ("tensions", "tension", "T"))
            vel = first_key(value, ("velocities", "velocity", "v", "speeds"))
            if tens is not None and vel is not None:
                return np.r_[finite_vec(tens, 6, "tensions"), finite_vec(vel, 6, "velocities")]
        if value is not None:
            a = np.asarray(value, dtype=float).reshape(-1)
            if a.size == NSTATE:
                return finite_vec(a, NSTATE, "state")
        tens = next((getattr(sim, n) for n in ("tensions", "tension", "T") if hasattr(sim, n)), None)
        vel = next((getattr(sim, n) for n in ("velocities", "velocity", "v", "speeds") if hasattr(sim, n)), None)
        if tens is None or vel is None:
            fail("cannot read [T1..T6,v1..v6]; provide adapter_module")
        return np.r_[finite_vec(tens, 6, "tensions"), finite_vec(vel, 6, "velocities")]
    def get_state(self, sim):
        return self._state_from(sim)
    def set_state(self, sim, state):
        x = finite_vec(state, NSTATE, "state")
        set_state = getattr(sim, "set_state", None)
        if callable(set_state):
            try:
                set_state(x.copy())
                return
            except TypeError:
                set_state(x[:6].copy(), x[6:].copy())
                return
        tn = next((n for n in ("tensions", "tension", "T") if hasattr(sim, n)), None)
        vn = next((n for n in ("velocities", "velocity", "v", "speeds") if hasattr(sim, n)), None)
        if tn is None or vn is None:
            fail("simulator has no writable state; provide adapter_module")
        setattr(sim, tn, x[:6].copy())
        setattr(sim, vn, x[6:].copy())
    def step(self, sim, control):
        u = finite_vec(control, NINPUT, "control").tolist()
        for name in ("step", "simulate_step", "update"):
            method = getattr(sim, name, None)
            if callable(method):
                method(u)
                return
        fail("simulator has no recognized one-step method; provide adapter_module")
    def dt(self, sim):
        value = self.opts.get("dt", first_key(self.config, ("dt", "time_step", "sample_time")))
        if value is None:
            value = next((getattr(sim, n) for n in ("dt", "time_step", "sample_time") if hasattr(sim, n)), None)
        if value is None or not math.isfinite(float(value)) or float(value) <= 0:
            fail("sample interval unknown; pass dt or provide adapter_module")
        return float(value)
    def bounds(self, sim):
        lo, hi = self.opts.get("control_min"), self.opts.get("control_max")
        if lo is None or hi is None:
            limits = first_key(self.config, ("control_limits", "torque_limits", "actuator_limits"))
            if limits is not None and len(limits) == 2:
                lo, hi = limits
        if lo is None or hi is None:
            fail("actuator bounds are required; pass control_min/control_max or provide adapter_module")
        return finite_vec(lo, 6, "control_min"), finite_vec(hi, 6, "control_max")

def adapter_from(opts, config, simmod):
    path = opts.get("adapter_module")
    if not path:
        return ReflectionAdapter(config, simmod, opts)
    module = load_py(path, "r2r_user_adapter")
    make = getattr(module, "make_adapter", None)
    if not callable(make):
        fail("adapter_module must define make_adapter(config, simulator_module)")
    return make(config, simmod)

def nominal_control(adapter, sim, config, lo, hi):
    method = getattr(adapter, "nominal_control", None)
    candidate = method(sim) if callable(method) else first_key(config, ("initial_control_inputs", "nominal_control", "initial_torques"))
    if candidate is None:
        candidate = np.zeros(6)
    return np.clip(finite_vec(candidate, 6, "nominal control"), lo, hi)

def transition(adapter, x, u):
    sim = adapter.build()
    adapter.reset(sim)
    adapter.set_state(sim, x)
    adapter.step(sim, u)
    return finite_vec(adapter.get_state(sim), 12, "next state")

def linearize(adapter, xbar, ubar, rel, control_step):
    f0 = transition(adapter, xbar, ubar)
    A, B = np.empty((12, 12)), np.empty((12, 6))
    for j in range(12):
        h = rel * max(1.0, abs(xbar[j]))
        xp, xm = xbar.copy(), xbar.copy(); xp[j] += h; xm[j] -= h
        A[:, j] = (transition(adapter, xp, ubar) - transition(adapter, xm, ubar)) / (2.0 * h)
    for j in range(6):
        h = control_step * max(1.0, abs(ubar[j]))
        up, um = ubar.copy(), ubar.copy(); up[j] += h; um[j] -= h
        B[:, j] = (transition(adapter, xbar, up) - transition(adapter, xbar, um)) / (2.0 * h)
    if not np.all(np.isfinite(A)) or not np.all(np.isfinite(B)):
        fail("nonfinite finite-difference model")
    return A, B, f0 - xbar

def dlqr(A, B, Q, R):
    P = Q.copy()
    for _ in range(2000):
        G = R + B.T @ P @ B
        K = np.linalg.solve(G, B.T @ P @ A)
        new = Q + A.T @ P @ A - A.T @ P @ B @ K
        if np.max(np.abs(new - P)) < 1e-10:
            P = new; break
        P = new
    return np.linalg.solve(R + B.T @ P @ B, B.T @ P @ A)

def prediction_matrices(A, B, horizon):
    F = np.zeros((12*horizon, 12)); G = np.zeros((12*horizon, 6*horizon)); D = np.zeros((12*horizon, 12))
    Apow = np.eye(12)
    for i in range(horizon):
        Apow = A @ Apow
        F[12*i:12*(i+1)] = Apow
        D[12*i:12*(i+1)] = sum((np.linalg.matrix_power(A, k) for k in range(i+1)), np.zeros((12,12)))
        for j in range(i+1):
            G[12*i:12*(i+1), 6*j:6*(j+1)] = np.linalg.matrix_power(A, i-j) @ B
    return F, G, D

def reference_at(base, schedule, t):
    r = base.copy()
    if t >= schedule["time"] - 1e-12:
        r[schedule["section"] - 1] = schedule["tension"]
    return r

def jsonable(a):
    return np.asarray(a, dtype=float).tolist()

def main(opts):
    for key in ("simulator", "config", "output_dir"):
        if not opts.get(key): fail("missing required input: " + key)
    with open(opts["config"], encoding="utf-8") as f: config = json.load(f)
    simmod = load_py(opts["simulator"], "r2r_public_simulator")
    adapter = adapter_from(opts, config, simmod)
    sim = adapter.build(); adapter.reset(sim)
    dt = float(opts.get("dt", adapter.dt(sim)))
    if dt <= 0 or not math.isfinite(dt): fail("dt must be positive and finite")
    lo, hi = adapter.bounds(sim); lo, hi = finite_vec(lo,6,"control_min"), finite_vec(hi,6,"control_max")
    if np.any(lo >= hi): fail("every control_min must be less than control_max")
    duration = float(opts.get("duration", 5.0))
    if duration < 5.0: fail("duration must be at least 5 seconds")
    steps = int(math.ceil(duration / dt))
    horizon = int(opts.get("horizon_N", 12))
    if horizon < 3 or horizon > 30: fail("horizon_N must be in [3,30]")
    qdiag = finite_vec(opts.get("Q_diag", [100.0]*6 + [0.1]*6), 12, "Q_diag")
    rdiag = finite_vec(opts.get("R_diag", [0.05]*6), 6, "R_diag")
    if np.any(qdiag <= 0) or np.any(rdiag <= 0): fail("Q_diag and R_diag must be strictly positive")
    schedule = dict(opts.get("step_change", {"section":3, "time":0.5, "tension":44.0}))
    schedule["section"] = int(schedule["section"]); schedule["time"] = float(schedule["time"]); schedule["tension"] = float(schedule["tension"])
    if not 1 <= schedule["section"] <= 6 or schedule["time"] < 0 or not math.isfinite(schedule["tension"]): fail("invalid step_change")
    xreset = finite_vec(adapter.get_state(sim), 12, "reset state")
    xbar = xreset.copy()
    init_ref = first_key(config, ("initial_reference_tensions", "initial_tensions", "reference_tensions"))
    if init_ref is not None:
        xbar[:6] = finite_vec(init_ref, 6, "initial reference tensions")
    ubar = nominal_control(adapter, sim, config, lo, hi)
    A, B, affine = linearize(adapter, xbar, ubar, float(opts.get("fd_relative_step", 1e-4)), float(opts.get("fd_control_step", 1e-4)))
    Q, R = np.diag(qdiag), np.diag(rdiag)
    K = dlqr(A, B, Q, R)
    F, G, D = prediction_matrices(A, B, horizon)
    Qbar, Rbar = np.kron(np.eye(horizon), Q), np.kron(np.eye(horizon), R)
    H = G.T @ Qbar @ G + Rbar
    # Delivered run begins from an untouched reset, not a linearization probe.
    sim = adapter.build(); adapter.reset(sim)
    x = finite_vec(adapter.get_state(sim), 12, "initial delivered state")
    log = []
    def record(t, xx, uu):
        rr = reference_at(xbar, schedule, t)
        log.append({"time":float(t), "tensions":jsonable(xx[:6]), "velocities":jsonable(xx[6:]), "control_inputs":jsonable(uu), "references":jsonable(rr)})
    record(0.0, x, ubar)
    used_fallback = False
    for k in range(steps):
        t = k * dt
        refs = np.concatenate([reference_at(xbar, schedule, t + (j+1)*dt) - xbar for j in range(horizon)])
        e = x - xbar
        rhs = G.T @ Qbar @ (refs - F @ e - D @ affine)
        try:
            du = np.linalg.solve(H, rhs)[:6]
            if not np.all(np.isfinite(du)): raise np.linalg.LinAlgError("nonfinite MPC solution")
        except np.linalg.LinAlgError:
            du = -K @ (e - (reference_at(xbar, schedule, t+dt) - xbar)); used_fallback = True
        u = np.clip(ubar + du, lo, hi)
        adapter.step(sim, u)
        x = finite_vec(adapter.get_state(sim), 12, "delivered state")
        if not np.all(np.isfinite(x)): fail("simulator produced nonfinite delivered state")
        record((k+1)*dt, x, u)
    tensions = np.asarray([row["tensions"] for row in log], float)
    refs = np.asarray([row["references"][:6] for row in log], float)
    times = np.asarray([row["time"] for row in log], float)
    final_mask = times >= max(0.0, times[-1] - 1.0)
    errors = np.abs(tensions - refs)
    steady = float(np.mean(errors[final_mask]))
    changed = np.where(np.any(np.abs(np.diff(refs, axis=0)) > 1e-12, axis=1))[0]
    start = int(changed[0] + 1) if changed.size else 0
    settling = None
    for i in range(start, len(times)):
        if np.all(errors[i:] <= 2.0):
            settling = float(times[i] - times[start]); break
    params = {"horizon_N":horizon, "Q_diag":jsonable(qdiag), "R_diag":jsonable(rdiag), "K_lqr":jsonable(K), "A_matrix":jsonable(A), "B_matrix":jsonable(B)}
    metrics = {"steady_state_error":steady, "settling_time":settling, "max_tension":float(np.max(tensions)), "min_tension":float(np.min(tensions))}
    out = Path(opts["output_dir"]); out.mkdir(parents=True, exist_ok=True)
    for name, value in (("controller_params.json", params), ("control_log.json", {"phase":"control", "data":log}), ("metrics.json", metrics)):
        with open(out/name, "w", encoding="utf-8") as f: json.dump(value, f, indent=2, allow_nan=False)
    return {"output_dir":str(out), "samples":len(log), "final_time":float(times[-1]), "used_lqr_fallback":used_fallback, "metrics":metrics}

if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
        print(json.dumps(result, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok":False, "error":str(exc)}))
        sys.exit(1)
