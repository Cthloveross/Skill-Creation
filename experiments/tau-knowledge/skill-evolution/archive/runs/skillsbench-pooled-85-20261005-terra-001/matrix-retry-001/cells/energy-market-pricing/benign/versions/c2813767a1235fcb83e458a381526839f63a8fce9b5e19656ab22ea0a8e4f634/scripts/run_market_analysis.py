#!/usr/bin/env python3
"""Read a JSON request from stdin, write a DC-OPF counterfactual report, emit JSON."""
import json
import math
import os
import sys
from collections import deque

import numpy as np
from scipy import sparse

try:
    import cvxpy as cp
except ImportError as exc:
    raise SystemExit("cvxpy is required for this DC-OPF Skill: %s" % exc)

TARGET_FROM = 64
TARGET_TO = 1501


def norm_key(value):
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def number(value, label):
    if isinstance(value, bool) or value is None:
        raise ValueError("%s must be numeric" % label)
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s must be numeric" % label)
    if not math.isfinite(out):
        raise ValueError("%s must be finite" % label)
    return out


def rows(case, key):
    if key not in case or not isinstance(case[key], list):
        raise ValueError("MATPOWER case is missing list field %r" % key)
    if not case[key]:
        raise ValueError("MATPOWER case field %r is empty" % key)
    return case[key]


def field(row, index, names, default=None):
    """Obtain either a named-record value or a MATPOWER positional value."""
    if isinstance(row, dict):
        lookup = {norm_key(k): v for k, v in row.items()}
        for name in names:
            if norm_key(name) in lookup:
                return lookup[norm_key(name)]
        if default is not None:
            return default
        raise ValueError("record is missing one of %s" % names)
    if not isinstance(row, (list, tuple)) or len(row) <= index:
        if default is not None:
            return default
        raise ValueError("row is missing column %d" % index)
    return row[index]


def scalar_from(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, dict):
        lookup = {norm_key(k): v for k, v in value.items()}
        for key in ("mw", "value", "requirement", "amount"):
            if key in lookup and isinstance(lookup[key], (int, float)):
                return float(lookup[key])
    return None


def find_named(obj, names, depth=0):
    """Find the first numeric value with one of the requested normalized keys."""
    if depth > 5:
        return None
    wanted = {norm_key(x) for x in names}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if norm_key(key) in wanted:
                candidate = scalar_from(value)
                if candidate is not None:
                    return candidate
        # Restrict recursive descent to mappings/lists: this avoids inspecting text fields.
        for value in obj.values():
            if isinstance(value, (dict, list)):
                found = find_named(value, names, depth + 1)
                if found is not None:
                    return found
    elif isinstance(obj, list):
        for value in obj:
            if isinstance(value, (dict, list)):
                found = find_named(value, names, depth + 1)
                if found is not None:
                    return found
    return None


def find_raw_named(obj, names, depth=0):
    """Find an arbitrary (possibly vector) named value."""
    if depth > 5:
        return None
    wanted = {norm_key(x) for x in names}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if norm_key(key) in wanted:
                return value
        for value in obj.values():
            if isinstance(value, (dict, list)):
                found = find_raw_named(value, names, depth + 1)
                if found is not None:
                    return found
    elif isinstance(obj, list):
        for value in obj:
            if isinstance(value, (dict, list)):
                found = find_raw_named(value, names, depth + 1)
                if found is not None:
                    return found
    return None


def vector(value, n, label, default=None, boolean=False):
    """Convert a scalar, list, or index-keyed mapping to a generator vector."""
    if value is None:
        if default is None:
            raise ValueError("missing %s" % label)
        return np.full(n, default, dtype=float)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = np.full(n, float(value), dtype=float)
    elif isinstance(value, list):
        if len(value) != n:
            raise ValueError("%s must have one entry per generator (%d)" % (label, n))
        result = np.asarray([number(x, label) for x in value], dtype=float)
    elif isinstance(value, dict):
        # Accept an unambiguous 0-based or 1-based numerical mapping.
        try:
            keys = {int(k) for k in value}
        except (TypeError, ValueError):
            raise ValueError("%s mapping keys must be generator indices" % label)
        if keys == set(range(n)):
            result = np.asarray([number(value[str(i)] if str(i) in value else value[i], label)
                                 for i in range(n)], dtype=float)
        elif keys == set(range(1, n + 1)):
            result = np.asarray([number(value[str(i)] if str(i) in value else value[i], label)
                                 for i in range(1, n + 1)], dtype=float)
        else:
            raise ValueError("%s mapping must contain all 0-based or all 1-based generator indices" % label)
    else:
        raise ValueError("%s must be scalar, vector, or generator-indexed mapping" % label)
    if not np.all(np.isfinite(result)):
        raise ValueError("%s contains a non-finite value" % label)
    if boolean:
        return (result != 0.0).astype(float)
    return result


