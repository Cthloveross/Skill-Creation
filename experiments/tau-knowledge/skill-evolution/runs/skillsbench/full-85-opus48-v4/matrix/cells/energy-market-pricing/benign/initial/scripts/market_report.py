#!/usr/bin/env python3
"""DC-OPF with spinning-reserve co-optimization + transmission counterfactual.

Stdin (JSON, all keys optional):
  {"network_path":"/root/network.json","target_from":64,"target_to":1501,
   "cf_factor":1.2,"output_path":"/root/report.json","binding_pct":99.0,
   "top_k":3,"reserve_requirement":null,"round_price":4,"round_cost":2,
   "round_flow":4}

Stdout (JSON): the report dict (also written to output_path).
Stderr: validation diagnostics (nodal residual, recomputed cost, solver status).
"""
import sys, json
import numpy as np
import scipy.sparse as sp


def _find(d, *names):
    if not isinstance(d, dict):
        return None
    low = {k.lower(): k for k in d.keys()}
    for n in names:
        if n.lower() in low:
            return d[low[n.lower()]]
    return None


def load_case(path):
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, dict) and _find(data, 'bus') is None:
        m = _find(data, 'mpc', 'case', 'casedata', 'network')
        if isinstance(m, dict):
            data = m
    base = _find(data, 'baseMVA', 'base_mva', 'basemva')
    base = float(base) if base is not None else 100.0
    bus = np.array(_find(data, 'bus'), dtype=float)
    gen = np.array(_find(data, 'gen'), dtype=float)
    branch = np.array(_find(data, 'branch'), dtype=float)
    gc = _find(data, 'gencost')
    gc = np.array(gc, dtype=float) if gc is not None else None
    reserves = _find(data, 'reserves', 'reserve')
    return dict(baseMVA=base, bus=bus, gen=gen, branch=branch,
                gencost=gc, reserves=reserves)


