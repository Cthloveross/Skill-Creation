#!/usr/bin/env python3
"""Solve a standard MATPOWER ACOPF and write a validated task report.

Reads one JSON object from stdin:
  {"network_path": str, "output_path": str}
Writes one JSON completion object to stdout.  CasADi/IPOPT is required.
"""
import json
import math
import os
import sys

try:
    import casadi as ca
except ImportError as exc:
    raise SystemExit("CasADi is required. Install it in the runtime, then rerun: " + str(exc))


# MATPOWER positional columns, with useful names for object-form JSON rows.
def val(row, index, *names, default=None):
    if isinstance(row, dict):
        lowered = {str(k).lower(): v for k, v in row.items()}
        for name in names:
            if name.lower() in lowered:
                return lowered[name.lower()]
        if default is not None:
            return default
        raise ValueError("Missing field one of %s in object row" % (names,))
    if index < len(row):
        return row[index]
    if default is not None:
        return default
    raise ValueError("Row lacks column %d" % index)


def num(v, what):
    try:
        x = float(v)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid numeric %s: %r" % (what, v)) from exc
    if not math.isfinite(x):
        raise ValueError("Non-finite %s" % what)
    return x


def array(case, key):
    for candidate in (key, key.lower(), key.upper()):
        if candidate in case:
            got = case[candidate]
            if not isinstance(got, list):
                raise ValueError("%s must be an array" % key)
            return got
    raise ValueError("Case has no %s array" % key)


def parse_case(raw):
    # Permit an outer network object while retaining ordinary MATPOWER JSON.
    case = raw.get("network", raw) if isinstance(raw, dict) else None
    if not isinstance(case, dict):
        raise ValueError("network JSON must be an object")
    base = num(case.get("baseMVA", case.get("basemva")), "baseMVA")
    if base <= 0:
        raise ValueError("baseMVA must be positive")
    buses_raw, gens_raw, branches_raw, costs_raw = (array(case, k) for k in ("bus", "gen", "branch", "gencost"))
    if len(costs_raw) < len(gens_raw):
        raise ValueError("gencost must have at least one row per generator")

    buses = []
    for r in buses_raw:
        buses.append({
            "id": int(num(val(r, 0, "bus_i", "id", "bus"), "bus id")),
            "type": int(num(val(r, 1, "bus_type", "type"), "bus type")),
            "pd": num(val(r, 2, "pd"), "Pd"), "qd": num(val(r, 3, "qd"), "Qd"),
            "gs": num(val(r, 4, "gs"), "Gs"), "bs": num(val(r, 5, "bs"), "Bs"),
            "vm": num(val(r, 7, "vm"), "Vm"), "va": num(val(r, 8, "va"), "Va"),
            "vmax": num(val(r, 11, "vmax"), "Vmax"), "vmin": num(val(r, 12, "vmin"), "Vmin"),
        })
    ids = [b["id"] for b in buses]
    if len(set(ids)) != len(ids):
        raise ValueError("Bus identifiers must be unique")
    bus_index = {bid: i for i, bid in enumerate(ids)}
    refs = [i for i, b in enumerate(buses) if b["type"] == 3]
    if len(refs) != 1:
        raise ValueError("Exactly one BUS_TYPE=3 reference bus is required")
    for b in buses:
        if b["vmin"] > b["vmax"] or b["vmin"] <= 0:
            raise ValueError("Invalid voltage bounds at bus %s" % b["id"])

    gens = []
    for k, r in enumerate(gens_raw):
        bid = int(num(val(r, 0, "gen_bus", "bus"), "generator bus"))
        if bid not in bus_index:
            raise ValueError("Generator %d references unknown bus %s" % (k + 1, bid))
        g = {"bus": bid, "pg0": num(val(r, 1, "pg"), "Pg"), "qg0": num(val(r, 2, "qg"), "Qg"),
             "qmax": num(val(r, 3, "qmax"), "Qmax"), "qmin": num(val(r, 4, "qmin"), "Qmin"),
             "status": int(num(val(r, 7, "gen_status", "status"), "gen status")),
             "pmax": num(val(r, 8, "pmax"), "Pmax"), "pmin": num(val(r, 9, "pmin"), "Pmin")}
        if g["pmin"] > g["pmax"] or g["qmin"] > g["qmax"]:
            raise ValueError("Invalid generator bounds for generator %d" % (k + 1))
        gens.append(g)

    branches = []
    for k, r in enumerate(branches_raw):
        fb = int(num(val(r, 0, "f_bus", "from_bus"), "from bus")); tb = int(num(val(r, 1, "t_bus", "to_bus"), "to bus"))
        if fb not in bus_index or tb not in bus_index:
            raise ValueError("Branch %d references an unknown bus" % (k + 1))
        br = {"f": fb, "t": tb, "r": num(val(r, 2, "br_r", "r"), "branch r"),
              "x": num(val(r, 3, "br_x", "x"), "branch x"), "b": num(val(r, 4, "br_b", "b"), "branch b"),
              "rate": num(val(r, 5, "rate_a", "ratea"), "rateA"),
              "tap": num(val(r, 8, "tap"), "tap"), "shift": num(val(r, 9, "shift"), "shift"),
              "status": int(num(val(r, 10, "br_status", "status"), "branch status")),
              "amin": num(val(r, 11, "angmin", "angle_min"), "angmin"),
              "amax": num(val(r, 12, "angmax", "angle_max"), "angmax")}
        if br["r"] == 0 and br["x"] == 0:
            raise ValueError("Branch %d has zero series impedance" % (k + 1))
        if br["rate"] < 0 or br["amin"] > br["amax"]:
            raise ValueError("Invalid branch bounds for branch %d" % (k + 1))
        branches.append(br)

    costs = []
    for k in range(len(gens)):
        r = costs_raw[k]
        model = int(num(val(r, 0, "model"), "cost model"))
        ncost = int(num(val(r, 3, "ncost"), "ncost"))
        if model != 2 or ncost < 1:
            raise ValueError("Only polynomial (model 2) gencost rows are supported (generator %d)" % (k + 1))
        if isinstance(r, dict):
            coeff = val(r, 4, "cost", "coefficients", "coeffs")
            if not isinstance(coeff, list) or len(coeff) < ncost:
                raise ValueError("Invalid polynomial coefficients for generator %d" % (k + 1))
            coeff = coeff[:ncost]
        else:
            if len(r) < 4 + ncost:
                raise ValueError("Truncated gencost row for generator %d" % (k + 1))
            coeff = r[4:4 + ncost]
        costs.append([num(c, "cost coefficient") for c in coeff])
    return base, buses, gens, branches, costs, bus_index, refs[0]


