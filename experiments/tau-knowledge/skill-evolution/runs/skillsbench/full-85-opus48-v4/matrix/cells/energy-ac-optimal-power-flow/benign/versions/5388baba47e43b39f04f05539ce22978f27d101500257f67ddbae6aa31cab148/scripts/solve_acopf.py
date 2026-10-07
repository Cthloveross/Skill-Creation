#!/usr/bin/env python3
"""Solve a MATPOWER-style ACOPF and write report.json.

Reads a JSON object on stdin:
  {"network_path": "/root/network.json",
   "output_path":  "/root/report.json",
   "top_n": 10}
All keys optional. Emits a JSON summary on stdout and writes the full report.

The electrical model follows the frozen ACOPF background (pi-model branch
flows with transformer tap asymmetry, per-unit power balance with MATPOWER
shunt sign conventions, squared apparent-power branch limits, angle-difference
bounds, and a quadratic cost in physical MW).
"""
import json
import math
import sys

import numpy as np

# ---- MATPOWER column indices (0-based) --------------------------------------
BUS_I, BUS_TYPE, PD, QD, GS, BS = 0, 1, 2, 3, 4, 5
VM, VA, VMAX, VMIN = 7, 8, 11, 12
GEN_BUS, PG, QG, QMAX, QMIN, VG, MBASE, GEN_STATUS, PMAX, PMIN = \
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9
F_BUS, T_BUS, BR_R, BR_X, BR_B, RATE_A = 0, 1, 2, 3, 4, 5
BR_TAP, BR_SHIFT, BR_STATUS, ANGMIN, ANGMAX = 8, 9, 10, 11, 12


def _find_arrays(data):
    """Return (baseMVA, bus, gen, branch, gencost) handling light nesting."""
    d = data
    if 'bus' not in d:
        for key in ('mpc', 'case', 'network'):
            if isinstance(d.get(key), dict) and 'bus' in d[key]:
                d = d[key]
                break
    base = float(d.get('baseMVA', d.get('base_mva', 100.0)))
    bus = [list(map(float, r)) for r in d['bus']]
    gen = [list(map(float, r)) for r in d['gen']]
    branch = [list(map(float, r)) for r in d['branch']]
    gencost = d.get('gencost')
    if gencost is not None:
        gencost = [list(map(float, r)) for r in gencost]
    return base, bus, gen, branch, gencost


def _branch_params(br):
    r, x, bc = br[BR_R], br[BR_X], br[BR_B]
    denom = r * r + x * x
    g = r / denom if denom != 0 else 0.0
    b = -x / denom if denom != 0 else 0.0
    t = br[BR_TAP]
    t = 1.0 if t == 0.0 else t
    shift = math.radians(br[BR_SHIFT])
    return g, b, bc, t, shift


def _flows(vm_i, vm_j, va_i, va_j, g, b, bc, t, shift, M):
    """Pi-model flows in pu. M provides cos/sin (math/np for numeric, casadi)."""
    delta = va_i - va_j - shift
    dp = va_j - va_i + shift
    cos, sin = M['cos'], M['sin']
    p_ij = g * vm_i**2 / t**2 - (vm_i * vm_j / t) * (g * cos(delta) + b * sin(delta))
    q_ij = -(b + bc / 2.0) * vm_i**2 / t**2 - (vm_i * vm_j / t) * (g * sin(delta) - b * cos(delta))
    p_ji = g * vm_j**2 - (vm_i * vm_j / t) * (g * cos(dp) + b * sin(dp))
    q_ji = -(b + bc / 2.0) * vm_j**2 - (vm_i * vm_j / t) * (g * sin(dp) - b * cos(dp))
    return p_ij, q_ij, p_ji, q_ji


def _poly_cost(coeffs, pg_mw):
    """coeffs highest-order first; cost at pg_mw (MW)."""
    deg = len(coeffs) - 1
    total = 0.0
    for k, c in enumerate(coeffs):
        total = total + c * pg_mw ** (deg - k)
    return total


