"""Pure-python helpers for first-order thermal ID, lambda/IMC PI tuning and
control metrics. No third-party dependencies required.

All functions operate on plain data (lists of dicts / floats) so they are
reusable and independent of the simulator API.
"""
import math


def _linear_ab(x, y):
    """Least-squares fit y = a + b*x. Returns (a, b)."""
    n = len(x)
    sx = sum(x)
    sxx = sum(v * v for v in x)
    sy = sum(y)
    sxy = sum(x[i] * y[i] for i in range(n))
    det = n * sxx - sx * sx
    if abs(det) < 1e-12:
        return (sy / n if n else 0.0, 0.0)
    a = (sxx * sy - sx * sxy) / det
    b = (n * sxy - sx * sy) / det
    return a, b


def fit_first_order(data, power=None, ambient=None):
    """Fit T(t)=a+b*exp(-t/tau) to step-response data.

    data: list of dicts with 'time','temperature' (and optionally 'heater_power').
    power: constant test power used (% ); if None inferred from data.
    ambient: pre-heat steady temperature; if None uses fitted T0.
    Returns dict with K (degC per %), tau (s), r_squared, fitting_error (RMS),
    T_ss, T0, ambient, power.
    """
    t = [float(d['time']) for d in data]
    T = [float(d['temperature']) for d in data]
    n = len(T)
    if n < 3:
        raise ValueError('need at least 3 calibration points to fit')
    if power is None:
        powers = [float(d['heater_power']) for d in data
                  if d.get('heater_power') is not None]
        nz = [p for p in powers if p and p > 0]
        power = (sum(nz) / len(nz)) if nz else (max(powers) if powers else 1.0)
    t0 = t[0]
    ts = [v - t0 for v in t]

    def best_for(taus):
        best = None
        for tau in taus:
            if tau <= 0:
                continue
            x = [math.exp(-v / tau) for v in ts]
            a, b = _linear_ab(x, T)
            sse = sum((T[i] - (a + b * x[i])) ** 2 for i in range(n))
            if best is None or sse < best[0]:
                best = (sse, tau, a, b)
        return best

    span = ts[-1] - ts[0] if ts[-1] > ts[0] else 1.0
    coarse = [0.3 + i * (max(span * 3.0, 60.0) / 240.0) for i in range(241)]
    best = best_for(coarse)
    sse, tau, a, b = best
    lo = max(0.1, tau * 0.5)
    hi = tau * 1.8
    fine = [lo + i * (hi - lo) / 300.0 for i in range(301)]
    best2 = best_for(fine)
    if best2[0] < sse:
        sse, tau, a, b = best2

    T_ss = a
    T0 = a + b
    if ambient is None:
        ambient = T0
    K = (T_ss - ambient) / power if power not in (0, 0.0) else 0.0
    mean_T = sum(T) / n
    sst = sum((v - mean_T) ** 2 for v in T)
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    rmse = math.sqrt(sse / n)
    return {
        'K': float(K), 'tau': float(tau), 'r_squared': float(r2),
        'fitting_error': float(rmse), 'T_ss': float(T_ss), 'T0': float(T0),
        'ambient': float(ambient), 'power': float(power),
    }


def compute_gains(K, tau, lam=None, settling_target=120.0):
    """IMC/lambda PI tuning for a first-order plant.

    Kp = tau/(|K|*lambda), Ki = 1/(|K|*lambda), Kd = 0.
    lambda defaults so ~5*lambda stays under the settling target with margin.
    """
    try:
        tau = float(tau)
    except Exception:
        tau = 20.0
    Kmag = abs(float(K)) if K else 0.0
    if Kmag < 1e-6:
        Kmag = 0.1  # guard against degenerate fit
    if lam is None:
        lam = max(tau * 0.5, 6.0)
        lam = min(lam, settling_target / 5.0)
        lam = max(lam, 3.0)
    lam = float(lam)
    Kp = tau / (Kmag * lam)
    Ki = 1.0 / (Kmag * lam)
    return {'Kp': float(Kp), 'Ki': float(Ki), 'Kd': 0.0, 'lambda': float(lam)}


def compute_metrics(data, setpoint, band=0.5, ss_frac=0.2):
    """Performance metrics from a control trace.

    data: list of dicts with 'time','temperature'.
    Returns {rise_time, overshoot, settling_time, steady_state_error, max_temp}.
    Times are relative to the first sample.
    """
    t = [float(d['time']) for d in data]
    T = [float(d['temperature']) for d in data]
    n = len(T)
    if n == 0:
        raise ValueError('empty control trace')
    t0 = t[0]
    rel = [v - t0 for v in t]
    initial = T[0]
    setpoint = float(setpoint)
    max_temp = max(T)
    denom = setpoint - initial
    overshoot = max(0.0, (max_temp - setpoint) / denom) if denom > 0 else 0.0

    thr = initial + 0.9 * (setpoint - initial)
    rise_time = None
    for i in range(n):
        if (setpoint >= initial and T[i] >= thr) or (
                setpoint < initial and T[i] <= thr):
            rise_time = rel[i]
            break

    settling_time = None
    for i in range(n):
        if all(abs(T[j] - setpoint) <= band for j in range(i, n)):
            settling_time = rel[i]
            break

    k = max(1, int(n * ss_frac))
    ss_err = abs(sum(T[-k:]) / k - setpoint)

    return {
        'rise_time': rise_time,
        'overshoot': float(overshoot),
        'settling_time': settling_time,
        'steady_state_error': float(ss_err),
        'max_temp': float(max_temp),
    }


class PID:
    """Discrete PID with output clamp and conditional-integration anti-windup."""

    def __init__(self, Kp, Ki, Kd, lower=0.0, upper=100.0):
        self.Kp = float(Kp)
        self.Ki = float(Ki)
        self.Kd = float(Kd)
        self.lower = lower
        self.upper = upper
        self.integ = 0.0
        self.prev_err = None

    def reset(self):
        self.integ = 0.0
        self.prev_err = None

    def step(self, error, dt):
        deriv = 0.0 if self.prev_err is None else (error - self.prev_err) / dt
        integ_new = self.integ + error * dt
        out = self.Kp * error + self.Ki * integ_new + self.Kd * deriv
        if out > self.upper:
            out = self.upper
            if error <= 0:
                self.integ = integ_new
        elif out < self.lower:
            out = self.lower
            if error >= 0:
                self.integ = integ_new
        else:
            self.integ = integ_new
        self.prev_err = error
        return out