def branch_pq(vm_f, va_f, vm_t, va_t, br):
    """Numerical pi-model flows in pu, retaining MATPOWER tap-side asymmetry."""
    tap = 1.0 if br["tap"] == 0 else br["tap"]
    den = br["r"] * br["r"] + br["x"] * br["x"]
    g, bb = br["r"] / den, -br["x"] / den
    d = va_f - va_t - math.radians(br["shift"])
    c, s = math.cos(d), math.sin(d)
    pf = g * vm_f * vm_f / (tap * tap) - vm_f * vm_t / tap * (g * c + bb * s)
    qf = -(bb + br["b"] / 2) * vm_f * vm_f / (tap * tap) - vm_f * vm_t / tap * (g * s - bb * c)
    # Reverse expression uses delta' = -delta and no tap-square to-side self term.
    dr = -d
    cr, sr = math.cos(dr), math.sin(dr)
    pt = g * vm_t * vm_t - vm_f * vm_t / tap * (g * cr + bb * sr)
    qt = -(bb + br["b"] / 2) * vm_t * vm_t - vm_f * vm_t / tap * (g * sr - bb * cr)
    return pf, qf, pt, qt


def solve(base, buses, gens, branches, costs, bi, ref):
    n, ng = len(buses), len(gens)
    vm, va, pg, qg = ca.SX.sym("vm", n), ca.SX.sym("va", n), ca.SX.sym("pg", ng), ca.SX.sym("qg", ng)
    x = ca.vertcat(vm, va, pg, qg)
    constraints, lo_g, hi_g = [], [], []
    def add(expr, lo, hi):
        constraints.append(expr); lo_g.append(lo); hi_g.append(hi)

    p_out = [0 for _ in range(n)]; q_out = [0 for _ in range(n)]
    for br in branches:
        if br["status"] == 0:
            continue
        i, j = bi[br["f"]], bi[br["t"]]
        tap = 1.0 if br["tap"] == 0 else br["tap"]
        den = br["r"] ** 2 + br["x"] ** 2
        g, bb, shift = br["r"] / den, -br["x"] / den, math.radians(br["shift"])
        d = va[i] - va[j] - shift
        pf = g * vm[i]**2 / tap**2 - vm[i] * vm[j] / tap * (g * ca.cos(d) + bb * ca.sin(d))
        qf = -(bb + br["b"] / 2) * vm[i]**2 / tap**2 - vm[i] * vm[j] / tap * (g * ca.sin(d) - bb * ca.cos(d))
        dr = -d
        pt = g * vm[j]**2 - vm[i] * vm[j] / tap * (g * ca.cos(dr) + bb * ca.sin(dr))
        qt = -(bb + br["b"] / 2) * vm[j]**2 - vm[i] * vm[j] / tap * (g * ca.sin(dr) - bb * ca.cos(dr))
        p_out[i] += pf; q_out[i] += qf; p_out[j] += pt; q_out[j] += qt
        if br["rate"] > 0:
            cap2 = (br["rate"] / base) ** 2
            add(pf**2 + qf**2, -ca.inf, cap2); add(pt**2 + qt**2, -ca.inf, cap2)
        add(va[i] - va[j], math.radians(br["amin"]), math.radians(br["amax"]))

    for i, b in enumerate(buses):
        gp = sum((pg[k] for k, gen in enumerate(gens) if bi[gen["bus"]] == i), 0)
        gq = sum((qg[k] for k, gen in enumerate(gens) if bi[gen["bus"]] == i), 0)
        add(gp - b["pd"] / base - b["gs"] / base * vm[i]**2 - p_out[i], 0, 0)
        add(gq - b["qd"] / base + b["bs"] / base * vm[i]**2 - q_out[i], 0, 0)
    add(va[ref], 0, 0)

    objective = 0
    for k, coeff in enumerate(costs):
        mw = pg[k] * base
        degree = len(coeff) - 1
        objective += sum(c * mw ** (degree - z) for z, c in enumerate(coeff))

    lb, ub, x0 = [], [], []
    for b in buses:
        lb.append(b["vmin"]); ub.append(b["vmax"]); x0.append(min(max(b["vm"], b["vmin"]), b["vmax"]))
    for b in buses:
        lb.append(-math.pi); ub.append(math.pi); x0.append(min(max(math.radians(b["va"]), -math.pi), math.pi))
    x0[n + ref] = 0.0
    for gen in gens:
        l, u = (0.0, 0.0) if gen["status"] == 0 else (gen["pmin"] / base, gen["pmax"] / base)
        lb.append(l); ub.append(u); x0.append(min(max(gen["pg0"] / base, l), u))
    for gen in gens:
        l, u = (0.0, 0.0) if gen["status"] == 0 else (gen["qmin"] / base, gen["qmax"] / base)
        lb.append(l); ub.append(u); x0.append(min(max(gen["qg0"] / base, l), u))

    nlp = {"x": x, "f": objective, "g": ca.vertcat(*constraints)}
    opts = {"print_time": False, "ipopt.print_level": 0, "ipopt.sb": "yes", "ipopt.tol": 1e-9,
            "ipopt.acceptable_tol": 1e-8, "ipopt.max_iter": 3000, "ipopt.mu_strategy": "adaptive"}
    solver = ca.nlpsol("acopf", "ipopt", nlp, opts)
    result = solver(x0=x0, lbx=lb, ubx=ub, lbg=lo_g, ubg=hi_g)
    stats = solver.stats()
    if not stats.get("success", False):
        raise RuntimeError("IPOPT did not converge: " + str(stats.get("return_status", "unknown")))
    z = [float(v) for v in result["x"].full().ravel()]
    return z[:n], z[n:2*n], z[2*n:2*n+ng], z[2*n+ng:]


