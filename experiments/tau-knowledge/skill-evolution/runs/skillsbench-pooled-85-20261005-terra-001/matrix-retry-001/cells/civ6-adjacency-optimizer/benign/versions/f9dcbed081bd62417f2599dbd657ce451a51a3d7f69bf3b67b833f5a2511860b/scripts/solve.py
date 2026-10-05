#!/usr/bin/env python3
"""Civ6 map-only district placement optimizer.

stdin schema:
  {"action":"solve", "scenario_path":str, "output_path"?:str}
  {"action":"validate", "scenario_path":str,
   "solution_path"?:str, "solution"?:object}
stdout schema:
  solve: the task solution object
  validate: {valid, errors, computed_adjacency_bonuses, computed_total_adjacency}
"""
import itertools
import json
import os
import sqlite3
import sys

SPECIALTY = {
    "CAMPUS", "HOLY_SITE", "THEATER_SQUARE", "COMMERCIAL_HUB", "HARBOR",
    "INDUSTRIAL_ZONE", "ENTERTTAINMENT_COMPLEX", "ENTERTAINMENT_COMPLEX",
    "WATER_PARK", "ENCAMPMENT", "AERODROME", "GOVERNMENT_PLAZA",
    "DIPLOMATIC_QUARTER", "PRESERVE",
}
NON_SPECIALTY = {"AQUEDUCT", "DAM", "CANAL", "SPACEPORT", "NEIGHBORHOOD"}
KNOWN = SPECIALTY | NON_SPECIALTY
WATER_DISTRICTS = {"HARBOR", "WATER_PARK"}
FLAT_ONLY = {"AERODROME", "SPACEPORT"}
SCORING = {"CAMPUS", "HOLY_SITE", "THEATER_SQUARE", "COMMERCIAL_HUB", "HARBOR", "INDUSTRIAL_ZONE"}
NATURAL_WONDERS = {
    "FEATURE_BARRIER_REEF", "FEATURE_GREAT_BARRIER_REEF", "FEATURE_CRATER_LAKE",
    "FEATURE_DELICATE_ARCH", "FEATURE_EYE_OF_THE_SAHARA", "FEATURE_GALAPAGOS",
    "FEATURE_GIANTS_CAUSEWAY", "FEATURE_LAKE_RETBA", "FEATURE_MATTERHORN",
    "FEATURE_MOUNT_EVEREST", "FEATURE_PAITITI", "FEATURE_PIOPIOTAHI",
    "FEATURE_PANTANAL", "FEATURE_RORAIMA", "FEATURE_TORRES_DEL_PAINE",
    "FEATURE_TSINGY", "FEATURE_UBSUNUR_HOLLOW", "FEATURE_ULURU",
    "FEATURE_YOSEMITE", "FEATURE_ZHANGYE_DANXIA",
}
STRATEGIC = {
    "RESOURCE_HORSES", "RESOURCE_IRON", "RESOURCE_NITER", "RESOURCE_COAL",
    "RESOURCE_OIL", "RESOURCE_ALUMINUM", "RESOURCE_URANIUM",
}
LUXURY = {
    "RESOURCE_AMBER", "RESOURCE_CITRUS", "RESOURCE_COCOA", "RESOURCE_COFFEE",
    "RESOURCE_COTTON", "RESOURCE_DYES", "RESOURCE_DIAMONDS", "RESOURCE_FURS",
    "RESOURCE_GYPSUM", "RESOURCE_INCENSE", "RESOURCE_IVORY", "RESOURCE_JADE",
    "RESOURCE_MARBLE", "RESOURCE_MERCURY", "RESOURCE_PEARLS", "RESOURCE_SALT",
    "RESOURCE_SILK", "RESOURCE_SILVER", "RESOURCE_SPICES", "RESOURCE_SUGAR",
    "RESOURCE_TEA", "RESOURCE_TOBACCO", "RESOURCE_TRUFFLES", "RESOURCE_WHALES",
    "RESOURCE_WINE", "RESOURCE_CINNAMON", "RESOURCE_CLOVES", "RESOURCE_COSMETICS",
    "RESOURCE_JEANS", "RESOURCE_OLIVES", "RESOURCE_PERFUME", "RESOURCE_TOYS",
}


def field(row, name, default=None):
    for key in row.keys():
        if key.lower() == name.lower():
            return row[key]
    return default


