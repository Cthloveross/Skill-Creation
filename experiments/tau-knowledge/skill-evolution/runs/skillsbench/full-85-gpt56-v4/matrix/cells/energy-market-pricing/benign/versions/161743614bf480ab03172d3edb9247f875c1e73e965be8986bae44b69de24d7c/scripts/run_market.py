#!/usr/bin/env python3
"""Read DC-OPF counterfactual configuration from stdin and create report.json.
Requires numpy and scipy (HiGHS via scipy.optimize.linprog).
"""
import json, sys, math, os, subprocess, importlib
from pathlib import Path

def load_numerical_backend():
    """Import the sparse LP backend, installing it to a disposable cache if needed."""
    try:
        import numpy as np
        from scipy.optimize import linprog
        from scipy import sparse
        return np, linprog, sparse
    except ModuleNotFoundError:
        cache = os.environ.get("DCOPF_PYTHON_DEPS", "/tmp/dcopf_market_python_deps")
        if cache not in sys.path: sys.path.insert(0, cache)
        try:
            import numpy as np
            from scipy.optimize import linprog
            from scipy import sparse
            return np, linprog, sparse
        except ModuleNotFoundError:
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--target", cache, "numpy", "scipy"], check=True, stdout=sys.stderr, stderr=sys.stderr)
            except (OSError, subprocess.CalledProcessError) as exc:
                raise RuntimeError("numpy/scipy are required and automatic installation failed: %s" % exc)
            if cache not in sys.path: sys.path.insert(0, cache)
            # A failed import is cached as None in sys.modules; remove it before
            # retrying after pip has populated the target directory.
            sys.modules.pop('numpy', None)
            sys.modules.pop('scipy', None)
            importlib.invalidate_caches()
            import numpy as np
            from scipy.optimize import linprog
            from scipy import sparse
            return np, linprog, sparse

np, linprog, sparse = load_numerical_backend()

EPS = 1e-8

def keynorm(k):
    return ''.join(c for c in str(k).lower() if c.isalnum())

def get(obj, *names, default=None):
    wanted = {keynorm(x) for x in names}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if keynorm(k) in wanted:
                return v
    return default

def number(v):
    if isinstance(v, (int, float)) and math.isfinite(float(v)):
        return float(v)
    if isinstance(v, str):
        return float(v)
    if isinstance(v, dict):
        for k in ('mw', 'value', 'requirement', 'system_mw', 'amount'):
            x = get(v, k)
            if x is not None:
                return number(x)
    raise ValueError('expected a finite numeric value')

def rows(data, name):
    x = get(data, name)
    if not isinstance(x, list):
        raise ValueError('network is missing array '+name)
    return x

def reserve_requirement(data, cfg):
    x = get(cfg, 'reserve_requirement', 'spinning_reserve_requirement')
    if x is None:
        x = get(data, 'reserve_requirement', 'spinning_reserve_requirement',
                'reserveRequirement', 'spinningReserveRequirement')
    if x is None:
        r = get(data, 'reserve', 'reserves', 'spinning_reserve')
        x = get(r, 'requirement', 'requirement_mw', 'system_requirement') if isinstance(r, dict) else None
    return 0.0 if x is None else number(x)

def vector_spec(x, n, ids, label, default):
    """Interpret a scalar, positional vector, or ID-keyed mapping."""
    if x is None:
        return np.full(n, default, dtype=float)
    if isinstance(x, (int, float, bool)):
        return np.full(n, float(x), dtype=float)
    if isinstance(x, dict):
        out = np.full(n, default, dtype=float)
        for i, ident in enumerate(ids):
            v = x.get(str(ident), x.get(ident, default))
            if isinstance(v, dict):
                v = get(v, 'cost', 'offer', 'value', 'eligible', default=default)
            out[i] = float(v)
        return out
    if isinstance(x, list):
        if len(x) != n:
            raise ValueError('%s must have one entry per generator' % label)
        out = []
        for v in x:
            if isinstance(v, dict):
                v = get(v, 'cost', 'offer', 'value', 'eligible', default=default)
            out.append(float(v))
        return np.array(out)
    raise ValueError('unsupported '+label+' representation')

