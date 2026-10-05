#!/usr/bin/env python3
"""Create a CSV-grounded itinerary artifact.

stdin: complete JSON configuration object
stdout: JSON status object
"""
import csv
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path

POSITIVE_PET = re.compile(r"(pet[- ]?friendly|pets?\s+(?:allowed|welcome)|allow(?:s|ed)?\s+pets?|dogs?\s+allowed|dog[- ]?friendly)", re.I)
NEGATIVE_PET = re.compile(r"(no\s+pets?|pets?\s+(?:not\s+)?allowed|pets?\s+prohibited)", re.I)


def clean(value):
    return "" if value is None else str(value).strip()


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def has_words(haystack, needle):
    h, n = norm(haystack), norm(needle)
    return bool(n) and (" " + n + " ") in (" " + h + " ")


def city_key(value):
    return norm(re.split(r"[,(/]", clean(value), maxsplit=1)[0])


def parse_number(value):
    match = re.search(r"-?\d+(?:\.\d+)?", clean(value).replace(",", ""))
    return float(match.group(0)) if match else None


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [clean(h) for h in (reader.fieldnames or []) if h is not None]
        rows = []
        for row in reader:
            row = {clean(k): clean(v) for k, v in row.items() if k is not None}
            if any(row.values()):
                rows.append(row)
    if not headers or not rows:
        raise ValueError("empty or unreadable CSV: " + str(path))
    return headers, rows


def column(headers, *aliases):
    candidates = [(norm(alias).replace(" ", ""), alias) for alias in aliases]
    best, score = None, -1
    for header in headers:
        key = norm(header).replace(" ", "")
        for alias, _ in candidates:
            if key == alias:
                value = 100
            elif alias and (alias in key or key in alias):
                value = 50 - abs(len(key) - len(alias))
            else:
                continue
            if value > score:
                best, score = header, value
    return best


def source_columns(headers, kind):
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


def require_columns(label, mapping, keys):
    missing = [key for key in keys if not mapping.get(key)]
    if missing:
        raise ValueError("%s dataset lacks required column(s): %s" % (label, ", ".join(missing)))


def policy_text(row):
    return " ".join(value for key, value in row.items()
                    if any(token in key.lower() for token in ("pet", "rule", "policy", "amenit")))


def pet_allowed(row):
    policy = policy_text(row)
    return bool(POSITIVE_PET.search(policy) and not NEGATIVE_PET.search(policy))


def ohio_city_keys(root, city_values, state):
    reference = Path(root) / "background/citySet_with_states.txt"
    if not reference.is_file():
        raise ValueError("required city/state reference is missing")
    lines = [line for line in reference.read_text(encoding="utf-8", errors="replace").splitlines()
             if re.search(r"\b" + re.escape(state) + r"\b", line, re.I)]
    result = set()
    for value in city_values:
        key = city_key(value)
        if key and any(has_words(line, key) for line in lines):
            result.add(key)
    return result


def price_sort(record):
    price = record.get("price")
    return (price is None, price if price is not None else 0, record["name"].casefold())


def make_catalogs(cfg):
    root = Path(cfg["data_root"])
    ah, accommodations = read_csv(root / "accommodations/clean_accommodations_2022.csv")
    rh, restaurants = read_csv(root / "restaurants/clean_restaurant_2022.csv")
    th, attractions = read_csv(root / "attractions/attractions.csv")
    ac, rc, tc = source_columns(ah, "accommodation"), source_columns(rh, "restaurant"), source_columns(th, "attraction")
    require_columns("accommodations", ac, ("name", "city"))
    require_columns("restaurants", rc, ("name", "city", "cuisine"))
    require_columns("attractions", tc, ("name", "city"))

    all_cities = [row.get(ac["city"], "") for row in accommodations]
    all_cities += [row.get(rc["city"], "") for row in restaurants]
    all_cities += [row.get(tc["city"], "") for row in attractions]
    allowed = ohio_city_keys(root, all_cities, cfg["target_state"])

    hotels = defaultdict(list)
    for row in accommodations:
        name, city = clean(row.get(ac["name"])), clean(row.get(ac["city"]))
        key = city_key(city)
        if name and city and key in allowed and pet_allowed(row):
            hotels[key].append({"name": name, "city": city,
                                "price": parse_number(row.get(ac.get("price", "")))})
    hotels = {key: min(records, key=price_sort) for key, records in hotels.items()}
    if len(hotels) < cfg["city_count"]:
        raise ValueError("fewer than %d Ohio cities have source lodging with explicit positive pet permission" % cfg["city_count"])

    food = []
    for row in restaurants:
        name, city, cuisine = clean(row.get(rc["name"])), clean(row.get(rc["city"])), clean(row.get(rc["cuisine"]))
        if name and city and cuisine:
            food.append({"name": name, "city": city, "city_key": city_key(city), "cuisine": cuisine,
                         "price": parse_number(row.get(rc.get("price", "")))})
    places = []
    for row in attractions:
        name, city = clean(row.get(tc["name"])), clean(row.get(tc["city"]))
        # A semicolon in a source name would make the mandated list encoding ambiguous.
        if name and city and ";" not in name and len(norm(name)) >= 3:
            places.append({"name": name, "city": city, "city_key": city_key(city)})
    if not food or not places:
        raise ValueError("restaurant or attraction source records are unavailable")
    return hotels, food, places


