#!/usr/bin/env python3
"""Civ6 map-only placement solver.
stdin: {action: solve|validate, scenario_path: str, output_path?: str,
        solution_path?: str, solution?: object}
stdout for solve is the task solution; stdout for validate is a validation report.
"""
import itertools
import json
import os
import sqlite3
import sys

SPECIALTY = {"CAMPUS", "HOLY_SITE", "THEATER_SQUARE", "COMMERCIAL_HUB", "HARBOR",
             "INDUSTRIAL_ZONE", "ENTERTAINMENT_COMPLEX", "WATER_PARK", "ENCAMPMENT",
             "AERODROME", "GOVERNMENT_PLAZA", "DIPLOMATIC_QUARTER", "PRESERVE"}
NON_SPECIALTY = {"AQUEDUCT", "DAM", "CANAL", "SPACEPORT", "NEIGHBORHOOD"}
KNOWN = SPECIALTY | NON_SPECIALTY
WATER_KINDS = {"HARBOR", "WATER_PARK"}
FLAT_KINDS = {"AERODROME", "SPACEPORT"}
SCORING = ("CAMPUS", "HOLY_SITE", "COMMERCIAL_HUB", "HARBOR", "INDUSTRIAL_ZONE", "THEATER_SQUARE")
NATURAL = {"FEATURE_BARRIER_REEF", "FEATURE_GREAT_BARRIER_REEF", "FEATURE_CRATER_LAKE",
           "FEATURE_DELICATE_ARCH", "FEATURE_EYE_OF_THE_SAHARA", "FEATURE_GALAPAGOS",
           "FEATURE_GIANTS_CAUSEWAY", "FEATURE_LAKE_RETBA", "FEATURE_MATTERHORN",
           "FEATURE_MOUNT_EVEREST", "FEATURE_PAITITI", "FEATURE_PIOPIOTAHI",
           "FEATURE_PANTANAL", "FEATURE_RORAIMA", "FEATURE_TORRES_DEL_PAINE",
           "FEATURE_TSINGY", "FEATURE_UBSUNUR_HOLLOW", "FEATURE_ULURU",
           "FEATURE_YOSEMITE", "FEATURE_ZHANGYE_DANXIA"}
STRATEGIC = {"RESOURCE_HORSES", "RESOURCE_IRON", "RESOURCE_NITER", "RESOURCE_COAL",
             "RESOURCE_OIL", "RESOURCE_ALUMINUM", "RESOURCE_URANIUM"}
LUXURY = {"RESOURCE_AMBER", "RESOURCE_CITRUS", "RESOURCE_COCOA", "RESOURCE_COFFEE",
          "RESOURCE_COTTON", "RESOURCE_DYES", "RESOURCE_DIAMONDS", "RESOURCE_FURS",
          "RESOURCE_GYPSUM", "RESOURCE_INCENSE", "RESOURCE_IVORY", "RESOURCE_JADE",
          "RESOURCE_MARBLE", "RESOURCE_MERCURY", "RESOURCE_PEARLS", "RESOURCE_SALT",
          "RESOURCE_SILK", "RESOURCE_SILVER", "RESOURCE_SPICES", "RESOURCE_SUGAR",
          "RESOURCE_TEA", "RESOURCE_TOBACCO", "RESOURCE_TRUFFLES", "RESOURCE_WHALES",
          "RESOURCE_WINE", "RESOURCE_CINNAMON", "RESOURCE_CLOVES", "RESOURCE_COSMETICS",
          "RESOURCE_JEANS", "RESOURCE_OLIVES", "RESOURCE_PERFUME", "RESOURCE_TOYS"}
REEFS = {"FEATURE_GEOTHERMAL_FISSURE", "FEATURE_REEF", "FEATURE_BARRIER_REEF", "FEATURE_GREAT_BARRIER_REEF"}


def get(row, name, default=None):
    return row[name] if name in row.keys() and row[name] is not None else default