def parse_cost(row, generator_number):
    if isinstance(row, dict):
        model = int(number(field(row, 0, ("model",), 2), "gencost model"))
        ncost = int(number(field(row, 3, ("ncost", "n_cost"), 3), "gencost ncost"))
        raw = field(row, 4, ("cost", "coefficients", "coeffs"), None)
        if raw is None:
            # Named polynomial records are also accepted.
            lookup = {norm_key(k): v for k, v in row.items()}
            raw = [lookup[x] for x in ("c2", "c1", "c0") if x in lookup]
        coeff = list(raw) if isinstance(raw, (list, tuple)) else []
    else:
        model = int(number(field(row, 0, ("model",)), "gencost model"))
        ncost = int(number(field(row, 3, ("ncost",)), "gencost ncost"))
        coeff = list(row[4:4 + ncost])
    if model != 2:
        raise ValueError("generator %d uses unsupported gencost model %d; only polynomial model 2 is supported" % (generator_number, model))
    if ncost < 1 or ncost > 3 or len(coeff) != ncost:
        raise ValueError("generator %d must have a constant, linear, or quadratic polynomial cost" % generator_number)
    coeff = [number(x, "gencost coefficient") for x in coeff]
    coeff = [0.0] * (3 - len(coeff)) + coeff
    c2, c1, c0 = coeff
    if c2 < -1e-12:
        raise ValueError("generator %d has non-convex quadratic energy cost" % generator_number)
    return max(c2, 0.0), c1, c0


