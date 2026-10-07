#!/usr/bin/env python3
"""Create a source-grounded road itinerary from local CSV data.

stdin: configuration object documented in SKILL.md
stdout: {ok: bool, ...}; on success writes config.output_path
Uses Python standard library only.
"""
import csv
import itertools
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date

MISSING = {"", "na", "n/a", "none", "null", "nan", "unknown", "-"}
DEFAULT_TOOLS = [
    "search_cities", "search_accommodations", "search_restaurants",
    "search_attractions", "search_distance_matrix"
]


def text(v):
    return "" if v is None else str(v).strip()


def token(v):
    return re.sub(r"[^a-z0-9]+", "", text(v).casefold())


def city_key(v):
    s = text(v).casefold().replace("\ufeff", "")
    s = re.sub(r"\s+", " ", s).strip(" ,")
    s = re.sub(r"\bcity\b", "", s).strip(" ,")
    # City columns sometimes include a state suffix. This only removes the suffix,
    # not words in the city name.
    s = re.sub(r",\s*(?:[a-z]{2}|[a-z ]+)\s*$", "", s).strip(" ,")
    return s


def is_missing(v):
    return text(v).casefold() in MISSING


def number(v):
    """Parse a conventional price/count cell, returning None for unknown values."""
    s = text(v).replace(",", "")
    if is_missing(s):
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def csv_headers(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f), [])


def find_col(headers, aliases, contains=()):
    by_token = {token(h): h for h in headers}
    for a in aliases:
        if token(a) in by_token:
            return by_token[token(a)]
    for h in headers:
        th = token(h)
        if any(token(part) in th for part in contains):
            return h
    return None


def rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


def discover_csvs(root):
    found = {}
    for base, _, files in os.walk(root):
        for fn in files:
            low = fn.casefold()
            if not low.endswith(".csv"):
                continue
            p = os.path.join(base, fn)
            label = (base + "/" + fn).casefold()
            for kind, hints in {
                "accommodations": ("accommodation", "hotel", "lodging"),
                "restaurants": ("restaurant",),
                "attractions": ("attraction", "poi"),
                "distance": ("distance", "matrix")
            }.items():
                if kind not in found and any(h in label for h in hints):
                    found[kind] = p
    return found


def require_config(c):
    needed = ["data_root", "output_path", "origin", "state", "days", "city_count",
              "party_size", "budget", "cuisines"]
    absent = [k for k in needed if k not in c]
    if absent:
        raise ValueError("missing required configuration keys: " + ", ".join(absent))
    if int(c["days"]) != 7 or int(c["city_count"]) != 3:
        raise ValueError("this schedule constructor currently requires exactly 7 days and 3 cities")
    if int(c["party_size"]) < 1 or float(c["budget"]) < 0:
        raise ValueError("party_size must be positive and budget must be nonnegative")
    if not isinstance(c["cuisines"], list) or not c["cuisines"]:
        raise ValueError("cuisines must be a nonempty array")


def ohio_city_keys(root, aliases):
    """Read generic city/state reference text without assuming its line serialization."""
    wanted = {token(x) for x in aliases}
    result = set()
    for base, _, files in os.walk(root):
        for fn in files:
            if "cityset" not in fn.casefold():
                continue
            try:
                data = open(os.path.join(base, fn), encoding="utf-8").read()
            except OSError:
                continue
            for raw in data.splitlines():
                line = raw.strip().strip("[]{}'\"")
                low = token(line)
                if not any(a and a in low for a in wanted):
                    continue
                # Typical forms include City, State; City|State; or quoted tuples.
                parts = [p.strip(" []{}'\"") for p in re.split(r"[,|\t]", line)]
                if len(parts) >= 2:
                    for p in parts:
                        if token(p) not in wanted and p:
                            result.add(city_key(p))
                            break
    return result


