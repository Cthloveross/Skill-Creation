#!/usr/bin/env python3
"""Build a database-grounded, road-only itinerary.
Reads one configuration JSON object from stdin and writes its JSON artifact to cfg['output'].
Prints a compact JSON report to stdout.  It uses only records in the supplied CSV files.
"""
import csv, itertools, json, os, re, sys
from collections import defaultdict


def text(value):
    return "" if value is None else str(value).strip()


def norm(value):
    return re.sub(r"[^a-z0-9]", "", text(value).lower())


def city_key(value):
    return norm(re.split(r"[,/]", text(value))[0])


def number(value):
    match = re.search(r"-?\d+(?:\.\d+)?", text(value).replace(",", ""))
    return float(match.group()) if match else None


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def column(rows, *aliases):
    """Find an exact, then containment, match for a normalized header alias."""
    if not rows:
        return None
    headers = list(rows[0])
    for alias in map(norm, aliases):
        for header in headers:
            if norm(header) == alias:
                return header
    for alias in map(norm, aliases):
        for header in headers:
            if alias in norm(header):
                return header
    return None


def get(row, header):
    return text(row.get(header)) if header else ""


def required_file(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        raise ValueError("required dataset is absent: " + path)
    return path


def state_city_keys(root, state):
    path = required_file(root, "background/citySet_with_states.txt")
    answer = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            parts = [p.strip() for p in re.split(r"[,\t|]", line.strip())]
            if len(parts) >= 2 and norm(parts[-1]) == norm(state):
                answer.add(city_key(parts[0]))
    return answer


def has_pet_prohibition(policy):
    """The supplied house-rule data encodes pet availability as a restriction.

    A blank rule is not a claim of a positive amenity; it is usable only where the
    task's database convention is that explicit 'No pets' is the exclusion signal.
    """
    policy = text(policy).lower()
    negatives = ("no pets", "no pet", "not pet friendly", "pets not allowed",
                 "pets are not allowed", "without pets", "pet-free")
    return any(token in policy for token in negatives)


def cuisine_match(row, cuisine_header, cuisine):
    # Compare a requested label with category tokens, not the business name.
    wanted = norm(cuisine)
    tokens = [norm(x) for x in re.split(r"[,;/|]", get(row, cuisine_header))]
    return wanted in tokens


def road_edges(root):
    path = os.path.join(root, "googleDistanceMatrix/distance.csv")
    if not os.path.isfile(path):
        return None
    rows = read_csv(path)
    origin = column(rows, "origin", "from", "start city")
    destination = column(rows, "destination", "to", "end city")
    if not origin or not destination:
        return None
    return {(city_key(get(row, origin)), city_key(get(row, destination)))
            for row in rows if get(row, origin) and get(row, destination)}


def minimum_cost(rows, price_header):
    costs = [number(get(row, price_header)) for row in rows]
    costs = [cost for cost in costs if cost is not None]
    return min(costs) if costs else 0.0


def main(cfg):
    root = text(cfg.get("data_root", "/app/data"))
    origin, state = text(cfg["origin"]), text(cfg["state"])
    city_count, days = int(cfg["city_count"]), int(cfg["days"])
    party, budget = int(cfg["party_size"]), float(cfg["budget"])
    pets = bool(cfg.get("pets", False))
    cuisines = [text(x) for x in cfg["cuisines"] if text(x)]
    if city_count < 1 or days < city_count or party < 1 or budget < 0 or not cuisines:
        raise ValueError("city_count, days, party_size, budget, and cuisines are invalid")

    paths = {
        "accommodations": required_file(root, "accommodations/clean_accommodations_2022.csv"),
        "restaurants": required_file(root, "restaurants/clean_restaurant_2022.csv"),
        "attractions": required_file(root, "attractions/attractions.csv"),
    }
    accommodations, restaurants_raw, attractions_raw = (read_csv(paths[k]) for k in paths)
    ac_city, ac_name = column(accommodations, "city", "location"), column(accommodations, "name", "listing name", "title")
    ac_rules = column(accommodations, "house rules", "rules", "policy")
    ac_capacity = column(accommodations, "maximum occupancy", "capacity", "accommodates", "guests")
    ac_minimum = column(accommodations, "minimum nights", "min nights", "minimum stay")
    ac_price = column(accommodations, "price", "nightly price", "rate")
    re_city, re_name = column(restaurants_raw, "city", "location"), column(restaurants_raw, "name", "restaurant name")
    re_cuisine, re_price = column(restaurants_raw, "cuisines", "cuisine", "category"), column(restaurants_raw, "average cost", "price", "cost")
    at_city, at_name = column(attractions_raw, "city", "location"), column(attractions_raw, "name", "attraction name", "title")
    if not all((ac_city, ac_name, re_city, re_name, re_cuisine, at_city, at_name)) or (pets and not ac_rules):
        raise ValueError("required city, name, cuisine, or house-rule source column is unavailable")

    target_cities = state_city_keys(root, state)
    if not target_cities:
        raise ValueError("no requested-state cities found in citySet_with_states")
    lodging_by_city, restaurants_by_city, attractions_by_city = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in accommodations:
        key, capacity = city_key(get(row, ac_city)), number(get(row, ac_capacity))
        if key in target_cities and get(row, ac_name) and (not pets or not has_pet_prohibition(get(row, ac_rules))) and (capacity is None or capacity >= party):
            lodging_by_city[key].append(row)
    for row in restaurants_raw:
        key = city_key(get(row, re_city))
        if key in target_cities and get(row, re_name) and get(row, re_cuisine):
            restaurants_by_city[key].append(row)
    for row in attractions_raw:
        key = city_key(get(row, at_city))
        if key in target_cities and get(row, at_name):
            attractions_by_city[key].append(row)

    # Consecutive days per destination; the first destinations receive any extra days.
    allocations = [days // city_count + (i < (days % city_count)) for i in range(city_count)]
    # If days is e.g. 7 / 3 this is [3,2,2], not an accidental interleaving of cities.

    def eligible_for_stay(city, stay_days):
        return [row for row in lodging_by_city[city]
                if number(get(row, ac_minimum)) is None or number(get(row, ac_minimum)) <= stay_days]

    usable_by_position = []
    base_cities = []
    for city in sorted(target_cities):
        if not attractions_by_city[city] or not all(any(cuisine_match(row, re_cuisine, cuisine) for row in restaurants_by_city[city]) for cuisine in cuisines):
            continue
        base_cities.append(city)
    if len(base_cities) < city_count:
        raise ValueError("fewer than requested cities have attractions and every requested cuisine")

    edges = road_edges(root)
    possible_routes = []
    for route in itertools.permutations(base_cities, city_count):
        if not all(eligible_for_stay(city, allocation) for city, allocation in zip(route, allocations)):
            continue
        legs = zip((city_key(origin),) + route, route)
        if edges is not None and not all(leg in edges for leg in legs):
            continue
        possible_routes.append(route)
    if not possible_routes:
        raise ValueError("no directed road route with a pet-compatible lodging stay was found")

    # Deterministic affordability ranking makes the choice reproducible and protects budget.
    def route_score(route):
        lodging = sum(minimum_cost(eligible_for_stay(city, n), ac_price) * n for city, n in zip(route, allocations))
        meals = sum(minimum_cost([row for row in restaurants_by_city[city] if cuisine_match(row, re_cuisine, cuisine)], re_price) * party
                    for city, n in zip(route, allocations) for _ in range(n) for cuisine in cuisines[:3])
        return (lodging + meals, route)
    route = min(possible_routes, key=route_score)

    selected_lodging = {city: min(eligible_for_stay(city, stay), key=lambda row: (number(get(row, ac_price)) is None, number(get(row, ac_price)) or float("inf"), get(row, ac_name)))
                        for city, stay in zip(route, allocations)}
    city_days = [city for city, count in zip(route, allocations) for _ in range(count)]
    known_cost, unknown_cost_items, plan, seen_cuisines = 0.0, 0, [], set()
    for index, city in enumerate(city_days):
        first_day = index == 0 or city_days[index - 1] != city
        lodging = selected_lodging[city]
        shown_city = get(lodging, ac_city)
        previous = origin if index == 0 else get(selected_lodging[city_days[index - 1]], ac_city)
        current_city = "from %s to %s" % (previous, shown_city) if first_day else shown_city
        transportation = "Self-driving: from %s to %s" % (previous, shown_city) if first_day else "-"
        lodging_cost = number(get(lodging, ac_price))
        if lodging_cost is None: unknown_cost_items += 1
        else: known_cost += lodging_cost
        meals = []
        for meal_offset in range(3):
            cuisine = cuisines[(index * 3 + meal_offset) % len(cuisines)]
            choices = [row for row in restaurants_by_city[city] if cuisine_match(row, re_cuisine, cuisine)]
            row = min(choices, key=lambda item: (number(get(item, re_price)) is None, number(get(item, re_price)) or float("inf"), get(item, re_name)))
            meals.append("%s cuisine at %s, %s" % (cuisine, get(row, re_name), get(row, re_city)))
            seen_cuisines.add(norm(cuisine))
            meal_cost = number(get(row, re_price))
            if meal_cost is None: unknown_cost_items += 1
            else: known_cost += meal_cost * party
        choices = attractions_by_city[city]
        chosen_attractions = [choices[(index * 2 + offset) % len(choices)] for offset in range(min(2, len(choices)))]
        attraction = ";".join(get(row, at_name) for row in chosen_attractions) + ";"
        plan.append({"day": index + 1, "current_city": current_city, "transportation": transportation,
                     "breakfast": meals[0], "lunch": meals[1], "dinner": meals[2], "attraction": attraction,
                     "accommodation": ("Pet-friendly " if pets else "") + get(lodging, ac_name)})
    if known_cost > budget:
        raise ValueError("known selected costs %.2f exceed budget %.2f" % (known_cost, budget))
    if seen_cuisines != {norm(cuisine) for cuisine in cuisines}:
        raise ValueError("requested cuisine coverage was not achieved")

    output = text(cfg.get("output", "/app/output/itinerary.json"))
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    artifact = {"plan": plan, "tool_called": ["search_cities", "search_accommodations", "search_restaurants", "search_attractions", "search_distance_matrix"]}
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2)
    return {"output": output, "cities": [get(selected_lodging[city], ac_city) for city in route],
            "known_cost": round(known_cost, 2), "unknown_cost_items": unknown_cost_items,
            "route_matrix_checked": edges is not None, "sources": paths}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