def parse_case(case, reserve_override=None):
    if not isinstance(case, dict):
        raise ValueError("network JSON must contain a top-level object")
    base = number(case.get("baseMVA", case.get("base_mva")), "baseMVA")
    if base <= 0:
        raise ValueError("baseMVA must be positive")

    bus_rows = rows(case, "bus")
    bus_ids = [int(number(field(r, 0, ("bus_i", "bus", "id")), "bus ID")) for r in bus_rows]
    if len(set(bus_ids)) != len(bus_ids):
        raise ValueError("bus identifiers must be unique")
    bus_index = {bus: i for i, bus in enumerate(bus_ids)}
    demand = np.asarray([number(field(r, 2, ("pd", "p_d", "demand"), 0.0), "Pd") for r in bus_rows])
    btype = np.asarray([int(number(field(r, 1, ("bus_type", "type"), 1), "bus type")) for r in bus_rows])

    gen_rows = rows(case, "gen")
    ng = len(gen_rows)
    gen_bus_id = [int(number(field(r, 0, ("gen_bus", "bus")), "generator bus")) for r in gen_rows]
    if any(b not in bus_index for b in gen_bus_id):
        raise ValueError("a generator references an unknown bus")
    gen_bus = np.asarray([bus_index[b] for b in gen_bus_id], dtype=int)
    pmax = np.asarray([number(field(r, 8, ("pmax", "p_max")), "Pmax") for r in gen_rows])
    pmin = np.asarray([number(field(r, 9, ("pmin", "p_min")), "Pmin") for r in gen_rows])
    status = np.asarray([number(field(r, 7, ("gen_status", "status"), 1), "generator status") != 0 for r in gen_rows])
    if np.any(pmax < pmin):
        raise ValueError("a generator has Pmax below Pmin")
    pmin = pmin.copy()
    pmax = pmax.copy()
    pmin[~status] = 0.0
    pmax[~status] = 0.0

    cost_rows = rows(case, "gencost")
    if len(cost_rows) < ng:
        raise ValueError("gencost has fewer rows than gen")
    costs = [parse_cost(cost_rows[i], i + 1) for i in range(ng)]
    c2 = np.asarray([x[0] for x in costs])
    c1 = np.asarray([x[1] for x in costs])
    c0 = np.asarray([x[2] for x in costs])

    branch_rows = rows(case, "branch")
    br_from_id = [int(number(field(r, 0, ("f_bus", "from", "from_bus")), "from bus")) for r in branch_rows]
    br_to_id = [int(number(field(r, 1, ("t_bus", "to", "to_bus")), "to bus")) for r in branch_rows]
    if any(x not in bus_index for x in br_from_id + br_to_id):
        raise ValueError("a branch references an unknown bus")
    br_from = np.asarray([bus_index[x] for x in br_from_id], dtype=int)
    br_to = np.asarray([bus_index[x] for x in br_to_id], dtype=int)
    x = np.asarray([number(field(r, 3, ("br_x", "x", "reactance")), "branch reactance") for r in branch_rows])
    rate = np.asarray([number(field(r, 5, ("rate_a", "ratea", "rating"), 0.0), "RATE_A") for r in branch_rows])
    tap = np.asarray([number(field(r, 8, ("tap", "tap_ratio"), 0.0), "tap") for r in branch_rows])
    tap[np.abs(tap) < 1e-14] = 1.0
    shift = np.deg2rad(np.asarray([number(field(r, 9, ("shift", "angle_shift"), 0.0), "SHIFT") for r in branch_rows]))
    br_status = np.asarray([number(field(r, 10, ("br_status", "status"), 1), "branch status") != 0 for r in branch_rows])
    amin = np.asarray([number(field(r, 11, ("angmin", "angle_min"), -360.0), "ANGMIN") for r in branch_rows])
    amax = np.asarray([number(field(r, 12, ("angmax", "angle_max"), 360.0), "ANGMAX") for r in branch_rows])
    active = np.flatnonzero(br_status)
    if np.any(np.abs(x[active]) < 1e-12):
        raise ValueError("an in-service branch has zero reactance, unsupported by DC-OPF")
    if np.any(rate < 0):
        raise ValueError("RATE_A must be nonnegative")

    requirement = reserve_override
    if requirement is None:
        requirement = find_named(case, (
            "reserve_requirement_mw", "reserve_requirement", "spinning_reserve_requirement_mw",
            "spinning_reserve_requirement", "reserve_req", "spinning_reserve_req"))
    if requirement is None:
        raise ValueError("no spinning-reserve requirement found; provide reserve_requirement_mw in the request")
    requirement = number(requirement, "reserve requirement")
    if requirement < 0:
        raise ValueError("reserve requirement must be nonnegative")
    reserve_offer = vector(find_raw_named(case, ("reserve_cost", "reserve_costs", "reserve_offer", "reserve_offers")), ng, "reserve offer", default=0.0)
    eligible = vector(find_raw_named(case, ("reserve_eligible", "spinning_reserve_eligible")), ng, "reserve eligibility", default=1.0, boolean=True)
    eligible *= status.astype(float)
    if np.any(reserve_offer < 0):
        raise ValueError("reserve offers must be nonnegative for this convex market model")

    target = [i for i in active if {br_from_id[i], br_to_id[i]} == {TARGET_FROM, TARGET_TO}]
    if len(target) != 1:
        raise ValueError("expected exactly one in-service branch connecting buses %d and %d; found %d" % (TARGET_FROM, TARGET_TO, len(target)))
    target = target[0]
    if rate[target] <= 0:
        raise ValueError("the target branch has no positive RATE_A to relax")

    return {
        "base": base, "bus_ids": bus_ids, "bus_index": bus_index, "demand": demand, "btype": btype,
        "gen_bus": gen_bus, "pmin": pmin, "pmax": pmax, "c2": c2, "c1": c1, "c0": c0,
        "reserve_offer": reserve_offer, "eligible": eligible, "requirement": requirement,
        "br_from": br_from, "br_to": br_to, "br_from_id": br_from_id, "br_to_id": br_to_id,
        "x": x, "rate": rate, "tap": tap, "shift": shift, "active": active,
        "amin": amin, "amax": amax, "target": target,
    }


def reference_indices(model):
    """Use declared slack buses and add a gauge only for disconnected islands."""
    n = len(model["bus_ids"])
    adjacency = [[] for _ in range(n)]
    for line in model["active"]:
        i, j = model["br_from"][line], model["br_to"][line]
        adjacency[i].append(j)
        adjacency[j].append(i)
    declared = set(np.flatnonzero(model["btype"] == 3).tolist())
    refs = []
    seen = set()
    for start in range(n):
        if start in seen:
            continue
        component, queue = [], deque([start])
        seen.add(start)
        while queue:
            u = queue.popleft()
            component.append(u)
            for v in adjacency[u]:
                if v not in seen:
                    seen.add(v)
                    queue.append(v)
        local = sorted(declared.intersection(component))
        refs.append(local[0] if local else min(component))
    return np.asarray(refs, dtype=int)