class MapData:
    def __init__(self, path):
        con = sqlite3.connect("file:" + os.path.abspath(path) + "?mode=ro&immutable=1", uri=True)
        con.row_factory = sqlite3.Row
        try:
            meta = con.execute('SELECT * FROM "Map"').fetchone()
            if meta is None:
                raise ValueError("Map table has no row")
            self.w, self.h = int(get(meta, "Width")), int(get(meta, "Height"))
            self.wrapx, self.wrapy = bool(get(meta, "WrapX", 0)), bool(get(meta, "WrapY", 0))
            self.plots = {int(get(r, "ID")): {"terrain": get(r, "TerrainType", ""),
                          "impassable": bool(get(r, "IsImpassable", 0))}
                          for r in con.execute('SELECT * FROM "Plots"')}
            self.features = {int(get(r, "ID")): get(r, "FeatureType")
                             for r in con.execute('SELECT * FROM "PlotFeatures")')}
            self.resources = {int(get(r, "ID")): get(r, "ResourceType")
                              for r in con.execute('SELECT * FROM "PlotResources")')}
            self.rivers = {int(get(r, "ID")): {"ne": bool(get(r, "IsNEOfRiver", 0)),
                           "w": bool(get(r, "IsWOfRiver", 0)), "nw": bool(get(r, "IsNWOfRiver", 0))}
                           for r in con.execute('SELECT * FROM "PlotRivers")')}
        finally:
            con.close()
        if not self.plots:
            raise ValueError("Plots table is empty")

    def pid(self, p): return p[1] * self.w + p[0]
    def terrain(self, p): return self.plots[self.pid(p)]["terrain"]
    def feature(self, p): return self.features.get(self.pid(p))
    def resource(self, p): return self.resources.get(self.pid(p))
    def water(self, p): return self.terrain(p) in {"TERRAIN_COAST", "TERRAIN_OCEAN", "TERRAIN_LAKE"}
    def mountain(self, p): return self.terrain(p).endswith("_MOUNTAIN")

    def norm(self, p):
        x, y = p
        if self.wrapx: x %= self.w
        if self.wrapy: y %= self.h
        return (x, y) if 0 <= x < self.w and 0 <= y < self.h and self.pid((x, y)) in self.plots else None

    def neighbors(self, p):
        x, y = p
        ds = [(1, 0), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1)] if y % 2 == 0 else [(1, 0), (1, -1), (0, -1), (-1, 0), (0, 1), (1, 1)]
        return [q for q in (self.norm((x + dx, y + dy)) for dx, dy in ds) if q is not None]

    def distance(self, a, b):
        def cube(p):
            q = p[0] - (p[1] - (p[1] % 2)) // 2
            return q, p[1], -q - p[1]
        aa, bb = cube(a), cube(b)
        return max(abs(aa[i] - bb[i]) for i in range(3))

    def river_at(self, p):
        r = self.rivers.get(self.pid(p), {})
        if r.get("ne") or r.get("w") or r.get("nw"):
            return True
        x, y = p
        east = ((x + 1) % self.w if self.wrapx else x + 1, y)
        return 0 <= east[0] < self.w and bool(self.rivers.get(self.pid(east), {}).get("w"))


def city_ok(m, p):
    return (m.norm(p) == p and not m.water(p) and not m.mountain(p)
            and not m.plots[m.pid(p)]["impassable"] and m.feature(p) != "FEATURE_ICE"
            and m.feature(p) not in NATURAL)


def fresh(m, p):
    return m.river_at(p) or any(m.mountain(q) or m.feature(q) == "FEATURE_OASIS" or m.terrain(q) == "TERRAIN_LAKE" for q in m.neighbors(p))


def canal_ok(m, p, centers):
    ns = m.neighbors(p)
    waters = [q for q in ns if m.water(q)]
    if any(q in centers for q in ns) and waters:
        return True
    if len(waters) < 2:
        return False
    comp, number = {}, 0
    for y in range(m.h):
        for x in range(m.w):
            start = (x, y)
            if start in comp or m.pid(start) not in m.plots or not m.water(start):
                continue
            comp[start] = number
            todo = [start]
            while todo:
                cur = todo.pop()
                for q in m.neighbors(cur):
                    if q not in comp and m.water(q):
                        comp[q] = number
                        todo.append(q)
            number += 1
    return len({comp[q] for q in waters}) >= 2


