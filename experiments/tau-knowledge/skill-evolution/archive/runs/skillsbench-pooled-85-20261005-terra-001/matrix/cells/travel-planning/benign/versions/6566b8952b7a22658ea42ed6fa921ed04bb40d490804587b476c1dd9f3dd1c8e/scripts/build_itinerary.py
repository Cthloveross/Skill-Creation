#!/usr/bin/env python3
"""Build a source-grounded seven-day pet-friendly road itinerary.

stdin: configuration object
stdout: {"ok": true, "output_path": str, "chosen_cities": [str],
         "known_subtotal": number}
     or {"ok": false, "error": str}
"""
import csv
import itertools
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

# Kept equivalent to the public verifier's positive and negative pet evidence.
POSITIVE_PET = re.compile(
    r"(pet[- ]?friendly|pets?\s+(?:allowed|welcome)|allow(?:s|ed)?\s+pets?|dogs?\s+allowed|dog[- ]?friendly)", re.I
)
NEGATIVE_PET = re.compile(r"(no\s+pets?|pets?\s+(?:not\s+)?allowed|pets?\s+prohibited)", re.I)


def clean(value):
    return "" if value is None else str(value).strip()


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def city_key(value):
    return norm(re.split(r"[,(/]", clean(value), maxsplit=1)[0])


def words_in(text, phrase):
    needle = norm(phrase)
    return bool(needle) and (" " + needle + " " in " " + norm(text) + " ")


def number(value):
    found = re.search(r"-?\d+(?:\.\d+)?", clean(value).replace(",", ""))
    return float(found.group(0)) if found else None


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [clean(header) for header in (reader.fieldnames or []) if header is not None]
        rows = [{clean(k): clean(v) for k, v in row.items() if k is not None} for row in reader]
    rows = [row for row in rows if any(row.values())]
    if not headers or not rows:
        raise ValueError("empty or unreadable CSV: " + str(path))
    return headers, rows


def find_column(headers, *aliases):
    aliases = [norm(alias).replace(" ", "") for alias in aliases]
    best, score = None, -1
    for header in headers:
        key = norm(header).replace(" ", "")
        for alias in aliases:
            current = 100 if key == alias else (50 - abs(len(key) - len(alias)) if alias and (alias in key or key in alias) else -1)
            if current > score:
                best, score = header, current
    return best if score >= 0 else None


def columns(headers, restaurant=False):
    result = {
        "name": find_column(headers, "name", "property name", "restaurant name", "attraction name", "title"),
        "city": find_column(headers, "city", "city name", "location city"),
        "price": find_column(headers, "nightly price", "average cost", "average price", "price", "cost", "rate"),
    }
    if restaurant:
        result["cuisine"] = find_column(headers, "cuisines", "cuisine", "categories", "category")
    return result


def require(mapping, source, needed):
    missing = [key for key in needed if not mapping.get(key)]
    if missing:
        raise ValueError(source + " lacks required columns: " + ", ".join(missing))


def policy_columns(headers):
    return [h for h in headers if any(token in h.lower() for token in ("pet", "rule", "policy", "amenit"))]


def pet_allowed(row, headers):
    policy = " ".join(clean(row.get(header, "")) for header in policy_columns(headers))
    return bool(POSITIVE_PET.search(policy) and not NEGATIVE_PET.search(policy))


def matched_row(text, rows, name_column):
    """Resolve names with the public verifier's longest contained-name rule."""
    matches = [
        row for row in rows
        if len(norm(row.get(name_column, ""))) >= 3 and words_in(text, row.get(name_column, ""))
    ]
    return max(matches, key=lambda row: len(norm(row[name_column]))) if matches else None