def reserve_vectors(data, cfg, ngen):
    offer = get(cfg, 'reserve_offers', 'reserve_offer', 'reserve_costs', 'reserve_cost')
    elig = get(cfg, 'reserve_eligible')
    if offer is None:
        offer = get(data, 'reserve_offers', 'reserve_offer', 'reserve_costs', 'reserve_cost',
                    'spinning_reserve_cost')
    if elig is None:
        elig = get(data, 'reserve_eligible', 'spinning_reserve_eligible')
    block = get(data, 'reserve', 'reserves', 'spinning_reserve')
    if isinstance(block, dict):
        if offer is None: offer = get(block, 'offers', 'offer', 'costs', 'cost')
        if elig is None: elig = get(block, 'eligible', 'eligibility')
    cap = get(cfg, 'reserve_capacity', 'spinning_reserve_capacity')
    if cap is None:
        cap = get(data, 'reserve_capacity', 'spinning_reserve_capacity')
    if cap is None and isinstance(block, dict):
        cap = get(block, 'capacity', 'capacities', 'max_capacity')
    ids = list(range(1, ngen + 1))
    return (vector_spec(offer, ngen, ids, 'reserve offers', 0.0),
            vector_spec(elig, ngen, ids, 'reserve eligibility', 1.0) > 0.5,
            vector_spec(cap, ngen, ids, 'reserve capacity', float('inf')))

def poly_value(coef, p):
    return sum(float(a) * p ** (len(coef)-1-i) for i, a in enumerate(coef))

def pwl_cost(row, pmin, pmax, pieces):
    model = int(round(float(row[0])))
    if model == 2:
        ncost = int(round(float(row[3])))
        coef = [float(x) for x in row[4:4+ncost]]
        if len(coef) != ncost or ncost < 1:
            raise ValueError('invalid polynomial gencost row')
        # Exact derivative sampled over short intervals is a convex LP approximation.
        nodes = np.linspace(pmin, pmax, pieces + 1)
        vals = [poly_value(coef, float(x)) for x in nodes]
        slopes = np.diff(vals) / np.diff(nodes) if pmax > pmin else np.array([])
        if len(slopes) > 1 and np.min(np.diff(slopes)) < -1e-7:
            raise ValueError('nonconvex polynomial cost is unsupported by DC LP')
        return nodes, slopes, float(vals[0]), lambda p: poly_value(coef, p)
    if model == 1:
        ncost = int(round(float(row[3])))
        raw = [float(x) for x in row[4:4+2*ncost]]
        if ncost < 2 or len(raw) != 2*ncost:
            raise ValueError('invalid piecewise-linear gencost row')
        pts = sorted((raw[2*i], raw[2*i+1]) for i in range(ncost))
        xs = [pmin] + [x for x, _ in pts if pmin < x < pmax] + [pmax]
        xs = sorted(set(xs))
        def val(p):
            if p < pts[0][0]-EPS or p > pts[-1][0]+EPS:
                raise ValueError('generator bounds lie outside MODEL=1 cost curve')
            for (x0,y0),(x1,y1) in zip(pts,pts[1:]):
                if x0-EPS <= p <= x1+EPS:
                    return y0 + (y1-y0)*(p-x0)/(x1-x0)
            return pts[-1][1]
        slopes = np.diff([val(x) for x in xs]) / np.diff(xs) if len(xs)>1 else np.array([])
        if len(slopes)>1 and np.min(np.diff(slopes)) < -1e-7:
            raise ValueError('nonconvex MODEL=1 cost is unsupported by DC LP')
        return np.array(xs), slopes, val(pmin), val
    raise ValueError('unsupported gencost MODEL %s' % model)

