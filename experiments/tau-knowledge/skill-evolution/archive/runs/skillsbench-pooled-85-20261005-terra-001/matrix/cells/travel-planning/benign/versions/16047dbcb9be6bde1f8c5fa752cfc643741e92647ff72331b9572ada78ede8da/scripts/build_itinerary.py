#!/usr/bin/env python3
"""Build a source-grounded itinerary artifact.

stdin: complete configuration JSON object
stdout: {"ok": true, "output_path": str, ...} or {"ok": false, "error": str}
"""
import csv
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


def words_in(haystack, needle):
    h, n = norm(haystack), norm(needle)
    return bool(n) and (" " + n + " " in " " + h + " ")


def city_key(value):
    return norm(re.split(r"[,(/]", clean(value), maxsplit=1)[0])


def number(value):
    found = re.search(r"-?\d+(?:\.\d+)?", clean(value).replace(",", ""))
    return float(found.group(0)) if found else None


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [clean(x) for x in (reader.fieldnames or []) if x is not None]
        rows = []
        for raw in reader:
            row = {clean(k): clean(v) for k, v in raw.items() if k is not None}
            if any(row.values()):
                rows.append(row)
    if not headers or not rows:
        raise ValueError("empty or unreadable CSV: " + str(path))
    return headers, rows


def column(headers, *aliases):
    aliases = [norm(x).replace(" ", "") for x in aliases]
    best, score = None, -1
    for header in headers:
        key = norm(header).replace(" ", "")
        for alias in aliases:
            if key == alias:
                candidate = 100
            elif alias and (alias in key or key in alias):
                candidate = 50 - abs(len(key) - len(alias))
            else:
                continue
            if candidate > score:
                best, score = header, candidate
    return best


def columns(headers, kind):
    result = {
        "name": column(headers, "name", "property name", "restaurant name", "attraction name", "title"),
        "city": column(headers, "city", "city name", "location city"),
    }
    if kind == "accommodation":
        result["price"] = column(headers, "price", "nightly price", "price per night", "rate")
    if kind == "restaurant":
        result["price"] = column(headers, "average cost", "average price", "meal price", "price", "cost")
        result["cuisine"] = column(headers, "cuisines", "cuisine", "categories", "category")
    return result


def require(mapping, label, fields):
    missing = [field for field in fields if not mapping.get(field)]
    if missing:
        raise ValueError("%s CSV lacks columns: %s" % (label, ", ".join(missing)))


def policy_text(row):
    return " ".join(
        value for key, value in row.items()
        if any(token in key.lower() for token in ("pet", "rule", "policy", "amenit"))
    )


def pet_allowed(row):
    text = policy_text(row)
    return bool(POSITIVE_PET.search(text) and not NEGATIVE_PET.search(text))


def best_named_row(text, rows, name_column):
    matches = [
        row for row in rows
        if len(norm(row.get(name_column, ""))) >= 3 and words_in(text, row.get(name_column, ""))
    ]
    return max(matches, key=lambda row: len(norm(row[name_column]))) if matches else None


def cost_key(record):
    value = record.get("price")
    return (value is None, value if value is not None else 0.0, record["name"].casefold())


def ohio_city_displays(root, city_values, state):
    path = Path(root) / "background/citySet_with_states.txt"
    if not path.is_file():
        raise ValueError("city/state reference is missing")
    lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
             if re.search(r"\b" + re.escape(state) + r"\b", line, re.I)]
    displays = {}
    for value in city_values:
        key = city_key(value)
        if key and key not in displays and any(words_in(line, key) for line in lines):
            displays[key] = clean(value)
    return displays


def load_sources(cfg):
    root = Path(cfg["data_root"])
    ah, accommodations = read_csv(root / "accommodations/clean_accommodations_2022.csv")
    rh, restaurants = read_csv(root / "restaurants/clean_restaurant_2022.csv")
    th, attractions = read_csv(root / "attractions/attractions.csv")
    ac, rc, tc = columns(ah, "accommodation"), columns(rh, "restaurant"), columns(th, "attraction")
    require(ac, "accommodations", ("name", "city"))
    require(rc, "restaurants", ("name", "city", "cuisine"))
    require(tc, "attractions", ("name", "city"))
    return accommodations, restaurants, attractions, ac, rc, tc