def legal(m, kind, p, centers, occupied=()):
    if kind not in KNOWN or m.norm(p) != p or p in occupied or p in centers:
        return False
    if not any(m.distance(p, c) <= 3 for c in centers):
        return False
    if m.mountain(p) or m.feature(p) in NATURAL or m.feature(p) == "FEATURE_GEOTHERMAL_FISSURE":
        return False
    if m.resource(p) in STRATEGIC | LUXURY:
        return False
    if kind in WATER_KINDS:
        if not m.water(p) or not any(not m.water(q) for q in m.neighbors(p)): return False
    elif m.water(p):
        return False
    if kind in FLAT_KINDS and m.terrain(p).endswith("_HILLS"): return False
    if kind in {"ENCAMPMENT", "PRESERVE"} and any(m.distance(p, c) == 1 for c in centers): return False
    if kind == "AQUEDUCT" and (not any(m.distance(p, c) == 1 for c in centers) or not fresh(m, p)): return False
    if kind == "DAM" and m.feature(p) != "FEATURE_FLOODPLAINS": return False
    if kind == "CANAL" and not canal_ok(m, p, centers): return False
    return True


def score(m, placements, centers):
    destroyed, all_districts = set(placements.values()), set(placements.values()) | set(centers)
    feature = lambda p: None if p in destroyed else m.feature(p)
    result = {}
    for kind, p in placements.items():
        ns, districts = m.neighbors(p), 0
        districts = sum(q in all_districts for q in ns)
        value = 0
        if kind == "CAMPUS":
            value = 2 * sum(feature(q) in REEFS for q in ns) + sum(m.mountain(q) for q in ns)
            value += sum(feature(q) == "FEATURE_JUNGLE" for q in ns) // 2 + districts // 2
        elif kind == "HOLY_SITE":
            value = 2 * sum(feature(q) in NATURAL for q in ns) + sum(m.mountain(q) for q in ns)
            value += sum(feature(q) == "FEATURE_FOREST" for q in ns) // 2 + districts // 2
        elif kind == "COMMERCIAL_HUB":
            value = (2 if m.river_at(p) else 0) + 2 * sum(placements.get("HARBOR") == q for q in ns) + districts // 2
        elif kind == "INDUSTRIAL_ZONE":
            value = 2 * sum(q == placements.get("AQUEDUCT") or q == placements.get("DAM") or q == placements.get("CANAL") for q in ns)
            value += sum(m.resource(q) in STRATEGIC for q in ns) + districts // 2
        elif kind == "HARBOR":
            value = 2 * sum(q in centers for q in ns) + sum(m.resource(q) is not None for q in ns) + districts // 2
        elif kind == "THEATER_SQUARE":
            value = 2 * sum(q == placements.get("ENTERTAINMENT_COMPLEX") or q == placements.get("WATER_PARK") for q in ns) + districts // 2
        result[kind] = int(value)
    return result, int(sum(result.values()))


def nearby(m, c):
    out = set()
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            p = m.norm((c[0] + dx, c[1] + dy))
            if p is not None and m.distance(c, p) <= 3: out.add(p)
    return sorted(out)


def intrinsic(m, kind, p):
    ns = m.neighbors(p)
    if kind == "CAMPUS": return 2 * sum(m.feature(q) in REEFS for q in ns) + sum(m.mountain(q) for q in ns) + sum(m.feature(q) == "FEATURE_JUNGLE" for q in ns) // 2
    if kind == "HOLY_SITE": return 2 * sum(m.feature(q) in NATURAL for q in ns) + sum(m.mountain(q) for q in ns) + sum(m.feature(q) == "FEATURE_FOREST" for q in ns) // 2
    if kind == "COMMERCIAL_HUB": return 2 if m.river_at(p) else 0
    if kind == "HARBOR": return sum(m.resource(q) is not None for q in ns)
    if kind == "INDUSTRIAL_ZONE": return sum(m.resource(q) in STRATEGIC for q in ns)
    return 0


def capacity(pop): return 1 + (max(1, int(pop)) - 1) // 3