def solve(data, cfg, multiplier=1.0):
    bus, gen, branch, costs = rows(data,'bus'), rows(data,'gen'), rows(data,'branch'), rows(data,'gencost')
    nb, ng = len(bus), len(gen)
    if len(costs) < ng: raise ValueError('gencost has fewer active-cost rows than generators')
    base = number(get(data, 'baseMVA', 'base_mva'))
    bid = [int(round(float(r[0]))) for r in bus]
    if len(set(bid)) != nb: raise ValueError('duplicate bus identifiers')
    bmap = {v:i for i,v in enumerate(bid)}
    pd = np.array([float(r[2]) for r in bus])
    ref = next((i for i,r in enumerate(bus) if int(round(float(r[1]))) == 3), None)
    if ref is None: raise ValueError('no MATPOWER reference bus (BUS_TYPE=3)')
    active = np.array([len(r)>8 and float(r[7]) > 0 for r in gen])
    gbus = []
    pmin = np.zeros(ng); pmax=np.zeros(ng)
    for k,r in enumerate(gen):
        if int(round(float(r[0]))) not in bmap: raise ValueError('generator references unknown bus')
        gbus.append(bmap[int(round(float(r[0])))])
        if active[k]:
            pmax[k],pmin[k] = float(r[8]),float(r[9])
            if pmax[k] < pmin[k]-EPS: raise ValueError('generator PMAX < PMIN')
    req = reserve_requirement(data,cfg)
    if req < -EPS: raise ValueError('reserve requirement cannot be negative')
    roffer, eligible, reserve_cap = reserve_vectors(data,cfg,ng)
    if np.any(reserve_cap < -EPS): raise ValueError('reserve capacity cannot be negative')
    eligible &= active
    pieces = max(2, int(cfg.get('segments',48)))
    # energy segment columns, then reserve columns, then all non-reference angles
    qstart=[]; qwidth=[]; qcost=[]; basep=np.zeros(ng); costfun=[]; cconst=0.; col=0
    for k in range(ng):
        qstart.append(col)
        if active[k] and pmax[k] > pmin[k]+EPS:
            nodes, slopes, c0, fn = pwl_cost(costs[k],pmin[k],pmax[k],pieces)
            widths=np.diff(nodes); qwidth.extend(widths.tolist()); qcost.extend(slopes.tolist()); col += len(widths)
            basep[k]=pmin[k]; cconst += c0; costfun.append(fn)
        else:
            # Still validate declared cost row at its fixed output when online.
            if active[k]:
                _,_,c0,fn=pwl_cost(costs[k],pmin[k],pmax[k],pieces); cconst += c0; costfun.append(fn)
            else: costfun.append(lambda p: 0.0)
    nq=col; rstart=nq; tstart=nq+ng
    angle_col={i:tstart+(i if i < ref else i-1) for i in range(nb) if i != ref}
    nvar=tstart+nb-1
    c=np.zeros(nvar); c[:nq]=qcost; c[rstart:rstart+ng]=roffer
    bounds=[(0.0,w) for w in qwidth] + [(0.0, min(pmax[k]-pmin[k], reserve_cap[k]) if eligible[k] else 0.0) for k in range(ng)] + [(None,None)]*(nb-1)
    # Sparse equality: generation increments - C*B*theta = load - C*B*shift.
    er=[]; ec=[]; ev=[]; rhs=pd.copy()
    for k in range(ng):
        for j in range(qstart[k], qstart[k+1] if k+1<ng else nq): er.append(gbus[k]); ec.append(j); ev.append(1.)
        rhs[gbus[k]] -= basep[k]
    lineinfo=[]
    for li,r in enumerate(branch):
        if len(r)<11 or float(r[10]) <= 0: continue
        f,t=int(round(float(r[0]))),int(round(float(r[1])))
        if f not in bmap or t not in bmap: raise ValueError('branch references unknown bus')
        x=float(r[3]); tap=float(r[8]) if len(r)>8 else 0.; tap=1. if abs(tap)<EPS else tap
        if abs(x*tap)<EPS: raise ValueError('zero DC branch reactance')
        shift=math.radians(float(r[9])) if len(r)>9 else 0.
        rate=float(r[5]) if len(r)>5 else 0.
        i,j=bmap[f],bmap[t]; beta=base/(x*tap)
        # In row i, subtract f_ij; in row j, subtract f_ji=-f_ij.
        # Each nodal equation therefore contains angles from *both* ends.
        if i != ref:
            er.append(i); ec.append(angle_col[i]); ev.append(-beta)
        if j != ref:
            er.append(i); ec.append(angle_col[j]); ev.append(beta)
        if i != ref:
            er.append(j); ec.append(angle_col[i]); ev.append(beta)
        if j != ref:
            er.append(j); ec.append(angle_col[j]); ev.append(-beta)
        rhs[i] -= beta*shift
        rhs[j] += beta*shift
        lineinfo.append((li,i,j,beta,shift,rate,r))
    Aeq=sparse.coo_matrix((ev,(er,ec)),shape=(nb,nvar)).tocsr()
    # Inequalities: thermal, stated angular constraints, capacity coupling, reserve requirement.
    ir=[]; ic=[]; iv=[]; ub=[]; rr=0
    def theta_terms(row, i, j, scale):
        if i != ref: ir.append(row); ic.append(angle_col[i]); iv.append(scale)
        if j != ref: ir.append(row); ic.append(angle_col[j]); iv.append(-scale)
    target=[]
    tf,tt=int(cfg.get('target_from_bus',64)),int(cfg.get('target_to_bus',1501))
    for li,i,j,beta,shift,rate,raw in lineinfo:
        is_target={bid[i],bid[j]} == {tf,tt}
        actual_rate=rate*(multiplier if is_target else 1.0)
        if is_target: target.append(li)
        if actual_rate > 0:
            theta_terms(rr,i,j,beta); ub.append(actual_rate+beta*shift); rr+=1
            theta_terms(rr,i,j,-beta); ub.append(actual_rate-beta*shift); rr+=1
        if len(raw)>12:
            amin,amax=math.radians(float(raw[11])),math.radians(float(raw[12]))
            if math.isfinite(amax): theta_terms(rr,i,j,1.); ub.append(amax); rr+=1
            if math.isfinite(amin): theta_terms(rr,i,j,-1.); ub.append(-amin); rr+=1
    if not target: raise ValueError('no in-service branch connects target buses %s and %s' % (tf,tt))
    for k in range(ng):
        for j in range(qstart[k], qstart[k+1] if k+1<ng else nq): ir.append(rr); ic.append(j); iv.append(1.)
        ir.append(rr); ic.append(rstart+k); iv.append(1.); ub.append(pmax[k]-pmin[k]); rr+=1
    for k in range(ng): ir.append(rr); ic.append(rstart+k); iv.append(-1.)
    ub.append(-req); rr+=1
    Aub=sparse.coo_matrix((iv,(ir,ic)),shape=(rr,nvar)).tocsr()
    ans=linprog(c, A_ub=Aub,b_ub=np.array(ub),A_eq=Aeq,b_eq=rhs,bounds=bounds,method='highs')
    if not ans.success: raise RuntimeError('DC-OPF failed: '+ans.message)
    z=ans.x; pg=basep.copy()
    for k in range(ng): pg[k]+=sum(z[qstart[k]:qstart[k+1] if k+1<ng else nq])
    reserve=z[rstart:rstart+ng]
    theta=np.zeros(nb)
    for i,cc in angle_col.items(): theta[i]=z[cc]
    flows=[]
    for li,i,j,beta,shift,rate,raw in lineinfo:
        fl=beta*(theta[i]-theta[j]-shift)
        actual=rate*(multiplier if {bid[i],bid[j]}=={tf,tt} else 1.0)
        flows.append((li,i,j,fl,actual))
    # Independent checks of the quantities actually reported.
    injection=np.zeros(nb)
    for k in range(ng): injection[gbus[k]] += pg[k]
    injection -= pd
    for _,i,j,fl,_, in flows: injection[i]-=fl; injection[j]+=fl
    maxbal=float(np.max(np.abs(injection)))
    cap=max([0.0]+[(pg[k]+reserve[k]-pmax[k]) for k in range(ng)])
    reserve_bound=max([0.0]+[reserve[k]-reserve_cap[k] for k in range(ng) if eligible[k]])
    overload=max([0.0]+[abs(fl)-lim for _,_,_,fl,lim in flows if lim>0])
    if maxbal>2e-5 or cap>2e-5 or reserve_bound>2e-5 or overload>2e-5 or reserve.sum()+2e-5<req:
        raise RuntimeError('post-solve validation failed (balance %.3g, coupling %.3g, reserve bound %.3g, overload %.3g)'%(maxbal,cap,reserve_bound,overload))
    exact=float(sum(costfun[k](float(pg[k])) for k in range(ng) if active[k]) + np.dot(roffer,reserve))
    lmp=np.asarray(ans.eqlin.marginals, dtype=float)
    # Final inequality is -sum(reserve) <= -requirement, so negate its RHS dual.
    mcp=max(0.0, float(-ans.ineqlin.marginals[-1])) if req>EPS else 0.0
    bindings=[{'from':int(bid[i]),'to':int(bid[j]),'flow_MW':float(fl),'limit_MW':float(lim)}
              for _,i,j,fl,lim in flows if lim>0 and abs(fl)>=.99*lim-EPS]
    modified_binding=any(li in target and lim>0 and abs(fl)>=.99*lim-EPS for li,i,j,fl,lim in flows)
    return {'total_cost_dollars_per_hour':exact,
            'lmp_by_bus':[{'bus':int(bid[i]),'lmp_dollars_per_MWh':float(lmp[i])} for i in range(nb)],
            'reserve_mcp_dollars_per_MWh':mcp,
            'binding_lines':bindings}, modified_binding

