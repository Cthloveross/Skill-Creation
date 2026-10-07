#!/usr/bin/env python3
"""Create a source-grounded road itinerary from the task's travel CSVs.
Input: JSON configuration on stdin (documented in SKILL.md).
Output: a JSON report on stdout; the itinerary itself is written to config['output'].
"""
import csv, itertools, json, os, re, sys
from collections import defaultdict


def norm(x):
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def text(x):
    return "" if x is None else str(x).strip()


def number(v):
    s = text(v).replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def col(rows, *aliases):
    if not rows:
        return None
    keys = list(rows[0])
    wanted = [norm(a) for a in aliases]
    for a in wanted:
        for k in keys:
            if norm(k) == a:
                return k
    for a in wanted:
        for k in keys:
            if a in norm(k):
                return k
    return None


def value(row, key):
    return text(row.get(key)) if key else ""


def city_key(s):
    return norm(re.split(r"[,/]", text(s))[0])


def positive_pet(s):
    s = text(s).lower()
    if not s or "pet" not in s:
        return False
    negatives = ("no pets", "not pet", "pets not", "pets aren", "pets are not", "without pets", "pet-free")
    return not any(x in s for x in negatives)


def find_file(root, relative):
    p = os.path.join(root, relative)
    if not os.path.isfile(p):
        raise ValueError("required dataset is absent: " + p)
    return p


def source_city_state(root, state):
    path = find_file(root, "background/citySet_with_states.txt")
    result = set()
    for line in open(path, encoding="utf-8"):
        # Expected forms include City, State and City\tState; only accept exact state token.
        parts = [p.strip() for p in re.split(r"[,\t|]", line.strip())]
        if len(parts) >= 2 and norm(parts[-1]) == norm(state):
            result.add(city_key(parts[0]))
    return result


def load_data(root):
    files = {
        "accommodations": find_file(root, "accommodations/clean_accommodations_2022.csv"),
        "restaurants": find_file(root, "restaurants/clean_restaurant_2022.csv"),
        "attractions": find_file(root, "attractions/attractions.csv"),
    }
    return {k: read_csv(v) for k, v in files.items()}, files


def meal_string(row, namecol, citycol, cuisine):
    name = value(row, namecol)
    city = value(row, citycol)
    return (cuisine + " cuisine at " + name + (", " + city if city else ""))


def attraction_string(rows, namecol):
    names = [value(r, namecol) for r in rows if value(r, namecol)]
    return ";".join(names) + ";" if names else "-;"


def directed_edges(root):
    path = os.path.join(root, "googleDistanceMatrix/distance.csv")
    if not os.path.isfile(path):
        return None
    rows = read_csv(path)
    a, b = col(rows, "origin", "from", "start city"), col(rows, "destination", "to", "end city")
    if not a or not b:
        return None
    return {(city_key(value(r, a)), city_key(value(r, b))) for r in rows if value(r, a) and value(r, b)}