def solve(model, rates):
    nbus = len(model["bus_ids"])
    ngen = len(model["gen_bus"])
    active = model["active"]
    nline = len(active)
    f = model["br_from"][active]
    t = model["br_to"][active]
    susceptance = model["base"] / (model["x"][active] * model["tap"][active])
    shift = model["shift"][active]

    # Sparse G maps generator injections to buses; A maps signed line flows to buses.
    G = sparse.csr_matrix((np.ones(ngen), (model["gen_bus"], np.arange(ngen))), shape=(nbus, ngen))
    A = sparse.csr_matrix((np.r_[np.ones(nline), -np.ones(nline)],
                           (np.r_[f, t], np.r_[np.arange(nline), np.arange(nline)])),
                          shape=(nbus, nline))
    pg = cp.Variable(ngen, name="Pg_MW")
    reserve = cp.Variable(ngen, nonneg=True, name="reserve_MW")
    theta = cp.Variable(nbus, name="theta_rad")
    flow = cp.multiply(susceptance, theta[f] - theta[t] - shift)

    balance = G @ pg - model["demand"] - A @ flow == 0
    reserve_requirement = cp.sum(reserve) >= model["requirement"]
    constraints = [balance, reserve_requirement, pg >= model["pmin"], pg <= model["pmax"],
                   reserve <= cp.multiply(model["eligible"], model["pmax"]),
                   pg + reserve <= model["pmax"], theta[reference_indices(model)] == 0]
    rated = rates[active] > 0
    if np.any(rated):
        constraints += [flow[rated] <= rates[active][rated], flow[rated] >= -rates[active][rated]]
    # MATPOWER's +/-360 degree defaults mean no angle constraint.
    amin = model["amin"][active]
    amax = model["amax"][active]
    has_min = amin > -360.0 + 1e-10
    has_max = amax < 360.0 - 1e-10
    angle_diff = theta[f] - theta[t]
    if np.any(has_min):
        constraints.append(angle_diff[has_min] >= np.deg2rad(amin[has_min]))
    if np.any(has_max):
        constraints.append(angle_diff[has_max] <= np.deg2rad(amax[has_max]))

    objective = cp.sum(cp.multiply(model["c2"], cp.square(pg))) + model["c1"] @ pg + float(np.sum(model["c0"])) + model["reserve_offer"] @ reserve
    problem = cp.Problem(cp.Minimize(objective), constraints)
    installed = set(cp.installed_solvers())
    failures = []
    attempts = []
    if "OSQP" in installed:
        attempts.append((cp.OSQP, {"eps_abs": 1e-7, "eps_rel": 1e-7, "max_iter": 300000, "polishing": True}))
    if "CLARABEL" in installed:
        attempts.append((cp.CLARABEL, {"tol_gap_abs": 1e-8, "tol_feas": 1e-8, "tol_gap_rel": 1e-8, "max_iter": 1000}))
    if not attempts:
        raise RuntimeError("no supported cvxpy solver found; install OSQP or CLARABEL")
    for solver, options in attempts:
        try:
            problem.solve(solver=solver, **options)
            if problem.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE) and pg.value is not None:
                break
            failures.append("%s: %s" % (solver, problem.status))
        except Exception as exc:
            failures.append("%s: %s" % (solver, exc))
    else:
        raise RuntimeError("DC-OPF did not solve to optimality (" + "; ".join(failures) + ")")

    pg_v = np.asarray(pg.value, dtype=float).reshape(-1)
    r_v = np.asarray(reserve.value, dtype=float).reshape(-1)
    theta_v = np.asarray(theta.value, dtype=float).reshape(-1)
    active_flow = susceptance * (theta_v[f] - theta_v[t] - shift)
    all_flow = np.zeros(len(model["br_from"]), dtype=float)
    all_flow[active] = active_flow
    lmp = -np.asarray(balance.dual_value, dtype=float).reshape(-1)
    reserve_mcp = float(np.asarray(reserve_requirement.dual_value).reshape(()))
    reconstructed = float(np.dot(model["c2"], pg_v * pg_v) + np.dot(model["c1"], pg_v) + np.sum(model["c0"]) + np.dot(model["reserve_offer"], r_v))

    # Independent physical/accounting validation, using no cvxpy expressions.
    injection = np.zeros(nbus)
    np.add.at(injection, model["gen_bus"], pg_v)
    signed = np.zeros(nbus)
    np.add.at(signed, f, active_flow)
    np.add.at(signed, t, -active_flow)
    residual = injection - model["demand"] - signed
    rated_all = rates > 0
    line_excess = np.zeros_like(rates)
    line_excess[rated_all] = np.maximum(np.abs(all_flow[rated_all]) - rates[rated_all], 0.0)
    validation = {
        "solver_status": str(problem.status),
        "max_abs_nodal_balance_MW": float(np.max(np.abs(residual))),
        "max_generator_bound_violation_MW": float(max(np.max(model["pmin"] - pg_v), np.max(pg_v - model["pmax"]), 0.0)),
        "max_reserve_capacity_violation_MW": float(max(np.max(pg_v + r_v - model["pmax"]), np.max(-r_v), 0.0)),
        "reserve_shortfall_MW": float(max(model["requirement"] - np.sum(r_v), 0.0)),
        "max_line_limit_violation_MW": float(np.max(line_excess) if len(line_excess) else 0.0),
        "reconstructed_objective_dollars_per_hour": reconstructed,
    }
    return {"pg": pg_v, "reserve": r_v, "flow": all_flow, "lmp": lmp, "reserve_mcp": reserve_mcp,
            "cost": reconstructed, "validation": validation}