def main():
    cfg=json.load(sys.stdin) if not sys.stdin.isatty() else {}
    path=cfg.get('network_path','/root/network.json')
    with open(path,encoding='utf-8') as f: data=json.load(f)
    base,bbase=solve(data,cfg,1.0)
    cf,bcf=solve(data,cfg,float(cfg.get('rating_multiplier',1.2)))
    byb={x['bus']:x['lmp_dollars_per_MWh'] for x in base['lmp_by_bus']}
    byc={x['bus']:x['lmp_dollars_per_MWh'] for x in cf['lmp_by_bus']}
    drops=sorted(({'bus':b,'base_lmp':float(byb[b]),'cf_lmp':float(byc[b]),'delta':float(byc[b]-byb[b])} for b in byb), key=lambda x:(x['delta'],x['bus']))[:3]
    report={'base_case':base,'counterfactual':cf,'impact_analysis':{
        'cost_reduction_dollars_per_hour':float(base['total_cost_dollars_per_hour']-cf['total_cost_dollars_per_hour']),
        'buses_with_largest_lmp_drop':drops,
        'congestion_relieved':bool(not bcf)}}
    out=Path(cfg.get('output_path','report.json')); out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',encoding='utf-8') as f: json.dump(report,f,indent=2,allow_nan=False)
    print(json.dumps({'ok':True,'report_path':str(out)}))
if __name__=='__main__':
    try: main()
    except Exception as e:
        print(json.dumps({'ok':False,'error':str(e)})); sys.exit(2)