def load_accommodations(path, party, require_pet):
    h = csv_headers(path)
    name_c = find_col(h, ["name", "listing_name", "hotel_name"], ["name"])
    city_c = find_col(h, ["city", "destination"], ["city"])
    price_c = find_col(h, ["price", "nightly_price", "rate"], ["price", "rate"])
    policy_c = find_col(h, ["house_rules", "pet_policy", "policies", "rules"], ["pet", "rule", "policy"])
    cap_c = find_col(h, ["maximum_occupancy", "max_occupancy", "capacity", "accommodates"], ["occup", "accommod"])
    min_c = find_col(h, ["minimum_nights", "min_nights", "minimum_stay"], ["minimum", "minnight"])
    required = {"name": name_c, "city": city_c, "price": price_c}
    if not all(required.values()):
        raise ValueError("accommodations CSV lacks required name, city, or price column")
    result = defaultdict(list)
    for r in rows(path):
        n, city, cost = text(r.get(name_c)), text(r.get(city_c)), number(r.get(price_c))
        if not n or not city or cost is None or cost < 0:
            continue
        policy = text(r.get(policy_c)) if policy_c else ""
        p = policy.casefold()
        explicitly_allowed = ("pet friendly" in p or "pets allowed" in p or
                              "pet allowed" in p or "allow pets" in p)
        explicitly_denied = bool(re.search(r"\b(no|not)\s+(pets?|animals?)\b", p))
        if require_pet and (not explicitly_allowed or explicitly_denied):
            continue
        cap = number(r.get(cap_c)) if cap_c else None
        if cap is not None and cap < party:
            continue
        # Unknown capacity is retained because some lodging exports do not expose it;
        # policy and price remain explicit. If capacity is represented, it is enforced.
        mn = number(r.get(min_c)) if min_c else 0
        result[city_key(city)].append({"name": n, "city": city, "cost": cost,
                                        "min_nights": int(mn or 0), "policy": policy})
    for k in result:
        result[k].sort(key=lambda x: x["cost"])
    return result


def split_cuisines(v):
    return [token(x) for x in re.split(r"[,;/|]", text(v)) if token(x)]


def load_restaurants(path):
    h = csv_headers(path)
    name_c = find_col(h, ["name", "restaurant_name"], ["name"])
    city_c = find_col(h, ["city", "destination"], ["city"])
    cuisine_c = find_col(h, ["cuisines", "cuisine", "category"], ["cuisine", "category"])
    price_c = find_col(h, ["average_cost", "avg_cost", "price", "cost"], ["cost", "price"])
    if not all((name_c, city_c, cuisine_c, price_c)):
        raise ValueError("restaurants CSV lacks required name, city, cuisine, or price column")
    result = defaultdict(list)
    for r in rows(path):
        n, city, cost = text(r.get(name_c)), text(r.get(city_c)), number(r.get(price_c))
        if n and city and cost is not None and cost >= 0:
            result[city_key(city)].append({"name": n, "city": city, "cost": cost,
                                            "cuisines": split_cuisines(r.get(cuisine_c))})
    for k in result:
        result[k].sort(key=lambda x: x["cost"])
    return result


def load_attractions(path):
    h = csv_headers(path)
    name_c = find_col(h, ["name", "attraction", "attraction_name"], ["name", "attraction"])
    city_c = find_col(h, ["city", "destination"], ["city"])
    if not name_c or not city_c:
        raise ValueError("attractions CSV lacks required name or city column")
    result = defaultdict(list)
    seen = defaultdict(set)
    for r in rows(path):
        n, city = text(r.get(name_c)), text(r.get(city_c))
        k = city_key(city)
        if n and city and n not in seen[k]:
            seen[k].add(n)
            result[k].append({"name": n, "city": city})
    return result


def load_edges(path):
    h = csv_headers(path)
    origin_c = find_col(h, ["origin", "from", "source", "origin_city"], ["origin", "source"])
    dest_c = find_col(h, ["destination", "to", "target", "destination_city"], ["destination", "target"])
    if not origin_c or not dest_c:
        raise ValueError("distance CSV lacks directed origin/from and destination/to columns")
    out = defaultdict(set)
    for r in rows(path):
        a, b = city_key(r.get(origin_c)), city_key(r.get(dest_c))
        if a and b:
            out[a].add(b)
    return out