def serial_float(value):
    value = float(value)
    if abs(value) < 5e-11:
        value = 0.0
    return round(value, 8)


def scenario_report(model, result, rates, binding_fraction):
    bindings = []
    for i in model["active"]:
        if rates[i] > 0 and abs(result["flow"][i]) >= binding_fraction * rates[i] - 1e-7:
            bindings.append({"from": int(model["br_from_id"][i]), "to": int(model["br_to_id"][i]),
                             "flow_MW": serial_float(result["flow"][i]), "limit_MW": serial_float(rates[i])})
    bindings.sort(key=lambda x: (x["from"], x["to"]))
    order = sorted(range(len(model["bus_ids"])), key=lambda i: model["bus_ids"][i])
    return {
        "total_cost_dollars_per_hour": serial_float(result["cost"]),
        "lmp_by_bus": [{"bus": int(model["bus_ids"][i]), "lmp_dollars_per_MWh": serial_float(result["lmp"][i])} for i in order],
        "reserve_mcp_dollars_per_MWh": serial_float(result["reserve_mcp"]),
        "binding_lines": bindings,
    }


def main(request):
    if not isinstance(request, dict):
        raise ValueError("stdin must contain a JSON object")
    network_path = request.get("network_path", "/root/network.json")
    output_path = request.get("output_path", "report.json")
    fraction = number(request.get("binding_fraction", 0.99), "binding_fraction")
    if not (0 < fraction <= 1):
        raise ValueError("binding_fraction must be in (0, 1]")
    override = request.get("reserve_requirement_mw")
    if override is not None:
        override = number(override, "reserve_requirement_mw")
    with open(network_path, "r", encoding="utf-8") as handle:
        model = parse_case(json.load(handle), override)

    base_rates = model["rate"].copy()
    cf_rates = base_rates.copy()
    cf_rates[model["target"]] *= 1.20
    base = solve(model, base_rates)
    counterfactual = solve(model, cf_rates)
    target = model["target"]
    drops = []
    for i, bus in enumerate(model["bus_ids"]):
        delta = counterfactual["lmp"][i] - base["lmp"][i]
        drops.append((delta, int(bus), base["lmp"][i], counterfactual["lmp"][i]))
    drops.sort(key=lambda x: (x[0], x[1]))
    top_drops = [{"bus": bus, "base_lmp": serial_float(b), "cf_lmp": serial_float(c), "delta": serial_float(delta)}
                 for delta, bus, b, c in drops[:min(3, len(drops))]]
    relieved = abs(counterfactual["flow"][target]) < fraction * cf_rates[target] - 1e-7
    report = {
        "base_case": scenario_report(model, base, base_rates, fraction),
        "counterfactual": scenario_report(model, counterfactual, cf_rates, fraction),
        "impact_analysis": {
            "cost_reduction_dollars_per_hour": serial_float(base["cost"] - counterfactual["cost"]),
            "buses_with_largest_lmp_drop": top_drops,
            "congestion_relieved": bool(relieved),
        },
    }
    parent = os.path.dirname(os.path.abspath(output_path))
    if parent and not os.path.isdir(parent):
        raise ValueError("output directory does not exist: %s" % parent)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return {"report_path": output_path, "report": report,
            "validation": {"base_case": base["validation"], "counterfactual": counterfactual["validation"]}}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        print(json.dumps(main(request), indent=2, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, allow_nan=False), file=sys.stderr)
        raise SystemExit(1)
