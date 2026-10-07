#!/usr/bin/env python3
"""Read a MATPOWER JSON case, solve DC energy/reserve co-optimization, write report.

stdin: optional JSON object {network_path: str, report_path: str}
stdout: {ok: bool, report_path: str, validation: {...}} or {ok:false,error:str}
"""
import json
import math
import os
import sys
import subprocess
from typing import Any, Dict, List, Tuple

def ensure_solver_dependencies() -> None:
    """Install the public Python solver stack only when the runtime lacks it.

    The task runtime provides Python and pip and permits internet access.  Keeping
    this fallback here lets the package run in minimal containers without
    shipping platform-specific binary wheels.
    """
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
        import cvxpy  # noqa: F401
        import highspy  # noqa: F401
        return
    except ImportError:
        pass
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
        "--no-cache-dir", "numpy", "scipy", "cvxpy", "highspy",
    ], stdout=sys.stderr, stderr=sys.stderr)


ensure_solver_dependencies()
import numpy as np
import scipy.sparse as sp


REQ_NAMES = (
    "reserve_requirement_MW", "spinning_reserve_requirement_MW",
    "spinning_reserve_requirement", "reserve_requirement", "reserve_req",
)
PCT_NAMES = (
    "reserve_requirement_pct", "spinning_reserve_requirement_pct",
    "reserve_pct",
)