def ranked_centers(m):
    answer = []
    for ident in m.plots:
        c = (ident % m.w, ident // m.w)
        if not city_ok(m, c): continue
        region = nearby(m, c)
        vals = [max((intrinsic(m, k, p) for p in region if legal(m, k, p, [c])), default=0) for k in SCORING]
        answer.append((sum(sorted(vals, reverse=True)[:3]), c))
    return sorted(answer, key=lambda z: (-z[0], z[1][1], z[1][0]))


def center_plans(ranked, count):
    pool = ranked[:30]
    beam = [(0, ())]
    for _ in range(count):
        nxt = []
        for val, prior in beam:
            for gain, c in pool:
                if c not in prior: nxt.append((val + gain, prior + (c,)))
        nxt.sort(key=lambda z: (-z[0], z[1]))
        beam, seen = [], set()
        for item in nxt:
            if item[1] not in seen:
                beam.append(item); seen.add(item[1])
            if len(beam) >= 100: break
    return [p for _, p in beam]


def optimize(m, centers, pop):
    region = sorted(set().union(*(nearby(m, c) for c in centers)))
    candidates = {k: [p for p in region if legal(m, k, p, centers)] for k in KNOWN}
    cap, state, owners = capacity(pop), {}, {}
    used = [0] * len(centers)
    potentials = []
    for k in SCORING:
        if candidates[k]: potentials.append((max(intrinsic(m, k, p) for p in candidates[k]), k))
    potentials.sort(key=lambda z: (-z[0], z[1]))

    def add(kind, specialty=False, permit_equal=True):
        nonlocal state
        old_total = score(m, state, centers)[1]
        best = None
        for p in candidates[kind]:
            if p in state.values(): continue
            eligible = range(len(centers)) if specialty else [-1]
            for owner in eligible:
                if specialty and (used[owner] >= cap or m.distance(p, centers[owner]) > 3): continue
                trial = dict(state); trial[kind] = p
                value = score(m, trial, centers)[1]
                item = (value, p, owner)
                if best is None or item[0] > best[0] or (item[0] == best[0] and item[1] < best[1]): best = item
        if best is not None and (best[0] >= old_total if permit_equal else best[0] > old_total):
            state[kind] = best[1]; owners[kind] = best[2]
            if specialty: used[best[2]] += 1
            return True
        return False

    for _, kind in potentials:
        add(kind, True, True)
    # Canal is intentionally excluded: it is optional, scores zero itself, and must meet a strict connection rule.
    for kind in ("AQUEDUCT", "DAM", "NEIGHBORHOOD", "SPACEPORT"):
        add(kind, False, True)
    if not state:
        for kind in ("NEIGHBORHOOD", "AQUEDUCT", "SPACEPORT"):
            if add(kind, False, True): break
    # Deterministic local coordinate improvement, preserving each specialty's assigned-city capacity.
    for _ in range(3):
        improved = False
        for kind in list(state):
            old = state.pop(kind)
            old_total = score(m, state, centers)[1]
            best, bestv = old, score(m, {**state, kind: old}, centers)[1]
            for p in candidates[kind]:
                if p in state.values(): continue
                if kind in SPECIALTY and m.distance(p, centers[owners[kind]]) > 3: continue
                v = score(m, {**state, kind: p}, centers)[1]
                if v > bestv or (v == bestv and p < best): best, bestv = p, v
            state[kind] = best
            improved = improved or bestv > old_total
        if not improved: break
    bonuses, total = score(m, state, centers)
    return state, bonuses, total


def solve(scenario):
    m, n, pop = MapData(scenario["map_file"]), int(scenario["num_cities"]), int(scenario["population"])
    if n < 1: raise ValueError("num_cities must be positive")
    best = None
    for centers in center_plans(ranked_centers(m), n):
        state, bonuses, total = optimize(m, list(centers), pop)
        if state and (best is None or total > best[3]): best = (centers, state, bonuses, total)
    if best is None: raise ValueError("no legal nonempty placement layout found")
    centers, state, bonuses, total = best
    out = {"placements": {k: list(state[k]) for k in sorted(state)},
           "adjacency_bonuses": {k: bonuses[k] for k in sorted(state)}, "total_adjacency": total}
    if n == 1: out["city_center"] = list(centers[0])
    else: out["cities"] = [{"center": list(c)} for c in centers]
    return out


def coord(v, m): return isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in v) and 0 <= v[0] < m.w and 0 <= v[1] < m.h

def validate(scenario, out):
    errors = []
    try:
        if not isinstance(out, dict): return {"valid": False, "errors": ["solution must be an object"], "computed_adjacency_bonuses": {}, "computed_total_adjacency": 0}
        m, n, pop = MapData(scenario["map_file"]), int(scenario["num_cities"]), int(scenario["population"])
        rawcenters = [out.get("city_center")] if n == 1 and "cities" not in out else ([x.get("center") if isinstance(x, dict) else None for x in out.get("cities", [])] if n != 1 else [])
        if len(rawcenters) != n or not all(coord(x, m) for x in rawcenters): errors.append("wrong or invalid city centers"); centers = []
        else: centers = [tuple(x) for x in rawcenters]
        if len(set(centers)) != len(centers) or any(not city_ok(m, c) for c in centers): errors.append("illegal city center")
        raw = out.get("placements")
        if not isinstance(raw, dict) or not raw: errors.append("placements must be nonempty object"); raw = {}
        placements = {k: tuple(v) for k, v in raw.items() if k in KNOWN and coord(v, m)}
        if len(placements) != len(raw): errors.append("unknown or invalid district coordinate")
        if len(set(placements.values())) != len(placements) or set(placements.values()) & set(centers): errors.append("overlapping placement")
        for k, p in placements.items():
            if not legal(m, k, p, centers, set(placements.values()) - {p}): errors.append("illegal " + k)
        slots = [0] * n
        special = [(k, p) for k, p in placements.items() if k in SPECIALTY]
        def assign(i):
            if i == len(special): return True
            _, p = special[i]
            for j, c in enumerate(centers):
                if m.distance(p, c) <= 3 and slots[j] < capacity(pop):
                    slots[j] += 1
                    if assign(i + 1): return True
                    slots[j] -= 1
            return False
        if not assign(0): errors.append("per-city specialty capacity exceeded")
        expected, total = score(m, placements, centers)
        if out.get("adjacency_bonuses") != expected: errors.append("adjacency_bonuses differs from recomputation")
        if not isinstance(out.get("total_adjacency"), int) or isinstance(out.get("total_adjacency"), bool) or out.get("total_adjacency") != total: errors.append("total_adjacency differs from recomputation")
        return {"valid": not errors, "errors": errors, "computed_adjacency_bonuses": expected, "computed_total_adjacency": total}
    except Exception as exc:
        return {"valid": False, "errors": errors + [str(exc)], "computed_adjacency_bonuses": {}, "computed_total_adjacency": 0}


def load_scenario(path):
    with open(path, encoding="utf-8") as f: s = json.load(f)
    mp = s.get("map_file")
    if not mp: raise ValueError("scenario is missing map_file")
    if not os.path.isabs(mp):
        local = os.path.normpath(os.path.join(os.path.dirname(path), mp))
        s["map_file"] = local if os.path.exists(local) else os.path.join("/data/maps", os.path.basename(mp))
    return s


def main():
    req = json.load(sys.stdin)
    scenario = load_scenario(req["scenario_path"])
    if req.get("action", "solve") == "validate":
        solution = req.get("solution")
        if solution is None:
            with open(req["solution_path"], encoding="utf-8") as f: solution = json.load(f)
        print(json.dumps(validate(scenario, solution), sort_keys=True)); return
    if req.get("action", "solve") != "solve": raise ValueError("action must be solve or validate")
    answer = solve(scenario)
    destination = req.get("output_path")
    if destination:
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        with open(destination, "w", encoding="utf-8") as f: json.dump(answer, f, indent=2, sort_keys=True); f.write("\n")
        with open(destination, encoding="utf-8") as f: report = validate(scenario, json.load(f))
        if not report["valid"]: raise ValueError("written artifact failed validation: " + "; ".join(report["errors"]))
    print(json.dumps(answer, sort_keys=True))

if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)})); sys.exit(1)
