#!/usr/bin/env python3
"""Sparse MATPOWER DC-OPF plus deterministic spinning reserve report.

stdin schema:
  {"network_path": str, "report_path": str,
   "tolerance": number?, "ipopt_max_iter": integer?}
stdout schema:
  {"ok": true, "report_path": str, "validation": object, "report": object}
  or {"ok": false, "error": str}
"""
import json
import math
import sys
from pathlib import Path


def fail(message):
    raise ValueError(message)


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        fail(f"{label} must be a finite number")
    return float(value)


def requirement(case):
    names = ("reserve_requirement_MW", "reserve_requirement",
             "spinning_reserve_requirement_MW", "spinning_reserve_requirement",
             "reserve_req_MW", "reserve_req")
    for name in names:
        if name in case:
            value = number(case[name], name)
            if value < 0:
                fail("reserve requirement must be nonnegative")
            return value
    reserve = case.get("reserve")
    if isinstance(reserve, dict):
        for name in ("requirement_MW", "requirement"):
            if name in reserve:
                value = number(reserve[name], "reserve." + name)
                if value < 0:
                    fail("reserve requirement must be nonnegative")
                return value
    fail("no explicit spinning-reserve requirement found in network JSON")


def eligibility(case, ng):
    candidates = [case.get("reserve_eligible"), case.get("gen_reserve_eligible")]
    if isinstance(case.get("reserve"), dict):
        candidates.append(case["reserve"].get("eligible"))
    supplied = [x for x in candidates if x is not None]
    if not supplied:
        return [True] * ng
    values = supplied[0]
    if not isinstance(values, list) or len(values) != ng:
        fail("reserve eligibility must be a list aligned with gen")
    return [bool(x) for x in values]


def cost_curve(row, index):
    if len(row) < 4:
        fail(f"gencost row {index + 1} is shorter than four fields")
    model = int(row[0])
    n = int(row[3])
    if n <= 0:
        fail(f"gencost row {index + 1} has invalid NCOST")
    if model == 2:
        if len(row) < 4 + n:
            fail(f"polynomial gencost row {index + 1} lacks coefficients")
        coeff = [number(v, f"gencost[{index}] coefficient") for v in row[4:4+n]]
        # IPOPT can formulate arbitrary polynomials, but reject an obviously
        # nonconvex quadratic because this Skill promises economic minimization.
        if n == 3 and coeff[0] < -1e-12:
            fail(f"gencost row {index + 1} has nonconvex quadratic cost")
        return {"model": 2, "coeff": coeff}
    if model == 1:
        if len(row) < 4 + 2*n or n < 2:
            fail(f"piecewise-linear gencost row {index + 1} is invalid")
        points = []
        for j in range(n):
            points.append((number(row[4 + 2*j], "piecewise power"),
                           number(row[5 + 2*j], "piecewise cost")))
        if any(points[j+1][0] <= points[j][0] for j in range(n-1)):
            fail(f"piecewise-linear gencost row {index + 1} powers are not increasing")
        slopes = [(points[j+1][1] - points[j][1]) / (points[j+1][0] - points[j][0])
                  for j in range(n-1)]
        if any(slopes[j+1] < slopes[j] - 1e-10 for j in range(len(slopes)-1)):
            fail(f"piecewise-linear gencost row {index + 1} is nonconvex")
        return {"model": 1, "points": points, "slopes": slopes}
    fail(f"unsupported MATPOWER gencost MODEL {model} at generator {index + 1}")


def evaluate_cost(curve, p):
    if curve["model"] == 2:
        coeff = curve["coeff"]
        degree = len(coeff) - 1
        return sum(c * p ** (degree - j) for j, c in enumerate(coeff))
    # A convex PWL curve equals the maximum of the affine extensions of its segments.
    vals = []
    for j, slope in enumerate(curve["slopes"]):
        x0, y0 = curve["points"][j]
        vals.append(y0 + slope * (p - x0))
    return max(vals)