def number(x: Any, label: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(f"{label} must be numeric")
    ans = float(x)
    if not math.isfinite(ans):
        raise ValueError(f"{label} must be finite")
    return ans


def vector_or_scalar(value: Any, n: int, label: str, default: float) -> np.ndarray:
    if value is None:
        return np.full(n, default, dtype=float)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return np.full(n, float(value), dtype=float)
    if not isinstance(value, list) or len(value) != n:
        raise ValueError(f"{label} must be a scalar or a length-{n} list")
    return np.asarray([number(v, label) for v in value], dtype=float)


def reserve_container(case: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("reserve", "reserves"):
        value = case.get(key)
        if isinstance(value, dict):
            return value
    return {}


def find_requirement(case: Dict[str, Any], total_load: float) -> float:
    nested = reserve_container(case)
    for mapping in (case, nested):
        for key in REQ_NAMES:
            if key in mapping:
                req = number(mapping[key], key)
                if req < 0:
                    raise ValueError("reserve requirement cannot be negative")
                return req
        for key in PCT_NAMES:
            if key in mapping:
                pct = number(mapping[key], key)
                if pct < 0:
                    raise ValueError("reserve percentage cannot be negative")
                return total_load * pct / 100.0
    raise ValueError("missing system spinning-reserve requirement")


def first_present(maps: List[Dict[str, Any]], names: Tuple[str, ...]) -> Any:
    for mapping in maps:
        for name in names:
            if name in mapping:
                return mapping[name]
    return None


def polynomial(row: List[Any], generator_index: int) -> Tuple[float, float, float]:
    if len(row) < 5:
        raise ValueError(f"gencost row {generator_index + 1} is incomplete")
    if int(number(row[0], "gencost model")) != 2:
        raise ValueError(f"generator {generator_index + 1} uses unsupported non-polynomial cost")
    ncost = int(number(row[3], "gencost ncost"))
    if ncost < 1 or len(row) < 4 + ncost:
        raise ValueError(f"generator {generator_index + 1} has invalid polynomial cost")
    coeff = [number(v, "gencost coefficient") for v in row[4:4 + ncost]]
    degree = ncost - 1
    if degree > 2:
        raise ValueError(f"generator {generator_index + 1} has unsupported polynomial degree {degree}")
    if degree == 2:
        q, linear, constant = coeff
        if q < -1e-12:
            raise ValueError(f"generator {generator_index + 1} has nonconvex quadratic cost")
        return max(q, 0.0), linear, constant
    if degree == 1:
        return 0.0, coeff[0], coeff[1]
    return 0.0, 0.0, coeff[0]


def rounded(x: float) -> float:
    # Avoid JSON -0.0 while retaining substantially more precision than reporting needs.
    y = round(float(x), 6)
    return 0.0 if abs(y) < 0.0000005 else y


def solve(case: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, float]]:
    try:
        base = number(case["baseMVA"], "baseMVA")
        buses = case["bus"]
        gens = case["gen"]
        branches = case["branch"]
        costs = case["gencost"]
    except KeyError as exc:
        raise ValueError(f"missing required MATPOWER field {exc.args[0]}")
    if base <= 0 or not isinstance(buses, list) or not isinstance(gens, list) or not isinstance(branches, list):
        raise ValueError("invalid MATPOWER array data")
    if len(gens) != len(costs) or not buses:
        raise ValueError("gencost must have one row per generator and bus must be nonempty")

    bus_ids: List[Any] = []
    pd = []
    ref = None
    for i, row in enumerate(buses):
        if not isinstance(row, list) or len(row) < 3:
            raise ValueError(f"bus row {i + 1} is incomplete")
        bid = row[0]
        if bid in bus_ids:
            raise ValueError(f"duplicate bus identifier {bid}")
        bus_ids.append(bid)
        pd.append(number(row[2], "bus Pd"))
        if len(row) > 1 and int(number(row[1], "bus type")) == 3 and ref is None:
            ref = i
    bus_index = {bid: i for i, bid in enumerate(bus_ids)}
    if ref is None:
        raise ValueError("no MATPOWER reference bus (type 3) is present")
    pdv = np.asarray(pd, dtype=float)
    total_load = float(pdv.sum())
    requirement = find_requirement(case, total_load)

    ng = len(gens)
    online = np.zeros(ng, dtype=bool)
    gbus = np.empty(ng, dtype=int)
    pmin = np.zeros(ng)
    pmax = np.zeros(ng)
    polys: List[Tuple[float, float, float]] = []
    for i, row in enumerate(gens):
        if not isinstance(row, list) or len(row) < 10:
            raise ValueError(f"generator row {i + 1} is incomplete")
        if row[0] not in bus_index:
            raise ValueError(f"generator {i + 1} references unknown bus {row[0]}")
        gbus[i] = bus_index[row[0]]
        online[i] = number(row[7], "generator status") > 0
        pmax[i] = number(row[8], "PMAX")
        pmin[i] = number(row[9], "PMIN")
        if pmin[i] > pmax[i] + 1e-9:
            raise ValueError(f"generator {i + 1} has PMIN greater than PMAX")
        polys.append(polynomial(costs[i], i))
    active = np.where(online)[0]
    if not len(active):
        raise ValueError("there are no in-service generators")

    reserve_map = reserve_container(case)
    maps = [case, reserve_map]
    offer_all = vector_or_scalar(first_present(maps, ("reserve_cost_per_MW", "reserve_cost", "reserve_costs", "cost_per_MW", "cost")), ng, "reserve cost", 0.0)
    eligible_raw = first_present(maps, ("reserve_eligible", "reserve_eligibility"))
    eligible_all = vector_or_scalar(eligible_raw, ng, "reserve eligibility", 1.0) > 0.0
    cap_raw = first_present(maps, ("reserve_max_MW", "reserve_max", "reserve_capability_MW", "reserve_capacity"))
    reserve_cap_all = vector_or_scalar(cap_raw, ng, "reserve maximum", float("inf"))
    if np.any(reserve_cap_all < 0):
        raise ValueError("reserve maximum cannot be negative")

    fbus: List[int] = []
    tbus: List[int] = []
    susceptance: List[float] = []
    shift: List[float] = []
    rating: List[float] = []
    amin: List[float] = []
    amax: List[float] = []
    original_branch: List[int] = []
    for k, row in enumerate(branches):
        if not isinstance(row, list) or len(row) < 11:
            raise ValueError(f"branch row {k + 1} is incomplete")
        if number(row[10], "branch status") <= 0:
            continue
        if row[0] not in bus_index or row[1] not in bus_index:
            raise ValueError(f"branch {k + 1} references unknown bus")
        x = number(row[3], "branch reactance")
        if abs(x) < 1e-14:
            raise ValueError(f"branch {k + 1} has zero reactance, unsupported by DC model")
        tap_stored = number(row[8], "branch tap") if len(row) > 8 else 0.0
        tap = 1.0 if abs(tap_stored) < 1e-14 else tap_stored
        if abs(tap) < 1e-14:
            raise ValueError(f"branch {k + 1} has invalid tap")
        fbus.append(bus_index[row[0]])
        tbus.append(bus_index[row[1]])
        susceptance.append(base / (x * tap))
        shift.append(math.radians(number(row[9], "branch shift") if len(row) > 9 else 0.0))
        rating.append(number(row[5], "RATE_A") if len(row) > 5 else 0.0)
        amin.append(math.radians(number(row[11], "ANGMIN")) if len(row) > 11 else -math.inf)
        amax.append(math.radians(number(row[12], "ANGMAX")) if len(row) > 12 else math.inf)
        original_branch.append(k)
    if not fbus and abs(total_load) > 1e-9:
        raise ValueError("loaded network has no in-service branches")

    nb, na, nl = len(buses), len(active), len(fbus)
    fi = np.asarray(fbus, dtype=int)
    ti = np.asarray(tbus, dtype=int)
    b = np.asarray(susceptance, dtype=float)
    sh = np.asarray(shift, dtype=float)
    rate = np.asarray(rating, dtype=float)
    lowang = np.asarray(amin, dtype=float)
    highang = np.asarray(amax, dtype=float)
    # Generator-to-bus and oriented branch incidence matrices use explicit source IDs.
    G = sp.coo_matrix((np.ones(na), (gbus[active], np.arange(na))), shape=(nb, na)).tocsr()
    if nl:
        A = sp.coo_matrix((np.r_[np.ones(nl), -np.ones(nl)], (np.r_[fi, ti], np.r_[np.arange(nl), np.arange(nl)])), shape=(nb, nl)).tocsr()
    else:
        A = sp.csr_matrix((nb, 0))

    try:
        import cvxpy as cp
    except ImportError as exc:
        raise RuntimeError("CVXPY is required for this convex DC co-optimization") from exc

    pg = cp.Variable(na, name="Pg_MW")
    reserve = cp.Variable(na, name="R_MW")
    theta = cp.Variable(nb, name="theta_rad")
    flow = cp.multiply(b, theta[fi] - theta[ti] - sh) if nl else cp.Constant(np.zeros(0))
    constraints = [G @ pg - pdv == A @ flow, theta[ref] == 0,
                   pg >= pmin[active], pg <= pmax[active], reserve >= 0,
                   pg + reserve <= pmax[active], cp.sum(reserve) == requirement]
    local_cap = reserve_cap_all[active].copy()
    local_cap[~eligible_all[active]] = 0.0
    constraints.append(reserve <= local_cap)
    if nl:
        limited = rate > 0
        if np.any(limited):
            constraints += [flow[limited] <= rate[limited], flow[limited] >= -rate[limited]]
        finite_low = np.isfinite(lowang)
        finite_high = np.isfinite(highang)
        if np.any(finite_low):
            constraints.append(theta[fi[finite_low]] - theta[ti[finite_low]] >= lowang[finite_low])
        if np.any(finite_high):
            constraints.append(theta[fi[finite_high]] - theta[ti[finite_high]] <= highang[finite_high])

    quad = np.asarray([polys[i][0] for i in active])
    linear = np.asarray([polys[i][1] for i in active])
    constant = float(sum(polys[i][2] for i in active))
    objective = cp.sum(cp.multiply(quad, cp.square(pg))) + linear @ pg + constant + offer_all[active] @ reserve
    problem = cp.Problem(cp.Minimize(objective), constraints)
    solved = False
    errors: List[str] = []
    # HiGHS is substantially faster and more deterministic for the common
    # linear-cost dispatch.  Use a conic/QP method first only when a genuine
    # quadratic term is present.
    if np.all(np.abs(quad) <= 1e-14):
        solver_plan = (("HIGHS", {}), ("CLARABEL", {"tol_gap_abs": 1e-8, "tol_feas": 1e-8}),
                       ("OSQP", {"eps_abs": 1e-7, "eps_rel": 1e-7, "max_iter": 200000, "polishing": True}),
                       ("SCIPY", {}))
    else:
        solver_plan = (("CLARABEL", {"tol_gap_abs": 1e-8, "tol_feas": 1e-8}),
                       ("OSQP", {"eps_abs": 1e-7, "eps_rel": 1e-7, "max_iter": 200000, "polishing": True}),
                       ("HIGHS", {}), ("SCIPY", {}))
    for solver, kwargs in solver_plan:
        try:
            problem.solve(solver=solver, **kwargs)
            if problem.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE) and pg.value is not None:
                solved = True
                break
            errors.append(f"{solver}: {problem.status}")
        except Exception as exc:  # Try a different installed solver.
            errors.append(f"{solver}: {exc}")
    if not solved:
        raise RuntimeError("DC optimization did not produce an optimum (" + "; ".join(errors) + ")")

    pg_a = np.asarray(pg.value, dtype=float).reshape(-1)
    r_a = np.asarray(reserve.value, dtype=float).reshape(-1)
    th = np.asarray(theta.value, dtype=float).reshape(-1)
    fl = b * (th[fi] - th[ti] - sh) if nl else np.zeros(0)
    # Independent numerical validation in physical MW units.
    residual = G.dot(pg_a) - pdv - A.dot(fl)
    flow_violation = np.maximum(np.abs(fl) - np.maximum(rate, 0.0), 0.0) if nl else np.zeros(0)
    angle_diff = th[fi] - th[ti] if nl else np.zeros(0)
    angle_violation = np.maximum(lowang - angle_diff, 0.0) + np.maximum(angle_diff - highang, 0.0) if nl else np.zeros(0)
    bound_violation = max(float(np.max(pmin[active] - pg_a)), float(np.max(pg_a - pmax[active])), 0.0)
    coupling_violation = max(float(np.max(pg_a + r_a - pmax[active])), 0.0)
    reserve_violation = max(requirement - float(r_a.sum()), 0.0)
    reserve_cap_violation = max(float(np.max(r_a - local_cap)), 0.0)
    validation = {
        "max_bus_balance_MW": float(np.max(np.abs(residual))) if nb else 0.0,
        "max_line_limit_violation_MW": float(np.max(flow_violation)) if nl else 0.0,
        "max_angle_limit_violation_rad": float(np.max(angle_violation)) if nl else 0.0,
        "max_generator_bound_violation_MW": bound_violation,
        "max_capacity_coupling_violation_MW": coupling_violation,
        "reserve_shortfall_MW": reserve_violation,
        "max_reserve_cap_violation_MW": reserve_cap_violation,
    }
    if max(validation.values()) > 2e-4:
        raise RuntimeError("post-solve validation failed: " + json.dumps(validation, sort_keys=True))

    pg_all = np.zeros(ng)
    r_all = np.zeros(ng)
    pg_all[active] = pg_a
    r_all[active] = r_a
    energy_cost = float(np.sum(np.asarray([polys[i][0] for i in active]) * pg_a * pg_a + np.asarray([polys[i][1] for i in active]) * pg_a + np.asarray([polys[i][2] for i in active])))
    total_cost = energy_cost + float(offer_all[active] @ r_a)
    rows = []
    for i, row in enumerate(gens):
        rows.append({"id": i + 1, "bus": row[0], "output_MW": rounded(pg_all[i]),
                     "reserve_MW": rounded(r_all[i]), "pmax_MW": rounded(pmax[i])})
    line_rows = []
    for j, source_index in enumerate(original_branch):
        if rate[j] > 0:
            line_rows.append((abs(float(fl[j])) / rate[j] * 100.0, branches[source_index][0], branches[source_index][1], source_index))
    line_rows.sort(key=lambda x: (-x[0], str(x[1]), str(x[2]), x[3]))
    loaded = [{"from": fr, "to": to, "loading_pct": rounded(pct)} for pct, fr, to, _ in line_rows[:3]]
    margin = float(np.sum(pmax[active]) - np.sum(pg_a) - np.sum(r_a))
    report = {
        "generator_dispatch": rows,
        "totals": {"cost_dollars_per_hour": rounded(total_cost), "load_MW": rounded(total_load),
                   "generation_MW": rounded(float(pg_a.sum())), "reserve_MW": rounded(float(r_a.sum()))},
        "most_loaded_lines": loaded,
        "operating_margin_MW": rounded(margin),
    }
    validation["objective_reconstructed_dollars_per_hour"] = total_cost
    validation["solver_objective_dollars_per_hour"] = float(problem.value)
    validation["objective_difference_dollars_per_hour"] = abs(total_cost - float(problem.value))
    return report, validation


def main() -> int:
    try:
        text = sys.stdin.read().strip()
        config = json.loads(text) if text else {}
        if not isinstance(config, dict):
            raise ValueError("stdin configuration must be a JSON object")
        network_path = config.get("network_path", "/root/network.json")
        report_path = config.get("report_path", "/root/report.json")
        with open(network_path, "r", encoding="utf-8") as handle:
            case = json.load(handle)
        if not isinstance(case, dict):
            raise ValueError("network JSON root must be an object")
        report, validation = solve(case)
        parent = os.path.dirname(os.path.abspath(report_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
            handle.write("\n")
        print(json.dumps({"ok": True, "report_path": report_path, "validation": validation}, allow_nan=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
