#!/usr/bin/env python3
"""Exact Hodrick-Prescott trend (equals the Solver minimum).

stdin : {"series":[float,...], "lambda":100}
stdout: {"trend":[...], "second_diffs":[...], "objective":float, "lambda":float}

Minimizes sum((y-tau)^2) + lambda*sum((tau_{t+1}-tau_t)-(tau_t-tau_{t-1}))^2
via the closed form (I + lambda*D'D) tau = y, D the (T-2)xT second-difference
matrix. Write the returned trend into the HP decision column (e.g. L6:L27);
those cells are legitimately numeric Solver output.
"""
import sys, json


def hp_trend(y, lam):
    import numpy as np
    y = np.asarray(y, dtype=float)
    T = len(y)
    if T < 3:
        return y.tolist(), [], 0.0
    D = np.zeros((T - 2, T))
    for i in range(T - 2):
        D[i, i] = 1.0
        D[i, i + 1] = -2.0
        D[i, i + 2] = 1.0
    A = np.eye(T) + lam * (D.T @ D)
    tau = np.linalg.solve(A, y)
    sd = (D @ tau).tolist()
    obj = float(((y - tau) ** 2).sum() + lam * (D @ tau @ (D @ tau)))
    return tau.tolist(), sd, obj


def main():
    req = json.load(sys.stdin)
    series = [float(v) for v in req["series"]]
    lam = float(req.get("lambda", 100))
    trend, sd, obj = hp_trend(series, lam)
    print(json.dumps({
        "trend": [float(v) for v in trend],
        "second_diffs": [float(v) for v in sd],
        "objective": obj,
        "lambda": lam,
    }))


if __name__ == "__main__":
    main()