def select_meal(pool, cuisine):
    desired = token(cuisine)
    matching = [x for x in pool if desired in x["cuisines"]]
    return (matching or pool)[0], bool(matching)


def make_candidate(route, lodgings, restaurants, attractions, cfg):
    # 2 / 2 / 3 nights correspond to seven emitted day entries.
    spans = [2, 2, 3]
    hotels = []
    for city, span in zip(route, spans):
        eligible = [x for x in lodgings[city] if x["min_nights"] <= span]
        if not eligible:
            return None
        hotels.append(eligible[0])
    day_cities = [route[0], route[0], route[1], route[1], route[2], route[2], route[2]]
    transitions = {0: (city_key(cfg["origin"]), route[0]), 2: (route[0], route[1]), 4: (route[1], route[2])}
    meals, total, coverage = [], 0.0, set()
    for i, city in enumerate(day_cities):
        pool = restaurants[city]
        for offset in range(3):
            choice, matched = select_meal(pool, cfg["cuisines"][(i * 3 + offset) % len(cfg["cuisines"])])
            meals.append(choice)
            if matched:
                coverage.update(choice["cuisines"])
            total += choice["cost"] * int(cfg["party_size"])
    total += sum(h["cost"] * span for h, span in zip(hotels, spans))
    entries = []
    for i, city in enumerate(day_cities):
        hotel = hotels[0] if i < 2 else hotels[1] if i < 4 else hotels[2]
        attraction = attractions[city][i % len(attractions[city])]
        if i in transitions:
            a, b = transitions[i]
            a_display = cfg["origin"] if i == 0 else route[0]
            b_display = route[0] if i == 0 else route[1] if i == 2 else route[2]
            current = "from %s to %s" % (a_display, b_display)
            transport = "Self-driving: from %s to %s" % (a_display, b_display)
        else:
            current = hotel["city"]
            transport = "Local self-driving in " + hotel["city"]
        m = meals[i * 3:(i + 1) * 3]
        entries.append({"day": i + 1, "current_city": current, "transportation": transport,
                        "breakfast": m[0]["name"], "lunch": m[1]["name"], "dinner": m[2]["name"],
                        "attraction": attraction["name"] + ";", "accommodation": hotel["name"]})
    preferred = {token(x) for x in cfg["cuisines"]}
    return {"plan": entries, "cost": total, "coverage": len(preferred & coverage),
            "coverage_labels": sorted(preferred & coverage), "hotels": hotels}


def validate_output(out, candidate, cfg, edges, route):
    expected = {"plan", "tool_called"}
    if set(out) != expected or len(out["plan"]) != 7:
        raise ValueError("internal output shape validation failed")
    all_names = set()
    for d in out["plan"]:
        required = {"day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"}
        if set(d) != required or not isinstance(d["day"], int):
            raise ValueError("day object schema validation failed")
        if "flight" in d["transportation"].casefold() or not d["attraction"].endswith(";"):
            raise ValueError("transportation or attraction validation failed")
        all_names.update((d["breakfast"], d["lunch"], d["dinner"], d["attraction"][:-1], d["accommodation"]))
    if [d["day"] for d in out["plan"]] != list(range(1, 8)):
        raise ValueError("day numbering validation failed")
    source_names = set()
    for h in candidate["hotels"]:
        if "pet" not in h["policy"].casefold():
            raise ValueError("selected lodging lacks pet-policy evidence")
        source_names.add(h["name"])
    # Restaurants and attractions are checked from constructed plan names. Entity names
    # can overlap across categories, so verify each scheduled field against its own source.
    restaurant_names = {x["name"] for pool in _RUNTIME_RESTAURANTS.values() for x in pool}
    attraction_names = {x["name"] for pool in _RUNTIME_ATTRACTIONS.values() for x in pool}
    for d in out["plan"]:
        if any(d[k] not in restaurant_names for k in ("breakfast", "lunch", "dinner")):
            raise ValueError("meal is not a source restaurant")
        if d["attraction"][:-1] not in attraction_names:
            raise ValueError("attraction is not a source attraction")
    origin = city_key(cfg["origin"])
    if route[0] not in edges[origin] or route[1] not in edges[route[0]] or route[2] not in edges[route[1]]:
        raise ValueError("route-leg validation failed")
    if candidate["cost"] > float(cfg["budget"]) + 1e-7:
        raise ValueError("budget validation failed")