def _poly_cost_sym(coeffs, pg_mw):
    deg = len(coeffs) - 1
    total = 0.0
    for k, c in enumerate(coeffs):
        total = total + c * pg_mw ** (deg - k)
    return total


def solve(network_path, output_path, top_n):
    import casadi as ca

    with open(network_path) as f:
        data = json.load(f)
    base, bus, gen, branch, gencost = _find_arrays(data)

    nb = len(bus)
    ng = len(gen)
    id2idx = {int(bus[i][BUS_I]): i for i in range(nb)}

    # per-unit demand / shunt per bus
    Pd = np.array([bus[i][PD] / base for i in range(nb)])
    Qd = np.array([bus[i][QD] / base for i in range(nb)])
    Gs = np.array([bus[i][GS] / base for i in range(nb)])
    Bs = np.array([bus[i][BS] / base for i in range(nb)])
    Vmin = np.array([bus[i][VMIN] for i in range(nb)])
    Vmax = np.array([bus[i][VMAX] for i in range(nb)])
    slack = [i for i in range(nb) if int(bus[i][BUS_TYPE]) == 3]

    # generator attributes
    gbus = [id2idx[int(gen[k][GEN_BUS])] for k in range(ng)]
    gstat = [int(gen[k][GEN_STATUS]) for k in range(ng)]
    Pmin = np.array([gen[k][PMIN] / base for k in range(ng)])
    Pmax = np.array([gen[k][PMAX] / base for k in range(ng)])
    Qmin = np.array([gen[k][QMIN] / base for k in range(ng)])
    Qmax = np.array([gen[k][QMAX] / base for k in range(ng)])
    for k in range(ng):
        if gstat[k] == 0:
            Pmin[k] = Pmax[k] = 0.0
            Qmin[k] = Qmax[k] = 0.0

    # cost coefficients (highest-order first) per gen, in MW
    cost_coeffs = []
    for k in range(ng):
        if gencost is not None and k < len(gencost):
            row = gencost[k]
            ncost = int(row[3])
            cost_coeffs.append(row[4:4 + ncost])
        else:
            cost_coeffs.append([0.0, 0.0])

    # in-service branches
    br_idx = [j for j in range(len(branch)) if int(branch[j][BR_STATUS]) == 1]

    # ---- symbolic model -----------------------------------------------------
    Vm = ca.MX.sym('Vm', nb)
    Va = ca.MX.sym('Va', nb)
    Pg = ca.MX.sym('Pg', ng)
    Qg = ca.MX.sym('Qg', ng)
    Mca = {'cos': ca.cos, 'sin': ca.sin}

    # bus injection accumulators (flows out), pu
    Pout = [ca.MX(0) for _ in range(nb)]
    Qout = [ca.MX(0) for _ in range(nb)]
    g_ineq = []
    lbg_i = []
    ubg_i = []
    for j in br_idx:
        br = branch[j]
        fi = id2idx[int(br[F_BUS])]
        ti = id2idx[int(br[T_BUS])]
        g, b, bc, t, shift = _branch_params(br)
        p_ij, q_ij, p_ji, q_ji = _flows(Vm[fi], Vm[ti], Va[fi], Va[ti],
                                        g, b, bc, t, shift, Mca)
        Pout[fi] = Pout[fi] + p_ij
        Qout[fi] = Qout[fi] + q_ij
        Pout[ti] = Pout[ti] + p_ji
        Qout[ti] = Qout[ti] + q_ji
        rateA = br[RATE_A]
        if rateA > 0:
            lim2 = (rateA / base) ** 2
            g_ineq.append(p_ij**2 + q_ij**2 - lim2)
            lbg_i.append(-ca.inf); ubg_i.append(0.0)
            g_ineq.append(p_ji**2 + q_ji**2 - lim2)
            lbg_i.append(-ca.inf); ubg_i.append(0.0)
        amin, amax = br[ANGMIN], br[ANGMAX]
        if not (amin == 0.0 and amax == 0.0):
            g_ineq.append(Va[fi] - Va[ti])
            lbg_i.append(math.radians(amin)); ubg_i.append(math.radians(amax))

    # gen contributions per bus
    Pgen = [ca.MX(0) for _ in range(nb)]
    Qgen = [ca.MX(0) for _ in range(nb)]
    for k in range(ng):
        Pgen[gbus[k]] = Pgen[gbus[k]] + Pg[k]
        Qgen[gbus[k]] = Qgen[gbus[k]] + Qg[k]

    g_eq = []
    for i in range(nb):
        g_eq.append(Pgen[i] - Pd[i] - Gs[i] * Vm[i]**2 - Pout[i])
        g_eq.append(Qgen[i] - Qd[i] + Bs[i] * Vm[i]**2 - Qout[i])
    lbg_e = [0.0] * len(g_eq)
    ubg_e = [0.0] * len(g_eq)

    # objective: cost in MW
    obj = ca.MX(0)
    for k in range(ng):
        pg_mw = Pg[k] * base
        obj = obj + _poly_cost_sym(cost_coeffs[k], pg_mw)

    x = ca.vertcat(Vm, Va, Pg, Qg)
    gall = ca.vertcat(*(g_eq + g_ineq)) if (g_eq + g_ineq) else ca.MX()
    lbg = lbg_e + lbg_i
    ubg = ubg_e + ubg_i

    nlp = {'x': x, 'f': obj, 'g': gall}
    opts = {'ipopt.print_level': 0, 'print_time': 0,
            'ipopt.tol': 1e-6, 'ipopt.max_iter': 2000,
            'ipopt.mu_strategy': 'adaptive'}
    solver = ca.nlpsol('acopf', 'ipopt', nlp, opts)

    # bounds
    lbx = np.concatenate([Vmin, np.full(nb, -math.pi), Pmin, Qmin])
    ubx = np.concatenate([Vmax, np.full(nb, math.pi), Pmax, Qmax])
    for s in slack:
        lbx[nb + s] = 0.0
        ubx[nb + s] = 0.0

    def clip(v, lo, hi):
        return np.minimum(np.maximum(v, lo), hi)

    # start points
    starts = []
    # flat start
    vm0 = clip(np.ones(nb), Vmin, Vmax)
    va0 = np.zeros(nb)
    pg0 = clip((Pmin + Pmax) / 2.0, Pmin, Pmax)
    qg0 = clip((Qmin + Qmax) / 2.0, Qmin, Qmax)
    starts.append(np.concatenate([vm0, va0, pg0, qg0]))
    # data-based start
    vmd = clip(np.array([bus[i][VM] for i in range(nb)]), Vmin, Vmax)
    vad = np.array([math.radians(bus[i][VA]) for i in range(nb)])
    for s in slack:
        vad[s] = 0.0
    pgd = clip(np.array([gen[k][PG] / base for k in range(ng)]), Pmin, Pmax)
    qgd = clip(np.array([gen[k][QG] / base for k in range(ng)]), Qmin, Qmax)
    starts.append(np.concatenate([vmd, vad, pgd, qgd]))

    best = None
    for x0 in starts:
        try:
            sol = solver(x0=x0, lbx=lbx, ubx=ubx, lbg=lbg, ubg=ubg)
        except Exception:
            continue
        status = solver.stats().get('return_status', 'Unknown')
        xv = np.array(sol['x']).flatten()
        cost = float(sol['f'])
        feas = _feasibility(xv, nb, ng, bus, gen, branch, gencost, base,
                            id2idx, gbus, Pd, Qd, Gs, Bs, Vmin, Vmax, br_idx)
        score = (feas['max_p_mismatch_MW'] + feas['max_q_mismatch_MVAr']
                 + 1e3 * feas['max_voltage_violation_pu']
                 + feas['max_branch_overload_MVA'])
        ok = (status == 'Solve_Succeeded')
        cand = (0 if ok else 1, round(score, 3) if not ok else 0.0, cost,
                xv, status, feas)
        if best is None or cand[:3] < best[:3]:
            best = cand
    if best is None:
        raise RuntimeError('solver failed from all starts')

    _, _, cost, xv, status, feas = best
    report = _build_report(xv, status, nb, ng, bus, gen, branch, gencost,
                           base, id2idx, gbus, gstat, Pd, Qd, Vmin, Vmax,
                           br_idx, top_n, feas)
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    return report, status