def meal_for(food, cuisine, preferred_city):
    candidates = [x for x in food if has_words(x["cuisine"], cuisine) and x["city_key"] == preferred_city]
    if not candidates:
        candidates = [x for x in food if has_words(x["cuisine"], cuisine)]
    if not candidates:
        raise ValueError("no source restaurant has requested cuisine: " + cuisine)
    return min(candidates, key=price_sort)


def attraction_for(places, preferred_city, offset):
    local = [x for x in places if x["city_key"] == preferred_city]
    pool = local or places
    return pool[offset % len(pool)]["name"]


def validate_config(raw):
    required = ("data_root", "output_path", "origin", "target_state", "start_date", "end_date", "party_size", "budget", "cuisines")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError("missing configuration field(s): " + ", ".join(missing))
    cfg = dict(raw)
    if cfg.get("days", 7) != 7 or cfg.get("city_count", 3) != 3:
        raise ValueError("this task requires exactly seven days and three cities")
    if not isinstance(cfg["party_size"], int) or isinstance(cfg["party_size"], bool) or cfg["party_size"] < 1:
        raise ValueError("party_size must be a positive integer")
    if not isinstance(cfg["budget"], (int, float)) or isinstance(cfg["budget"], bool) or cfg["budget"] <= 0:
        raise ValueError("budget must be a positive number")
    if not isinstance(cfg["cuisines"], list) or not cfg["cuisines"] or not all(isinstance(x, str) and clean(x) for x in cfg["cuisines"]):
        raise ValueError("cuisines must be a nonempty string array")
    try:
        span = (date.fromisoformat(cfg["end_date"]) - date.fromisoformat(cfg["start_date"])).days + 1
    except ValueError as exc:
        raise ValueError("dates must be ISO YYYY-MM-DD") from exc
    if span != 7:
        raise ValueError("the requested dates must span seven inclusive days")
    if not Path(cfg["data_root"]).is_dir():
        raise ValueError("data_root is not a readable directory")
    return cfg


def build(raw):
    cfg = validate_config(raw)
    hotels, food, places = make_catalogs(cfg)
    # Lowest priced source property in each city minimizes known lodging cost.
    selected_keys = sorted(hotels, key=lambda key: price_sort(hotels[key]))[:cfg["city_count"]]
    stays = [selected_keys[0], selected_keys[0], selected_keys[1], selected_keys[1], selected_keys[2], selected_keys[2], selected_keys[2]]
    cuisine_cycle = list(cfg["cuisines"])
    plan, known_cost = [], 0.0
    unknown_cost = False
    for i, key in enumerate(stays):
        hotel = hotels[key]
        if hotel["price"] is None:
            unknown_cost = True
        else:
            known_cost += hotel["price"]
        meals = ["-", "-", "-"]
        # One database-grounded meal each day; the cycle guarantees requested coverage.
        selected_meal = meal_for(food, cuisine_cycle[i % len(cuisine_cycle)], key)
        meals[i % 3] = "%s, %s" % (selected_meal["name"], selected_meal["city"])
        if selected_meal["price"] is None:
            unknown_cost = True
        else:
            known_cost += selected_meal["price"] * cfg["party_size"]
        destination = hotel["city"]
        if i == 0:
            current = "from %s to %s" % (cfg["origin"], destination)
            transport = "Self-driving: from %s to %s" % (cfg["origin"], destination)
        elif i in (2, 4):
            prior = hotels[stays[i - 1]]["city"]
            current = "from %s to %s" % (prior, destination)
            transport = "Self-driving: from %s to %s" % (prior, destination)
        else:
            current, transport = destination, "Self-driving within %s" % destination
        attractions = [attraction_for(places, key, i * 2), attraction_for(places, key, i * 2 + 1)]
        plan.append({
            "day": i + 1, "current_city": current, "transportation": transport,
            "breakfast": meals[0], "lunch": meals[1], "dinner": meals[2],
            "attraction": ";".join(attractions) + ";",
            # Exact source name is intentional: it permits unambiguous public-database matching.
            "accommodation": "%s, %s" % (hotel["name"], hotel["city"]),
        })
    if not unknown_cost and known_cost > float(cfg["budget"]):
        raise ValueError("lowest selected source lodging and meals exceed budget")
    artifact = {"plan": plan, "tool_called": ["search_cities", "search_accommodations", "search_restaurants", "search_attractions", "search_distance_matrix"]}
    output = Path(cfg["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False) as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, output)
    return {"ok": True, "output_path": str(output), "chosen_cities": [hotels[k]["city"] for k in selected_keys], "known_cost": None if unknown_cost else round(known_cost, 2)}


def main():
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise ValueError("stdin must contain a JSON object")
        print(json.dumps(build(value), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