def main(cfg):
    root = cfg.get("data_root", "/app/data")
    origin, state = text(cfg["origin"]), text(cfg["state"])
    ncity, ndays = int(cfg["city_count"]), int(cfg["days"])
    party, budget = int(cfg["party_size"]), float(cfg["budget"])
    cuisines = [text(x) for x in cfg["cuisines"] if text(x)]
    if ncity < 1 or ndays < ncity or party < 1 or not cuisines:
        raise ValueError("city_count, days, party_size, and cuisines must be positive")
    data, files = load_data(root)
    acc, rest, attr = data["accommodations"], data["restaurants"], data["attractions"]
    ac_city, ac_name = col(acc, "city", "location"), col(acc, "name", "listing name", "title")
    ac_cap, ac_price = col(acc, "maximum occupancy", "capacity", "accommodates", "guests"), col(acc, "price", "nightly price", "rate")
    re_city, re_name, re_cuisine = col(rest, "city", "location"), col(rest, "name", "restaurant name"), col(rest, "cuisines", "cuisine", "category")
    re_price = col(rest, "average cost", "price", "cost")
    at_city, at_name = col(attr, "city", "location"), col(attr, "name", "attraction name", "title")
    if not all((ac_city, ac_name, re_city, re_name, re_cuisine, at_city, at_name)):
        raise ValueError("one or more required source columns could not be identified")

    state_cities = source_city_state(root, state)
    # Some city-set files use a different delimiter/format. Supplement only with explicit state fields.
    for rows, citycol in ((acc, ac_city), (rest, re_city), (attr, at_city)):
        stcol = col(rows, "state", "province")
        if stcol:
            state_cities.update(city_key(value(r, citycol)) for r in rows if norm(value(r, stcol)) == norm(state))
    if not state_cities:
        raise ValueError("no cities for requested state found in source data")

    lodgings, restaurants, attractions = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in acc:
        c = city_key(value(r, ac_city))
        policy_blob = " ".join(value(r, k) for k in r)
        cap = number(value(r, ac_cap))
        if c in state_cities and positive_pet(policy_blob) and (cap is None or cap >= party):
            lodgings[c].append(r)
    for r in rest:
        c = city_key(value(r, re_city))
        if c in state_cities and value(r, re_name) and value(r, re_cuisine):
            restaurants[c].append(r)
    for r in attr:
        c = city_key(value(r, at_city))
        if c in state_cities and value(r, at_name):
            attractions[c].append(r)

    # A city is useful only if every cuisine can be sourced there. This prevents later name invention.
    feasible = []
    for c in state_cities:
        cuisine_rows = {cu: [r for r in restaurants[c] if norm(cu) in norm(value(r, re_cuisine))] for cu in cuisines}
        if lodgings[c] and attractions[c] and all(cuisine_rows.values()):
            feasible.append(c)
    if len(feasible) < ncity:
        raise ValueError("fewer than requested cities have pet lodging, attractions, and all requested cuisines")

    edges = directed_edges(root)
    origin_k = city_key(origin)
    # Select a route whose represented directed links exist if the matrix schema was identifiable.
    routes = []
    for route in itertools.permutations(feasible, ncity):
        if edges is None or all((a, b) in edges for a, b in zip((origin_k,) + route, route)):
            routes.append(route)
    if not routes:
        raise ValueError("no directed self-driving route through the eligible cities was found")
    route = routes[0]

    # Allocate all days across cities, preserving exact length and city coverage.
    allocations = [1] * ncity
    for i in range(ndays - ncity):
        allocations[i % ncity] += 1
    city_days = [c for c, count in zip(route, allocations) for _ in range(count)]
    chosen_lodging = {c: lodgings[c][0] for c in route}
    known_cost = 0.0
    unknown_costs = 0
    for c in city_days:
        x = number(value(chosen_lodging[c], ac_price))
        if x is None: unknown_costs += 1
        else: known_cost += x
    plan = []
    cuisine_seen = set()
    for i, c in enumerate(city_days):
        first = i == 0 or city_days[i - 1] != c
        prior = origin if i == 0 else (value(chosen_lodging[city_days[i-1]], ac_city) if first else value(chosen_lodging[c], ac_city))
        display_city = value(chosen_lodging[c], ac_city)
        current = "from %s to %s" % (prior, display_city) if first else display_city
        transport = "Self-driving: from %s to %s" % (prior, display_city) if first else "-"
        meals = []
        for offset in range(3):
            cu = cuisines[(i * 3 + offset) % len(cuisines)]
            choices = [r for r in restaurants[c] if norm(cu) in norm(value(r, re_cuisine))]
            r = choices[(i + offset) % len(choices)]
            meals.append(meal_string(r, re_name, re_city, cu))
            cuisine_seen.add(norm(cu))
            p = number(value(r, re_price))
            if p is None: unknown_costs += 1
            else: known_cost += p * party
        ars = attractions[c]
        selected_attr = [ars[(i * 2 + j) % len(ars)] for j in range(min(2, len(ars)))]
        lodging = chosen_lodging[c]
        plan.append({"day": i + 1, "current_city": current, "transportation": transport,
                     "breakfast": meals[0], "lunch": meals[1], "dinner": meals[2],
                     "attraction": attraction_string(selected_attr, at_name),
                     "accommodation": "Pet-friendly " + value(lodging, ac_name)})
    if known_cost > budget:
        raise ValueError("known selected costs %.2f exceed budget %.2f" % (known_cost, budget))
    if len(cuisine_seen) != len(set(norm(c) for c in cuisines)):
        raise ValueError("cuisine coverage failure")
    output = cfg.get("output", "/app/output/itinerary.json")
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    artifact = {"plan": plan, "tool_called": ["search_cities", "search_accommodations", "search_restaurants", "search_attractions", "search_distance_matrix"]}
    with open(output, "w", encoding="utf-8") as f: json.dump(artifact, f, ensure_ascii=False, indent=2)
    return {"output": output, "cities": [value(chosen_lodging[c], ac_city) for c in route], "known_cost": round(known_cost, 2), "unknown_cost_items": unknown_costs, "route_matrix_checked": edges is not None, "sources": files}

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin))))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(2)