def _numeric_flows(xv, nb, branch, id2idx, base, br_idx):
    Vm = xv[0:nb]
    Va = xv[nb:2 * nb]
    Mnp = {'cos': np.cos, 'sin': np.sin}
    out = {}
    for j in br_idx:
        br = branch[j]
        fi = id2idx[int(br[F_BUS])]
        ti = id2idx[int(br[T_BUS])]
        g, b, bc, t, shift = _branch_params(br)
        p_ij, q_ij, p_ji, q_ji = _flows(Vm[fi], Vm[ti], Va[fi], Va[ti],
                                        g, b, bc, t, shift, Mnp)
        s_ij = math.sqrt(p_ij**2 + q_ij**2) * base
        s_ji = math.sqrt(p_ji**2 + q_ji**2) * base
        out[j] = (p_ij, q_ij, p_ji, q_ji, s_ij, s_ji, fi, ti)
    return out


def _feasibility(xv, nb, ng, bus, gen, branch, gencost, base, id2idx, gbus,
                 Pd, Qd, Gs, Bs, Vmin, Vmax, br_idx):
    Vm = xv[0:nb]
    Pg = xv[2 * nb:2 * nb + ng]
    Qg = xv[2 * nb + ng:2 * nb + 2 * ng]
    flows = _numeric_flows(xv, nb, branch, id2idx, base, br_idx)
    Pout = np.zeros(nb); Qout = np.zeros(nb)
    for j, (p_ij, q_ij, p_ji, q_ji, s_ij, s_ji, fi, ti) in flows.items():
        Pout[fi] += p_ij; Qout[fi] += q_ij
        Pout[ti] += p_ji; Qout[ti] += q_ji
    Pgen = np.zeros(nb); Qgen = np.zeros(nb)
    for k in range(ng):
        Pgen[gbus[k]] += Pg[k]; Qgen[gbus[k]] += Qg[k]
    pres = (Pgen - Pd - Gs * Vm**2 - Pout) * base
    qres = (Qgen - Qd + Bs * Vm**2 - Qout) * base
    vviol = np.maximum(0.0, np.maximum(Vm - Vmax, Vmin - Vm))
    overload = 0.0
    for j, (p_ij, q_ij, p_ji, q_ji, s_ij, s_ji, fi, ti) in flows.items():
        rateA = branch[j][RATE_A]
        if rateA > 0:
            overload = max(overload, max(s_ij, s_ji) - rateA)
    return {
        'max_p_mismatch_MW': float(np.max(np.abs(pres))) if nb else 0.0,
        'max_q_mismatch_MVAr': float(np.max(np.abs(qres))) if nb else 0.0,
        'max_voltage_violation_pu': float(np.max(vviol)) if nb else 0.0,
        'max_branch_overload_MVA': float(max(0.0, overload)),
    }


