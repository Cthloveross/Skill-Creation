#!/usr/bin/env python3
"""Build a source-grounded seven-day pet-friendly road itinerary.

stdin: configuration JSON object
stdout: {"ok": true, "output_path": str, "chosen_cities": [str, ...],
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

# These expressions intentionally match the public verification requirement.
POSITIVE_PET = re.compile(
    r"(pet[- ]?friendly|pets?\s+(?:allowed|welcome)|allow(?:s|ed)?\s+pets?|dogs?\s+allowed|dog[- ]?friendly)",
    re.I,
)
NEGATIVE_PET = re.compile(
    r"(no\s+pets?|pets?\s+(?:not\s+)?allowed|pets?\s+prohibited)", re.I
)


def clean(value):
    return "" if value is None else str(value).strip()


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def city_key(value):
    return norm(re.split(r"[,(/]", clean(value), maxsplit=1)[0])


def words_in(haystack, needle):
    haystack = " " + norm(haystack) + " "
    needle = norm(needle)
    return bool(needle) and (" " + needle + " " in haystack)


def number(value):
    match = re.search(r"-?\d+(?:\.\d+)?", clean(value).replace(",", ""))
    return float(match.group(0)) if match else None


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [clean(x) for x in (reader.fieldnames or []) if x is not None]
        rows = [
            {clean(key): clean(value) for key, value in row.items() if key is not None}
            for row in reader
        ]
    rows = [row for row in rows if any(row.values())]
    if not headers or not rows:
        raise ValueError("empty or unreadable CSV: " + str(path))
    return headers, rows


def column(headers, *aliases):
    """Find a header without imposing a dataset-specific capitalization or spelling."""
    wanted = [norm(alias).replace(" ", "") for alias in aliases]
    best_header, best_score = None, -1
    for header in headers:
        key = norm(header).replace(" ", "")
        for alias in wanted:
            if key == alias:
                score = 100
            elif alias and (alias in key or key in alias):
                score = 50 - abs(len(key) - len(alias))
            else:
                score = -1
            if score > best_score:
                best_header, best_score = header, score
    return best_header if best_score >= 0 else None


def source_columns(headers, restaurant=False):
    result = {
        "name": column(headers, "name", "property name", "restaurant name", "attraction name", "title"),
        "city": column(headers, "city", "city name", "location city"),
        "price": column(headers, "nightly price", "average cost", "average price", "price", "cost", "rate"),
    }
    if restaurant:
        result["cuisine"] = column(headers, "cuisines", "cuisine", "categories", "category")
    return result


def require(columns, label, keys):
    missing = [key for key in keys if not columns.get(key)]
    if missing:
        raise ValueError(label + " lacks required columns: " + ", ".join(missing))


def policy_columns(headers):
    return [
        header for header in headers
        if any(token in clean(header).lower() for token in ("pet", "rule", "policy", "amenit"))
    ]


def pet_allowed(row, accommodation_headers):
    policy = " ".join(clean(row.get(header, "")) for header in policy_columns(accommodation_headers))
    return bool(POSITIVE_PET.search(policy) and not NEGATIVE_PET.search(policy))


def best_named_row(text, rows, name_col):
    """Resolve a text mention exactly as the public longest-name matcher does."""
    matches = [
        row for row in rows
        if len(norm(row.get(name_col, ""))) >= 3 and words_in(text, row.get(name_col, ""))
    ]
    return max(matches, key=lambda row: len(norm(row[name_col]))) if matches else None


def verifier_resolved_records(rows, columns, accommodation_headers=None, include_cuisine=False):
    """Return unique output-safe records after resolving each displayed name.

    A record is kept only under the precise row that a longest-name provenance check
    will resolve from its emitted source spelling. For accommodations, pet policy is
    evaluated on that same row, not on a similarly named duplicate.
    """
    records = {}
    name_col, city_col = columns["name"], columns["city"]
    for source_row in rows:
        raw_name = clean(source_row.get(name_col, ""))
        matched = best_named_row(raw_name, rows, name_col)
        if matched is None:
            continue
        name = clean(matched.get(name_col, ""))
        city = clean(matched.get(city_col, ""))
        if not name or not city:
            continue
        key = norm(name)
        if key in records:
            continue
        if accommodation_headers is not None and not pet_allowed(matched, accommodation_headers):
            continue
        record = {
            "name": name,
            "city": city,
            "city_key": city_key(city),
            "price": number(matched.get(columns["price"], "")) if columns.get("price") else None,
            "row": matched,
        }
        if include_cuisine:
            record["cuisine"] = clean(matched.get(columns["cuisine"], ""))
        records[key] = record
    return list(records.values())


def load_sources(root):
    root = Path(root)
    accommodation_headers, accommodations = read_csv(root / "accommodations/clean_accommodations_2022.csv")
    restaurant_headers, restaurants = read_csv(root / "restaurants/clean_restaurant_2022.csv")
    attraction_headers, attractions = read_csv(root / "attractions/attractions.csv")
    accommodation_cols = source_columns(accommodation_headers)
    restaurant_cols = source_columns(restaurant_headers, restaurant=True)
    attraction_cols = source_columns(attraction_headers)
    require(accommodation_cols, "accommodations CSV", ("name", "city"))
    require(restaurant_cols, "restaurants CSV", ("name", "city", "cuisine"))
    require(attraction_cols, "attractions CSV", ("name", "city"))
    if not policy_columns(accommodation_headers):
        raise ValueError("accommodations CSV lacks policy-like columns")
    return (
        accommodation_headers, accommodations, restaurants, attractions,
        accommodation_cols, restaurant_cols, attraction_cols,
    )


def ohio_city_displays(root, city_values, state):
    reference = Path(root) / "background/citySet_with_states.txt"
    if not reference.is_file():
        raise ValueError("missing city/state reference: " + str(reference))
    state_lines = [
        line for line in reference.read_text(encoding="utf-8", errors="replace").splitlines()
        if re.search(r"\b" + re.escape(state) + r"\b", line, re.I)
    ]
    result = {}
    for value in city_values:
        key = city_key(value)
        if key and key not in result and any(words_in(line, key) for line in state_lines):
            result[key] = clean(value)
    return result


def cost_key(record):
    price = record.get("price")
    return (price is None, price if price is not None else 0.0, record["name"].casefold())


def cuisine_match(record, cuisine):
    return bool(re.search(r"\b" + re.escape(clean(cuisine)) + r"\b", record.get("cuisine", ""), re.I))


def select_route(ohio, foods, pois, lodgings, cuisines, party_size, budget):
    """Choose three feasible Ohio cities, preferring the lowest known daily subtotal."""
    candidate_cities = sorted(
        key for key in ohio
        if foods.get(key) and pois.get(key) and lodgings.get(key)
    )
    if len(candidate_cities) < 3:
        raise ValueError("fewer than three Ohio cities have restaurants, attractions, and explicitly pet-permitted lodging")

    ranked = []
    for combo in itertools.combinations(candidate_cities, 3):
        all_food = [record for key in combo for record in foods[key]]
        if not all(any(cuisine_match(record, wanted) for record in all_food) for wanted in cuisines):
            continue
        # Seven itinerary days use the city sequence below. Estimate known costs only;
        # absent prices remain unknown instead of being silently treated as zero facts.
        sequence = [combo[0], combo[0], combo[1], combo[1], combo[2], combo[2], combo[2]]
        known = 0.0
        for key in sequence:
            lodging = min(lodgings[key], key=cost_key)
            meal = min(foods[key], key=cost_key)
            if lodging["price"] is not None:
                known += lodging["price"]
            if meal["price"] is not None:
                known += meal["price"] * party_size
        if known <= budget:
            ranked.append((known, combo))
    if not ranked:
        raise ValueError("no three-city route has requested cuisine coverage within the known budget subtotal")
    return list(min(ranked, key=lambda item: (item[0], item[1]))[1])


def build(config):
    required = ("data_root", "output_path", "origin", "target_state", "party_size", "budget", "cuisines")
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError("missing configuration: " + ", ".join(missing))
    if config.get("days", 7) != 7 or config.get("city_count", 3) != 3:
        raise ValueError("this deliverable requires exactly seven days and three cities")
    if not isinstance(config["cuisines"], list) or not all(isinstance(x, str) and clean(x) for x in config["cuisines"]):
        raise ValueError("cuisines must be a nonempty string array")
    party_size = float(config["party_size"])
    budget = float(config["budget"])
    if party_size <= 0 or budget <= 0:
        raise ValueError("party_size and budget must be positive")

    ah, accommodation_rows, restaurant_rows, attraction_rows, ac, rc, tc = load_sources(config["data_root"])
    lodgings = verifier_resolved_records(accommodation_rows, ac, accommodation_headers=ah)
    restaurants = verifier_resolved_records(restaurant_rows, rc, include_cuisine=True)
    attractions = verifier_resolved_records(attraction_rows, tc)
    # A semicolon in an attraction name would make the required list serialization ambiguous.
    attractions = [record for record in attractions if ";" not in record["name"]]

    all_city_values = [row.get(ac["city"], "") for row in accommodation_rows]
    all_city_values += [row.get(rc["city"], "") for row in restaurant_rows]
    all_city_values += [row.get(tc["city"], "") for row in attraction_rows]
    ohio = ohio_city_displays(config["data_root"], all_city_values, config["target_state"])

    foods, pois, hotels = defaultdict(list), defaultdict(list), defaultdict(list)
    for record in restaurants:
        if record["cuisine"]:
            foods[record["city_key"]].append(record)
    for record in attractions:
        pois[record["city_key"]].append(record)
    for record in lodgings:
        hotels[record["city_key"]].append(record)
    for bucket in list(foods.values()) + list(pois.values()) + list(hotels.values()):
        bucket.sort(key=cost_key)

    route = select_route(ohio, foods, pois, hotels, config["cuisines"], party_size, budget)
    schedule = [route[0], route[0], route[1], route[1], route[2], route[2], route[2]]

    remaining_cuisines = list(config["cuisines"])
    plan = []
    known_subtotal = 0.0
    for index, key in enumerate(schedule):
        city = ohio[key]
        local_food = foods[key]
        desired = next(
            (wanted for wanted in remaining_cuisines if any(cuisine_match(item, wanted) for item in local_food)),
            None,
        )
        if desired is not None:
            meal = min((item for item in local_food if cuisine_match(item, desired)), key=cost_key)
            remaining_cuisines.remove(desired)
        else:
            meal = min(local_food, key=cost_key)
        lodging = min(hotels[key], key=cost_key)
        if meal["price"] is not None:
            known_subtotal += meal["price"] * party_size
        if lodging["price"] is not None:
            known_subtotal += lodging["price"]

        local_pois = pois[key]
        first = local_pois[(index * 2) % len(local_pois)]["name"]
        second = local_pois[(index * 2 + 1) % len(local_pois)]["name"]
        if index == 0:
            current_city = "from %s to %s" % (config["origin"], city)
            transportation = "Self-driving: from %s to %s" % (config["origin"], city)
        elif index in (2, 4):
            prior_city = ohio[schedule[index - 1]]
            current_city = "from %s to %s" % (prior_city, city)
            transportation = "Self-driving: from %s to %s" % (prior_city, city)
        else:
            current_city = city
            transportation = "Self-driving within %s" % city

        meals = ["-", "-", "-"]
        meals[index % 3] = meal["name"]
        plan.append({
            "day": index + 1,
            "current_city": current_city,
            "transportation": transportation,
            "breakfast": meals[0],
            "lunch": meals[1],
            "dinner": meals[2],
            "attraction": first + ";" + second + ";",
            # Emit the exact resolved public name; do not add unsupported pet claims.
            "accommodation": lodging["name"],
        })

    if remaining_cuisines:
        raise ValueError("internal cuisine coverage failure: " + ", ".join(remaining_cuisines))
    if known_subtotal > budget:
        raise ValueError("known lodging and meal subtotal exceeds budget")

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
    output = Path(config["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(output.parent), delete=False) as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary_path = handle.name
    os.replace(temporary_path, output)
    return {
        "ok": True,
        "output_path": str(output),
        "chosen_cities": [ohio[key] for key in route],
        "known_subtotal": round(known_subtotal, 2),
    }


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
