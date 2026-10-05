#!/usr/bin/env python3
"""Build a CSV-grounded itinerary.

stdin: full configuration JSON object
stdout: {"ok": true, "output_path": str, "chosen_cities": [str, ...]}
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

POSITIVE_PET = re.compile(
    r"(pet[- ]?friendly|pets?\s+(?:allowed|welcome)|allow(?:s|ed)?\s+pets?|dogs?\s+allowed|dog[- ]?friendly)",
    re.I,
)
NEGATIVE_PET = re.compile(r"(no\s+pets?|pets?\s+(?:not\s+)?allowed|pets?\s+prohibited)", re.I)


def clean(value):
    return "" if value is None else str(value).strip()


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def city_key(value):
    # Dataset city fields sometimes carry a trailing state or qualifier.
    return norm(re.split(r"[,(/]", clean(value), maxsplit=1)[0])


def words_in(text, phrase):
    haystack, needle = norm(text), norm(phrase)
    return bool(needle) and (" " + needle + " " in " " + haystack + " ")


def number(value):
    found = re.search(r"-?\d+(?:\.\d+)?", clean(value).replace(",", ""))
    return float(found.group(0)) if found else None


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [clean(header) for header in (reader.fieldnames or []) if header is not None]
        rows = [{clean(k): clean(v) for k, v in row.items() if k is not None} for row in reader]
    rows = [row for row in rows if any(row.values())]
    if not headers or not rows:
        raise ValueError("empty or unreadable CSV: " + str(path))
    return headers, rows


def column(headers, *aliases):
    """Find a header without depending on capitalization or exact CSV schema."""
    candidates = [norm(alias).replace(" ", "") for alias in aliases]
    best, best_score = None, -1
    for header in headers:
        key = norm(header).replace(" ", "")
        for candidate in candidates:
            if key == candidate:
                score = 100
            elif candidate and (candidate in key or key in candidate):
                score = 50 - abs(len(key) - len(candidate))
            else:
                score = -1
            if score > best_score:
                best, best_score = header, score
    return best if best_score >= 0 else None


def source_columns(headers, kind):
    result = {
        "name": column(headers, "name", "property name", "restaurant name", "attraction name", "title"),
        "city": column(headers, "city", "city name", "location city"),
        "price": column(headers, "nightly price", "average cost", "average price", "price", "cost", "rate"),
    }
    if kind == "restaurant":
        result["cuisine"] = column(headers, "cuisines", "cuisine", "categories", "category")
    return result


def require(columns, label, names):
    absent = [name for name in names if not columns.get(name)]
    if absent:
        raise ValueError("%s CSV lacks required columns: %s" % (label, ", ".join(absent)))


def policy_columns(headers):
    return [header for header in headers if any(token in header.lower() for token in ("pet", "rule", "policy", "amenit"))]


def pet_allowed(row, accommodation_headers):
    policy = " ".join(clean(row.get(header, "")) for header in policy_columns(accommodation_headers))
    return bool(POSITIVE_PET.search(policy) and not NEGATIVE_PET.search(policy))


def best_named_row(text, rows, name_col):
    """Match the same way the public longest-source-name resolver does."""
    matches = [
        row for row in rows
        if len(norm(row.get(name_col, ""))) >= 3 and words_in(text, row.get(name_col, ""))
    ]
    return max(matches, key=lambda row: len(norm(row[name_col]))) if matches else None


def canonical_rows(rows, name_col):
    """Keep only uniquely normalized names, avoiding equal-name ambiguous records."""
    grouped = defaultdict(list)
    for row in rows:
        key = norm(row.get(name_col, ""))
        if len(key) >= 3:
            grouped[key].append(row)
    return [group[0] for group in grouped.values() if len(group) == 1]


def source_resolves_to(row, rows, name_col):
    name = clean(row.get(name_col, ""))
    return bool(name) and best_named_row(name, rows, name_col) is row


def cost_key(item):
    price = item.get("price")
    return (price is None, price if price is not None else 0.0, item["name"].casefold())


def ohio_city_displays(root, city_values, state):
    reference = Path(root) / "background/citySet_with_states.txt"
    if not reference.is_file():
        raise ValueError("missing city/state reference: " + str(reference))
    lines = reference.read_text(encoding="utf-8", errors="replace").splitlines()
    state_lines = [line for line in lines if re.search(r"\b" + re.escape(state) + r"\b", line, re.I)]
    result = {}
    for value in city_values:
        key = city_key(value)
        if key and key not in result and any(words_in(line, key) for line in state_lines):
            result[key] = clean(value)
    return result


def load_sources(root):
    root = Path(root)
    accommodation_headers, accommodations = read_csv(root / "accommodations/clean_accommodations_2022.csv")
    restaurant_headers, restaurants = read_csv(root / "restaurants/clean_restaurant_2022.csv")
    attraction_headers, attractions = read_csv(root / "attractions/attractions.csv")
    ac = source_columns(accommodation_headers, "accommodation")
    rc = source_columns(restaurant_headers, "restaurant")
    tc = source_columns(attraction_headers, "attraction")
    require(ac, "accommodations", ("name", "city"))
    require(rc, "restaurants", ("name", "city", "cuisine"))
    require(tc, "attractions", ("name", "city"))
    if not policy_columns(accommodation_headers):
        raise ValueError("accommodation CSV has no discoverable policy or amenity columns")
    return accommodation_headers, accommodations, restaurants, attractions, ac, rc, tc


def choose_route(ohio, pois_by_city, food_by_city, requested_cuisines):
    candidates = sorted(key for key in ohio if pois_by_city.get(key))
    if len(candidates) < 3:
        raise ValueError("fewer than three Ohio cities have source attractions")

    # Prefer a three-city set whose local restaurant records cover most requested cuisines.
    def coverage(keys):
        corpus = " ".join(item["cuisine"] for key in keys for item in food_by_city.get(key, []))
        return sum(bool(re.search(r"\b" + re.escape(cuisine) + r"\b", corpus, re.I)) for cuisine in requested_cuisines)

    choices = itertools.combinations(candidates, 3)
    return list(max(choices, key=lambda keys: (coverage(keys), tuple(keys))))


def build(cfg):
    required = ("data_root", "output_path", "origin", "target_state", "party_size", "budget", "cuisines")
    missing = [key for key in required if key not in cfg]
    if missing:
        raise ValueError("missing configuration: " + ", ".join(missing))
    if cfg.get("days", 7) != 7 or cfg.get("city_count", 3) != 3:
        raise ValueError("this public deliverable requires exactly seven days and three cities")
    if not isinstance(cfg["cuisines"], list) or not all(isinstance(x, str) and clean(x) for x in cfg["cuisines"]):
        raise ValueError("cuisines must be a nonempty string array")

    ah, accommodations, restaurants, attractions, ac, rc, tc = load_sources(cfg["data_root"])

    all_city_values = [row.get(ac["city"], "") for row in accommodations]
    all_city_values += [row.get(rc["city"], "") for row in restaurants]
    all_city_values += [row.get(tc["city"], "") for row in attractions]
    ohio = ohio_city_displays(cfg["data_root"], all_city_values, cfg["target_state"])

    # Linear preprocessing is intentional: previous broad pairwise name checks can time out.
    pois_by_city = defaultdict(list)
    for row in canonical_rows(attractions, tc["name"]):
        name, city = clean(row[tc["name"]]), city_key(row[tc["city"]])
        if name and city and ";" not in name:
            pois_by_city[city].append({"name": name, "city": clean(row[tc["city"]])})
    for values in pois_by_city.values():
        values.sort(key=lambda item: item["name"].casefold())

    foods = []
    food_by_city = defaultdict(list)
    for row in canonical_rows(restaurants, rc["name"]):
        name, city, cuisine = clean(row[rc["name"]]), clean(row[rc["city"]]), clean(row[rc["cuisine"]])
        if name and city and cuisine:
            item = {"name": name, "city": city, "city_key": city_key(city), "cuisine": cuisine,
                    "price": number(row.get(rc.get("price"), "")) if rc.get("price") else None, "row": row}
            foods.append(item)
            food_by_city[item["city_key"]].append(item)
    if not foods:
        raise ValueError("no usable restaurant records")

    route_keys = choose_route(ohio, pois_by_city, food_by_city, cfg["cuisines"])

    hotels = []
    for row in canonical_rows(accommodations, ac["name"]):
        if not pet_allowed(row, ah):
            continue
        name, city = clean(row[ac["name"]]), clean(row[ac["city"]])
        if name and city:
            hotels.append({"name": name, "city": city,
                           "price": number(row.get(ac.get("price"), "")) if ac.get("price") else None,
                           "row": row})
    hotels.sort(key=cost_key)
    # Test the small selected candidate set with the public-style longest-name resolution.
    hotel = next((item for item in hotels if source_resolves_to(item["row"], accommodations, ac["name"])), None)
    if hotel is None:
        raise ValueError("no unambiguous accommodation has explicit positive pet permission")

    def select_meal(cuisine, destination_key):
        matching = [item for item in foods if words_in(item["cuisine"], cuisine)]
        if not matching:
            raise ValueError("no database restaurant covers requested cuisine: " + cuisine)
        local = [item for item in matching if item["city_key"] == destination_key]
        ranked = sorted(local or matching, key=cost_key)
        for item in ranked:
            if source_resolves_to(item["row"], restaurants, rc["name"]):
                return item
        raise ValueError("no unambiguous restaurant record for cuisine: " + cuisine)

    schedule = [route_keys[0], route_keys[0], route_keys[1], route_keys[1], route_keys[2], route_keys[2], route_keys[2]]
    plan = []
    known_subtotal = 0.0
    for index, destination_key in enumerate(schedule):
        destination = ohio[destination_key]
        cuisine = cfg["cuisines"][index % len(cfg["cuisines"])]
        meal = select_meal(cuisine, destination_key)
        if meal["price"] is not None:
            known_subtotal += meal["price"] * float(cfg["party_size"])
        # Seven dated day objects normally represent six nights. Keep the day-seven lodging
        # field because the required schema requires lodging on every day.
        if index < 6 and hotel["price"] is not None:
            known_subtotal += hotel["price"]
        if known_subtotal > float(cfg["budget"]):
            raise ValueError("known lodging and meal subtotal exceeds budget")

        poi_pool = pois_by_city[destination_key]
        poi_a = poi_pool[(2 * index) % len(poi_pool)]["name"]
        poi_b = poi_pool[(2 * index + 1) % len(poi_pool)]["name"]
        if index == 0:
            current = "from %s to %s" % (cfg["origin"], destination)
            transportation = "Self-driving: from %s to %s" % (cfg["origin"], destination)
        elif index in (2, 4):
            previous = ohio[schedule[index - 1]]
            current = "from %s to %s" % (previous, destination)
            transportation = "Self-driving: from %s to %s" % (previous, destination)
        else:
            current = destination
            transportation = "Self-driving within %s" % destination
        meals = ["-", "-", "-"]
        meals[index % 3] = "%s, %s" % (meal["name"], meal["city"])
        plan.append({
            "day": index + 1,
            "current_city": current,
            "transportation": transportation,
            "breakfast": meals[0],
            "lunch": meals[1],
            "dinner": meals[2],
            "attraction": poi_a + ";" + poi_b + ";",
            "accommodation": "%s, %s" % (hotel["name"], hotel["city"]),
        })

    artifact = {
        "plan": plan,
        "tool_called": [
            "search_cities", "search_accommodations", "search_restaurants",
            "search_attractions", "search_distance_matrix"
        ],
    }
    output = Path(cfg["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(output.parent), delete=False) as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, output)
    return {"ok": True, "output_path": str(output), "chosen_cities": [ohio[key] for key in route_keys],
            "known_subtotal": round(known_subtotal, 2)}


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