def prepare(case):
    import cvxpy as cp
    bus = case['bus']; gen = case['gen']; br = case['branch']
    gc = case['gencost']; base = case['baseMVA']
    nbus = bus.shape[0]
    busid = bus[:, 0].astype(int)
    id2idx = {int(b): i for i, b in enumerate(busid)}
    Pd = bus[:, 2].astype(float).copy()
    ref = np.where(bus[:, 1].astype(int) == 3)[0]
    ref_idx = int(ref[0]) if len(ref) > 0 else 0

    status = gen[:, 7].astype(int)
    gidx = np.where(status == 1)[0]
    ngen = len(gidx)
    gbus = gen[gidx, 0].astype(int)
    Pmax = gen[gidx, 8].astype(float)
    Pmin = gen[gidx, 9].astype(float)

    c2 = np.zeros(ngen); c1 = np.zeros(ngen); c0 = np.zeros(ngen)
    if gc is not None:
        for k, g in enumerate(gidx):
            row = gc[g]
            nc = int(row[3])
            co = row[4:4 + nc]
            if nc == 3:
                c2[k], c1[k], c0[k] = co[0], co[1], co[2]
            elif nc == 2:
                c1[k], c0[k] = co[0], co[1]
            elif nc == 1:
                c0[k] = co[0]
            elif nc >= 3:
                c2[k], c1[k], c0[k] = co[-3], co[-2], co[-1]
    if np.any(c2 < 0):
        print('WARN: negative quadratic cost coefficient(s); QP may be nonconvex',
              file=sys.stderr)

    rows = [id2idx[int(b)] for b in gbus]
    Cg = sp.csr_matrix((np.ones(ngen), (rows, np.arange(ngen))), shape=(nbus, ngen))

    bstat = br[:, 10].astype(int)
    bi = np.where(bstat == 1)[0]
    nbr = len(bi)
    fb = br[bi, 0].astype(int); tb = br[bi, 1].astype(int)
    x = br[bi, 3].astype(float)
    tap = br[bi, 8].astype(float); tap = np.where(tap == 0, 1.0, tap)
    shift = np.deg2rad(br[bi, 9].astype(float))
    rateA = br[bi, 5].astype(float).copy()
    bvec = base / (x * tap)
    fcol = [id2idx[int(b)] for b in fb]
    tcol = [id2idx[int(b)] for b in tb]
    A = sp.csr_matrix((np.concatenate([np.ones(nbr), -np.ones(nbr)]),
                       (np.concatenate([np.arange(nbr), np.arange(nbr)]),
                        np.array(fcol + tcol))), shape=(nbr, nbus))
    AT = A.T.tocsr()

    # ----- reserve data -----
    rcost = np.zeros(ngen)
    rqty = np.full(ngen, np.inf)
    zones = []  # list of (in-service gen-index array, requirement MW)
    res = case['reserves']
    gidx_list = list(gidx)

    def mapfull(arr):
        a = np.array(arr, dtype=float).ravel()
        full = np.zeros(gen.shape[0])
        if a.shape[0] == gen.shape[0]:
            full = a
        elif a.shape[0] == ngen:
            full[gidx] = a
        else:
            full[:min(a.shape[0], gen.shape[0])] = a[:gen.shape[0]]
        return full[gidx]

    if isinstance(res, dict):
        req = _find(res, 'req', 'requirement')
        cost = _find(res, 'cost')
        qty = _find(res, 'qty', 'quantity', 'rmax', 'max')
        zmat = _find(res, 'zones', 'zone')
        if cost is not None:
            rcost = mapfull(cost)
        if qty is not None:
            q = mapfull(qty)
            rqty = np.where(np.isfinite(q), q, np.inf)
        if zmat is not None:
            Z = np.array(zmat, dtype=float)
            if Z.ndim == 1:
                Z = Z.reshape(1, -1)
            reqarr = np.atleast_1d(np.array(req, dtype=float)) if req is not None \
                else np.zeros(Z.shape[0])
            for z in range(Z.shape[0]):
                cols = np.where(Z[z] != 0)[0]
                sel = [gidx_list.index(c) for c in cols if c in gidx_list]
                rr = float(reqarr[z]) if z < len(reqarr) else 0.0
                zones.append((np.array(sel, dtype=int), rr))
        elif req is not None:
            reqs = np.atleast_1d(np.array(req, dtype=float))
            zones.append((np.arange(ngen), float(reqs.sum())))

    def solve(rateA_vec, req_override=None):
        theta = cp.Variable(nbus)
        Pg = cp.Variable(ngen)
        cons = [theta[ref_idx] == 0, Pg >= Pmin, Pg <= Pmax]
        f = cp.multiply(bvec, A @ theta - shift)
        bal = Cg @ Pg - AT @ f == Pd
        cons.append(bal)
        robj = 0
        zone_cons = []
        active_zones = [(sel, (req if req_override is None else req_override))
                        for sel, req in zones]
        use_res = any(len(sel) > 0 and rr > 0 for sel, rr in active_zones)
        if use_res:
            R = cp.Variable(ngen)
            cons.append(R >= 0)
            fin = np.where(np.isfinite(rqty))[0]
            if len(fin) > 0:
                cons.append(R[fin] <= rqty[fin])
            cons.append(Pg + R <= Pmax)
            robj = cp.sum(cp.multiply(rcost, R))
            for sel, rr in active_zones:
                if len(sel) > 0 and rr > 0:
                    zc = cp.sum(R[sel]) >= rr
                    cons.append(zc); zone_cons.append(zc)
        else:
            R = None
        obj = cp.sum(cp.multiply(c2, cp.square(Pg)) + cp.multiply(c1, Pg)) \
            + float(np.sum(c0)) + robj
        lim = np.where(rateA_vec > 0)[0]
        if len(lim) > 0:
            cons.append(f[lim] <= rateA_vec[lim])
            cons.append(f[lim] >= -rateA_vec[lim])
        prob = cp.Problem(cp.Minimize(obj), cons)
        status = None
        for s in [cp.CLARABEL, cp.ECOS, cp.OSQP, cp.SCS]:
            try:
                prob.solve(solver=s)
            except Exception as e:
                status = 'err:%s' % e
                continue
            status = prob.status
            if prob.status in ('optimal', 'optimal_inaccurate'):
                break
        if prob.status not in ('optimal', 'optimal_inaccurate'):
            raise RuntimeError('solve failed: %s' % status)
        Pgv = np.array(Pg.value, dtype=float).ravel()
        thv = np.array(theta.value, dtype=float).ravel()
        fv = bvec * (A.dot(thv) - shift)
        lmp = np.array(bal.dual_value, dtype=float).ravel()
        if np.median(lmp) < 0:
            lmp = -lmp
        mcp = 0.0
        if zone_cons:
            mcp = max(abs(float(z.dual_value)) for z in zone_cons)
        resid = float(np.max(np.abs(Cg.dot(Pgv) - AT.dot(fv) - Pd)))
        recost = float(np.sum(c2 * Pgv ** 2 + c1 * Pgv + c0))
        print('solver=%s status=%s max_nodal_residual_MW=%.3e recomputed_energy_cost=%.4f obj=%.4f'
              % (s, prob.status, resid, recost, float(prob.value)), file=sys.stderr)
        return dict(Pg=Pgv, theta=thv, f=fv, lmp=lmp, mcp=mcp,
                    cost=float(prob.value), rateA=rateA_vec, residual=resid)

    return dict(solve=solve, fb=fb, tb=tb, rateA=rateA, nbus=nbus, busid=busid)


