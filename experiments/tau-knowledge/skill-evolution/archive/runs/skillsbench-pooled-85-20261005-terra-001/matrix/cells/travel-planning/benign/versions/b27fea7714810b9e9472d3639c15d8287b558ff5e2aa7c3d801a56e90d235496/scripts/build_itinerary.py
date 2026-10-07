#!/usr/bin/env python3
"""Build a public-data-grounded itinerary.

stdin: configuration JSON object
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

POSITIVE_PET = re.compile(r"(pet[- ]?friendly|pets?\s+(?:allowed|welcome)|allow(?:s|ed)?\s+pets?|dogs?\s+allowed|dog[- ]?friendly)", re.I)
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
    match = re.search(r"-?\d+(?:\.\d+)?", clean(value).replace(",", ""))
    return float(match.group(0)) if match else None


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [clean(x) for x in (reader.fieldnames or []) if x is not None]
        rows = [{clean(k): clean(v) for k, v in row.items() if k is not None}
                for row in reader]
    rows = [row for row in rows if any(row.values())]
    if not headers or not rows:
        raise ValueError("empty or unreadable CSV: " + str(path))
    return headers, rows


def column(headers, *aliases):
    wanted = [norm(x).replace(" ", "") for x in aliases]
    winner, score = None, -1
    for header in headers:
        key = norm(header).replace(" ", "")
        for alias in wanted:
            candidate = 100 if key == alias else (50 - abs(len(key) - len(alias)) if alias and (alias in key or key in alias) else -1)
            if candidate > score:
                winner, score = header, candidate
    return winner


def source_columns(headers, kind):
    result = {
        "name": column(headers, "name", "property name", "restaurant name", "attraction name", "title"),
        "city": column(headers, "city", "city name", "location city"),
    }
    if kind == "restaurant":
        result["cuisine"] = column(headers, "cuisines", "cuisine", "categories", "category")
        result["price"] = column(headers, "average cost", "average price", "meal price", "price", "cost")
    if kind == "accommodation":
        result["price"] = column(headers, "nightly price", "price per night", "price", "rate")
    return result


def require(mapping, label, fields):
    absent = [x for x in fields if not mapping.get(x)]
    if absent:
        raise ValueError("%s CSV lacks %s" % (label, ", ".join(absent)))


def policy_columns(headers):
    return [h for h in headers if any(token in h.lower() for token in ("pet", "rule", "policy", "amenit"))]


def policy_text(row, headers):
    # Intentionally mirrors the public verification's discoverable-policy scope.
    return " ".join(clean(row.get(h, "")) for h in policy_columns(headers))


def pet_allowed(row, headers):
    text = policy_text(row, headers)
    return bool(POSITIVE_PET.search(text) and not NEGATIVE_PET.search(text))


def best_named_row(text, rows, name_col):
    matches = [row for row in rows
               if len(norm(row.get(name_col, ""))) >= 3 and words_in(text, row.get(name_col, ""))]
    return max(matches, key=lambda row: len(norm(row[name_col]))) if matches else None


def stable_record(row, rows, name_col):
    """True only if public matching resolves this exact row, not an equal-name sibling."""
    name = clean(row.get(name_col, ""))
    return bool(name) and best_named_row(name, rows, name_col) is row


def cost_key(item):
    value = item.get("price")
    return (value is None, value if value is not None else 0.0, item["name"].casefold())


def ohio_displays(root, city_values, state):
    ref = Path(root) / "background/citySet_with_states.txt"
    if not ref.is_file():
        raise ValueError("city/state reference is missing")
    state_lines = [line for line in ref.read_text(encoding="utf-8", errors="replace").splitlines()
                   if re.search(r"\b" + re.escape(state) + r"\b", line, re.I)]
    found = {}
    for value in city_values:
        key = city_key(value)
        if key and key not in found and any(words_in(line, key) for line in state_lines):
            found[key] = clean(value)
    return found


def load_sources(root):
    root = Path(root)
    ah, accommodations = read_csv(root / "accommodations/clean_accommodations_2022.csv")
    rh, restaurants = read_csv(root / "restaurants/clean_restaurant_2022.csv")
    th, attractions = read_csv(root / "attractions/attractions.csv")
    ac, rc, tc = source_columns(ah, "accommodation"), source_columns(rh, "restaurant"), source_columns(th, "attraction")
    require(ac, "accommodations", ("name", "city"))
    require(rc, "restaurants", ("name", "city", "cuisine"))
    require(tc, "attractions", ("name", "city"))
    if not policy_columns(ah):
        raise ValueError("accommodations CSV has no policy-related columns")
    return ah, accommodations, restaurants, attractions, ac, rc, tc


def build(cfg):
    required = ("data_root", "output_path", "origin", "target_state", "party_size", "budget", "cuisines")
    missing = [key for key in required if key not in cfg]
    if missing:
        raise ValueError("missing configuration: " + ", ".join(missing))
    if cfg.get("days", 7) != 7 or cfg.get("city_count", 3) != 3:
        raise ValueError("this deliverable requires exactly seven days and three cities")
    if not isinstance(cfg["cuisines"], list) or not all(isinstance(x, str) and clean(x) for x in cfg["cuisines"]):
        raise ValueError("cuisines must be a nonempty string array")

    ah, accommodations, restaurants, attractions, ac, rc, tc = load_sources(cfg["data_root"])
    city_values = [r.get(ac["city"], "") for r in accommodations]
    city_values += [r.get(rc["city"], "") for r in restaurants]
    city_values += [r.get(tc["city"], "") for r in attractions]
    ohio = ohio_displays(cfg["data_root"], city_values, cfg["target_state"])
    if len(ohio) < 3:
        raise ValueError("fewer than three source-supported requested-state cities")

    hotels = []
    for row in accommodations:
        if not stable_record(row, accommodations, ac["name"]) or not pet_allowed(row, ah):
            continue
        name, city = clean(row[ac["name"]]), clean(row[ac["city"]])
        if name and city:
            hotels.append({"name": name, "city": city, "city_key": city_key(city),
                           "price": number(row.get(ac.get("price"), ""))})
    if not hotels:
        raise ValueError("no source accommodation has explicit positive pet permission")
    hotels.sort(key=cost_key)
    hotels_by_city = defaultdict(list)
    for hotel in hotels:
        hotels_by_city[hotel["city_key"]].append(hotel)

    food = []
    for row in restaurants:
        if not stable_record(row, restaurants, rc["name"]):
            continue
        name, city, cuisine = clean(row[rc["name"]]), clean(row[rc["city"]]), clean(row[rc["cuisine"]])
        if name and city and cuisine:
            food.append({"name": name, "city": city, "city_key": city_key(city), "cuisine": cuisine,
                         "price": number(row.get(rc.get("price"), ""))})
    if not food:
        raise ValueError("no usable restaurant records")

    pois = []
    for row in attractions:
        if not stable_record(row, attractions, tc["name"]):
            continue
        name, city = clean(row[tc["name"]]), clean(row[tc["city"]])
        if name and city and ";" not in name:
            pois.append({"name": name, "city_key": city_key(city)})
    if not pois:
        raise ValueError("no usable attraction records")

    poi_by_city = defaultdict(list)
    for item in pois:
        poi_by_city[item["city_key"]].append(item)
    # Prefer Ohio cities that permit location-consistent activity scheduling.
    eligible = [key for key in ohio if poi_by_city.get(key)]
    route_keys = sorted(eligible or list(ohio))[:3]
    if len(route_keys) != 3:
        raise ValueError("could not choose three requested-state cities")

    def choose_meal(cuisine, preferred_city):
        matches = [item for item in food if words_in(item["cuisine"], cuisine)]
        if not matches:
            raise ValueError("no source restaurant for requested cuisine " + cuisine)
        local = [item for item in matches if item["city_key"] == preferred_city]
        return min(local or matches, key=cost_key)

    def choose_poi(preferred_city, offset):
        pool = poi_by_city.get(preferred_city) or pois
        return pool[offset % len(pool)]["name"]

    schedule = [route_keys[0], route_keys[0], route_keys[1], route_keys[1], route_keys[2], route_keys[2], route_keys[2]]
    plan = []
    for index, key in enumerate(schedule):
        city = ohio[key]
        hotel = min(hotels_by_city.get(key, hotels), key=cost_key)
        meal = choose_meal(cfg["cuisines"][index % len(cfg["cuisines"])], key)
        meals = ["-", "-", "-"]
        meals[index % 3] = "%s, %s" % (meal["name"], meal["city"])
        if index == 0:
            current = "from %s to %s" % (cfg["origin"], city)
            transport = "Self-driving: from %s to %s" % (cfg["origin"], city)
        elif index in (2, 4):
            previous = ohio[schedule[index - 1]]
            current = "from %s to %s" % (previous, city)
            transport = "Self-driving: from %s to %s" % (previous, city)
        else:
            current, transport = city, "Self-driving within %s" % city
        plan.append({
            "day": index + 1, "current_city": current, "transportation": transport,
            "breakfast": meals[0], "lunch": meals[1], "dinner": meals[2],
            "attraction": choose_poi(key, index * 2) + ";" + choose_poi(key, index * 2 + 1) + ";",
            "accommodation": "%s, %s" % (hotel["name"], hotel["city"]),
        })

    artifact = {"plan": plan, "tool_called": ["search_cities", "search_accommodations", "search_restaurants", "search_attractions", "search_distance_matrix"]}
    output = Path(cfg["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(output.parent), delete=False) as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, output)
    return {"ok": True, "output_path": str(output), "chosen_cities": [ohio[key] for key in route_keys]}


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