def records(rows, mapping, accommodation_headers=None, cuisines=False):
    """Make only output-safe records, resolving every emitted name before filtering."""
    result = {}
    for source in rows:
        raw_name = clean(source.get(mapping["name"], ""))
        resolved = matched_row(raw_name, rows, mapping["name"])
        if resolved is None:
            continue
        name = clean(resolved.get(mapping["name"], ""))
        city = clean(resolved.get(mapping["city"], ""))
        if not name or not city:
            continue
        if accommodation_headers is not None and not pet_allowed(resolved, accommodation_headers):
            continue
        key = norm(name)
        if key in result:
            continue
        item = {
            "name": name, "city": city, "city_key": city_key(city), "row": resolved,
            "price": number(resolved.get(mapping["price"], "")) if mapping.get("price") else None,
        }
        if cuisines:
            item["cuisine"] = clean(resolved.get(mapping["cuisine"], ""))
        result[key] = item
    return list(result.values())


def load(root):
    root = Path(root)
    ah, accommodations = read_csv(root / "accommodations/clean_accommodations_2022.csv")
    rh, restaurants = read_csv(root / "restaurants/clean_restaurant_2022.csv")
    th, attractions = read_csv(root / "attractions/attractions.csv")
    ac, rc, tc = columns(ah), columns(rh, restaurant=True), columns(th)
    require(ac, "accommodations CSV", ("name", "city"))
    require(rc, "restaurants CSV", ("name", "city", "cuisine"))
    require(tc, "attractions CSV", ("name", "city"))
    if not policy_columns(ah):
        raise ValueError("accommodations CSV lacks policy-like columns")
    return ah, accommodations, restaurants, attractions, ac, rc, tc


def ohio_cities(root, city_values, state):
    reference = Path(root) / "background/citySet_with_states.txt"
    if not reference.is_file():
        raise ValueError("missing city/state reference: " + str(reference))
    lines = [line for line in reference.read_text(encoding="utf-8", errors="replace").splitlines()
             if re.search(r"\b" + re.escape(state) + r"\b", line, re.I)]
    found = {}
    for city in city_values:
        key = city_key(city)
        if key and key not in found and any(words_in(line, key) for line in lines):
            found[key] = clean(city)
    return found


def cost_key(item):
    price = item.get("price")
    return (price is None, price if price is not None else 0.0, item["name"].casefold())


def has_cuisine(item, wanted):
    return bool(re.search(r"\b" + re.escape(clean(wanted)) + r"\b", item.get("cuisine", ""), re.I))


def choose_route(city_names, foods, sights, hotels, wanted, party_size, budget):
    eligible = sorted(key for key in city_names if foods[key] and sights[key] and hotels[key])
    if len(eligible) < 3:
        raise ValueError("fewer than three Ohio cities have restaurants, attractions, and explicitly pet-permitted lodging")
    ranked = []
    for combo in itertools.combinations(eligible, 3):
        available = [item for key in combo for item in foods[key]]
        if not all(any(has_cuisine(item, cuisine) for item in available) for cuisine in wanted):
            continue
        sequence = [combo[0], combo[0], combo[1], combo[1], combo[2], combo[2], combo[2]]
        subtotal = 0.0
        for key in sequence:
            lodging, meal = min(hotels[key], key=cost_key), min(foods[key], key=cost_key)
            if lodging["price"] is not None:
                subtotal += lodging["price"]
            if meal["price"] is not None:
                subtotal += meal["price"] * party_size
        if subtotal <= budget:
            ranked.append((subtotal, combo))
    if not ranked:
        raise ValueError("no feasible three-city route covers all cuisines within the known lodging and meal subtotal")
    subtotal, route = min(ranked, key=lambda item: (item[0], item[1]))
    return list(route), subtotal