def _build_report(xv, status, nb, ng, bus, gen, branch, gencost, base,
                  id2idx, gbus, gstat, Pd, Qd, Vmin, Vmax, br_idx, top_n,
                  feas):
    Vm = xv[0:nb]; Va = xv[nb:2 * nb]
    Pg = xv[2 * nb:2 * nb + ng]; Qg = xv[2 * nb + ng:2 * nb + 2 * ng]

    # generators (reported, physical MW/MVAr); round then derive totals from them
    gens = []
    cost_coeffs = []
    for k in range(ng):
        if gencost is not None and k < len(gencost):
            ncost = int(gencost[k][3]); cost_coeffs.append(gencost[k][4:4 + ncost])
        else:
            cost_coeffs.append([0.0, 0.0])
    total_gen_p = 0.0; total_gen_q = 0.0; total_cost = 0.0
    for k in range(ng):
        pg_mw = round(float(Pg[k] * base), 6)
        qg_mw = round(float(Qg[k] * base), 6)
        gens.append({
            'id': k + 1,
            'bus': int(gen[k][GEN_BUS]),
            'pg_MW': pg_mw,
            'qg_MVAr': qg_mw,
            'pmin_MW': round(float(gen[k][PMIN]), 6),
            'pmax_MW': round(float(gen[k][PMAX]), 6),
            'qmin_MVAr': round(float(gen[k][QMIN]), 6),
            'qmax_MVAr': round(float(gen[k][QMAX]), 6),
        })
        total_gen_p += pg_mw
        total_gen_q += qg_mw
        total_cost += _poly_cost(cost_coeffs[k], pg_mw)

    buses = []
    for i in range(nb):
        buses.append({
            'id': int(bus[i][BUS_I]),
            'vm_pu': round(float(Vm[i]), 6),
            'va_deg': round(float(math.degrees(Va[i])), 6),
            'vmin_pu': round(float(bus[i][VMIN]), 6),
            'vmax_pu': round(float(bus[i][VMAX]), 6),
        })

    total_load_p = round(float(np.sum(Pd) * base), 6)
    total_load_q = round(float(np.sum(Qd) * base), 6)
    total_gen_p = round(total_gen_p, 6)
    total_gen_q = round(total_gen_q, 6)

    # most loaded branches: in-service, rateA>0, highest loading_pct
    flows = _numeric_flows(xv, nb, branch, id2idx, base, br_idx)
    ranked = []
    for j in br_idx:
        rateA = branch[j][RATE_A]
        if rateA <= 0:
            continue
        p_ij, q_ij, p_ji, q_ji, s_ij, s_ji, fi, ti = flows[j]
        loading = max(s_ij, s_ji) / rateA * 100.0
        ranked.append((loading, s_ij, s_ji, rateA, branch[j], j))
    # stable descending sort by loading; secondary key branch row index for ties
    ranked.sort(key=lambda r: (-r[0], r[5]))
    most_loaded = []
    for loading, s_ij, s_ji, rateA, br, j in ranked[:top_n]:
        most_loaded.append({
            'from_bus': int(br[F_BUS]),
            'to_bus': int(br[T_BUS]),
            'loading_pct': round(float(loading), 6),
            'flow_from_MVA': round(float(s_ij), 6),
            'flow_to_MVA': round(float(s_ji), 6),
            'limit_MVA': round(float(rateA), 6),
        })

    solver_status = 'optimal' if status == 'Solve_Succeeded' else status
    report = {
        'summary': {
            'total_cost_per_hour': round(float(total_cost), 2),
            'total_load_MW': total_load_p,
            'total_load_MVAr': total_load_q,
            'total_generation_MW': total_gen_p,
            'total_generation_MVAr': total_gen_q,
            'total_losses_MW': round(total_gen_p - total_load_p, 6),
            'solver_status': solver_status,
        },
        'generators': gens,
        'buses': buses,
        'most_loaded_branches': most_loaded,
        'feasibility_check': {
            'max_p_mismatch_MW': round(feas['max_p_mismatch_MW'], 6),
            'max_q_mismatch_MVAr': round(feas['max_q_mismatch_MVAr'], 6),
            'max_voltage_violation_pu': round(feas['max_voltage_violation_pu'], 6),
            'max_branch_overload_MVA': round(feas['max_branch_overload_MVA'], 6),
        },
    }
    return report


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    network_path = payload.get('network_path', '/root/network.json')
    output_path = payload.get('output_path', '/root/report.json')
    top_n = int(payload.get('top_n', 10))

    report, status = solve(network_path, output_path, top_n)
    out = {
        'status': report['summary']['solver_status'],
        'output_path': output_path,
        'total_cost_per_hour': report['summary']['total_cost_per_hour'],
        'feasibility_check': report['feasibility_check'],
    }
    print(json.dumps(out))


if __name__ == '__main__':
    main()