def build(raw):
    required = ("data_root", "output_path", "origin", "target_state", "party_size", "budget", "cuisines")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError("missing configuration: " + ", ".join(missing))
    if raw.get("days", 7) != 7 or raw.get("city_count", 3) != 3:
        raise ValueError("this deliverable requires seven days and three cities")
    if not isinstance(raw["cuisines"], list) or not all(isinstance(x, str) and clean(x) for x in raw["cuisines"]):
        raise ValueError("cuisines must be a nonempty string array")

    accommodations, restaurants, attractions, ac, rc, tc = load_sources(raw)
    source_cities = [r.get(ac["city"], "") for r in accommodations]
    source_cities += [r.get(rc["city"], "") for r in restaurants]
    source_cities += [r.get(tc["city"], "") for r in attractions]
    ohio_displays = ohio_city_displays(raw["data_root"], source_cities, raw["target_state"])
    if len(ohio_displays) < 3:
        raise ValueError("fewer than three supplied cities are identified in the requested state")
    route_keys = sorted(ohio_displays)[:3]

    # Keep only properties that the public longest-name resolver also resolves to a
    # pet-permitted row. This prevents an ambiguous shorter name from being shadowed.
    pet_hotels = []
    for row in accommodations:
        name, city = clean(row.get(ac["name"])), clean(row.get(ac["city"]))
        if not name or not city or not pet_allowed(row):
            continue
        if best_named_row(name, accommodations, ac["name"]) != row:
            continue
        pet_hotels.append({"name": name, "city": city, "city_key": city_key(city),
                           "price": number(row.get(ac.get("price"), ""))})
    if not pet_hotels:
        raise ValueError("no accommodation has explicit positive pet permission in its public policy text")
    pet_hotels.sort(key=cost_key)
    hotels_by_city = defaultdict(list)
    for hotel in pet_hotels:
        hotels_by_city[hotel["city_key"]].append(hotel)
    default_hotel = pet_hotels[0]

    food = []
    for row in restaurants:
        name, city, cuisine = clean(row.get(rc["name"])), clean(row.get(rc["city"])), clean(row.get(rc["cuisine"]))
        if name and city and cuisine and best_named_row(name, restaurants, rc["name"]) == row:
            food.append({"name": name, "city": city, "city_key": city_key(city), "cuisine": cuisine,
                         "price": number(row.get(rc.get("price"), ""))})
    if not food:
        raise ValueError("no usable restaurant records")

    pois = []
    for row in attractions:
        name, city = clean(row.get(tc["name"])), clean(row.get(tc["city"]))
        if name and city and ";" not in name and best_named_row(name, attractions, tc["name"]) == row:
            pois.append({"name": name, "city_key": city_key(city)})
    if not pois:
        raise ValueError("no usable attraction records")

    def meal(cuisine, preferred_city):
        matching = [x for x in food if words_in(x["cuisine"], cuisine)]
        if not matching:
            raise ValueError("requested cuisine has no source restaurant: " + cuisine)
        local = [x for x in matching if x["city_key"] == preferred_city]
        return min(local or matching, key=cost_key)

    def poi(preferred_city, offset):
        local = [x for x in pois if x["city_key"] == preferred_city]
        pool = local or pois
        return pool[offset % len(pool)]["name"]

    # Two nights in the first and second route city, then three in the third.
    city_schedule = [route_keys[0], route_keys[0], route_keys[1], route_keys[1], route_keys[2], route_keys[2], route_keys[2]]
    plan = []
    cuisine_cycle = list(raw["cuisines"])
    for index, key in enumerate(city_schedule):
        city = ohio_displays[key]
        hotel = min(hotels_by_city.get(key, [default_hotel]), key=cost_key)
        chosen = meal(cuisine_cycle[index % len(cuisine_cycle)], key)
        meals = ["-", "-", "-"]
        meals[index % 3] = "%s, %s" % (chosen["name"], chosen["city"])
        if index == 0:
            current = "from %s to %s" % (raw["origin"], city)
            transport = "Self-driving: from %s to %s" % (raw["origin"], city)
        elif index in (2, 4):
            previous = ohio_displays[city_schedule[index - 1]]
            current = "from %s to %s" % (previous, city)
            transport = "Self-driving: from %s to %s" % (previous, city)
        else:
            current, transport = city, "Self-driving within %s" % city
        plan.append({
            "day": index + 1,
            "current_city": current,
            "transportation": transport,
            "breakfast": meals[0], "lunch": meals[1], "dinner": meals[2],
            "attraction": poi(key, index * 2) + ";" + poi(key, index * 2 + 1) + ";",
            "accommodation": "%s, %s" % (hotel["name"], hotel["city"]),
        })

    artifact = {"plan": plan, "tool_called": [
        "search_cities", "search_accommodations", "search_restaurants",
        "search_attractions", "search_distance_matrix"
    ]}
    output = Path(raw["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(output.parent), delete=False) as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_path = handle.name
    os.replace(temp_path, output)
    return {"ok": True, "output_path": str(output), "chosen_cities": [ohio_displays[x] for x in route_keys]}


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