def validate_and_report(base, buses, gens, branches, costs, bi, vm, va, pg, qg):
    n = len(buses)
    pout, qout = [0.0] * n, [0.0] * n
    candidates, worst_overload = [], 0.0
    for row, br in enumerate(branches):
        if br["status"] == 0:
            continue
        i, j = bi[br["f"]], bi[br["t"]]
        pf, qf, pt, qt = branch_pq(vm[i], va[i], vm[j], va[j], br)
        pout[i] += pf; qout[i] += qf; pout[j] += pt; qout[j] += qt
        sf, st = math.hypot(pf, qf) * base, math.hypot(pt, qt) * base
        if br["rate"] > 0:
            loading = max(sf, st) / br["rate"] * 100.0
            candidates.append((loading, br["f"], br["t"], row, sf, st, br["rate"]))
            worst_overload = max(worst_overload, sf - br["rate"], st - br["rate"])
    if len(candidates) < 10:
        raise ValueError("The required report needs 10 in-service positive-rateA branches; case has %d" % len(candidates))

    pgen, qgen = [0.0] * n, [0.0] * n
    for k, gen in enumerate(gens):
        i = bi[gen["bus"]]; pgen[i] += pg[k]; qgen[i] += qg[k]
    pmis, qmis, vviol = [], [], []
    for i, b in enumerate(buses):
        pmis.append((pgen[i] - b["pd"] / base - b["gs"] / base * vm[i]**2 - pout[i]) * base)
        qmis.append((qgen[i] - b["qd"] / base + b["bs"] / base * vm[i]**2 - qout[i]) * base)
        vviol.append(max(0.0, b["vmin"] - vm[i], vm[i] - b["vmax"]))
    maxp, maxq, maxv = max(map(abs, pmis)), max(map(abs, qmis)), max(vviol)
    overload = max(0.0, worst_overload)
    # Guard against a report whose serialized values are materially infeasible.
    if maxp > 1e-3 or maxq > 1e-3 or maxv > 1e-7 or overload > 1e-3:
        raise RuntimeError("Independent feasibility check failed: P=%g MW Q=%g MVAr V=%g pu overload=%g MVA" % (maxp, maxq, maxv, overload))

    total_cost = 0.0
    for k, coeff in enumerate(costs):
        power = pg[k] * base; degree = len(coeff) - 1
        total_cost += sum(c * power ** (degree - z) for z, c in enumerate(coeff))
    total_gen_mw, total_gen_mvar = sum(pg) * base, sum(qg) * base
    total_load_mw, total_load_mvar = sum(b["pd"] for b in buses), sum(b["qd"] for b in buses)
    candidates.sort(key=lambda r: (-r[0], r[1], r[2], r[3]))
    ranked = [{"from_bus": f, "to_bus": t, "loading_pct": load, "flow_from_MVA": sf,
               "flow_to_MVA": st, "limit_MVA": limit}
              for load, f, t, row, sf, st, limit in candidates[:10]]
    return {
        "summary": {"total_cost_per_hour": total_cost, "total_load_MW": total_load_mw,
                    "total_load_MVAr": total_load_mvar, "total_generation_MW": total_gen_mw,
                    "total_generation_MVAr": total_gen_mvar,
                    "total_losses_MW": total_gen_mw - total_load_mw, "solver_status": "optimal"},
        "generators": [{"id": k + 1, "bus": g["bus"], "pg_MW": pg[k] * base, "qg_MVAr": qg[k] * base,
                        "pmin_MW": g["pmin"], "pmax_MW": g["pmax"], "qmin_MVAr": g["qmin"], "qmax_MVAr": g["qmax"]}
                       for k, g in enumerate(gens)],
        "buses": [{"id": b["id"], "vm_pu": vm[i], "va_deg": math.degrees(va[i]),
                   "vmin_pu": b["vmin"], "vmax_pu": b["vmax"]} for i, b in enumerate(buses)],
        "most_loaded_branches": ranked,
        "feasibility_check": {"max_p_mismatch_MW": maxp, "max_q_mismatch_MVAr": maxq,
                              "max_voltage_violation_pu": maxv, "max_branch_overload_MVA": overload}
    }


def main():
    req = json.load(sys.stdin)
    if not isinstance(req, dict) or "network_path" not in req or "output_path" not in req:
        raise ValueError("stdin must be an object with network_path and output_path")
    with open(req["network_path"], "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    base, buses, gens, branches, costs, bi, ref = parse_case(raw)
    vm, va, pg, qg = solve(base, buses, gens, branches, costs, bi, ref)
    report = validate_and_report(base, buses, gens, branches, costs, bi, vm, va, pg, qg)
    out = req["output_path"]
    parent = os.path.dirname(os.path.abspath(out))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, allow_nan=False)
        fh.write("\n")
    print(json.dumps({"status": "ok", "output_path": out, "solver_status": "optimal"}))


if __name__ == "__main__":
    main()
