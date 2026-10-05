"""Parsing, pi-model evaluation, reporting, and independent ACOPF checks."""
import json, math


def load_case(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    for key in ("case", "mpc", "network"):
        if isinstance(raw, dict) and isinstance(raw.get(key), dict) and "bus" in raw[key]:
            raw = raw[key]
            break
    required = ("bus", "gen", "branch", "gencost")
    if not isinstance(raw, dict) or any(k not in raw for k in required):
        raise ValueError("case must contain baseMVA, bus, gen, branch, and gencost arrays")
    base = raw.get("baseMVA", raw.get("baseMva"))
    if not isinstance(base, (int, float)) or base <= 0:
        raise ValueError("baseMVA must be positive")
    c = {k: raw[k] for k in required}
    c["baseMVA"] = float(base)
    if not all(isinstance(c[k], list) for k in required):
        raise ValueError("MATPOWER tables must be arrays")
    if len(c["gencost"]) < len(c["gen"]):
        raise ValueError("gencost must have at least one row per generator")
    c["bus_index"] = {}
    for i, row in enumerate(c["bus"]):
        if len(row) < 13: raise ValueError("bus row is shorter than 13 MATPOWER columns")
        bid = int(row[0])
        if bid in c["bus_index"]: raise ValueError("duplicate bus identifier")
        c["bus_index"][bid] = i
    for row in c["gen"]:
        if len(row) < 10: raise ValueError("generator row is shorter than 10 MATPOWER columns")
        if int(row[0]) not in c["bus_index"]: raise ValueError("generator references unknown bus")
    for row in c["branch"]:
        if len(row) < 13: raise ValueError("branch row is shorter than 13 MATPOWER columns")
        if int(row[0]) not in c["bus_index"] or int(row[1]) not in c["bus_index"]:
            raise ValueError("branch references unknown bus")
        if row[10] != 0 and float(row[2]) == 0 and float(row[3]) == 0:
            raise ValueError("in-service zero-impedance branch is unsupported")
    refs = [i for i, r in enumerate(c["bus"]) if int(r[1]) == 3]
    if len(refs) != 1: raise ValueError("exactly one BUS_TYPE=3 reference bus is required")
    c["ref"] = refs[0]
    for i, row in enumerate(c["gencost"][:len(c["gen"])]):
        if len(row) < 5 or int(row[0]) != 2:
            raise ValueError("only polynomial (MODEL=2) generator costs are supported")
        n = int(row[3])
        if n < 1 or len(row) < 4 + n: raise ValueError("malformed polynomial gencost row")
    return c


def effective_tap(branch_row):
    t = float(branch_row[8])
    return 1.0 if t == 0.0 else t


def branch_flows(case, vm, va):
    """Return one dict per branch; inactive rows have zero flows."""
    ans = []
    ix, base = case["bus_index"], case["baseMVA"]
    for k, r in enumerate(case["branch"]):
        f, tbus = ix[int(r[0])], ix[int(r[1])]
        active = int(r[10]) != 0
        if not active:
            ans.append(dict(index=k, active=False, f=f, t=tbus, pf=0., qf=0., pt=0., qt=0., sf=0., st=0.))
            continue
        rr, xx, bc = float(r[2]), float(r[3]), float(r[4])
        den = rr*rr + xx*xx
        g, b = rr/den, -xx/den
        tap, shift = effective_tap(r), math.radians(float(r[9]))
        d = va[f] - va[tbus] - shift
        cf, sd = math.cos(d), math.sin(d)
        vf, vt = vm[f], vm[tbus]
        pf = g*vf*vf/(tap*tap) - vf*vt/tap*(g*cf + b*sd)
        qf = -(b + bc/2)*vf*vf/(tap*tap) - vf*vt/tap*(g*sd - b*cf)
        # Reverse expression uses delta' = -delta and no to-side tap self factor.
        dp = -d
        pt = g*vt*vt - vf*vt/tap*(g*math.cos(dp) + b*math.sin(dp))
        qt = -(b + bc/2)*vt*vt - vf*vt/tap*(g*math.sin(dp) - b*math.cos(dp))
        ans.append(dict(index=k, active=True, f=f, t=tbus, pf=pf, qf=qf, pt=pt, qt=qt,
                        sf=math.hypot(pf, qf)*base, st=math.hypot(pt, qt)*base))
    return ans


def cost_value(case, pg_pu):
    total = 0.0
    base = case["baseMVA"]
    for p, row in zip(pg_pu, case["gencost"]):
        value = 0.0
        for a in row[4:4+int(row[3])]: value = value * (p*base) + float(a)
        total += value
    return total


def metrics(case, vm, va, pg, qg):
    """Recompute constraints. pg/qg are pu and all results are physical units."""
    n, base, ix = len(case["bus"]), case["baseMVA"], case["bus_index"]
    flows = branch_flows(case, vm, va)
    pout, qout = [0.0]*n, [0.0]*n
    for z in flows:
        if z["active"]:
            pout[z["f"]] += z["pf"]; qout[z["f"]] += z["qf"]
            pout[z["t"]] += z["pt"]; qout[z["t"]] += z["qt"]
    gp, gq = [0.0]*n, [0.0]*n
    gen_violation = 0.0
    for k, r in enumerate(case["gen"]):
        b = ix[int(r[0])]
        gp[b] += pg[k]; gq[b] += qg[k]
        lo_p, hi_p, lo_q, hi_q = float(r[9])/base, float(r[8])/base, float(r[4])/base, float(r[3])/base
        if int(r[7]) == 0: lo_p = hi_p = lo_q = hi_q = 0.0
        gen_violation = max(gen_violation, lo_p-pg[k], pg[k]-hi_p, lo_q-qg[k], qg[k]-hi_q)
    pres, qres, vv = [], [], 0.0
    for i, r in enumerate(case["bus"]):
        pres.append((gp[i] - float(r[2])/base - float(r[4])/base*vm[i]*vm[i] - pout[i])*base)
        qres.append((gq[i] - float(r[3])/base + float(r[5])/base*vm[i]*vm[i] - qout[i])*base)
        vv = max(vv, float(r[12])-vm[i], vm[i]-float(r[11]))
    overload, angle_violation = 0.0, 0.0
    for z, r in zip(flows, case["branch"]):
        if not z["active"]: continue
        rate = float(r[5])
        if rate > 0: overload = max(overload, z["sf"]-rate, z["st"]-rate)
        ddeg = math.degrees(va[z["f"]]-va[z["t"]])
        angle_violation = max(angle_violation, float(r[11])-ddeg, ddeg-float(r[12]))
    return {"flows": flows, "p_residuals_MW": pres, "q_residuals_MVAr": qres,
            "max_p_mismatch_MW": max(map(abs, pres), default=0.0),
            "max_q_mismatch_MVAr": max(map(abs, qres), default=0.0),
            "max_voltage_violation_pu": max(0.0, vv),
            "max_branch_overload_MVA": max(0.0, overload),
            "max_generator_violation_pu": max(0.0, gen_violation),
            "max_angle_violation_deg": max(0.0, angle_violation),
            "reference_angle_deg": math.degrees(va[case["ref"]])}


def report_object(case, vm, va, pg, qg):
    base, m = case["baseMVA"], metrics(case, vm, va, pg, qg)
    gens = []
    for k, r in enumerate(case["gen"]):
        gens.append({"id": k+1, "bus": int(r[0]), "pg_MW": pg[k]*base, "qg_MVAr": qg[k]*base,
                     "pmin_MW": float(r[9]), "pmax_MW": float(r[8]),
                     "qmin_MVAr": float(r[4]), "qmax_MVAr": float(r[3])})
    buses = [{"id": int(r[0]), "vm_pu": vm[i], "va_deg": math.degrees(va[i]),
              "vmin_pu": float(r[12]), "vmax_pu": float(r[11])}
             for i, r in enumerate(case["bus"])]
    eligible = []
    for z, r in zip(m["flows"], case["branch"]):
        rate = float(r[5])
        if z["active"] and rate > 0:
            loading = max(z["sf"], z["st"]) / rate * 100.0
            eligible.append((loading, z["index"], {"from_bus": int(r[0]), "to_bus": int(r[1]),
                "loading_pct": loading, "flow_from_MVA": z["sf"], "flow_to_MVA": z["st"], "limit_MVA": rate}))
    if len(eligible) < 10: raise ValueError("fewer than 10 in-service positive-rateA branches; exact ranking is impossible")
    eligible.sort(key=lambda x: (-x[0], x[1]))
    total_p, total_q = sum(pg)*base, sum(qg)*base
    return {"summary": {"total_cost_per_hour": cost_value(case, pg),
             "total_load_MW": sum(float(r[2]) for r in case["bus"]),
             "total_load_MVAr": sum(float(r[3]) for r in case["bus"]),
             "total_generation_MW": total_p, "total_generation_MVAr": total_q,
             "total_losses_MW": total_p-sum(float(r[2]) for r in case["bus"]), "solver_status": "optimal"},
            "generators": gens, "buses": buses, "most_loaded_branches": [x[2] for x in eligible[:10]],
            "feasibility_check": {k:m[k] for k in ("max_p_mismatch_MW", "max_q_mismatch_MVAr", "max_voltage_violation_pu", "max_branch_overload_MVA")}}


def is_feasible(m, balance_tol=1e-3):
    return (m["max_p_mismatch_MW"] <= balance_tol and m["max_q_mismatch_MVAr"] <= balance_tol and
            m["max_voltage_violation_pu"] <= 1e-7 and m["max_branch_overload_MVA"] <= balance_tol and
            m["max_generator_violation_pu"] <= 1e-7 and m["max_angle_violation_deg"] <= 1e-6 and
            abs(m["reference_angle_deg"]) <= 1e-7)