_RUNTIME_RESTAURANTS = {}
_RUNTIME_ATTRACTIONS = {}


def build(cfg):
    global _RUNTIME_RESTAURANTS, _RUNTIME_ATTRACTIONS
    require_config(cfg)
    paths = discover_csvs(cfg["data_root"])
    paths.update(cfg.get("dataset_paths", {}))
    absent = [k for k in ("accommodations", "restaurants", "attractions", "distance") if not paths.get(k) or not os.path.isfile(paths[k])]
    if absent:
        raise ValueError("could not locate required datasets: " + ", ".join(absent))
    party = int(cfg["party_size"])
    lodgings = load_accommodations(paths["accommodations"], party, bool(cfg.get("pet_required", True)))
    restaurants = load_restaurants(paths["restaurants"])
    attractions = load_attractions(paths["attractions"])
    edges = load_edges(paths["distance"])
    _RUNTIME_RESTAURANTS, _RUNTIME_ATTRACTIONS = restaurants, attractions

    aliases = cfg.get("state_aliases") or [cfg["state"]]
    requested = ohio_city_keys(cfg["data_root"], aliases)
    # Explicit state columns are preferred when exposed. If city reference discovery did
    # not identify a city, the cross-source intersection below remains conservative.
    viable = set(lodgings) & set(restaurants) & set(attractions)
    cities = sorted(viable & requested) if requested else []
    if len(cities) < 3:
        raise ValueError("fewer than three requested-state cities have lodging, restaurants, and attractions")

    origin_keys = [city_key(cfg["origin"])] + [city_key(x) for x in cfg.get("origin_aliases", [])]
    best = None
    for origin in origin_keys:
        for c1 in cities:
            if c1 not in edges.get(origin, set()):
                continue
            for c2 in (edges.get(c1, set()) & set(cities)):
                if c2 == c1:
                    continue
                for c3 in (edges.get(c2, set()) & set(cities)):
                    if c3 in (c1, c2):
                        continue
                    candidate = make_candidate([c1, c2, c3], lodgings, restaurants, attractions, cfg)
                    if candidate is None or candidate["cost"] > float(cfg["budget"]) + 1e-7:
                        continue
                    key = (-candidate["coverage"], candidate["cost"], tuple([c1, c2, c3]))
                    if best is None or key < best[0]:
                        best = (key, [c1, c2, c3], candidate, origin)
    if best is None:
        raise ValueError("no directed three-city road route satisfies policy, data, and budget constraints")
    _, route, candidate, selected_origin = best
    out = {"plan": candidate["plan"], "tool_called": cfg.get("tool_called", DEFAULT_TOOLS)}
    # Validation expects the exact origin key used for the first edge.
    original_origin = cfg["origin"]
    if selected_origin != city_key(original_origin):
        cfg = dict(cfg)
        cfg["origin"] = selected_origin
    validate_output(out, candidate, cfg, edges, route)
    # Preserve the user-facing spelling if an alias was necessary.
    if selected_origin != city_key(original_origin):
        first = out["plan"][0]
        first["current_city"] = "from %s to %s" % (original_origin, candidate["hotels"][0]["city"])
        first["transportation"] = "Self-driving: from %s to %s" % (original_origin, candidate["hotels"][0]["city"])
    os.makedirs(os.path.dirname(os.path.abspath(cfg["output_path"])), exist_ok=True)
    with open(cfg["output_path"], "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return {"ok": True, "output_path": cfg["output_path"],
            "estimated_total": round(candidate["cost"], 2),
            "cuisine_coverage": candidate["coverage_labels"],
            "route_city_keys": route}


def main():
    try:
        cfg = json.load(sys.stdin)
        if not isinstance(cfg, dict):
            raise ValueError("stdin must be one JSON object")
        status = build(cfg)
        print(json.dumps(status, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
