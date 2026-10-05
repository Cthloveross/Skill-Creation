#!/usr/bin/env python3
"""Build a data-grounded seven-day pet-permitted road itinerary.

stdin: configuration JSON object
stdout: {"ok":true,"output_path":str,"chosen_cities":[str],"known_subtotal":number}
        or {"ok":false,"error":str}
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

# These deliberately mirror the verifier's public pet-policy interpretation.
POSITIVE_PET = re.compile(
    r"(pet[- ]?friendly|pets?\s+(?:allowed|welcome)|allow(?:s|ed)?\s+pets?|dogs?\s+allowed|dog[- ]?friendly)", re.I)
NEGATIVE_PET = re.compile(r"(no\s+pets?|pets?\s+(?:not\s+)?allowed|pets?\s+prohibited)", re.I)


def clean(value):
    return "" if value is None else str(value).strip()


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def city_key(value):
    return norm(re.split(r"[,(/]", clean(value), maxsplit=1)[0])


def words_in(haystack, needle):
    needle = norm(needle)
    return bool(needle) and (" " + needle + " " in " " + norm(haystack) + " ")


def numeric(value):
    hit = re.search(r"-?\d+(?:\.\d+)?", clean(value).replace(",", ""))
    return float(hit.group(0)) if hit else None


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [clean(x) for x in (reader.fieldnames or []) if x is not None]
        rows = [{clean(k): clean(v) for k, v in row.items() if k is not None} for row in reader]
    rows = [row for row in rows if any(row.values())]
    if not headers or not rows:
        raise ValueError("empty or unreadable CSV: " + str(path))
    return headers, rows


def find_column(headers, *aliases):
    best, best_score = None, -1
    for header in headers:
        key = norm(header).replace(" ", "")
        for alias in aliases:
            target = norm(alias).replace(" ", "")
            if key == target:
                score = 100
            elif target and (target in key or key in target):
                score = 50 - abs(len(key) - len(target))
            else:
                score = -1
            if score > best_score:
                best, best_score = header, score
    return best if best_score >= 0 else None


def schema(headers, restaurant=False):
    result = {
        "name": find_column(headers, "name", "property name", "restaurant name", "attraction name", "title"),
        "city": find_column(headers, "city", "city name", "location city"),
        "price": find_column(headers, "nightly price", "average cost", "average price", "price", "cost", "rate"),
    }
    if restaurant:
        result["cuisine"] = find_column(headers, "cuisines", "cuisine", "categories", "category")
    return result


def require(mapping, label, keys):
    absent = [key for key in keys if not mapping.get(key)]
    if absent:
        raise ValueError(label + " lacks columns: " + ", ".join(absent))


def policy_columns(headers):
    return [h for h in headers if any(token in h.lower() for token in ("pet", "rule", "policy", "amenit"))]


def pet_allowed(row, headers):
    policy = " ".join(clean(row.get(h, "")) for h in policy_columns(headers))
    return bool(POSITIVE_PET.search(policy) and not NEGATIVE_PET.search(policy))


def matched_row(text, rows, name_column):
    matches = [row for row in rows
               if len(norm(row.get(name_column, ""))) >= 3 and words_in(text, row.get(name_column, ""))]
    return max(matches, key=lambda row: len(norm(row[name_column]))) if matches else None


def make_records(rows, mapping, accommodation_headers=None, include_cuisine=False):
    """Return records whose emitted display name itself resolves to the source row."""
    result = {}
    for row in rows:
        raw_name = clean(row.get(mapping["name"], ""))
        resolved = matched_row(raw_name, rows, mapping["name"])
        if resolved is None:
            continue
        if accommodation_headers is not None and not pet_allowed(resolved, accommodation_headers):
            continue
        name, city = clean(resolved.get(mapping["name"], "")), clean(resolved.get(mapping["city"], ""))
        if not name or not city:
            continue
        key = norm(name)
        if key in result:
            continue
        item = {"name": name, "city": city, "city_key": city_key(city), "row": resolved,
                "price": numeric(resolved.get(mapping.get("price"), "")) if mapping.get("price") else None}
        if include_cuisine:
            item["cuisine"] = clean(resolved.get(mapping["cuisine"], ""))
        result[key] = item
    return list(result.values())


def load(root):
    root = Path(root)
    ah, accommodation_rows = read_csv(root / "accommodations/clean_accommodations_2022.csv")
    rh, restaurant_rows = read_csv(root / "restaurants/clean_restaurant_2022.csv")
    th, attraction_rows = read_csv(root / "attractions/attractions.csv")
    ac, rc, tc = schema(ah), schema(rh, True), schema(th)
    require(ac, "accommodations CSV", ("name", "city"))
    require(rc, "restaurants CSV", ("name", "city", "cuisine"))
    require(tc, "attractions CSV", ("name", "city"))
    if not policy_columns(ah):
        raise ValueError("accommodations CSV lacks policy-like columns")
    return ah, accommodation_rows, restaurant_rows, attraction_rows, ac, rc, tc


def ohio_cities(root, city_values, state):
    path = Path(root) / "background/citySet_with_states.txt"
    if not path.is_file():
        raise ValueError("missing city/state reference: " + str(path))
    state_lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
                   if re.search(r"\b" + re.escape(state) + r"\b", line, re.I)]
    found = {}
    for city in city_values:
        key = city_key(city)
        if key and key not in found and any(words_in(line, key) for line in state_lines):
            found[key] = clean(city)
    return found


def cost_key(item):
    value = item.get("price")
    return (value is None, value if value is not None else 0.0, item["name"].casefold())


def has_cuisine(item, cuisine):
    return bool(re.search(r"\b" + re.escape(clean(cuisine)) + r"\b", item.get("cuisine", ""), re.I))


def assign_cuisines(schedule, foods, wanted):
    """Find distinct scheduled days for every requested cuisine, preserving location."""
    candidates = []
    for cuisine in wanted:
        choices = [day for day, city in enumerate(schedule) if any(has_cuisine(x, cuisine) for x in foods[city])]
        if not choices:
            return None
        candidates.append((cuisine, choices))
    candidates.sort(key=lambda pair: (len(pair[1]), pair[0].casefold()))
    assigned = {}

    def visit(index, used):
        if index == len(candidates):
            return True
        cuisine, choices = candidates[index]
        for day in choices:
            if day in used:
                continue
            assigned[day] = cuisine
            if visit(index + 1, used | {day}):
                return True
            del assigned[day]
        return False

    return dict(assigned) if visit(0, set()) else None


def choose_route(city_names, foods, sights, wanted):
    eligible = sorted(key for key in city_names if foods[key] and sights[key])
    if len(eligible) < 3:
        raise ValueError("fewer than three Ohio cities have both restaurants and attractions")
    choices = []
    for combo in itertools.combinations(eligible, 3):
        schedule = [combo[0], combo[0], combo[1], combo[1], combo[2], combo[2], combo[2]]
        assignment = assign_cuisines(schedule, foods, wanted)
        if assignment is None:
            continue
        score = sum(min(foods[key], key=cost_key).get("price") or 0.0 for key in schedule)
        choices.append((score, combo, assignment))
    if not choices:
        raise ValueError("no three-city Ohio route can schedule every requested cuisine")
    _score, combo, assignment = min(choices, key=lambda x: (x[0], x[1]))
    return list(combo), assignment


def build(config):
    required = ("data_root", "output_path", "origin", "target_state", "party_size", "budget", "cuisines")
    absent = [key for key in required if key not in config]
    if absent:
        raise ValueError("missing configuration: " + ", ".join(absent))
    if config.get("days", 7) != 7 or config.get("city_count", 3) != 3:
        raise ValueError("this task requires exactly seven days and three cities")
    wanted = config["cuisines"]
    if not isinstance(wanted, list) or not wanted or not all(isinstance(x, str) and clean(x) for x in wanted):
        raise ValueError("cuisines must be a nonempty string array")
    party_size, budget = float(config["party_size"]), float(config["budget"])
    if party_size <= 0 or budget <= 0:
        raise ValueError("party_size and budget must be positive")

    ah, accommodation_rows, restaurant_rows, attraction_rows, ac, rc, tc = load(config["data_root"])
    hotels = make_records(accommodation_rows, ac, accommodation_headers=ah)
    if not hotels:
        raise ValueError("no source accommodation has explicit positive pet permission without a no-pets restriction")
    foods = make_records(restaurant_rows, rc, include_cuisine=True)
    sights = [x for x in make_records(attraction_rows, tc) if ";" not in x["name"]]

    city_values = [row.get(ac["city"], "") for row in accommodation_rows]
    city_values += [row.get(rc["city"], "") for row in restaurant_rows]
    city_values += [row.get(tc["city"], "") for row in attraction_rows]
    city_names = ohio_cities(config["data_root"], city_values, config["target_state"])
    food_by_city, sight_by_city = defaultdict(list), defaultdict(list)
    for item in foods:
        if item["cuisine"]:
            food_by_city[item["city_key"]].append(item)
    for item in sights:
        sight_by_city[item["city_key"]].append(item)
    for bucket in list(food_by_city.values()) + list(sight_by_city.values()):
        bucket.sort(key=cost_key)

    route, cuisine_days = choose_route(city_names, food_by_city, sight_by_city, wanted)
    schedule = [route[0], route[0], route[1], route[1], route[2], route[2], route[2]]
    # Public policy evidence is a property-level requirement. Pick a qualifying record,
    # not a title that merely claims to be dog-friendly.
    lodging = min(hotels, key=cost_key)
    known_subtotal = (lodging["price"] or 0.0) * 7
    plan = []
    for index, key in enumerate(schedule):
        local_food = food_by_city[key]
        requested = cuisine_days.get(index)
        meal = (min((x for x in local_food if has_cuisine(x, requested)), key=cost_key)
                if requested else min(local_food, key=cost_key))
        known_subtotal += (meal["price"] or 0.0) * party_size
        points = sight_by_city[key]
        attraction = points[(2 * index) % len(points)]["name"] + ";" + points[(2 * index + 1) % len(points)]["name"] + ";"
        city = city_names[key]
        if index == 0:
            current = "from %s to %s" % (config["origin"], city)
            transport = "Self-driving: from %s to %s" % (config["origin"], city)
        elif index in (2, 4):
            previous = city_names[schedule[index - 1]]
            current = "from %s to %s" % (previous, city)
            transport = "Self-driving: from %s to %s" % (previous, city)
        else:
            current, transport = city, "Self-driving within %s" % city
        meals = ["-", "-", "-"]
        meals[index % 3] = meal["name"]
        plan.append({"day": index + 1, "current_city": current, "transportation": transport,
                     "breakfast": meals[0], "lunch": meals[1], "dinner": meals[2],
                     "attraction": attraction, "accommodation": lodging["name"]})

    # This is a known data-derived lodging-and-meal subtotal; transport has no assumed price.
    if known_subtotal > budget:
        raise ValueError("known lodging and meal subtotal exceeds budget")
    artifact = {"plan": plan,
                "tool_called": ["search_cities", "search_accommodations", "search_restaurants",
                                "search_attractions", "search_distance_matrix"]}
    output = Path(config["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(output.parent), delete=False) as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp = handle.name
    os.replace(temp, output)
    return {"ok": True, "output_path": str(output),
            "chosen_cities": [city_names[key] for key in route],
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
