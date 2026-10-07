#!/usr/bin/env python3
"""Detect BGP oscillation + valley-free route leaks and evaluate solutions.

Stdin : optional JSON {"data_dir":str, "output_path":str}
Stdout: JSON {"status":str, "output_path":str, "report":{...}, "diagnostics":{...}}
Side effect: writes the report JSON to output_path.

The analyzer is intentionally format-tolerant: it accepts several common field
names for preferences, advertisements/relationships and solutions. If the real
generated schema differs, extend the extraction helpers below.
"""
import json
import os
import sys
from collections import defaultdict


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def norm_rel(value):
    if value is None:
        return None
    t = str(value).strip().lower()
    if not t:
        return None
    if "cust" in t or t in ("c", "down", "downstream", "child"):
        return "customer"
    if "prov" in t or t in ("p", "up", "upstream", "parent", "transit"):
        return "provider"
    if "peer" in t or t in ("r", "lateral", "settlement-free"):
        return "peer"
    return t


def as_int(x):
    try:
        return int(x)
    except Exception:
        try:
            return int(str(x).strip())
        except Exception:
            return None


def extract_pref_edges(prefs):
    """Return list of (u, v) edges: u currently prefers a route via v."""
    edges = []
    if isinstance(prefs, dict):
        for container in ("preferences", "edges", "prefers", "graph"):
            if container in prefs:
                return extract_pref_edges(prefs[container])
        for k, v in prefs.items():
            u = as_int(k)
            if u is None:
                continue
            if isinstance(v, (list, tuple)):
                for x in v:
                    xi = as_int(x)
                    if xi is not None:
                        edges.append((u, xi))
            elif isinstance(v, dict):
                for key in ("prefers", "preferred", "next", "via", "to", "nexthop"):
                    if key in v:
                        xi = as_int(v[key])
                        if xi is not None:
                            edges.append((u, xi))
            else:
                xi = as_int(v)
                if xi is not None:
                    edges.append((u, xi))
    elif isinstance(prefs, list):
        for item in prefs:
            if isinstance(item, dict):
                u = (item.get("from") or item.get("source") or item.get("as")
                     or item.get("src") or item.get("hub"))
                v = (item.get("to") or item.get("preferred") or item.get("prefers")
                     or item.get("via") or item.get("dst") or item.get("next")
                     or item.get("nexthop"))
                ui, vi = as_int(u), as_int(v)
                if ui is not None and vi is not None:
                    edges.append((ui, vi))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                ui, vi = as_int(item[0]), as_int(item[1])
                if ui is not None and vi is not None:
                    edges.append((ui, vi))
    # dedupe preserving order
    seen = set()
    out = []
    for e in edges:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def find_cycle(edges):
    """Return nodes of one directed cycle (traversal order), else []."""
    g = defaultdict(list)
    nodes = set()
    for u, v in edges:
        g[u].append(v)
        nodes.add(u)
        nodes.add(v)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    stack = []
    result = []

    def dfs(u):
        color[u] = GRAY
        stack.append(u)
        for w in g[u]:
            cw = color.get(w, WHITE)
            if cw == GRAY:
                idx = stack.index(w)
                result.extend(stack[idx:])
                return True
            if cw == WHITE and dfs(w):
                return True
        color[u] = BLACK
        stack.pop()
        return False

    for n in sorted(nodes):
        if color[n] == WHITE and dfs(n):
            return result
    return []


def collect_relationships(route, extra):
    """Build (u, v) -> relationship-type map from any available source."""
    rel = {}

    def ingest(obj):
        if isinstance(obj, list):
            for it in obj:
                if isinstance(it, dict):
                    u = as_int(it.get("from") or it.get("source") or it.get("as") or it.get("src"))
                    v = as_int(it.get("to") or it.get("dst") or it.get("neighbor") or it.get("target"))
                    t = norm_rel(it.get("type") or it.get("relationship") or it.get("rel"))
                    if u is not None and v is not None and t:
                        rel[(u, v)] = t
        elif isinstance(obj, dict):
            for k, v in obj.items():
                ingest(v)

    for src in (route, extra):
        if isinstance(src, dict):
            for key in ("relationships", "topology", "links", "adjacencies"):
                if key in src:
                    ingest(src[key])
    return rel


