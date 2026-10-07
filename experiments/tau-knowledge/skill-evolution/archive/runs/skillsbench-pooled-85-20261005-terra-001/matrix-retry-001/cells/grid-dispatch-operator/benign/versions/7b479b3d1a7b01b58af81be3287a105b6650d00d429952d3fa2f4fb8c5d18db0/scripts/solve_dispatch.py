#!/usr/bin/env python3
"""Dependency-free lossless DC dispatch and spinning-reserve report writer.

stdin:  {"network_path": str?, "report_path": str?, "tolerance": number?}
stdout: {"ok": true, "report_path": str, "validation": object, "report": object}
     or {"ok": false, "error": str}
"""
import json
import math
import sys
from pathlib import Path


EPS = 1.0e-10


def fail(message):
    raise ValueError(message)


def num(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail(label + " must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        fail(label + " must be a finite number")
    return value


def normkey(value):
    return "".join(c for c in str(value).lower() if c.isalnum())


def unwrap(data):
    if isinstance(data, dict) and isinstance(data.get("mpc"), dict):
        return data["mpc"]
    return data


def reserve_requirement(case):
    names = {
        "reserverequirement", "reserverequirementmw", "reservereq",
        "reservereqmw", "spinningreserverequirement",
        "spinningreserverequirementmw", "spinningreservereq",
        "spinningreservereqmw",
    }

    def visit(obj, key=""):
        keyname = normkey(key)
        if keyname in names:
            if isinstance(obj, (int, float)) and not isinstance(obj, bool):
                return num(obj, str(key))
            if isinstance(obj, dict):
                for subkey in ("MW", "mw", "value", "requirement"):
                    if subkey in obj and isinstance(obj[subkey], (int, float)) and not isinstance(obj[subkey], bool):
                        return num(obj[subkey], str(key) + "." + subkey)
        if isinstance(obj, dict):
            for childkey, child in obj.items():
                found = visit(child, childkey)
                if found is not None:
                    return found
        return None

    found = visit(case)
    if found is None:
        return 0.0
    if found < 0:
        fail("reserve requirement must be nonnegative")
    return found


def reserve_eligibility(case, ng):
    values = case.get("reserve_eligible", case.get("gen_reserve_eligible"))
    reserve = case.get("reserve")
    if values is None and isinstance(reserve, dict):
        values = reserve.get("eligible")
    if values is None:
        return [True] * ng
    if not isinstance(values, list) or len(values) != ng:
        fail("reserve eligibility must be a list aligned with gen")
    return [bool(v) for v in values]


def parse_curve(row, index):
    if not isinstance(row, list) or len(row) < 4:
        fail("gencost row %d is invalid" % (index + 1))
    model, count = int(row[0]), int(row[3])
    if count <= 0:
        fail("gencost row %d has invalid NCOST" % (index + 1))
    if model == 2:
        if len(row) < 4 + count:
            fail("polynomial gencost row %d lacks coefficients" % (index + 1))
        coeff = [num(v, "gencost coefficient") for v in row[4:4 + count]]
        return (2, coeff)
    if model == 1:
        if count < 2 or len(row) < 4 + 2 * count:
            fail("piecewise-linear gencost row %d is invalid" % (index + 1))
        points = [(num(row[4 + 2*j], "piecewise power"), num(row[5 + 2*j], "piecewise cost")) for j in range(count)]
        if any(points[j + 1][0] <= points[j][0] for j in range(count - 1)):
            fail("piecewise-linear gencost breakpoints must increase")
        return (1, points)
    fail("unsupported MATPOWER gencost MODEL %d" % model)


def cost(curve, p):
    if curve[0] == 2:
        value = 0.0
        for coefficient in curve[1]:
            value = value * p + coefficient
        return value
    points = curve[1]
    if p <= points[0][0]:
        a, b = points[0], points[1]
    elif p >= points[-1][0]:
        a, b = points[-2], points[-1]
    else:
        a, b = points[0], points[1]
        for left, right in zip(points, points[1:]):
            if left[0] <= p <= right[0]:
                a, b = left, right
                break
    return a[1] + (p - a[0]) * (b[1] - a[1]) / (b[0] - a[0])


def marginal_cost(curve, p):
    if curve[0] == 1:
        points = curve[1]
        for left, right in zip(points, points[1:]):
            if p <= right[0] + EPS:
                return (right[1] - left[1]) / (right[0] - left[0])
        left, right = points[-2], points[-1]
        return (right[1] - left[1]) / (right[0] - left[0])
    coeff = curve[1]
    degree = len(coeff) - 1
    return sum(coeff[j] * (degree - j) * p ** (degree - j - 1) for j in range(degree))


def components(nb, live):
    adjacent = [[] for _ in range(nb)]
    for edge in live:
        adjacent[edge[1]].append(edge[2])
        adjacent[edge[2]].append(edge[1])
    answer, owner = [], [-1] * nb
    for start in range(nb):
        if owner[start] >= 0:
            continue
        stack, group = [start], []
        owner[start] = len(answer)
        while stack:
            node = stack.pop()
            group.append(node)
            for other in adjacent[node]:
                if owner[other] < 0:
                    owner[other] = owner[start]
                    stack.append(other)
        answer.append(group)
    return answer, owner


def cg_component(nodes, edge_list, rhs):
    """Solve grounded weighted Laplacian theta=rhs with first node at zero."""
    if len(nodes) <= 1:
        return {nodes[0]: 0.0} if nodes else {}
    local = {node: i - 1 for i, node in enumerate(nodes) if i > 0}
    edges = []
    for edge in edge_list:
        f, t, b = edge[1], edge[2], edge[3]
        if f in local or t in local:
            edges.append((local.get(f, -1), local.get(t, -1), b))
    n = len(nodes) - 1
    x = [0.0] * n
    r = [rhs[node] for node in nodes[1:]]
    direction = r[:]
    rr = sum(v * v for v in r)
    target = max(1.0e-20, rr * 1.0e-24)
    for _ in range(max(1000, 30 * n)):
        if rr <= target:
            result = {nodes[0]: 0.0}
            result.update({node: x[k] for node, k in local.items()})
            return result
        ad = [0.0] * n
        for a, b, weight in edges:
            av = direction[a] if a >= 0 else 0.0
            bv = direction[b] if b >= 0 else 0.0
            if a >= 0:
                ad[a] += weight * (av - bv)
            if b >= 0:
                ad[b] += weight * (bv - av)
        denom = sum(direction[i] * ad[i] for i in range(n))
        if abs(denom) < 1.0e-30:
            fail("DC network matrix is singular")
        alpha = rr / denom
        for i in range(n):
            x[i] += alpha * direction[i]
            r[i] -= alpha * ad[i]
        newrr = sum(v * v for v in r)
        beta = newrr / rr
        for i in range(n):
            direction[i] = r[i] + beta * direction[i]
        rr = newrr
    fail("conjugate-gradient DC power flow did not converge")


def solve_angles(nb, groups, component_edges, rhs):
    angles = [0.0] * nb
    for group, edges in zip(groups, component_edges):
        partial = cg_component(group, edges, rhs)
        for node, value in partial.items():
            angles[node] = value
    return angles


def build_model(case):
    for key in ("bus", "gen", "branch", "gencost"):
        if not isinstance(case.get(key), list):
            fail("network JSON lacks MATPOWER " + key + " rows")
    buses, gens, branches, costrows = case["bus"], case["gen"], case["branch"], case["gencost"]
    if not buses or len(gens) != len(costrows):
        fail("MATPOWER case has no buses or mismatched gen/gencost rows")
    base = num(case.get("baseMVA", 100.0), "baseMVA")
    if base <= 0:
        fail("baseMVA must be positive")
    bus_ids = []
    demand = []
    for i, row in enumerate(buses):
        if not isinstance(row, list) or len(row) < 3:
            fail("bus row %d is invalid" % (i + 1))
        bus_ids.append(row[0])
        demand.append(num(row[2], "bus PD"))
    if len(set(bus_ids)) != len(bus_ids):
        fail("bus identifiers are not unique")
    bmap = {bus: i for i, bus in enumerate(bus_ids)}
    ng = len(gens)
    online, gbus, pmin, pmax, initial = [], [], [], [], []
    curves = [parse_curve(row, i) for i, row in enumerate(costrows)]
    for i, row in enumerate(gens):
        if not isinstance(row, list) or len(row) < 10 or row[0] not in bmap:
            fail("generator row %d is invalid or references an unknown bus" % (i + 1))
        gbus.append(bmap[row[0]])
        pmax.append(num(row[8], "generator PMAX"))
        pmin.append(num(row[9], "generator PMIN"))
        if pmin[-1] > pmax[-1] + EPS:
            fail("generator %d has PMIN greater than PMAX" % (i + 1))
        initial.append(num(row[1], "generator PG"))
        if num(row[7], "generator status") > 0:
            online.append(i)
    live = []
    for source, row in enumerate(branches):
        if not isinstance(row, list) or len(row) < 13:
            fail("branch row %d lacks MATPOWER DC columns" % (source + 1))
        if num(row[10], "branch status") <= 0:
            continue
        if row[0] not in bmap or row[1] not in bmap:
            fail("branch references an unknown bus")
        x = num(row[3], "branch BR_X")
        tapraw = num(row[8], "branch TAP")
        tap = 1.0 if abs(tapraw) < EPS else tapraw
        if abs(x) < EPS or abs(tap) < EPS:
            fail("live branch has zero reactance or tap")
        coefficient = base / (x * tap)
        if coefficient <= 0:
            fail("dependency-free DC solver requires positive BR_X * TAP on live branches")
        live.append((source, bmap[row[0]], bmap[row[1]], coefficient,
                     math.radians(num(row[9], "branch SHIFT")), num(row[5], "branch RATE_A"),
                     math.radians(num(row[11], "branch ANGMIN")), math.radians(num(row[12], "branch ANGMAX")), row))
    groups, owner = components(len(buses), live)
    by_component = [[] for _ in groups]
    for edge in live:
        by_component[owner[edge[1]]].append(edge)
    return (base, buses, gens, bus_ids, demand, online, gbus, pmin, pmax, initial,
            curves, live, groups, owner, by_component)


def adjust_component(pg, generators, target, pmin, pmax, curves, direction):
    current = sum(pg[g] for g in generators)
    amount = target - current
    if abs(amount) <= 1e-8:
        return
    if amount > 0:
        ordered = sorted(generators, key=lambda g: (marginal_cost(curves[g], pg[g]), g))
        for g in ordered:
            take = min(amount, pmax[g] - pg[g])
            pg[g] += take
            amount -= take
            if amount <= 1e-8:
                return
        fail("online PMAX cannot meet component active demand")
    else:
        amount = -amount
        ordered = sorted(generators, key=lambda g: (-marginal_cost(curves[g], pg[g]), g))
        for g in ordered:
            take = min(amount, pg[g] - pmin[g])
            pg[g] -= take
            amount -= take
            if amount <= 1e-8:
                return
        fail("online PMIN exceeds component active demand")


def injections_and_rhs(pg, demand, gbus, live):
    injection = [-value for value in demand]
    for g, value in enumerate(pg):
        injection[gbus[g]] += value
    phase = [0.0] * len(demand)
    for _, f, t, b, shift, _, _, _, _ in live:
        phase[f] -= b * shift
        phase[t] += b * shift
    return injection, [injection[i] - phase[i] for i in range(len(demand))]


def state(pg, demand, gbus, live, groups, component_edges):
    injection, rhs = injections_and_rhs(pg, demand, gbus, live)
    angles = solve_angles(len(demand), groups, component_edges, rhs)
    flows = [edge[3] * (angles[edge[1]] - angles[edge[2]] - edge[4]) for edge in live]
    return injection, angles, flows


def violations(angles, flows, live):
    result = []
    score = 0.0
    for k, edge in enumerate(live):
        _, f, t, b, _, rate, amin, amax, _ = edge
        flow = flows[k]
        if rate > 0 and abs(flow) > rate:
            excess = abs(flow) - rate
            result.append((excess, k, "flow", -1.0 if flow > 0 else 1.0))
            score += excess * excess
        diff = angles[f] - angles[t]
        if amin > math.radians(-360.0) and diff < amin:
            excess = amin - diff
            result.append((abs(b) * excess, k, "angle", 1.0))
            score += (abs(b) * excess) ** 2
        if amax < math.radians(360.0) and diff > amax:
            excess = diff - amax
            result.append((abs(b) * excess, k, "angle", -1.0))
            score += (abs(b) * excess) ** 2
    return score, result


def repair_limits(pg, demand, gbus, pmin, pmax, online, live, groups, owner, component_edges):
    injection, angles, flows = state(pg, demand, gbus, live, groups, component_edges)
    score, bad = violations(angles, flows, live)
    for _ in range(800):
        if not bad:
            return angles, flows
        _, edge_index, kind, desired = max(bad, key=lambda item: (item[0], -item[1], item[2]))
        edge = live[edge_index]
        component = owner[edge[1]]
        # lambda = B^-1(e_from-e_to), with the same arbitrary component reference.
        probe = [0.0] * len(demand)
        probe[edge[1]] = 1.0
        probe[edge[2]] = -1.0
        lam = cg_component(groups[component], component_edges[component], probe)
        candidates = [g for g in online if owner[gbus[g]] == component]
        downs = [g for g in candidates if pg[g] > pmin[g] + 1e-7]
        ups = [g for g in candidates if pg[g] < pmax[g] - 1e-7]
        if not downs or not ups:
            fail("no generator headroom remains for transmission-feasibility redispatch")
        # A transaction down at A and up at B changes angle difference by lam[B]-lam[A].
        factor = edge[3] if kind == "flow" else 1.0
        choices = []
        for down in downs:
            for up in ups:
                if down == up:
                    continue
                sensitivity = factor * (lam[gbus[up]] - lam[gbus[down]])
                if sensitivity * desired > 1e-12:
                    choices.append((abs(sensitivity), down, up, sensitivity))
        if not choices:
            fail("cannot find a redispatch direction that relieves a DC limit")
        choices.sort(key=lambda item: (-item[0], item[1], item[2]))
        accepted = False
        for _, down, up, sensitivity in choices[:24]:
            if kind == "flow":
                if desired < 0:
                    needed = (flows[edge_index] - edge[5]) / (-sensitivity)
                else:
                    needed = (-edge[5] - flows[edge_index]) / sensitivity
            else:
                difference = angles[edge[1]] - angles[edge[2]]
                needed = ((edge[6] - difference) if desired > 0 else (difference - edge[7])) / abs(sensitivity)
            move = min(max(needed, 1e-5), pg[down] - pmin[down], pmax[up] - pg[up])
            if move <= 1e-8:
                continue
            pg[down] -= move
            pg[up] += move
            _, candidate_angles, candidate_flows = state(pg, demand, gbus, live, groups, component_edges)
            candidate_score, candidate_bad = violations(candidate_angles, candidate_flows, live)
            if candidate_score < score - 1e-10:
                angles, flows, score, bad = candidate_angles, candidate_flows, candidate_score, candidate_bad
                accepted = True
                break
            pg[down] += move
            pg[up] -= move
        if not accepted:
            fail("DC transmission redispatch repair stalled")
    fail("DC transmission redispatch exceeded iteration limit")


def solve(case, tolerance):
    (base, buses, gens, bus_ids, demand, online, gbus, pmin, pmax, initial, curves,
     live, groups, owner, component_edges) = build_model(case)
    ng = len(gens)
    by_group_generators = [[] for _ in groups]
    for g in online:
        by_group_generators[owner[gbus[g]]].append(g)
    pg = [0.0] * ng
    for g in online:
        pg[g] = min(pmax[g], max(pmin[g], initial[g]))
    for ci, nodes in enumerate(groups):
        if not by_group_generators[ci] and abs(sum(demand[node] for node in nodes)) > tolerance:
            fail("an electrically isolated component has demand but no online generator")
        adjust_component(pg, by_group_generators[ci], sum(demand[node] for node in nodes), pmin, pmax, curves, 0)
    angles, flows = repair_limits(pg, demand, gbus, pmin, pmax, online, live, groups, owner, component_edges)

    requirement = reserve_requirement(case)
    eligible = reserve_eligibility(case, ng)
    reserve = [0.0] * ng
    candidates = [g for g in online if eligible[g]]
    remaining = requirement
    # Deterministic allocation retains lower-cost units for energy and uses headroom first.
    for g in sorted(candidates, key=lambda x: (marginal_cost(curves[x], pg[x]), x)):
        take = min(remaining, pmax[g] - pg[g])
        reserve[g] = take
        remaining -= take
    if remaining > tolerance:
        fail("eligible online generation headroom cannot meet reserve requirement")

    # Independent final DC reconstruction, rather than trusting the repair loop.
    injection, final_angles, final_flows = state(pg, demand, gbus, live, groups, component_edges)
    residual = injection[:]
    phase = [0.0] * len(demand)
    for _, f, t, b, shift, _, _, _, _ in live:
        phase[f] -= b * shift
        phase[t] += b * shift
        residual[f] -= b * (final_angles[f] - final_angles[t])
        residual[t] -= b * (final_angles[t] - final_angles[f])
    # residual above is injection-Btheta; compare against phase in Btheta=injection-phase.
    residual = [residual[i] - phase[i] for i in range(len(demand))]
    max_balance = max(abs(v) for v in residual) if residual else 0.0
    max_limit = 0.0
    for k, edge in enumerate(live):
        _, f, t, _, _, rate, amin, amax, _ = edge
        if rate > 0:
            max_limit = max(max_limit, abs(final_flows[k]) - rate)
        diff = final_angles[f] - final_angles[t]
        if amin > math.radians(-360.0):
            max_limit = max(max_limit, amin - diff)
        if amax < math.radians(360.0):
            max_limit = max(max_limit, diff - amax)
    for g in range(ng):
        if g in online:
            max_limit = max(max_limit, pmin[g] - pg[g], pg[g] - pmax[g], -reserve[g], pg[g] + reserve[g] - pmax[g])
        else:
            max_limit = max(max_limit, abs(pg[g]), abs(reserve[g]))
    max_limit = max(max_limit, abs(sum(reserve) - requirement))
    if max_balance > tolerance or max_limit > tolerance:
        fail("post-solve validation failed: balance %.6g, limit %.6g" % (max_balance, max_limit))

    total_load = sum(demand)
    total_generation = sum(pg)
    if abs(total_generation - total_load) > tolerance:
        fail("lossless DC generation does not equal active load")
    total_cost = sum(cost(curves[g], pg[g]) for g in range(ng))
    total_reserve = sum(reserve)
    margin = sum(pmax[g] for g in online) - total_generation - total_reserve
    dispatch = [{"id": g + 1, "bus": gens[g][0], "output_MW": pg[g],
                 "reserve_MW": reserve[g], "pmax_MW": pmax[g]} for g in range(ng)]
    loaded = []
    for k, edge in enumerate(live):
        source, f, t, _, _, rate, _, _, row = edge
        if rate > 0:
            loaded.append((source, {"from": row[0], "to": row[1], "loading_pct": abs(final_flows[k]) / rate * 100.0}))
    loaded.sort(key=lambda item: (-item[1]["loading_pct"], item[0]))
    report = {
        "generator_dispatch": dispatch,
        "totals": {"cost_dollars_per_hour": total_cost, "load_MW": total_load,
                   "generation_MW": total_generation, "reserve_MW": total_reserve},
        "most_loaded_lines": [item[1] for item in loaded[:3]],
        "operating_margin_MW": margin,
    }
    validation = {"max_nodal_balance_MW": max_balance,
                  "max_constraint_violation": max(0.0, max_limit),
                  "reserve_requirement_MW": requirement,
                  "reconstructed_cost_dollars_per_hour": total_cost}
    return report, validation


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            fail("stdin must contain a JSON object")
        network_path = Path(request.get("network_path", "/root/network.json"))
        report_path = Path(request.get("report_path", "/root/report.json"))
        tolerance = num(request.get("tolerance", 1e-6), "tolerance")
        if tolerance <= 0:
            fail("tolerance must be positive")
        with network_path.open("r", encoding="utf-8") as handle:
            case = unwrap(json.load(handle))
        if not isinstance(case, dict):
            fail("network JSON does not contain a MATPOWER case object")
        report, validation = solve(case, tolerance)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
            handle.write("\n")
        print(json.dumps({"ok": True, "report_path": str(report_path), "validation": validation, "report": report}, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
