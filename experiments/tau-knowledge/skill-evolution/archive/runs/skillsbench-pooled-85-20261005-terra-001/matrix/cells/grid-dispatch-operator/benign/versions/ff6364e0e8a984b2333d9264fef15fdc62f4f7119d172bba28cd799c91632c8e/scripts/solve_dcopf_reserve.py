#!/usr/bin/env python3
"""Read a MATPOWER JSON DC-reserve case and write a validated report JSON.
Input on stdin: {"network_path": str, "report_path": str, "tolerance": number?}.
Output on stdout: {"ok": true, ...} or {"ok": false, "error": str}.
"""
import json, math, os, sys, tempfile
import numpy as np
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, linprog, minimize


def fail(message):
    raise ValueError(message)


def number_id(value):
    value = float(value)
    return int(value) if value.is_integer() else value


def case_root(raw):
    if isinstance(raw, dict) and isinstance(raw.get("mpc"), dict):
        return raw["mpc"]
    return raw


def field(obj, names, default=None):
    for name in names:
        if name in obj:
            return obj[name]
    return default


def reserve_data(data, ngen):
    nested = data.get("reserve") if isinstance(data.get("reserve"), dict) else {}
    req = field(data, ["reserve_requirement_MW", "reserve_requirement",
                       "spinning_reserve_requirement_MW", "spinning_reserve_requirement"])
    if req is None:
        req = field(nested, ["requirement_MW", "requirement", "required_MW"])
    if req is None:
        fail("no explicit spinning-reserve requirement (MW) was supplied")
    req = float(req)
    if not math.isfinite(req) or req < 0:
        fail("reserve requirement must be a finite nonnegative MW value")

    offers = field(data, ["reserve_cost_per_MW", "reserve_costs", "reserve_cost"])
    if offers is None:
        offers = field(nested, ["cost_per_MW", "costs", "cost"])
    if offers is None:
        offers = np.zeros(ngen)
    elif np.isscalar(offers):
        offers = np.full(ngen, float(offers))
    else:
        offers = np.asarray(offers, dtype=float)
        if offers.size != ngen:
            fail("reserve cost array must have one entry per generator")
    if not np.all(np.isfinite(offers)):
        fail("reserve costs must be finite")

    eligible = field(data, ["reserve_eligible"])
    if eligible is None:
        eligible = field(nested, ["eligible"])
    if eligible is None:
        eligible = np.ones(ngen, dtype=bool)
    else:
        eligible = np.asarray(eligible).reshape(-1)
        if eligible.size != ngen:
            fail("reserve_eligible must have one entry per generator")
        eligible = eligible.astype(bool)
    return req, np.asarray(offers, dtype=float), eligible


def parse_cost(row, pmin, pmax):
    row = np.asarray(row, dtype=float).reshape(-1)
    if row.size < 4:
        fail("a gencost row has fewer than four columns")
    model, ncost = int(row[0]), int(row[3])
    if ncost < 1:
        fail("gencost NCOST must be positive")
    if model == 2:
        coeff = row[4:4 + ncost]
        if coeff.size != ncost:
            fail("polynomial gencost row is truncated")
        degree = ncost - 1
        if degree > 2:
            fail("polynomial generator costs above quadratic are unsupported")
        coeff = np.pad(coeff, (3 - ncost, 0), constant_values=0.0)
        q, linear, constant = map(float, coeff)
        if q < -1e-12:
            fail("nonconvex quadratic generator cost is unsupported")
        return {"kind": "poly", "q": max(q, 0.0), "linear": linear, "constant": constant}
    if model == 1:
        points = row[4:4 + 2 * ncost]
        if ncost < 2 or points.size != 2 * ncost:
            fail("piecewise-linear gencost needs at least two complete points")
        xy = points.reshape(ncost, 2)
        if np.any(np.diff(xy[:, 0]) <= 0):
            fail("piecewise-linear cost breakpoints must have increasing MW")
        if pmin < xy[0, 0] - 1e-8 or pmax > xy[-1, 0] + 1e-8:
            fail("generator bounds lie outside its piecewise-linear cost domain")
        slopes = np.diff(xy[:, 1]) / np.diff(xy[:, 0])
        if np.any(np.diff(slopes) < -1e-10):
            fail("nonconvex piecewise-linear generator cost is unsupported")
        return {"kind": "pwl", "segments": [(float(m), float(y - m*x))
                for m, (x, y) in zip(slopes, xy[:-1])]}
    fail("unsupported MATPOWER gencost model %s" % model)