class CivMap:
    def __init__(self, path):
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        try:
            meta = con.execute('SELECT * FROM "Map"').fetchone()
            if meta is None:
                raise ValueError("Map table has no metadata row")
            self.w = int(field(meta, "Width"))
            self.h = int(field(meta, "Height"))
            self.wrapx = bool(field(meta, "WrapX", 0))
            self.wrapy = bool(field(meta, "WrapY", 0))
            self.plots = {}
            self.features = {}
            self.resources = {}
            self.rivers = {}
            for row in con.execute('SELECT * FROM "Plots"'):
                ident = field(row, "ID")
                if ident is not None:
                    self.plots[int(ident)] = {
                        "terrain": field(row, "TerrainType", ""),
                        "impassable": bool(field(row, "IsImpassable", 0)),
                    }
            for row in con.execute('SELECT * FROM "PlotFeatures"'):
                ident = field(row, "ID")
                if ident is not None:
                    self.features[int(ident)] = field(row, "FeatureType")
            for row in con.execute('SELECT * FROM "PlotResources"'):
                ident = field(row, "ID")
                if ident is not None:
                    self.resources[int(ident)] = field(row, "ResourceType")
            for row in con.execute('SELECT * FROM "PlotRivers"'):
                ident = field(row, "ID")
                if ident is not None:
                    self.rivers[int(ident)] = {
                        "IsNEOfRiver": bool(field(row, "IsNEOfRiver", 0)),
                        "IsWOfRiver": bool(field(row, "IsWOfRiver", 0)),
                        "IsNWOfRiver": bool(field(row, "IsNWOfRiver", 0)),
                    }
        finally:
            con.close()
        if not self.plots:
            raise ValueError("Plots table is empty")

    def pid(self, p):
        return p[1] * self.w + p[0]

    def norm(self, p):
        x, y = p
        if self.wrapx:
            x %= self.w
        if self.wrapy:
            y %= self.h
        if not (0 <= x < self.w and 0 <= y < self.h):
            return None
        q = (x, y)
        return q if self.pid(q) in self.plots else None

    def terrain(self, p):
        return self.plots[self.pid(p)]["terrain"]

    def feature(self, p):
        return self.features.get(self.pid(p))

    def resource(self, p):
        return self.resources.get(self.pid(p))

    def neighbors(self, p):
        x, y = p
        offsets = ([(1, 0), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1)]
                   if y % 2 == 0 else
                   [(1, 0), (1, -1), (0, -1), (-1, 0), (0, 1), (1, 1)])
        ans = []
        for dx, dy in offsets:
            q = self.norm((x + dx, y + dy))
            if q is not None:
                ans.append(q)
        return ans

    def distance(self, a, b):
        # City-range validation uses the ordinary odd-r cube distance, not a wrapped shortcut.
        def cube(p):
            x, y = p
            q = x - (y - (y % 2)) // 2
            return q, y, -q - y
        aa, bb = cube(a), cube(b)
        return max(abs(aa[i] - bb[i]) for i in range(3))

    def water(self, p):
        return self.terrain(p) in ("TERRAIN_COAST", "TERRAIN_OCEAN", "TERRAIN_LAKE")

    def mountain(self, p):
        terrain = self.terrain(p)
        return terrain is not None and terrain.endswith("_MOUNTAIN")

    def river_at(self, p):
        # This deliberately matches the supplied map-evaluator representation.
        own = self.rivers.get(self.pid(p), {})
        if own.get("IsNEOfRiver") or own.get("IsWOfRiver") or own.get("IsNWOfRiver"):
            return True
        x, y = p
        east = ((x + 1) % self.w if self.wrapx else x + 1, y)
        return 0 <= east[0] < self.w and bool(self.rivers.get(self.pid(east), {}).get("IsWOfRiver"))


def is_mountain(m, p):
    return m.mountain(p)


def city_legal(m, p):
    return (m.norm(p) == p and not m.water(p) and not m.mountain(p)
            and not m.plots[m.pid(p)]["impassable"]
            and m.feature(p) != "FEATURE_ICE" and m.feature(p) not in NATURAL_WONDERS)


def fresh_water(m, p):
    if m.river_at(p):
        return True
    for q in m.neighbors(p):
        if (m.mountain(q) or m.feature(q) == "FEATURE_OASIS"
                or m.terrain(q) == "TERRAIN_LAKE"):
            return True
    return False


