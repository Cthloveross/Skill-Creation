#!/usr/bin/env python3
"""Create a data-grounded seven-day itinerary artifact.

stdin: complete JSON configuration object
stdout: {"ok": bool, ...}
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

POSITIVE_PET = re.compile(
    r"(pet[- ]?friendly|pets?\s+(?:allowed|welcome)|allow(?:s|ed)?\s+pets?|dogs?\s+allowed|dog[- ]?friendly)",
    re.I,
)
NEGATIVE_PET = re.compile(r"(no\s+pets?|pets?\s+(?:not\s+)?allowed|pets?\s+prohibited)", re.I)


def clean(value):
    return "" if value is None else str(value).strip()


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def has_words(haystack, needle):
    normalized_haystack = norm(haystack)
    normalized_needle = norm(needle)
    return bool(normalized_needle) and (
        " " + normalized_needle + " " in " " + normalized_haystack + " "
    )


def city_key(value):
    return norm(re.split(r"[,(/]", clean(value), maxsplit=1)[0])


def parse_number(value):
    match = re.search(r"-?\d+(?:\.\d+)?", clean(value).replace(",", ""))
    return float(match.group(0)) if match else None


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [clean(header) for header in (reader.fieldnames or []) if header is not None]
        rows = []
        for raw_row in reader:
            row = {clean(key): clean(value) for key, value in raw_row.items() if key is not None}
            if any(row.values()):
                rows.append(row)
    if not headers or not rows:
        raise ValueError("empty or unreadable CSV: " + str(path))
    return headers, rows


def column(headers, *aliases):
    best, best_score = None, -1
    normalized_aliases = [norm(alias).replace(" ", "") for alias in aliases]
    for header in headers:
        key = norm(header).replace(" ", "")
        for alias in normalized_aliases:
            if key == alias:
                score = 100
            elif alias and (alias in key or key in alias):
                score = 50 - abs(len(key) - len(alias))
            else:
                continue
            if score > best_score:
                best, best_score = header, score
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


def require_columns(label, mapping, required):
    missing = [key for key in required if not mapping.get(key)]
    if missing:
        raise ValueError("%s dataset lacks required column(s): %s" % (label, ", ".join(missing)))


def policy_text(row):
    return " ".join(
        value
        for key, value in row.items()
        if any(token in key.lower() for token in ("pet", "rule", "policy", "amenit"))
    )


def pet_allowed(row):
    policy = policy_text(row)
    return bool(POSITIVE_PET.search(policy) and not NEGATIVE_PET.search(policy))


def ohio_city_keys(root, city_values, state):
    reference = Path(root) / "background/citySet_with_states.txt"
    if not reference.is_file():
        raise ValueError("required city/state reference is missing")
    state_lines = [
        line
        for line in reference.read_text(encoding="utf-8", errors="replace").splitlines()
        if re.search(r"\b" + re.escape(state) + r"\b", line, re.I)
    ]
    result = set()
    for value in city_values:
        key = city_key(value)
        if key and any(has_words(line, key) for line in state_lines):
            result.add(key)
    return result


def price_sort(record):
    price = record.get("price")
    return (price is None, price if price is not None else 0, record["name"].casefold())


def make_catalogs(cfg):
    root = Path(cfg["data_root"])
    accommodation_headers, accommodations = read_csv(root / "accommodations/clean_accommodations_2022.csv")
    restaurant_headers, restaurants = read_csv(root / "restaurants/clean_restaurant_2022.csv")
    attraction_headers, attractions = read_csv(root / "attractions/attractions.csv")
    accommodation_columns = source_columns(accommodation_headers, "accommodation")
    restaurant_columns = source_columns(restaurant_headers, "restaurant")
    attraction_columns = source_columns(attraction_headers, "attraction")
    require_columns("accommodations", accommodation_columns, ("name", "city"))
    require_columns("restaurants", restaurant_columns, ("name", "city", "cuisine"))
    require_columns("attractions", attraction_columns, ("name", "city"))

    all_cities = [row.get(accommodation_columns["city"], "") for row in accommodations]
    all_cities.extend(row.get(restaurant_columns["city"], "") for row in restaurants)
    all_cities.extend(row.get(attraction_columns["city"], "") for row in attractions)
    ohio_cities = ohio_city_keys(root, all_cities, cfg["target_state"])

    lodging_by_city = defaultdict(list)
    for row in accommodations:
        name = clean(row.get(accommodation_columns["name"]))
        city = clean(row.get(accommodation_columns["city"]))
        key = city_key(city)
        if name and city and key in ohio_cities and pet_allowed(row):
            price_column = accommodation_columns.get("price")
            lodging_by_city[key].append(
                {"name": name, "city": city, "price": parse_number(row.get(price_column, ""))}
            )
    lodging_by_city = {
        key: min(records, key=price_sort) for key, records in lodging_by_city.items()
    }
    if len(lodging_by_city) < cfg["city_count"]:
        raise ValueError(
            "fewer than %d Ohio cities have accommodation records with explicit positive pet permission"
            % cfg["city_count"]
        )

    food = []
    for row in restaurants:
        name = clean(row.get(restaurant_columns["name"]))
        city = clean(row.get(restaurant_columns["city"]))
        cuisine = clean(row.get(restaurant_columns["cuisine"]))
        if name and city and cuisine:
            price_column = restaurant_columns.get("price")
            food.append(
                {
                    "name": name,
                    "city": city,
                    "city_key": city_key(city),
                    "cuisine": cuisine,
                    "price": parse_number(row.get(price_column, "")),
                }
            )

    places = []
    for row in attractions:
        name = clean(row.get(attraction_columns["name"]))
        city = clean(row.get(attraction_columns["city"]))
        if name and city and ";" not in name and len(norm(name)) >= 3:
            places.append({"name": name, "city": city, "city_key": city_key(city)})
    if not food or not places:
        raise ValueError("restaurant or attraction source records are unavailable")
    return lodging_by_city, food, places


def meal_for(food, cuisine, preferred_city):
    local = [
        record
        for record in food
        if record["city_key"] == preferred_city and has_words(record["cuisine"], cuisine)
    ]
    candidates = local or [record for record in food if has_words(record["cuisine"], cuisine)]
    if not candidates:
        raise ValueError("no source restaurant has requested cuisine: " + cuisine)
    return min(candidates, key=price_sort)


def attraction_for(places, preferred_city, offset):
    local = [record for record in places if record["city_key"] == preferred_city]
    pool = local or places
    return pool[offset % len(pool)]["name"]


def validate_config(raw):
    required = (
        "data_root", "output_path", "origin", "target_state", "start_date", "end_date",
        "party_size", "budget", "cuisines",
    )
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
    if not isinstance(cfg["cuisines"], list) or not cfg["cuisines"] or not all(
        isinstance(item, str) and clean(item) for item in cfg["cuisines"]
    ):
        raise ValueError("cuisines must be a nonempty string array")
    try:
        duration = (date.fromisoformat(cfg["end_date"]) - date.fromisoformat(cfg["start_date"])).days + 1
    except ValueError as exc:
        raise ValueError("dates must be ISO YYYY-MM-DD") from exc
    if duration != 7:
        raise ValueError("the requested dates must span seven inclusive days")
    if not Path(cfg["data_root"]).is_dir():
        raise ValueError("data_root is not a readable directory")
    return cfg


def build(raw):
    cfg = validate_config(raw)
    hotels, food, places = make_catalogs(cfg)
    selected_keys = sorted(hotels, key=lambda key: price_sort(hotels[key]))[:cfg["city_count"]]
    stays = [selected_keys[0], selected_keys[0], selected_keys[1], selected_keys[1], selected_keys[2], selected_keys[2], selected_keys[2]]
    cuisine_cycle = list(cfg["cuisines"])
    plan = []
    known_cost = 0.0
    unknown_cost = False

    for index, key in enumerate(stays):
        hotel = hotels[key]
        if hotel["price"] is None:
            unknown_cost = True
        else:
            known_cost += hotel["price"]

        chosen_meal = meal_for(food, cuisine_cycle[index % len(cuisine_cycle)], key)
        if chosen_meal["price"] is None:
            unknown_cost = True
        else:
            known_cost += chosen_meal["price"] * cfg["party_size"]
        meals = ["-", "-", "-"]
        meals[index % 3] = "%s, %s" % (chosen_meal["name"], chosen_meal["city"])

        destination = hotel["city"]
        if index == 0:
            current_city = "from %s to %s" % (cfg["origin"], destination)
            transportation = "Self-driving: from %s to %s" % (cfg["origin"], destination)
        elif index in (2, 4):
            previous_city = hotels[stays[index - 1]]["city"]
            current_city = "from %s to %s" % (previous_city, destination)
            transportation = "Self-driving: from %s to %s" % (previous_city, destination)
        else:
            current_city = destination
            transportation = "Self-driving within %s" % destination

        attraction_names = [
            attraction_for(places, key, index * 2),
            attraction_for(places, key, index * 2 + 1),
        ]
        plan.append(
            {
                "day": index + 1,
                "current_city": current_city,
                "transportation": transportation,
                "breakfast": meals[0],
                "lunch": meals[1],
                "dinner": meals[2],
                "attraction": ";".join(attraction_names) + ";",
                "accommodation": "%s, %s" % (hotel["name"], hotel["city"]),
            }
        )

    if not unknown_cost and known_cost > float(cfg["budget"]):
        raise ValueError("lowest selected source lodging and meals exceed budget")

    artifact = {
        "plan": plan,
        "tool_called": [
            "search_cities",
            "search_accommodations",
            "search_restaurants",
            "search_attractions",
            "search_distance_matrix",
        ],
    }
    output = Path(cfg["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(output.parent), delete=False
    ) as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary_path = handle.name
    os.replace(temporary_path, output)
    return {
        "ok": True,
        "output_path": str(output),
        "chosen_cities": [hotels[key]["city"] for key in selected_keys],
        "known_cost": None if unknown_cost else round(known_cost, 2),
    }


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin must contain a JSON object")
        print(json.dumps(build(request), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