def main():
    raw = sys.stdin.read()
    cfg = json.loads(raw) if raw.strip() else {}
    net = cfg.get('network_path', '/root/network.json')
    tf = int(cfg.get('target_from', 64))
    tt = int(cfg.get('target_to', 1501))
    factor = float(cfg.get('cf_factor', 1.2))
    outp = cfg.get('output_path', '/root/report.json')
    thr = float(cfg.get('binding_pct', 99.0))
    topk = int(cfg.get('top_k', 3))
    req_override = cfg.get('reserve_requirement', None)
    nd = int(cfg.get('round_price', 4))
    ncst = int(cfg.get('round_cost', 2))
    nfl = int(cfg.get('round_flow', 4))

    case = load_case(net)
    M = prepare(case)
    fb, tb = M['fb'], M['tb']
    tgt = [i for i in range(len(fb))
           if (fb[i] == tf and tb[i] == tt) or (fb[i] == tt and tb[i] == tf)]
    if not tgt:
        raise SystemExit('ERROR: no in-service branch between bus %d and %d' % (tf, tt))

    rbase = M['rateA'].copy()
    rcf = rbase.copy()
    for i in tgt:
        rcf[i] = rcf[i] * factor

    base = M['solve'](rbase, req_override)
    cf = M['solve'](rcf, req_override)

    busid = M['busid']; nbus = M['nbus']

    def lmplist(res):
        return [{'bus': int(busid[i]),
                 'lmp_dollars_per_MWh': round(float(res['lmp'][i]), nd)}
                for i in range(nbus)]

    def binding(res):
        out = []
        for i in range(len(fb)):
            ra = res['rateA'][i]
            if ra > 0 and abs(res['f'][i]) / ra * 100.0 >= thr:
                out.append({'from': int(fb[i]), 'to': int(tb[i]),
                            'flow_MW': round(float(res['f'][i]), nfl),
                            'limit_MW': round(float(ra), nfl)})
        return out

    def block(res):
        return {'total_cost_dollars_per_hour': round(res['cost'], ncst),
                'lmp_by_bus': lmplist(res),
                'reserve_mcp_dollars_per_MWh': round(res['mcp'], nd),
                'binding_lines': binding(res)}

    delta = cf['lmp'] - base['lmp']
    order = sorted(range(nbus), key=lambda i: (float(delta[i]), int(busid[i])))
    drops = [{'bus': int(busid[i]),
              'base_lmp': round(float(base['lmp'][i]), nd),
              'cf_lmp': round(float(cf['lmp'][i]), nd),
              'delta': round(float(delta[i]), nd)} for i in order[:topk]]

    relieved = all(not (rcf[i] > 0 and abs(cf['f'][i]) / rcf[i] * 100.0 >= thr)
                   for i in tgt)

    report = {'base_case': block(base),
              'counterfactual': block(cf),
              'impact_analysis': {
                  'cost_reduction_dollars_per_hour': round(base['cost'] - cf['cost'], ncst),
                  'buses_with_largest_lmp_drop': drops,
                  'congestion_relieved': bool(relieved)}}

    with open(outp, 'w') as fh:
        json.dump(report, fh, indent=2)
    json.dump(report, sys.stdout)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