def extract_advertisements(route, rel):
    """Return list of advertisement dicts with normalized relationship types."""
    ads = []
    candidates = []
    if isinstance(route, dict):
        for key in ("advertisements", "ads", "exports", "leaks", "route_leaks",
                    "advertised", "announcements"):
            if isinstance(route.get(key), list):
                candidates = route[key]
                break
    elif isinstance(route, list):
        candidates = route

    for item in candidates:
        if not isinstance(item, dict):
            continue
        leaker = as_int(item.get("leaker_as") or item.get("leaker")
                        or item.get("advertiser") or item.get("as") or item.get("hub"))
        src = as_int(item.get("source_as") or item.get("from_as")
                     or item.get("learned_from") or item.get("src") or item.get("origin_as"))
        dst = as_int(item.get("destination_as") or item.get("to_as")
                     or item.get("advertised_to") or item.get("dst") or item.get("neighbor"))
        st = norm_rel(item.get("source_type") or item.get("learned_type")
                      or item.get("learned_rel") or item.get("from_type"))
        dt = norm_rel(item.get("destination_type") or item.get("export_type")
                      or item.get("export_rel") or item.get("to_type"))
        if leaker is not None and src is not None:
            if st is None:
                st = rel.get((leaker, src)) or rel.get((src, leaker))
        if leaker is not None and dst is not None:
            if dt is None:
                dt = rel.get((leaker, dst)) or rel.get((dst, leaker))
        if leaker is not None and src is not None and dst is not None:
            ads.append({
                "leaker_as": leaker,
                "source_as": src,
                "destination_as": dst,
                "source_type": st,
                "destination_type": dt,
            })
    return ads


def is_leak(ad):
    """Valley-free violation: peer/provider-learned exported to a non-customer."""
    st = ad.get("source_type")
    dt = ad.get("destination_type")
    if st in ("peer", "provider") and dt is not None and dt != "customer":
        return True
    return False


def ad_key(ad):
    return (ad["leaker_as"], ad["source_as"], ad["destination_as"])


def extract_solutions(sols):
    out = []
    if isinstance(sols, dict):
        if "solutions" in sols:
            return extract_solutions(sols["solutions"])
        for k, v in sols.items():
            out.append((str(k), v if isinstance(v, dict) else {"description": str(k)}))
    elif isinstance(sols, list):
        for item in sols:
            if isinstance(item, str):
                out.append((item, {"description": item}))
            elif isinstance(item, dict):
                name = (item.get("description") or item.get("name")
                        or item.get("solution") or json.dumps(item, sort_keys=True))
                out.append((str(name), item))
    return out


TIMER_KW = ["keepalive", "holdtime", "hold time", "hold-time", "timer",
            "mtu", "logging", "monitor", "telemetry", "alarm", "alert", "dashboard"]
PREF_KW = ["local pref", "local-pref", "localpref", "as-path", "as path",
           "prepend", "routing preference", "change preference", "prefer",
           "weight", "med", "metric"]
LEAK_KW = ["branch-to-branch", "branch to branch", "route filter", "filter",
           "disable propagation", "stop advertis", "disconnect", "routing intent",
           "route map", "route-map", "prefix list", "prefix-list", "deny",
           "no-advertise", "no advertise", "community"]


def break_cycle_edge(removed, raw_cycle):
    if len(raw_cycle) >= 2:
        removed.add((raw_cycle[0], raw_cycle[1]))
    elif len(raw_cycle) == 1:
        removed.add((raw_cycle[0], raw_cycle[0]))


def build_modifications(name, sol, raw_cycle, leaks):
    """Translate a solution's stated effects into graph modifications.

    Returns {"removed_edges": set((u,v)), "blocked_ads": set((leaker,src,dst))}.
    Structured 'effects' take priority; otherwise documented keyword heuristics
    are used. Both are then re-simulated by the caller.
    """
    removed = set()
    blocked = set()
    eff = sol.get("effects") if isinstance(sol, dict) else None
    handled = False
    if isinstance(eff, dict):
        handled = True
        for e in (eff.get("remove_pref_edges") or eff.get("remove_edges") or []):
            if isinstance(e, (list, tuple)) and len(e) >= 2:
                a, b = as_int(e[0]), as_int(e[1])
                if a is not None and b is not None:
                    removed.add((a, b))
        for a in (eff.get("block_advertisements") or eff.get("block_ads") or []):
            if isinstance(a, dict):
                k = (as_int(a.get("leaker_as") or a.get("leaker")),
                     as_int(a.get("source_as") or a.get("from_as")),
                     as_int(a.get("destination_as") or a.get("to_as")))
                blocked.add(k)
        if eff.get("breaks_cycle") or eff.get("resolves_oscillation"):
            break_cycle_edge(removed, raw_cycle)
        if eff.get("stops_route_leak") or eff.get("resolves_route_leak"):
            for ad in leaks:
                blocked.add(ad_key(ad))

    if not handled:
        text = (name + " " + json.dumps(sol, sort_keys=True)).lower()
        timer_only = any(k in text for k in TIMER_KW)
        if not timer_only:
            if any(k in text for k in PREF_KW):
                break_cycle_edge(removed, raw_cycle)
            if any(k in text for k in LEAK_KW):
                for ad in leaks:
                    blocked.add(ad_key(ad))
    return {"removed_edges": removed, "blocked_ads": blocked}


