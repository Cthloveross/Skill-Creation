"""Reusable helpers for R2R MPC tension control.

State ordering: x = [T1..T6, v1..v6] (6 tensions then 6 velocities).
Input ordering: u = [u1..u6] (motor torques).

The simulator API is unknown ahead of time, so this module discovers it at
runtime and exposes a small adapter. Edit the NAME lists below if auto
detection fails for a given simulator.
"""
import importlib.util
import inspect
import json
import os
import numpy as np

# --- adapter configuration: extend these if detection fails -----------------
ATTR_TENSIONS = ["tensions", "T", "web_tensions", "tension", "Ts"]
ATTR_VELOCITIES = ["velocities", "v", "roller_velocities", "velocity", "vels", "V"]
ATTR_TIME = ["time", "t", "current_time", "sim_time"]
ATTR_DT = ["dt", "timestep", "ts", "delta_t", "sample_time"]
STEP_NAMES = ["step", "update", "advance", "simulate_step"]
RESET_NAMES = ["reset", "initialize", "init_state"]
CLASS_HINTS = ["sim", "r2r", "system", "plant", "model", "line"]

N_T = 6  # tensions
N_V = 6  # velocities
N_X = N_T + N_V
N_U = 6


def load_module(path):
    spec = importlib.util.spec_from_file_location("r2r_simulator_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_config(path):
    with open(path) as f:
        return json.load(f)


def _first_attr(obj, names):
    for n in names:
        if hasattr(obj, n):
            return n
    return None


def describe_module(mod):
    out = {"module_members": [], "classes": [], "functions": []}
    for name, obj in vars(mod).items():
        if name.startswith("_"):
            continue
        out["module_members"].append(name)
        if inspect.isclass(obj):
            methods = [m for m in dir(obj) if not m.startswith("_")]
            out["classes"].append({"name": name, "methods": methods})
        elif inspect.isfunction(obj):
            try:
                sig = str(inspect.signature(obj))
            except (ValueError, TypeError):
                sig = "?"
            out["functions"].append({"name": name, "signature": sig})
    return out


def pick_sim_class(mod):
    candidates = []
    for name, obj in vars(mod).items():
        if not inspect.isclass(obj):
            continue
        methods = {m.lower() for m in dir(obj)}
        has_step = any(s in methods for s in STEP_NAMES)
        score = 0
        if has_step:
            score += 10
        if any(h in name.lower() for h in CLASS_HINTS):
            score += 5
        if obj.__module__ == mod.__name__:
            score += 2
        if score > 0:
            candidates.append((score, name, obj))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates[0][2]


class SimAdapter:
    """Wrap a discovered simulator so the controller can reset/get/set/step."""

    def __init__(self, mod, config_path, config):
        self.mod = mod
        self.config_path = config_path
        self.config = config
        self.cls = pick_sim_class(mod)
        if self.cls is None:
            raise RuntimeError(
                "Could not find a simulator class with a step method. "
                "Run with --diagnose and edit mpc_lib.py adapter lists.")
        self._probe()

    def _construct(self):
        attempts = [
            lambda: self.cls(),
            lambda: self.cls(self.config),
            lambda: self.cls(self.config_path),
            lambda: self.cls(config=self.config),
            lambda: self.cls(config_path=self.config_path),
        ]
        last = None
        for a in attempts:
            try:
                return a()
            except Exception as e:  # noqa: BLE001
                last = e
        raise RuntimeError(f"Could not construct {self.cls.__name__}: {last}")

    def _probe(self):
        s = self._construct()
        self.attr_T = _first_attr(s, ATTR_TENSIONS)
        self.attr_v = _first_attr(s, ATTR_VELOCITIES)
        self.attr_t = _first_attr(s, ATTR_TIME)
        self.step_name = next((n for n in STEP_NAMES if hasattr(s, n)), None)
        self.reset_name = next((n for n in RESET_NAMES if hasattr(s, n)), None)
        self.dt = self._detect_dt(s)
        if self.step_name is None:
            raise RuntimeError("No step method found on simulator instance.")

    def _detect_dt(self, s):
        for n in ATTR_DT:
            if hasattr(s, n):
                try:
                    return float(getattr(s, n))
                except (TypeError, ValueError):
                    pass
        for n in ATTR_DT:
            if n in self.config:
                return float(self.config[n])
        return 0.01  # fallback; verify via --diagnose

    def new(self):
        s = self._construct()
        if self.reset_name is not None:
            try:
                getattr(s, self.reset_name)()
            except Exception:  # noqa: BLE001
                pass
        return s

    def get_state(self, s):
        T = np.asarray(getattr(s, self.attr_T), dtype=float).reshape(-1)
        v = np.asarray(getattr(s, self.attr_v), dtype=float).reshape(-1)
        return np.concatenate([T[:N_T], v[:N_V]])

    def get_time(self, s):
        if self.attr_t and hasattr(s, self.attr_t):
            try:
                return float(getattr(s, self.attr_t))
            except (TypeError, ValueError):
                return None
        return None

    def set_state(self, s, x):
        x = np.asarray(x, dtype=float).reshape(-1)
        cur_T = np.asarray(getattr(s, self.attr_T), dtype=float)
        cur_v = np.asarray(getattr(s, self.attr_v), dtype=float)
        newT = x[:N_T]
        newv = x[N_T:N_X]
        setattr(s, self.attr_T, type(cur_T)(newT) if isinstance(cur_T, np.ndarray) else list(newT))
        setattr(s, self.attr_v, type(cur_v)(newv) if isinstance(cur_v, np.ndarray) else list(newv))

    def step(self, s, u):
        u = np.asarray(u, dtype=float).reshape(-1)
        fn = getattr(s, self.step_name)
        try:
            fn(u)
        except Exception:
            fn(list(u))
        return self.get_state(s)

    def step_once(self, x, u):
        """Side-effect-free one-step map on a fresh instance (for linearization)."""
        s = self.new()
        self.set_state(s, x)
        return self.step(s, u)


# --- config reference extraction -------------------------------------------

def _as_float_list(val):
    try:
        arr = np.asarray(val, dtype=float).reshape(-1)
        return arr
    except (TypeError, ValueError):
        return None


def extract_references(config):
    """Return (ref_tensions[6], ref_velocities[6], info)."""
    info = {}
    T = None
    v = None
    for k, val in config.items():
        kl = k.lower()
        arr = _as_float_list(val)
        if arr is None:
            continue
        if "tension" in kl and arr.size >= N_T:
            T = arr[:N_T]
            info["tension_key"] = k
        if ("veloc" in kl or kl in ("v_ref", "v")) and arr.size >= N_V:
            v = arr[:N_V]
            info["velocity_key"] = k
    # velocity may be a scalar line speed
    if v is None:
        for k, val in config.items():
            kl = k.lower()
            if any(h in kl for h in ("speed", "veloc", "line")):
                arr = _as_float_list(val)
                if arr is not None and arr.size == 1:
                    v = np.full(N_V, float(arr[0]))
                    info["velocity_key"] = k + " (scalar broadcast)"
                    break
    if T is None:
        raise RuntimeError(
            "Could not find reference tensions (len>=6) in config. "
            "Keys present: %s" % list(config.keys()))
    if v is None:
        v = np.zeros(N_V)
        info["velocity_key"] = "<default zeros>"
    return np.asarray(T, float)[:N_T], np.asarray(v, float)[:N_V], info


def extract_u_limits(config):
    lo = hi = None
    for k, val in config.items():
        kl = k.lower()
        if "torque" in kl or kl.startswith("u_") or "control" in kl:
            arr = _as_float_list(val)
            if arr is None:
                continue
            if "max" in kl:
                hi = float(arr.reshape(-1)[0])
            elif "min" in kl:
                lo = float(arr.reshape(-1)[0])
            elif "limit" in kl and arr.size >= 1:
                hi = abs(float(arr.reshape(-1)[0]))
                lo = -hi
    if hi is not None and lo is None:
        lo = -abs(hi)
    return lo, hi


# --- linearization and control ---------------------------------------------

def linearize_discrete(step_once, x0, u0, eps_x=1e-3, eps_u=1e-3):
    x0 = np.asarray(x0, float)
    u0 = np.asarray(u0, float)
    n = x0.size
    m = u0.size
    A = np.zeros((n, n))
    B = np.zeros((n, m))
    for i in range(n):
        d = np.zeros(n)
        d[i] = eps_x
        fp = step_once(x0 + d, u0)
        fm = step_once(x0 - d, u0)
        A[:, i] = (fp - fm) / (2 * eps_x)
    for j in range(m):
        d = np.zeros(m)
        d[j] = eps_u
        fp = step_once(x0, u0 + d)
        fm = step_once(x0, u0 - d)
        B[:, j] = (fp - fm) / (2 * eps_u)
    return A, B


def estimate_u_ref(A, B, x_ref):
    # (I - A) x_ref = B u_ref  -> least squares for u_ref
    rhs = (np.eye(A.shape[0]) - A) @ x_ref
    u_ref, *_ = np.linalg.lstsq(B, rhs, rcond=None)
    return u_ref


def dlqr(A, B, Q, R, iters=20000, tol=1e-10):
    try:
        from scipy.linalg import solve_discrete_are
        P = solve_discrete_are(A, B, Q, R)
    except Exception:  # noqa: BLE001
        P = Q.copy()
        for _ in range(iters):
            BtPB = B.T @ P @ B + R
            K = np.linalg.solve(BtPB, B.T @ P @ A)
            Pn = Q + A.T @ P @ A - A.T @ P @ B @ K
            if np.max(np.abs(Pn - P)) < tol:
                P = Pn
                break
            P = Pn
    BtPB = B.T @ P @ B + R
    K = np.linalg.solve(BtPB, B.T @ P @ A)
    return K, P


def build_mpc(A, B, Q, R, N):
    n = A.shape[0]
    m = B.shape[1]
    Sx = np.zeros((N * n, n))
    Su = np.zeros((N * n, N * m))
    Apows = [np.eye(n)]
    for i in range(1, N + 1):
        Apows.append(Apows[-1] @ A)
    for i in range(N):
        Sx[i * n:(i + 1) * n, :] = Apows[i + 1]
        for j in range(i + 1):
            Su[i * n:(i + 1) * n, j * m:(j + 1) * m] = Apows[i - j] @ B
    Qbar = np.kron(np.eye(N), Q)
    Rbar = np.kron(np.eye(N), R)
    H = Su.T @ Qbar @ Su + Rbar
    # precompute factor for repeated solves
    Hinv = np.linalg.inv(H + 1e-9 * np.eye(H.shape[0]))
    G = Su.T @ Qbar @ Sx
    return {"Hinv": Hinv, "G": G, "m": m}


def mpc_first_move(mpc, xe0):
    # minimize over Ue: 0.5 Ue'H Ue + (G xe0)' Ue  -> Ue = -Hinv G xe0
    Ue = -mpc["Hinv"] @ (mpc["G"] @ xe0)
    return Ue[:mpc["m"]]


def clip_u(u, lo, hi):
    if lo is None and hi is None:
        return u
    lo = -np.inf if lo is None else lo
    hi = np.inf if hi is None else hi
    return np.clip(u, lo, hi)


def jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj
