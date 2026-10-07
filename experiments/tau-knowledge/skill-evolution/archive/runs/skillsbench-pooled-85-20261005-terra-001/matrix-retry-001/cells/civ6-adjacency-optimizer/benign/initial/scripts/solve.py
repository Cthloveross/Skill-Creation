#!/usr/bin/env python3
"""Civ6 map-only district optimizer and validator.
stdin: {action: solve|validate, scenario_path, output_path?, solution_path?|solution?}
stdout: solution for solve; validation report for validate.
"""
import itertools
import json
import math
import os
import random
import sqlite3
import sys

SCORING = {"CAMPUS", "HOLY_SITE", "COMMERCIAL_HUB", "INDUSTRIAL_ZONE", "HARBOR", "THEATER_SQUARE"}
SPECIALTY = SCORING | {"ENTERTAINMENT_COMPLEX", "ENCAMPMENT", "AERODROME", "GOVERNMENT_PLAZA", "DIPLOMATIC_QUARTER", "PRESERVE", "WATER_PARK"}
DESTROYED_FEATURES = {"FEATURE_FOREST", "FEATURE_JUNGLE", "FEATURE_MARSH"}
BONUS_RESOURCES = {
    "RESOURCE_BANANAS", "RESOURCE_CATTLE", "RESOURCE_COPPER", "RESOURCE_CRABS",
    "RESOURCE_DEER", "RESOURCE_FISH", "RESOURCE_MAIZE", "RESOURCE_RICE",
    "RESOURCE_SHEEP", "RESOURCE_STONE", "RESOURCE_WHEAT",
}
STRATEGIC_RESOURCES = {
    "RESOURCE_HORSES", "RESOURCE_IRON", "RESOURCE_NITER", "RESOURCE_COAL",
    "RESOURCE_OIL", "RESOURCE_ALUMINUM", "RESOURCE_URANIUM",
}
# Standard-feature whitelist lets ordinary removable features remain legal district sites.
ORDINARY_FEATURES = {
    "FEATURE_FOREST", "FEATURE_JUNGLE", "FEATURE_MARSH", "FEATURE_REEF", "FEATURE_ICE",
    "FEATURE_GEOTHERMAL_FISSURE", "FEATURE_FLOODPLAINS", "FEATURE_OASIS",
    "FEATURE_FLOODPLAINS_GRASSLAND", "FEATURE_FLOODPLAINS_PLAINS",
}