def district_legal(m, kind, p, centers, occupied=frozenset()):
    if kind not in KNOWN or m.norm(p) != p or p in occupied or p in centers:
        return False
    if not any(m.distance(p, c) <= 3 for c in centers):
        return False
    terrain, feature, resource = m.terrain(p), m.feature(p), m.resource(p)
    if m.mountain(p) or feature in NATURAL_WONDERS or feature == "FEATURE_GEOTHERMAL_FISSURE":
        return False
    if resource in STRATEGIC or resource in LUXURY:
        return False
    if kind in WATER_DISTRICTS:
        if not m.water(p) or not any(not m.water(q) for q in m.neighbors(p)):
            return False
    elif m.water(p):
        return False
    if kind in FLAT_ONLY and terrain.endswith("_HILLS"):
        return False
    if kind in {"ENCAMPMENT", "PRESERVE"} and any(m.distance(p, c) == 1 for c in centers):
        return False
    if kind == "AQUEDUCT":
        if not any(m.distance(p, c) == 1 for c in centers) or not fresh_water(m, p):
            return False
    if kind == "DAM" and feature != "FEATURE_FLOODPLAINS":
        return False
    return True


def score(m, placements, centers):
    """Recompute the evaluator's post-destruction adjacency values."""
    destroyed = set(placements.values())
    all_districts = destroyed | set(centers)

    def feat(q):
        return None if q in destroyed else m.feature(q)

    result = {}
    for kind, p in placements.items():
        adjacent = m.neighbors(p)
        district_count = sum(q in all_districts for q in adjacent)
        value = 0
        if kind == "CAMPUS":
            value = 2 * sum(feat(q) in {
                "FEATURE_GEOTHERMAL_FISSURE", "FEATURE_REEF", "FEATURE_BARRIER_REEF",
                "FEATURE_GREAT_BARRIER_REEF",
            } for q in adjacent)
            value += sum(m.mountain(q) for q in adjacent)
            value += sum(feat(q) == "FEATURE_JUNGLE" for q in adjacent) // 2
            value += district_count // 2
        elif kind == "HOLY_SITE":
            value = 2 * sum(feat(q) in NATURAL_WONDERS for q in adjacent)
            value += sum(m.mountain(q) for q in adjacent)
            value += sum(feat(q) == "FEATURE_FOREST" for q in adjacent) // 2
            value += district_count // 2
        elif kind == "COMMERCIAL_HUB":
            value = (2 if m.river_at(p) else 0)
            value += 2 * sum(placements.get("HARBOR") == q for q in adjacent)
            value += district_count // 2
        elif kind == "INDUSTRIAL_ZONE":
            value = 2 * sum(q == placements.get("AQUEDUCT") or q == placements.get("DAM")
                            or q == placements.get("CANAL") for q in adjacent)
            value += sum(m.resource(q) in STRATEGIC for q in adjacent)
            value += district_count // 2
        elif kind == "HARBOR":
            value = 2 * sum(q in centers for q in adjacent)
            value += sum(m.resource(q) is not None for q in adjacent)
            value += district_count // 2
        elif kind == "THEATER_SQUARE":
            value = 2 * sum(q == placements.get("ENTERTAINMENT_COMPLEX")
                            or q == placements.get("WATER_PARK") for q in adjacent)
            value += district_count // 2
        result[kind] = int(value)
    return result, int(sum(result.values()))


def nearby(m, center):
    """All map plots at evaluator distance <= 3 from center."""
    ans = set()
    x, y = center
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            p = m.norm((x + dx, y + dy))
            if p is not None and m.distance(p, center) <= 3:
                ans.add(p)
    return sorted(ans)