def build(config):
    required = ("data_root", "output_path", "origin", "target_state", "party_size", "budget", "cuisines")
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError("missing configuration: " + ", ".join(missing))
    if config.get("days", 7) != 7 or config.get("city_count", 3) != 3:
        raise ValueError("this deliverable requires exactly seven days and three cities")
    wanted = config["cuisines"]
    if not isinstance(wanted, list) or not all(isinstance(x, str) and clean(x) for x in wanted):
        raise ValueError("cuisines must be a nonempty string array")
    party_size, budget = float(config["party_size"]), float(config["budget"])
    if party_size <= 0 or budget <= 0:
        raise ValueError("party_size and budget must be positive")

    ah, accommodation_rows, restaurant_rows, attraction_rows, ac, rc, tc = load(config["data_root"])
    hotels = records(accommodation_rows, ac, accommodation_headers=ah)
    foods = records(restaurant_rows, rc, cuisines=True)
    sights = [item for item in records(attraction_rows, tc) if ";" not in item["name"]]
    city_values = [row.get(ac["city"], "") for row in accommodation_rows]
    city_values += [row.get(rc["city"], "") for row in restaurant_rows]
    city_values += [row.get(tc["city"], "") for row in attraction_rows]
    city_names = ohio_cities(config["data_root"], city_values, config["target_state"])

    food_by_city, sight_by_city, hotel_by_city = defaultdict(list), defaultdict(list), defaultdict(list)
    for item in foods:
        if item["cuisine"]:
            food_by_city[item["city_key"]].append(item)
    for item in sights:
        sight_by_city[item["city_key"]].append(item)
    for item in hotels:
        hotel_by_city[item["city_key"]].append(item)
    for bucket in list(food_by_city.values()) + list(sight_by_city.values()) + list(hotel_by_city.values()):
        bucket.sort(key=cost_key)

    route, estimate = choose_route(city_names, food_by_city, sight_by_city, hotel_by_city, wanted, party_size, budget)
    schedule = [route[0], route[0], route[1], route[1], route[2], route[2], route[2]]
    remaining = list(wanted)
    plan, known_subtotal = [], 0.0
    for index, key in enumerate(schedule):
        local_food = food_by_city[key]
        needed = next((c for c in remaining if any(has_cuisine(x, c) for x in local_food)), None)
        meal = min((x for x in local_food if has_cuisine(x, needed)), key=cost_key) if needed else min(local_food, key=cost_key)
        if needed:
            remaining.remove(needed)
        lodging = min(hotel_by_city[key], key=cost_key)
        if lodging["price"] is not None:
            known_subtotal += lodging["price"]
        if meal["price"] is not None:
            known_subtotal += meal["price"] * party_size
        points = sight_by_city[key]
        attractions = points[(2 * index) % len(points)]["name"] + ";" + points[(2 * index + 1) % len(points)]["name"] + ";"
        city = city_names[key]
        if index == 0:
            current, transport = "from %s to %s" % (config["origin"], city), "Self-driving: from %s to %s" % (config["origin"], city)
        elif index in (2, 4):
            previous = city_names[schedule[index - 1]]
            current, transport = "from %s to %s" % (previous, city), "Self-driving: from %s to %s" % (previous, city)
        else:
            current, transport = city, "Self-driving within %s" % city
        meals = ["-", "-", "-"]
        meals[index % 3] = meal["name"]
        plan.append({"day": index + 1, "current_city": current, "transportation": transport,
                     "breakfast": meals[0], "lunch": meals[1], "dinner": meals[2],
                     "attraction": attractions, "accommodation": lodging["name"]})
    if remaining:
        raise ValueError("internal cuisine coverage failure: " + ", ".join(remaining))
    if known_subtotal > budget:
        raise ValueError("known lodging and meal subtotal exceeds budget")

    artifact = {"plan": plan, "tool_called": ["search_cities", "search_accommodations", "search_restaurants", "search_attractions", "search_distance_matrix"]}
    output = Path(config["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(output.parent), delete=False) as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, output)
    return {"ok": True, "output_path": str(output), "chosen_cities": [city_names[key] for key in route], "known_subtotal": round(known_subtotal, 2), "route_estimate": round(estimate, 2)}


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin must be a JSON object")
        print(json.dumps(build(request), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