def table_rows(con, table):
    names = {r[0].lower(): r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    actual = names.get(table.lower())
    if not actual:
        return []
    return con.execute('SELECT * FROM "' + actual.replace('"', '""') + '"').fetchall()


def val(row, key, default=None):
    for k in row.keys():
        if k.lower() == key.lower():
            return row[k]
    return default


class CivMap:
    def __init__(self, filename):
        con = sqlite3.connect(filename)
        con.row_factory = sqlite3.Row
        maps = table_rows(con, "Map")
        if not maps:
            raise ValueError("Civ6Map has no Map table")
        self.w = int(val(maps[0], "Width"))
        self.h = int(val(maps[0], "Height"))
        self.wrapx = bool(val(maps[0], "WrapX", 0))
        self.wrapy = bool(val(maps[0], "WrapY", 0))
        self.plots, self.features, self.resources, self.rivers = {}, {}, {}, {}
        for r in table_rows(con, "Plots"):
            pid = val(r, "ID")
            if pid is not None:
                self.plots[int(pid)] = {"terrain": str(val(r, "TerrainType", "") or ""), "imp": bool(val(r, "IsImpassable", 0))}
        for r in table_rows(con, "PlotFeatures"):
            pid = val(r, "ID")
            if pid is not None:
                self.features[int(pid)] = str(val(r, "FeatureType", "") or "")
        for r in table_rows(con, "PlotResources"):
            pid = val(r, "ID")
            if pid is not None:
                self.resources[int(pid)] = str(val(r, "ResourceType", "") or "")
        for r in table_rows(con, "PlotRivers"):
            pid = val(r, "ID")
            if pid is not None:
                self.rivers[int(pid)] = (bool(val(r, "IsNEOfRiver", 0)), bool(val(r, "IsWOfRiver", 0)), bool(val(r, "IsNWOfRiver", 0)))
        con.close()
        if not self.plots:
            raise ValueError("Civ6Map has no readable Plots rows")

    def norm(self, p):
        x, y = p
        if self.wrapx:
            x %= self.w
        if self.wrapy:
            y %= self.h
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return None
        q = y * self.w + x
        return (x, y) if q in self.plots else None

    def pid(self, p): return p[1] * self.w + p[0]
    def plot(self, p): return self.plots.get(self.pid(p), {"terrain": "", "imp": True})
    def terrain(self, p): return self.plot(p)["terrain"]
    def feature(self, p): return self.features.get(self.pid(p), "")
    def resource(self, p): return self.resources.get(self.pid(p), "")

    def neighbors(self, p):
        x, y = p
        ds = [(1,0), (0,-1), (-1,-1), (-1,0), (-1,1), (0,1)] if y % 2 == 0 else [(1,0), (1,-1), (0,-1), (-1,0), (0,1), (1,1)]
        return [z for z in (self.norm((x + dx, y + dy)) for dx, dy in ds) if z is not None]

    def direction_neighbor(self, p, direction):
        # E, NE, NW, W, SW, SE follow the order in neighbors().
        ns = self.neighbors(p)
        raw = {"E": 0, "NE": 1, "NW": 2, "W": 3, "SW": 4, "SE": 5}[direction]
        x, y = p
        ds = [(1,0), (0,-1), (-1,-1), (-1,0), (-1,1), (0,1)] if y % 2 == 0 else [(1,0), (1,-1), (0,-1), (-1,0), (0,1), (1,1)]
        return self.norm((x + ds[raw][0], y + ds[raw][1]))

    def cube(self, p):
        x, y = p
        q = x - ((y - (y & 1)) // 2)
        return q, y, -q-y

    def distance(self, a, b):
        # For wrapped maps test translated copies; normal maps take the direct formula.
        optsx = [0] if not self.wrapx else [-self.w, 0, self.w]
        optsy = [0] if not self.wrapy else [-self.h, 0, self.h]
        aq, ar, az = self.cube(a)
        best = 10**9
        for dx in optsx:
            for dy in optsy:
                bq, br, bz = self.cube((b[0]+dx, b[1]+dy))
                best = min(best, max(abs(aq-bq), abs(ar-br), abs(az-bz)))
        return best

    def is_water(self, p):
        t = self.terrain(p)
        return "COAST" in t or "OCEAN" in t or "LAKE" in t

    def is_mountain(self, p): return "MOUNTAIN" in self.terrain(p)
    def is_hill(self, p): return "HILLS" in self.terrain(p)

    def river_edges(self, p):
        """Number of known river edges touching p, using the three stored and complements."""
        own = self.rivers.get(self.pid(p), (False, False, False))
        edges = int(own[0]) + int(own[1]) + int(own[2])
        # Opposite edges are stored on the E, SE, and SW adjacent plot respectively.
        for direction, flag_index in (("E", 1), ("SE", 2), ("SW", 0)):
            n = self.direction_neighbor(p, direction)
            if n:
                flags = self.rivers.get(self.pid(n), (False, False, False))
                edges += int(flags[flag_index])
        return edges

    def has_river(self, p): return self.river_edges(p) > 0


def natural_wonder(feature):
    if not feature or feature in ORDINARY_FEATURES:
        return False
    # Map natural wonders are FEATURE_* entries not among normal removable/map features.
    return feature.startswith("FEATURE_")


def is_bonus(res): return res in BONUS_RESOURCES

def is_strategic(res): return res in STRATEGIC_RESOURCES

def blocked_resource(res): return bool(res) and not is_bonus(res)


def source_feature(m, p, occupied, centers):
    """Feature after district destruction; City Center preserves its tile."""
    if p in occupied and p not in centers and m.feature(p) in DESTROYED_FEATURES:
        return ""
    return m.feature(p)


def source_resource(m, p, occupied, centers):
    if p in occupied and p not in centers and is_bonus(m.resource(p)):
        return ""
    return m.resource(p)


def city_legal(m, p):
    if m.is_water(p) or m.is_mountain(p) or m.plot(p)["imp"]:
        return False
    f = m.feature(p)
    return f != "FEATURE_ICE" and not natural_wonder(f)


def fresh_adjacent(m, p):
    for n in m.neighbors(p):
        if m.is_mountain(n) or "LAKE" in m.terrain(n) or m.feature(n) == "FEATURE_OASIS" or m.has_river(n):
            return True
    return m.has_river(p)


def district_legal(m, typ, p, centers, occupied):
    if p in occupied or p in centers or not any(m.distance(p, c) <= 3 for c in centers):
        return False
    f, r = m.feature(p), m.resource(p)
    water = m.is_water(p)
    if typ in {"HARBOR", "WATER_PARK"}:
        if not water or not any(not m.is_water(n) for n in m.neighbors(p)):
            return False
    else:
        if water or m.is_mountain(p) or m.plot(p)["imp"]:
            return False
    if natural_wonder(f) or f == "FEATURE_GEOTHERMAL_FISSURE" or blocked_resource(r):
        return False
    if typ in {"AERODROME", "SPACEPORT"} and (m.is_hill(p) or water): return False
    if typ in {"ENCAMPMENT", "PRESERVE"} and any(m.distance(p, c) == 1 for c in centers): return False
    if typ == "AQUEDUCT" and (not any(m.distance(p, c) == 1 for c in centers) or not fresh_adjacent(m, p)):
        return False
    if typ == "DAM" and ("FLOODPLAINS" not in f or m.river_edges(p) < 2): return False
    return True


def adjacency(m, typ, p, placements, centers):
    occupied = set(placements.values())
    ns = m.neighbors(p)
    district_count = sum(1 for n in ns if n in occupied or n in centers)
    minor = district_count // 2
    feats = [source_feature(m, n, occupied, centers) for n in ns]
    resources = [source_resource(m, n, occupied, centers) for n in ns]
    types_at = {n: t for t, n in placements.items()}
    if typ == "CAMPUS":
        return (2 * sum(1 for f in feats if "GEOTHERMAL" in f or "REEF" in f) +
                sum(1 for n in ns if m.is_mountain(n)) + sum(1 for f in feats if f == "FEATURE_JUNGLE") // 2 + minor)
    if typ == "HOLY_SITE":
        return (2 * sum(1 for f in feats if natural_wonder(f)) + sum(1 for n in ns if m.is_mountain(n)) +
                sum(1 for f in feats if f == "FEATURE_FOREST") // 2 + minor)
    if typ == "COMMERCIAL_HUB":
        return (2 if m.has_river(p) else 0) + 2 * sum(1 for n in ns if types_at.get(n) == "HARBOR") + minor
    if typ == "INDUSTRIAL_ZONE":
        major = sum(1 for n in ns if types_at.get(n) in {"AQUEDUCT", "BATH", "DAM", "CANAL"}) * 2
        major += sum(1 for r in resources if is_strategic(r))
        # Mines, lumber mills, and quarries deliberately contribute zero: maps do not store improvements.
        return major + minor
    if typ == "HARBOR":
        coastal = sum(1 for n, r in zip(ns, resources) if r and m.is_water(n))
        return 2 * sum(1 for n in ns if n in centers) + coastal + minor
    if typ == "THEATER_SQUARE":
        return 2 * sum(1 for n in ns if types_at.get(n) in {"ENTERTAINMENT_COMPLEX", "WATER_PARK"}) + minor
    return 0


def score_layout(m, placements, centers):
    bonuses = {t: int(adjacency(m, t, p, placements, centers)) for t, p in placements.items()}
    return bonuses, sum(bonuses.values())


def intrinsic(m, typ, p):
    ns = m.neighbors(p)
    fs = [m.feature(n) for n in ns]
    if typ == "CAMPUS": return 2*sum("GEOTHERMAL" in f or "REEF" in f for f in fs) + sum(m.is_mountain(n) for n in ns) + sum(f == "FEATURE_JUNGLE" for f in fs)//2
    if typ == "HOLY_SITE": return 2*sum(natural_wonder(f) for f in fs) + sum(m.is_mountain(n) for n in ns) + sum(f == "FEATURE_FOREST" for f in fs)//2
    if typ == "COMMERCIAL_HUB": return 2 if m.has_river(p) else 0
    if typ == "HARBOR": return sum(bool(m.resource(n)) and m.is_water(n) for n in ns)
    return 0


def specialty_cap(pop): return 1 + max(0, (int(pop) - 1) // 3)


def legal_sites(m):
    return [(pid % m.w, pid // m.w) for pid in m.plots]


def rank_centers(m):
    ranked = []
    for c in legal_sites(m):
        if not city_legal(m, c): continue
        near = [p for p in legal_sites(m) if m.distance(c, p) <= 3]
        values = []
        for typ in SCORING:
            values.append(max((intrinsic(m, typ, p) for p in near if district_legal(m, typ, p, [c], set())), default=0))
        ranked.append((sum(sorted(values, reverse=True)[:3]), c))
    ranked.sort(key=lambda z: (-z[0], z[1][1], z[1][0]))
    return [p for _, p in ranked]


def candidate_plans(center_pool, n):
    pool = center_pool[:min(24, len(center_pool))]
    if n == 1: return [(p,) for p in pool[:80]]
    combos = list(itertools.combinations(pool, n))
    if len(combos) <= 220: return combos
    # Keep high-ranked early combinations plus a deterministic spread over the remainder.
    chosen = combos[:120]
    step = max(1, len(combos) // 100)
    chosen.extend(combos[i] for i in range(0, len(combos), step))
    out, seen = [], set()
    for x in chosen:
        if x not in seen: out.append(x); seen.add(x)
        if len(out) >= 220: break
    return out


def optimize_for_centers(m, centers, pop, seed=0):
    cap = specialty_cap(pop)
    total_cap = cap * len(centers)
    allsites = legal_sites(m)
    # Select the scoring district types with the best terrain-only opportunities.
    potential = []
    for typ in SCORING:
        best = max((intrinsic(m, typ, p) for p in allsites if district_legal(m, typ, p, centers, set())), default=-999)
        if best >= 0: potential.append((best, typ))
    potential.sort(key=lambda z: (-z[0], z[1]))
    chosen = [t for _, t in potential[:min(total_cap, len(potential))]]
    # Add only rule-supported free infrastructure. It can create generic district minors and IZ majors.
    types = list(chosen)
    for t in ("AQUEDUCT", "DAM", "NEIGHBORHOOD"):
        if any(district_legal(m, t, p, centers, set()) for p in allsites): types.append(t)
    # Candidate (coordinate, owning-city) records. Ownership enforces capacity during optimization.
    candidates = {}
    for t in types:
        arr = []
        for owner, c in enumerate(centers):
            for p in allsites:
                if m.distance(p, c) <= 3 and district_legal(m, t, p, centers, set()):
                    arr.append((p, owner))
        # unique records only; keeping all radius-three tiles avoids pruning useful cluster positions.
        candidates[t] = list(dict.fromkeys(arr))
        if not candidates[t]: return None

    rng = random.Random(seed + sum(x*131+y*17 for x, y in centers))
    best_state, best_total = None, -1
    base_order = sorted(types, key=lambda t: (0 if t in SCORING else 1, -max((intrinsic(m, t, p) for p, _ in candidates[t]), default=0), t))

    def valid_add(t, item, state, owners):
        p, owner = item
        if p in state.values(): return False
        return t not in SPECIALTY or owners[owner] < cap

    def total(state): return score_layout(m, state, centers)[1]

    for restart in range(5):
        order = base_order[:]
        if restart: rng.shuffle(order)
        state, owner_of = {}, {}
        owners = [0] * len(centers)
        for t in order:
            choices = candidates[t][:]
            if restart: rng.shuffle(choices)
            local_best, local_score = None, -10**9
            for item in choices:
                if not valid_add(t, item, state, owners): continue
                trial = dict(state); trial[t] = item[0]
                s = total(trial)
                if s > local_score:
                    local_score, local_best = s, item
            if local_best is None: break
            state[t], owner_of[t] = local_best
            if t in SPECIALTY: owners[local_best[1]] += 1
        if len(state) != len(types): continue
        current = total(state)
        # Coordinate local search; all candidates are legal relative to centers. Recheck overlaps/capacity.
        improved = True
        passes = 0
        while improved and passes < 12:
            improved = False; passes += 1
            sweep = types[:]
            rng.shuffle(sweep)
            for t in sweep:
                oldp, oldowner = state[t], owner_of[t]
                if t in SPECIALTY: owners[oldowner] -= 1
                del state[t]
                candidate_best, candidate_score = (oldp, oldowner), -10**9
                for item in candidates[t]:
                    if not valid_add(t, item, state, owners): continue
                    state[t] = item[0]
                    s = total(state)
                    del state[t]
                    if s > candidate_score:
                        candidate_score, candidate_best = s, item
                state[t], owner_of[t] = candidate_best
                if t in SPECIALTY: owners[candidate_best[1]] += 1
                if candidate_score > current:
                    current = candidate_score; improved = True
        if current > best_total:
            best_total, best_state = current, dict(state)
    if best_state is None: return None
    bonuses, total_value = score_layout(m, best_state, centers)
    return best_state, bonuses, total_value


def solve(scenario):
    map_path = scenario.get("map_file")
    if not map_path: raise ValueError("scenario is missing map_file")
    m = CivMap(map_path)
    n = int(scenario.get("num_cities", 1))
    pop = int(scenario.get("population", 1))
    if n < 1: raise ValueError("num_cities must be at least 1")
    ranked = rank_centers(m)
    if len(ranked) < n: raise ValueError("map has fewer legal city-center tiles than requested cities")
    best = None
    for centers in candidate_plans(ranked, n):
        result = optimize_for_centers(m, list(centers), pop)
        if result and (best is None or result[2] > best[2]): best = (list(centers),) + result
    if best is None: raise ValueError("could not construct a legal layout from the map")
    centers, placements, bonuses, total_value = best
    out = {"placements": {t: [p[0], p[1]] for t, p in sorted(placements.items())},
           "adjacency_bonuses": {t: int(bonuses[t]) for t in sorted(placements)},
           "total_adjacency": int(total_value)}
    if len(centers) == 1: out["city_center"] = list(centers[0])
    else: out["cities"] = [{"center": list(c)} for c in centers]
    return out


def extract_centers(solution):
    if "city_center" in solution:
        return [tuple(solution["city_center"])]
    return [tuple(x["center"]) for x in solution.get("cities", []) if isinstance(x, dict) and "center" in x]


def validate(scenario, solution):
    try:
        m = CivMap(scenario["map_file"])
        centers = extract_centers(solution)
        want_n = int(scenario.get("num_cities", 1))
        errors = []
        if len(centers) != want_n: errors.append("wrong number of city centers")
        if len(set(centers)) != len(centers): errors.append("city centers overlap")
        for c in centers:
            if m.norm(c) != c or not city_legal(m, c): errors.append("illegal city center: %r" % (c,))
        raw = solution.get("placements")
        if not isinstance(raw, dict):
            errors.append("placements must be an object"); raw = {}
        placements = {}
        for t, xy in raw.items():
            try: placements[t] = tuple(xy)
            except Exception: errors.append("invalid coordinate for " + str(t))
        occupied = set()
        for t, p in placements.items():
            if m.norm(p) != p or not district_legal(m, t, p, centers, occupied): errors.append("illegal placement for %s: %r" % (t, p))
            if p in occupied: errors.append("district placements overlap")
            occupied.add(p)
        cap = specialty_cap(int(scenario.get("population", 1)))
        # Output lacks ownership. Conservatively verify that specialty placements can be assigned to centers in range.
        counts = [0] * len(centers)
        for t, p in placements.items():
            if t in SPECIALTY:
                viable = [i for i, c in enumerate(centers) if m.distance(p, c) <= 3 and counts[i] < cap]
                if not viable: errors.append("specialty district capacity exceeded")
                else: counts[min(viable, key=lambda i: counts[i])] += 1
        bonuses, total_value = score_layout(m, placements, centers)
        reported = solution.get("adjacency_bonuses", {})
        if reported != bonuses: errors.append("adjacency_bonuses does not equal independently computed bonuses")
        if solution.get("total_adjacency") != total_value: errors.append("total_adjacency does not equal independently computed total")
        if isinstance(reported, dict) and sum(reported.values()) != solution.get("total_adjacency"): errors.append("reported adjacency sum differs from total")
        return {"valid": not errors, "errors": errors, "computed_adjacency_bonuses": bonuses, "computed_total_adjacency": total_value}
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)], "computed_adjacency_bonuses": {}, "computed_total_adjacency": 0}


def main():
    req = json.load(sys.stdin)
    action = req.get("action", "solve")
    scenario_path = req.get("scenario_path")
    if not scenario_path: raise ValueError("scenario_path is required")
    with open(scenario_path, encoding="utf-8") as f: scenario = json.load(f)
    mp = scenario.get("map_file", "")
    if mp and not os.path.isabs(mp): scenario["map_file"] = os.path.normpath(os.path.join(os.path.dirname(scenario_path), mp))
    if action == "validate":
        solution = req.get("solution")
        if solution is None:
            with open(req["solution_path"], encoding="utf-8") as f: solution = json.load(f)
        print(json.dumps(validate(scenario, solution), sort_keys=True))
        return
    if action != "solve": raise ValueError("action must be solve or validate")
    answer = solve(scenario)
    outpath = req.get("output_path")
    if outpath:
        os.makedirs(os.path.dirname(outpath) or ".", exist_ok=True)
        with open(outpath, "w", encoding="utf-8") as f: json.dump(answer, f, indent=2, sort_keys=True); f.write("\n")
    print(json.dumps(answer, sort_keys=True))

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