def solve(data, tol):
    for key in ("baseMVA", "bus", "gen", "branch", "gencost"):
        if key not in data:
            fail("network is missing required field " + key)
    base = float(data["baseMVA"])
    if not math.isfinite(base) or base <= 0:
        fail("baseMVA must be positive")
    bus = np.asarray(data["bus"], dtype=float)
    gen = np.asarray(data["gen"], dtype=float)
    branch = np.asarray(data["branch"], dtype=float)
    costs = np.asarray(data["gencost"], dtype=float)
    if bus.ndim != 2 or bus.shape[1] < 5 or gen.ndim != 2 or gen.shape[1] < 10:
        fail("bus/gen arrays do not have required MATPOWER columns")
    if branch.ndim != 2 or branch.shape[1] < 13:
        fail("branch array does not have required MATPOWER columns")
    nb, ng = bus.shape[0], gen.shape[0]
    if nb == 0 or ng == 0 or costs.ndim != 2 or costs.shape[0] < ng:
        fail("empty network or insufficient active-power gencost rows")
    ids = [number_id(x) for x in bus[:, 0]]
    if len(set(ids)) != nb:
        fail("bus identifiers must be unique")
    bidx = {v: i for i, v in enumerate(ids)}
    def bus_index(v, what):
        key = number_id(v)
        if key not in bidx:
            fail(what + " references an unknown bus")
        return bidx[key]

    online = gen[:, 7] > 0
    pmax, pmin = gen[:, 8].copy(), gen[:, 9].copy()
    if np.any(pmin > pmax):
        fail("a generator has PMIN greater than PMAX")
    gbus = [bus_index(gen[k, 0], "generator") for k in range(ng)]
    req, reserve_offer, eligible = reserve_data(data, ng)
    eligible &= online
    descriptors = [parse_cost(costs[k], pmin[k], pmax[k]) for k in range(ng)]

    active_lines = []
    adjacency = [[] for _ in range(nb)]
    for k, row in enumerate(branch):
        if row[10] <= 0:
            continue
        f, t = bus_index(row[0], "branch"), bus_index(row[1], "branch")
        x = float(row[3]); tap = float(row[8]) if float(row[8]) != 0 else 1.0
        if not math.isfinite(x) or not math.isfinite(tap) or x == 0 or tap == 0:
            fail("an in-service branch has invalid zero/nonfinite reactance or tap")
        shift = math.radians(float(row[9]))
        rate = float(row[5])
        amin, amax = math.radians(float(row[11])), math.radians(float(row[12]))
        if amin > amax:
            fail("branch angle minimum exceeds maximum")
        line = (k, f, t, base / (x * tap), shift, rate, amin, amax)
        active_lines.append(line)
        adjacency[f].append(t); adjacency[t].append(f)

    refs = set(np.where(np.rint(bus[:, 1]).astype(int) == 3)[0].tolist())
    if not refs:
        fail("network has no MATPOWER reference bus")
    seen = set()
    for start in range(nb):
        if start in seen:
            continue
        stack, component = [start], set()
        while stack:
            u = stack.pop()
            if u in component:
                continue
            component.add(u); seen.add(u); stack.extend(adjacency[u])
        if not (component & refs):
            fail("each connected electrical island must contain a reference bus")

    pwl_gens = [k for k, d in enumerate(descriptors) if d["kind"] == "pwl" and online[k]]
    p0, r0, th0, y0 = 0, ng, 2 * ng, 2 * ng + nb
    y_index = {g: y0 + j for j, g in enumerate(pwl_gens)}
    nx = y0 + len(pwl_gens)
    lower, upper = np.full(nx, -np.inf), np.full(nx, np.inf)
    for k in range(ng):
        if online[k]:
            lower[p0+k], upper[p0+k] = pmin[k], pmax[k]
            lower[r0+k], upper[r0+k] = 0.0, (pmax[k] - pmin[k]) if eligible[k] else 0.0
        else:
            lower[p0+k] = upper[p0+k] = 0.0
            lower[r0+k] = upper[r0+k] = 0.0

    linear, quadratic = np.zeros(nx), np.zeros(nx)
    for k, d in enumerate(descriptors):
        if not online[k]:
            continue
        if d["kind"] == "poly":
            linear[p0+k] += d["linear"]; quadratic[p0+k] += d["q"]
        else:
            linear[y_index[k]] += 1.0
        linear[r0+k] += reserve_offer[k]

    rows, lbs, ubs = [], [], []
    def add(coeffs, lo, hi):
        rows.append(coeffs); lbs.append(float(lo)); ubs.append(float(hi))
    withdrawal = bus[:, 2] + bus[:, 4]
    rhs = withdrawal.copy()
    balance = [dict() for _ in range(nb)]
    for k, bi in enumerate(gbus):
        balance[bi][p0+k] = balance[bi].get(p0+k, 0.0) + 1.0
    for _, f, t, b, shift, rate, amin, amax in active_lines:
        balance[f][th0+f] = balance[f].get(th0+f, 0.0) - b
        balance[f][th0+t] = balance[f].get(th0+t, 0.0) + b
        balance[t][th0+f] = balance[t].get(th0+f, 0.0) + b
        balance[t][th0+t] = balance[t].get(th0+t, 0.0) - b
        rhs[f] -= b * shift; rhs[t] += b * shift
        if rate > 0:
            add({th0+f: b, th0+t: -b}, -rate + b*shift, rate + b*shift)
        add({th0+f: 1.0, th0+t: -1.0}, amin, amax)
    for i in range(nb):
        add(balance[i], rhs[i], rhs[i])
    for ref in refs:
        add({th0+ref: 1.0}, 0.0, 0.0)
    add({r0+k: 1.0 for k in range(ng)}, req, req)
    for k in range(ng):
        add({p0+k: 1.0, r0+k: 1.0}, -np.inf, pmax[k] if online[k] else 0.0)
    for k in pwl_gens:
        for slope, intercept in descriptors[k]["segments"]:
            add({y_index[k]: 1.0, p0+k: -slope}, intercept, np.inf)

    A = sparse.lil_matrix((len(rows), nx), dtype=float)
    for i, coeff in enumerate(rows):
        for col, val in coeff.items():
            A[i, col] = val
    A = A.tocsr(); lb = np.asarray(lbs); ub = np.asarray(ubs)
    eq = lb == ub
    au, bu = [], []
    for i in np.where(~eq)[0]:
        if np.isfinite(ub[i]): au.append(A.getrow(i)); bu.append(ub[i])
        if np.isfinite(lb[i]): au.append(-A.getrow(i)); bu.append(-lb[i])
    Aub = sparse.vstack(au).tocsr() if au else None
    bounds_lp = [(None if not np.isfinite(lower[i]) else lower[i],
                  None if not np.isfinite(upper[i]) else upper[i]) for i in range(nx)]
    feasible = linprog(np.zeros(nx), A_ub=Aub, b_ub=np.asarray(bu) if bu else None,
                       A_eq=A[eq], b_eq=lb[eq], bounds=bounds_lp, method="highs")
    if not feasible.success:
        fail("DC dispatch/reserve model is infeasible: " + feasible.message)
    if np.all(quadratic == 0):
        result = linprog(linear, A_ub=Aub, b_ub=np.asarray(bu) if bu else None,
                         A_eq=A[eq], b_eq=lb[eq], bounds=bounds_lp, method="highs")
        if not result.success:
            fail("linear DC OPF solver failed: " + result.message)
        xsol = result.x
    else:
        lc = LinearConstraint(A, lb, ub)
        def fun(x): return float(np.dot(linear, x) + np.dot(quadratic, x*x))
        def jac(x): return linear + 2.0*quadratic*x
        def hess(x): return sparse.diags(2.0*quadratic, format="csc")
        result = minimize(fun, feasible.x, method="trust-constr", jac=jac, hess=hess,
                          constraints=[lc], bounds=Bounds(lower, upper),
                          options={"gtol": tol*0.1, "xtol": tol*0.01,
                                   "barrier_tol": tol*0.01, "maxiter": 1500,
                                   "sparse_jacobian": True})
        if not result.success:
            fail("quadratic DC OPF solver failed: " + result.message)
        xsol = result.x

    p, r, theta = xsol[p0:p0+ng], xsol[r0:r0+ng], xsol[th0:th0+nb]
    flows, injection = [], np.zeros(nb)
    for k, f, t, b, shift, rate, amin, amax in active_lines:
        flow = b * (theta[f] - theta[t] - shift)
        flows.append((k, f, t, flow, rate))
        injection[f] += flow; injection[t] -= flow
    residual = np.array([sum(p[k] for k in range(ng) if gbus[k] == i)
                         for i in range(nb)]) - injection - withdrawal
    scale = max(1.0, float(np.max(np.abs(withdrawal))) if nb else 1.0)
    if np.max(np.abs(residual)) > tol * scale:
        fail("post-solve nodal balance validation failed")
    if np.any(p < lower[p0:p0+ng] - tol) or np.any(p > upper[p0:p0+ng] + tol):
        fail("post-solve generator-bound validation failed")
    if np.any(r < -tol) or np.any(p + r > pmax + tol) or abs(float(r.sum()) - req) > tol * max(1.0, req):
        fail("post-solve reserve validation failed")
    for _, f, t, flow, rate in flows:
        if rate > 0 and abs(flow) > rate + tol * max(1.0, rate):
            fail("post-solve branch-rating validation failed")

    def energy_cost(k, output):
        d = descriptors[k]
        if not online[k]: return 0.0
        if d["kind"] == "poly": return d["q"]*output*output + d["linear"]*output + d["constant"]
        return max(slope*output + intercept for slope, intercept in d["segments"])
    total_cost = sum(energy_cost(k, p[k]) + reserve_offer[k]*r[k] for k in range(ng))
    if not math.isfinite(total_cost) or abs(float(p.sum()) - float(withdrawal.sum())) > tol * max(1.0, abs(float(withdrawal.sum()))):
        fail("post-solve total/accounting validation failed")
    loaded = []
    for k, f, t, flow, rate in flows:
        if rate > 0:
            loaded.append((100.0*abs(flow)/rate, ids[f], ids[t], k))
    loaded.sort(key=lambda z: (-z[0], z[1], z[2], z[3]))
    clean = lambda v: 0.0 if abs(float(v)) < 1e-10 else float(v)
    report = {
        "generator_dispatch": [{"id": k+1, "bus": ids[gbus[k]], "output_MW": clean(p[k]),
                                  "reserve_MW": clean(r[k]), "pmax_MW": clean(pmax[k])}
                                 for k in range(ng)],
        "totals": {"cost_dollars_per_hour": clean(total_cost), "load_MW": clean(withdrawal.sum()),
                   "generation_MW": clean(p.sum()), "reserve_MW": clean(r.sum())},
        "most_loaded_lines": [{"from": f, "to": t, "loading_pct": clean(load)}
                              for load, f, t, k in loaded[:3]],
        "operating_margin_MW": clean(sum((pmax[k] - p[k] - r[k]) for k in range(ng) if online[k]))
    }
    return report, {"max_nodal_residual_MW": float(np.max(np.abs(residual))), "reserve_requirement_MW": req}


def main():
    try:
        cfg = json.load(sys.stdin)
        if not isinstance(cfg, dict) or "network_path" not in cfg or "report_path" not in cfg:
            fail("stdin must contain network_path and report_path")
        tol = float(cfg.get("tolerance", 1e-6))
        if not math.isfinite(tol) or tol <= 0: fail("tolerance must be positive")
        with open(cfg["network_path"], "r", encoding="utf-8") as fh:
            report, diagnostics = solve(case_root(json.load(fh)), tol)
        target = cfg["report_path"]; directory = os.path.dirname(os.path.abspath(target))
        fd, temporary = tempfile.mkstemp(prefix=".report-", suffix=".json", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(report, fh, allow_nan=False, separators=(",", ":")); fh.write("\n")
        os.replace(temporary, target)
        print(json.dumps({"ok": True, "report_path": target, "diagnostics": diagnostics}, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)

if __name__ == "__main__":
    main()