def solve(case, tol, max_iter):
    try:
        import casadi as ca
        import scipy.sparse as sp
    except ImportError as exc:
        fail("CasADi with IPOPT and SciPy are required by this solver: " + str(exc))

    for key in ("baseMVA", "bus", "gen", "branch", "gencost"):
        if key not in case:
            fail(f"network JSON lacks required field {key}")
    base = number(case["baseMVA"], "baseMVA")
    if base <= 0:
        fail("baseMVA must be positive")
    buses, gens, branches, costs = case["bus"], case["gen"], case["branch"], case["gencost"]
    if not all(isinstance(x, list) for x in (buses, gens, branches, costs)):
        fail("bus, gen, branch, and gencost must be arrays")
    if len(gens) != len(costs):
        fail("gen and gencost lengths differ")
    if not buses:
        fail("network has no buses")

    bus_ids = []
    for i, row in enumerate(buses):
        if len(row) < 6:
            fail(f"bus row {i + 1} lacks required MATPOWER columns")
        bus_ids.append(row[0])
    if len(set(bus_ids)) != len(bus_ids):
        fail("bus identifiers are not unique")
    bmap = {bid: i for i, bid in enumerate(bus_ids)}
    refs = [i for i, row in enumerate(buses) if len(row) > 1 and int(row[1]) == 3]
    if not refs:
        fail("no MATPOWER reference bus (BUS_TYPE 3) was supplied")
    refset = set(refs)
    theta_bus_to_col = {}
    for i in range(len(buses)):
        if i not in refset:
            theta_bus_to_col[i] = len(theta_bus_to_col)

    ng = len(gens)
    curves = [cost_curve(costs[i], i) for i in range(ng)]
    eligible = eligibility(case, ng)
    online = []
    gen_bus = []
    pmin = []
    pmax = []
    for i, row in enumerate(gens):
        if len(row) < 10:
            fail(f"generator row {i + 1} lacks required MATPOWER columns")
        if row[0] not in bmap:
            fail(f"generator {i + 1} references an unknown bus")
        gen_bus.append(bmap[row[0]])
        pmin.append(number(row[9], f"gen[{i}] PMIN"))
        pmax.append(number(row[8], f"gen[{i}] PMAX"))
        if pmin[-1] > pmax[-1] + tol:
            fail(f"generator {i + 1} has PMIN > PMAX")
        if int(row[7]) > 0:
            online.append(i)
    pslot = {g: k for k, g in enumerate(online)}
    rgens = [g for g in online if eligible[g]]
    rslot = {g: k for k, g in enumerate(rgens)}
    reserve_req = requirement(case)
    if reserve_req > sum(pmax[g] for g in rgens) - sum(pmin[g] for g in online) + tol:
        fail("reserve requirement exceeds capability after online minimum generation")

    # Variables: online MW dispatch, non-reference angles, eligible reserve, PWL epigraphs.
    n_p, n_t, n_r = len(online), len(theta_bus_to_col), len(rgens)
    pwl_gens = [g for g in online if curves[g]["model"] == 1]
    yslot = {g: k for k, g in enumerate(pwl_gens)}
    offset_t, offset_r = n_p, n_p + n_t
    offset_y = offset_r + n_r
    nvar = offset_y + len(pwl_gens)
    lb = [-math.inf] * nvar
    ub = [math.inf] * nvar
    for g in online:
        lb[pslot[g]], ub[pslot[g]] = pmin[g], pmax[g]
    for g in rgens:
        lb[offset_r + rslot[g]] = 0.0

    # Build B*theta + phase-shift constants as outgoing flow at each bus.
    nb = len(buses)
    B = sp.lil_matrix((nb, nb), dtype=float)
    shift_const = [0.0] * nb
    flow_rows = []  # (source index, f bus, t bus, coefficient, shift, rating, raw row)
    for k, row in enumerate(branches):
        if len(row) < 11:
            fail(f"branch row {k + 1} lacks required MATPOWER columns")
        if int(row[10]) <= 0:
            continue
        if row[0] not in bmap or row[1] not in bmap:
            fail(f"branch {k + 1} references an unknown bus")
        x = number(row[3], f"branch[{k}] BR_X")
        if abs(x) < 1e-14:
            fail(f"in-service branch {k + 1} has zero BR_X")
        tap_raw = number(row[8], f"branch[{k}] TAP") if len(row) > 8 else 0.0
        tap = 1.0 if abs(tap_raw) < 1e-14 else tap_raw
        if abs(tap) < 1e-14:
            fail(f"branch {k + 1} has invalid transformer tap")
        shift = math.radians(number(row[9], f"branch[{k}] SHIFT")) if len(row) > 9 else 0.0
        coeff = base / (x * tap)
        f, t = bmap[row[0]], bmap[row[1]]
        B[f, f] += coeff; B[f, t] -= coeff
        B[t, f] -= coeff; B[t, t] += coeff
        shift_const[f] -= coeff * shift
        shift_const[t] += coeff * shift
        rating = number(row[5], f"branch[{k}] RATE_A")
        flow_rows.append((k, f, t, coeff, shift, rating, row))

    # Balance: Pg - B*theta = Pd + Gs + shift_const.
    Aeq = sp.lil_matrix((nb + 1, nvar), dtype=float)
    rhs = [0.0] * (nb + 1)
    for i, row in enumerate(buses):
        pd, gs = number(row[2], f"bus[{i}] PD"), number(row[4], f"bus[{i}] GS")
        rhs[i] = pd + gs + shift_const[i]
        for g in online:
            if gen_bus[g] == i:
                Aeq[i, pslot[g]] = 1.0
        for j, col in theta_bus_to_col.items():
            v = B[i, j]
            if v:
                Aeq[i, offset_t + col] = -v
    # Exact procurement requirement.
    for g in rgens:
        Aeq[nb, offset_r + rslot[g]] = 1.0
    rhs[nb] = reserve_req

    ineq_rows, ineq_lb, ineq_ub = [], [], []
    def add_ineq(entries, lo=-math.inf, hi=math.inf):
        rr = sp.lil_matrix((1, nvar), dtype=float)
        for col, value in entries:
            rr[0, col] = value
        ineq_rows.append(rr.tocsr()); ineq_lb.append(lo); ineq_ub.append(hi)

    for g in rgens:
        add_ineq([(pslot[g], 1.0), (offset_r + rslot[g], 1.0)], hi=pmax[g])
    for source, f, t, coeff, shift, rating, row in flow_rows:
        entries = []
        if f in theta_bus_to_col: entries.append((offset_t + theta_bus_to_col[f], coeff))
        if t in theta_bus_to_col: entries.append((offset_t + theta_bus_to_col[t], -coeff))
        if rating > 0:
            # flow = angle_expression - coeff*shift
            add_ineq(entries, -rating + coeff * shift, rating + coeff * shift)
        if len(row) >= 13:
            amin, amax = number(row[11], "ANGMIN"), number(row[12], "ANGMAX")
            aentries = []
            if f in theta_bus_to_col: aentries.append((offset_t + theta_bus_to_col[f], 1.0))
            if t in theta_bus_to_col: aentries.append((offset_t + theta_bus_to_col[t], -1.0))
            add_ineq(aentries, math.radians(amin), math.radians(amax))
    # Epigraph constraints for convex PWL offers: y >= m*p+b.
    for g in pwl_gens:
        curve = curves[g]
        for j, slope in enumerate(curve["slopes"]):
            x0, y0 = curve["points"][j]
            # y - m*p >= y0 - m*x0
            add_ineq([(offset_y + yslot[g], 1.0), (pslot[g], -slope)], lo=y0 - slope*x0)

    Aeq = Aeq.tocsr()
    Aineq = sp.vstack(ineq_rows, format="csr") if ineq_rows else sp.csr_matrix((0, nvar))
    Aall = sp.vstack([Aeq, Aineq], format="csr")
    lbg = rhs + ineq_lb
    ubg = rhs + ineq_ub

    x = ca.MX.sym("x", nvar)
    objective = 0
    for g in online:
        p = x[pslot[g]]
        curve = curves[g]
        if curve["model"] == 2:
            degree = len(curve["coeff"]) - 1
            objective += sum(c * p ** (degree-j) for j, c in enumerate(curve["coeff"]))
        else:
            objective += x[offset_y + yslot[g]]
    nlp = {"x": x, "f": objective, "g": ca.DM(Aall) @ x}
    opts = {"ipopt.print_level": 0, "print_time": False, "ipopt.sb": "yes",
            "ipopt.tol": min(tol, 1e-8), "ipopt.constr_viol_tol": min(tol, 1e-8),
            "ipopt.max_iter": int(max_iter)}
    solver = ca.nlpsol("dcopf_reserve", "ipopt", nlp, opts)

    # A bounded, physically sensible start helps IPOPT but feasibility is not assumed.
    initial = [0.0] * nvar
    remaining = sum(number(row[2], "PD") + number(row[4], "GS") for row in buses) - sum(pmin[g] for g in online)
    for g in online:
        take = min(max(0.0, remaining), pmax[g] - pmin[g])
        initial[pslot[g]] = pmin[g] + take
        remaining -= take
    if remaining > 1e-7:
        fail("online generation PMAX cannot meet active demand")
    rem_r = reserve_req
    for g in rgens:
        available = max(0.0, pmax[g] - initial[pslot[g]])
        take = min(rem_r, available)
        initial[offset_r + rslot[g]] = take
        rem_r -= take
    # PWL epigraph initial values need only be finite.
    for g in pwl_gens:
        initial[offset_y + yslot[g]] = evaluate_cost(curves[g], initial[pslot[g]])
    try:
        result = solver(x0=initial, lbx=lb, ubx=ub, lbg=lbg, ubg=ubg)
    except Exception as exc:
        fail("IPOPT failed to solve the DC dispatch: " + str(exc))
    stats = solver.stats()
    if not stats.get("success", False):
        fail("IPOPT did not report a successful optimum: " + str(stats.get("return_status")))
    sol = [float(v) for v in result["x"].full().ravel()]

    pg = [0.0] * ng
    reserve = [0.0] * ng
    for g in online: pg[g] = sol[pslot[g]]
    for g in rgens: reserve[g] = sol[offset_r + rslot[g]]

    # Independent numerical reconstruction and validation.
    flow_values = []
    balance = [0.0] * nb
    for i, row in enumerate(buses):
        balance[i] = sum(pg[g] for g in range(ng) if gen_bus[g] == i) - number(row[2], "PD") - number(row[4], "GS")
    angles = [0.0] * nb
    for i, col in theta_bus_to_col.items(): angles[i] = sol[offset_t + col]
    max_flow_violation = 0.0
    for source, f, t, coeff, shift, rating, row in flow_rows:
        flow = coeff * (angles[f] - angles[t] - shift)
        balance[f] -= flow; balance[t] += flow
        if rating > 0: max_flow_violation = max(max_flow_violation, abs(flow) - rating)
        flow_values.append((source, flow, rating, f, t))
    max_balance = max(abs(v) for v in balance) if balance else 0.0
    max_gen_violation = 0.0
    for g in online:
        max_gen_violation = max(max_gen_violation, pmin[g]-pg[g], pg[g]-pmax[g])
        if g in rslot: max_gen_violation = max(max_gen_violation, pg[g]+reserve[g]-pmax[g], -reserve[g])
    reserve_error = abs(sum(reserve) - reserve_req)
    limit_error = max(0.0, max_flow_violation, max_gen_violation, reserve_error)
    if max(max_balance, limit_error) > tol:
        fail("post-solve validation failed: max balance %.3g, max limit %.3g" % (max_balance, limit_error))

    total_load = sum(number(row[2], "PD") for row in buses)
    total_generation = sum(pg)
    total_reserve = sum(reserve)
    total_cost = sum(evaluate_cost(curves[g], pg[g]) for g in range(ng))
    online_capacity = sum(pmax[g] for g in online)
    margin = online_capacity - total_generation - total_reserve
    dispatch = []
    for g, row in enumerate(gens):
        dispatch.append({"id": g + 1, "bus": row[0], "output_MW": pg[g],
                         "reserve_MW": reserve[g], "pmax_MW": pmax[g]})
    loaded = []
    for source, flow, rating, f, t in flow_values:
        if rating > 0:
            loaded.append({"from": bus_ids[f], "to": bus_ids[t],
                           "loading_pct": abs(flow) / rating * 100.0, "_source": source})
    loaded.sort(key=lambda z: (-z["loading_pct"], z["_source"]))
    for item in loaded: item.pop("_source")
    report = {"generator_dispatch": dispatch,
              "totals": {"cost_dollars_per_hour": total_cost, "load_MW": total_load,
                         "generation_MW": total_generation, "reserve_MW": total_reserve},
              "most_loaded_lines": loaded[:3], "operating_margin_MW": margin}
    validation = {"max_nodal_balance_MW": max_balance,
                  "max_constraint_violation_MW": max(0.0, limit_error),
                  "reserve_requirement_MW": reserve_req,
                  "reconstructed_cost_dollars_per_hour": total_cost}
    return report, validation


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict): fail("stdin must contain a JSON object")
        network_path = Path(request.get("network_path", "/root/network.json"))
        report_path = Path(request.get("report_path", "/root/report.json"))
        tol = number(request.get("tolerance", 1e-5), "tolerance")
        if tol <= 0: fail("tolerance must be positive")
        max_iter = int(request.get("ipopt_max_iter", 3000))
        if max_iter <= 0: fail("ipopt_max_iter must be positive")
        with network_path.open("r", encoding="utf-8") as handle:
            case = json.load(handle)
        report, validation = solve(case, tol, max_iter)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
            handle.write("\n")
        print(json.dumps({"ok": True, "report_path": str(report_path),
                          "validation": validation, "report": report}, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