def intrinsic(m, kind, p):
    adj = m.neighbors(p)
    if kind == "CAMPUS":
        return (2 * sum(m.feature(q) in {"FEATURE_GEOTHERMAL_FISSURE", "FEATURE_REEF", "FEATURE_BARRIER_REEF", "FEATURE_GREAT_BARRIER_REEF"} for q in adj)
                + sum(m.mountain(q) for q in adj) + sum(m.feature(q) == "FEATURE_JUNGLE" for q in adj) // 2)
    if kind == "HOLY_SITE":
        return (2 * sum(m.feature(q) in NATURAL_WONDERS for q in adj)
                + sum(m.mountain(q) for q in adj) + sum(m.feature(q) == "FEATURE_FOREST" for q in adj) // 2)
    if kind == "COMMERCIAL_HUB":
        return 2 if m.river_at(p) else 0
    if kind == "INDUSTRIAL_ZONE":
        return sum(m.resource(q) in STRATEGIC for q in adj)
    if kind == "HARBOR":
        return sum(m.resource(q) is not None for q in adj)
    return 0


def specialty_cap(population):
    return 1 + (max(1, int(population)) - 1) // 3


def rank_centers(m):
    ranked = []
    for pid in m.plots:
        c = (pid % m.w, pid // m.w)
        if not city_legal(m, c):
            continue
        region = nearby(m, c)
        values = []
        for kind in SCORING:
            values.append(max((intrinsic(m, kind, p) for p in region
                               if district_legal(m, kind, p, [c])), default=0))
        # A small density component avoids selecting feature sites with no room for support districts.
        legal_land = sum(district_legal(m, "NEIGHBORHOOD", p, [c]) for p in region)
        ranked.append((sum(sorted(values, reverse=True)[:3]) * 20 + legal_land, c))
    ranked.sort(key=lambda item: (-item[0], item[1][1], item[1][0]))
    return [c for _, c in ranked]


def center_plans(ranked, n):
    pool = ranked[:min(30, len(ranked))]
    if n == 1:
        return [(c,) for c in pool]
    if len(pool) < n:
        return []
    combos = list(itertools.combinations(pool, n))
    if len(combos) <= 180:
        return combos
    # Keep both the strongest-ranked prefix and a deterministic spread.
    selected = combos[:100]
    step = max(1, len(combos) // 80)
    selected.extend(combos[i] for i in range(0, len(combos), step))
    out, seen = [], set()
    for item in selected:
        if item not in seen:
            out.append(item)
            seen.add(item)
        if len(out) == 180:
            break
    return out


def optimize_for_centers(m, centers, population):
    region = sorted(set().union(*(nearby(m, c) for c in centers)))
    candidates = {}
    for kind in KNOWN:
        candidates[kind] = [p for p in region if district_legal(m, kind, p, centers)]

    cap = len(centers) * specialty_cap(population)
    specialty_options = []
    for kind in SCORING:
        if candidates[kind]:
            specialty_options.append((max(intrinsic(m, kind, p) for p in candidates[kind]), kind))
    specialty_options.sort(key=lambda x: (-x[0], x[1]))
    chosen_specialty = [kind for _, kind in specialty_options[:cap]]

    # Free support districts are useful generic neighbors and are always scored after placement.
    support_order = ["AQUEDUCT", "DAM", "CANAL", "SPACEPORT", "NEIGHBORHOOD"]
    types = [k for k in support_order if candidates[k]] + chosen_specialty
    if not types:
        return None

    state = {}
    def total(s):
        return score(m, s, centers)[1]

    # Greedy construction scores the entire partial layout, including changes to older districts.
    for kind in types:
        best_p, best_value = None, -1
        for p in candidates[kind]:
            if p in state.values():
                continue
            trial = dict(state)
            trial[kind] = p
            value = total(trial)
            if best_p is None or value > best_value or (value == best_value and p < best_p):
                best_p, best_value = p, value
        if best_p is None:
            return None
        state[kind] = best_p

    # Coordinate descent corrects greedy tie choices and couples infrastructure to scoring districts.
    current = total(state)
    for _ in range(8):
        changed = False
        for kind in types:
            old = state.pop(kind)
            best_p, best_value = old, -1
            for p in candidates[kind]:
                if p in state.values():
                    continue
                state[kind] = p
                value = total(state)
                del state[kind]
                if value > best_value or (value == best_value and p < best_p):
                    best_p, best_value = p, value
            state[kind] = best_p
            if best_value > current:
                current = best_value
                changed = True
        if not changed:
            break
    bonuses, total_value = score(m, state, centers)
    return state, bonuses, total_value


def solve(scenario):
    map_path = scenario.get("map_file")
    if not map_path:
        raise ValueError("scenario is missing map_file")
    m = CivMap(map_path)
    ncity = int(scenario.get("num_cities", 1))
    population = int(scenario.get("population", 1))
    if ncity < 1:
        raise ValueError("num_cities must be positive")
    ranked = rank_centers(m)
    best = None
    for plan in center_plans(ranked, ncity):
        result = optimize_for_centers(m, list(plan), population)
        if result is not None and (best is None or result[2] > best[2]):
            best = (list(plan),) + result
    if best is None:
        raise ValueError("unable to construct a legal placement layout")
    centers, placements, bonuses, total_value = best
    out = {
        "placements": {k: [placements[k][0], placements[k][1]] for k in sorted(placements)},
        "adjacency_bonuses": {k: int(bonuses[k]) for k in sorted(placements)},
        "total_adjacency": int(total_value),
    }
    if ncity == 1:
        out["city_center"] = [centers[0][0], centers[0][1]]
    else:
        out["cities"] = [{"center": [p[0], p[1]]} for p in centers]
    return out


def valid_coord(v, m):
    return (isinstance(v, list) and len(v) == 2
            and all(isinstance(x, int) and not isinstance(x, bool) for x in v)
            and 0 <= v[0] < m.w and 0 <= v[1] < m.h)


def validate(scenario, solution):
    errors = []
    try:
        m = CivMap(scenario["map_file"])
        ncity = int(scenario["num_cities"])
        if ncity == 1:
            raw_centers = [solution.get("city_center")] if "city_center" in solution else []
            if "cities" in solution:
                errors.append("single-city solution must not contain cities")
        else:
            raw_cities = solution.get("cities")
            raw_centers = [x.get("center") if isinstance(x, dict) else None for x in raw_cities] if isinstance(raw_cities, list) else []
        if len(raw_centers) != ncity or not all(valid_coord(p, m) for p in raw_centers):
            errors.append("wrong or invalid city centers")
            centers = []
        else:
            centers = [tuple(p) for p in raw_centers]
        if len(set(centers)) != len(centers):
            errors.append("city centers overlap")
        for c in centers:
            if not city_legal(m, c):
                errors.append("illegal city center %r" % (c,))
        raw = solution.get("placements")
        if not isinstance(raw, dict) or not raw:
            errors.append("placements must be a nonempty object")
            raw = {}
        placements = {}
        for kind, p in raw.items():
            if kind not in KNOWN or not valid_coord(p, m):
                errors.append("invalid district entry %r" % (kind,))
            else:
                placements[kind] = tuple(p)
        if sum(k in SPECIALTY for k in placements) > ncity * specialty_cap(int(scenario["population"])):
            errors.append("specialty capacity exceeded")
        occupied = set()
        for kind, p in placements.items():
            if p in occupied or not district_legal(m, kind, p, centers, occupied):
                errors.append("illegal placement for %s" % kind)
            occupied.add(p)
        if set(placements.values()) & set(centers):
            errors.append("district overlaps city center")
        expected, expected_total = score(m, placements, centers)
        reported = solution.get("adjacency_bonuses")
        if reported != expected:
            errors.append("adjacency_bonuses differs from recomputed values")
        if not isinstance(solution.get("total_adjacency"), int) or isinstance(solution.get("total_adjacency"), bool):
            errors.append("total_adjacency must be an integer")
        elif solution["total_adjacency"] != expected_total:
            errors.append("total_adjacency differs from recomputed total")
        return {"valid": not errors, "errors": errors,
                "computed_adjacency_bonuses": expected,
                "computed_total_adjacency": expected_total}
    except Exception as exc:
        return {"valid": False, "errors": errors + [str(exc)],
                "computed_adjacency_bonuses": {}, "computed_total_adjacency": 0}


def load_scenario(path):
    with open(path, encoding="utf-8") as handle:
        scenario = json.load(handle)
    map_path = scenario.get("map_file")
    if map_path and not os.path.isabs(map_path):
        candidate = os.path.normpath(os.path.join(os.path.dirname(path), map_path))
        if os.path.exists(candidate):
            scenario["map_file"] = candidate
        else:
            scenario["map_file"] = os.path.join("/data/maps", os.path.basename(map_path))
    return scenario


def main():
    request = json.load(sys.stdin)
    scenario_path = request.get("scenario_path")
    if not scenario_path:
        raise ValueError("scenario_path is required")
    scenario = load_scenario(scenario_path)
    action = request.get("action", "solve")
    if action == "validate":
        solution = request.get("solution")
        if solution is None:
            with open(request["solution_path"], encoding="utf-8") as handle:
                solution = json.load(handle)
        print(json.dumps(validate(scenario, solution), sort_keys=True))
        return
    if action != "solve":
        raise ValueError("action must be solve or validate")
    answer = solve(scenario)
    destination = request.get("output_path")
    if destination:
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        with open(destination, "w", encoding="utf-8") as handle:
            json.dump(answer, handle, indent=2, sort_keys=True)
            handle.write("\n")
        # Validate the parsed artifact, not merely the in-memory object.
        with open(destination, encoding="utf-8") as handle:
            report = validate(scenario, json.load(handle))
        if not report["valid"]:
            raise ValueError("written solution failed validation: " + "; ".join(report["errors"]))
    print(json.dumps(answer, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