def main():
    raw = sys.stdin.read().strip()
    cfg = {}
    if raw:
        try:
            cfg = json.loads(raw)
        except Exception:
            cfg = {}
    data_dir = cfg.get("data_dir") or "/app/data"
    if not os.path.isdir(data_dir) or not any(
            os.path.exists(os.path.join(data_dir, f))
            for f in ("preferences.json", "route.json")):
        alt = "/app/environment/data"
        if os.path.isdir(alt):
            data_dir = alt if not os.path.isdir(cfg.get("data_dir") or "/app/data") else data_dir
    output_path = cfg.get("output_path") or "/app/output/oscillation_report.json"

    files = {}
    missing = []
    for name in ("route.json", "preferences.json", "local_pref.json",
                 "possible_solutions.json"):
        p = os.path.join(data_dir, name)
        if os.path.exists(p):
            try:
                files[name] = load_json(p)
            except Exception as exc:
                files[name] = None
                missing.append("%s (parse error: %s)" % (name, exc))
        else:
            missing.append(name)

    prefs = files.get("preferences.json")
    route = files.get("route.json")
    local_pref = files.get("local_pref.json")
    solutions_raw = files.get("possible_solutions.json")

    edges = extract_pref_edges(prefs) if prefs is not None else []
    rel = collect_relationships(route, local_pref)
    ads = extract_advertisements(route, rel) if route is not None else []
    solutions = extract_solutions(solutions_raw) if solutions_raw is not None else []

    raw_cycle = find_cycle(edges)
    cycle_sorted = sorted(set(raw_cycle))
    base_leaks = [ad for ad in ads if is_leak(ad)]
    osc_detected = len(raw_cycle) > 0
    leak_detected = len(base_leaks) > 0

    route_leaks_out = []
    for ad in base_leaks:
        route_leaks_out.append({
            "leaker_as": ad["leaker_as"],
            "source_as": ad["source_as"],
            "destination_as": ad["destination_as"],
            "source_type": ad.get("source_type"),
            "destination_type": ad.get("destination_type"),
        })

    solution_results = {}
    for name, sol in solutions:
        mod = build_modifications(name, sol, raw_cycle, base_leaks)
        new_edges = [e for e in edges if e not in mod["removed_edges"]]
        c2 = find_cycle(new_edges)
        kept_ads = [ad for ad in ads if ad_key(ad) not in mod["blocked_ads"]]
        l2 = [ad for ad in kept_ads if is_leak(ad)]
        osc_res = bool(osc_detected and len(c2) == 0)
        leak_res = bool(leak_detected and len(l2) == 0)
        solution_results[name] = {
            "oscillation_resolved": osc_res,
            "route_leak_resolved": leak_res,
        }

    report = {
        "oscillation_detected": osc_detected,
        "oscillation_cycle": cycle_sorted,
        "affected_ases": cycle_sorted,
        "route_leak_detected": leak_detected,
        "route_leaks": route_leaks_out,
        "solution_results": solution_results,
    }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as fh:
        json.dump(report, fh, indent=2)

    diagnostics = {
        "data_dir": data_dir,
        "missing": missing,
        "pref_edges": [list(e) for e in edges],
        "relationships": {"%d->%d" % k: v for k, v in rel.items()},
        "advertisements": ads,
        "solution_names": [n for n, _ in solutions],
    }
    print(json.dumps({
        "status": "ok" if not missing else "ok_with_warnings",
        "output_path": output_path,
        "report": report,
        "diagnostics": diagnostics,
    }, indent=2))


if __name__ == "__main__":
    main()
