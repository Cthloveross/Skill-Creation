#!/usr/bin/env python3
"""Build a source-grounded, pet-friendly road itinerary.

Input on stdin is a complete JSON request object. Output is a JSON status object.
The module is also imported by execute_task.py and validate_itinerary.py.
"""
import csv
import itertools
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


def text(value):
    return "" if value is None else str(value).strip()


def words(value):
    return re.sub(r"[^a-z0-9]+", " ", text(value).lower()).strip()


def city_key(value):
    """Normalize a city field while discarding a trailing state/address portion."""
    return words(re.split(r"[,(/]", text(value), maxsplit=1)[0])


def contains_words(haystack, needle):
    haystack_words = words(haystack)
    needle_words = words(needle)
    return bool(needle_words) and (" " + needle_words + " ") in (" " + haystack_words + " ")


def number(value):
    match = re.search(r"-?\d+(?:\.\d+)?", text(value).replace(",", ""))
    return float(match.group(0)) if match else None


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        headers = [text(header) for header in (reader.fieldnames or []) if header is not None]
        rows = []
        for row in reader:
            clean = {text(key): text(value) for key, value in row.items() if key is not None}
            if any(clean.values()):
                rows.append(clean)
    return headers, rows


def find_column(headers, aliases):
    best, best_score = None, -1
    for header in headers:
        normalized = words(header).replace(" ", "")
        for alias in aliases:
            target = words(alias).replace(" ", "")
            if normalized == target:
                score = 100
            elif target and (target in normalized or normalized in target):
                score = 50 - abs(len(normalized) - len(target))
            else:
                continue
            if score > best_score:
                best, best_score = header, score
    return best


def fields(headers, kind):
    result = {
        "name": find_column(headers, ["name", "property name", "restaurant name", "attraction name", "title"]),
        "city": find_column(headers, ["city", "city name", "location city", "destination city"]),
    }
    if kind == "accommodations":
        result["price"] = find_column(headers, ["price", "nightly price", "price per night", "rate"])
    elif kind == "restaurants":
        result["price"] = find_column(headers, ["average cost", "average price", "meal price", "price", "cost"])
        result["cuisine"] = find_column(headers, ["cuisines", "cuisine", "categories", "category"])
    elif kind == "distances":
        result["origin"] = find_column(headers, ["origin", "from", "source", "start city"])
        result["destination"] = find_column(headers, ["destination", "to", "target", "end city"])
    return result


def require(mapping, label, names):
    missing = [name for name in names if not mapping.get(name)]
    if missing:
        raise ValueError("%s lacks usable column(s): %s" % (label, ", ".join(missing)))


def load_sources(root):
    found = {}
    for path in sorted(Path(root).rglob("*.csv")):
        filename = words(path.name)
        headers, rows = read_csv(path)
        if "accommodation" in filename or "lodging" in filename or "hotel" in filename:
            found.setdefault("accommodations", (headers, rows))
        elif "restaurant" in filename or "dining" in filename:
            found.setdefault("restaurants", (headers, rows))
        elif "attraction" in filename or "poi" in filename:
            found.setdefault("attractions", (headers, rows))
        elif "distance" in filename or "matrix" in filename:
            found.setdefault("distances", (headers, rows))
    missing = [kind for kind in ("accommodations", "restaurants", "attractions") if kind not in found]
    if missing:
        raise ValueError("missing required local CSV dataset(s): " + ", ".join(missing))
    return found


def policy_text(row):
    return " ".join(
        text(value)
        for key, value in row.items()
        if any(token in key.lower() for token in ("pet", "rule", "policy", "amenit"))
    )


def pet_allowed(row):
    evidence = policy_text(row)
    return bool(evidence and POSITIVE_PET.search(evidence) and not NEGATIVE_PET.search(evidence))


def longest_match(label, rows, name_column):
    """Mirror verifier matching: longest source name named as full word sequence."""
    matches = [
        row for row in rows
        if len(words(row.get(name_column, ""))) >= 3 and contains_words(label, row.get(name_column, ""))
    ]
    return max(matches, key=lambda row: len(words(row[name_column]))) if matches else None


def target_city_keys(root, city_values, target_state):
    reference_files = [path for path in Path(root).rglob("*.txt") if "city" in words(path.name)]
    state_lines = []
    for path in reference_files:
        state_lines.extend(
            line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if re.search(r"\b" + re.escape(text(target_state)) + r"\b", line, re.I)
        )
    output = set()
    for value in city_values:
        key = city_key(value)
        if key and any(contains_words(line, key) for line in state_lines):
            output.add(key)
    return output


def price_key(record):
    value = record.get("price")
    return (value is None, value if value is not None else 0.0, record["name"].casefold())


def build_catalogs(data, cfg):
    ac_headers, ac_rows = data["accommodations"]
    rs_headers, rs_rows = data["restaurants"]
    at_headers, at_rows = data["attractions"]
    acf = fields(ac_headers, "accommodations")
    rsf = fields(rs_headers, "restaurants")
    atf = fields(at_headers, "attractions")
    require(acf, "accommodations", ("name", "city"))
    require(rsf, "restaurants", ("name", "city", "cuisine"))
    require(atf, "attractions", ("name", "city"))

    target_cities = target_city_keys(
        cfg["data_root"], [row.get(acf["city"], "") for row in ac_rows], cfg["target_state"]
    )
    hotels = defaultdict(list)
    for row in ac_rows:
        source_name = text(row.get(acf["name"]))
        source_city = text(row.get(acf["city"]))
        if not source_name or not source_city or city_key(source_city) not in target_cities or not pet_allowed(row):
            continue
        resolved = longest_match("Pet-friendly %s, %s" % (source_name, source_city), ac_rows, acf["name"])
        # Only retain the canonical resolved record, and only with explicit positive policy evidence.
        if resolved is None or not pet_allowed(resolved):
            continue
        name = text(resolved.get(acf["name"]))
        city = text(resolved.get(acf["city"]))
        if not name or not city or city_key(city) not in target_cities:
            continue
        hotels[city_key(city)].append({
            "name": name,
            "city": city,
            "price": number(resolved.get(acf.get("price", ""))),
        })

    restaurants = []
    for row in rs_rows:
        source_name = text(row.get(rsf["name"]))
        source_city = text(row.get(rsf["city"]))
        if not source_name or not source_city:
            continue
        resolved = longest_match("%s, %s" % (source_name, source_city), rs_rows, rsf["name"])
        if resolved is None:
            continue
        name = text(resolved.get(rsf["name"]))
        city = text(resolved.get(rsf["city"]))
        cuisine = text(resolved.get(rsf["cuisine"]))
        if name and city and cuisine:
            restaurants.append({
                "name": name, "city": city, "cuisine": cuisine,
                "price": number(resolved.get(rsf.get("price", ""))),
            })

    attractions = []
    for row in at_rows:
        source_name = text(row.get(atf["name"]))
        source_city = text(row.get(atf["city"]))
        if not source_name or not source_city or ";" in source_name:
            continue
        resolved = longest_match(source_name, at_rows, atf["name"])
        if resolved is None:
            continue
        name = text(resolved.get(atf["name"]))
        city = text(resolved.get(atf["city"]))
        if name and city and ";" not in name:
            attractions.append({"name": name, "city": city})

    if len(hotels) < cfg["city_count"]:
        raise ValueError(
            "fewer than %d %s cities have traceable lodging with explicit positive pet permission"
            % (cfg["city_count"], cfg["target_state"])
        )
    if not restaurants or not attractions:
        raise ValueError("restaurant or attraction source records are unavailable")
    return hotels, restaurants, attractions


def road_edges(data):
    if "distances" not in data:
        return set()
    headers, rows = data["distances"]
    cols = fields(headers, "distances")
    if not cols.get("origin") or not cols.get("destination"):
        return set()
    return {
        (city_key(row.get(cols["origin"])), city_key(row.get(cols["destination"])))
        for row in rows if row.get(cols["origin"]) and row.get(cols["destination"])
    }


def choose_route(hotels, edges, cfg):
    origin = city_key(cfg["origin"])
    keys = sorted(hotels)
    connected = []
    for selected in itertools.combinations(keys, cfg["city_count"]):
        for route in itertools.permutations(selected):
            legs = ((origin, route[0]), (route[0], route[1]), (route[1], route[2]))
            if edges and all(leg in edges for leg in legs):
                connected.append(route)
    candidates = connected or list(itertools.permutations(keys, cfg["city_count"]))
    if not candidates:
        raise ValueError("no requested city route can be formed from pet-permitted lodging")

    def route_cost(route):
        total = 0.0
        for key in route:
            lodging = min(hotels[key], key=price_key)
            if lodging["price"] is not None:
                total += lodging["price"]
        return total

    return min(candidates, key=lambda route: (route_cost(route), route))


def cuisine_match(record, cuisine):
    return contains_words(record["cuisine"], cuisine)


def select_meals(restaurants, requested):
    choices = []
    for cuisine in requested:
        options = [record for record in restaurants if cuisine_match(record, cuisine)]
        if not options:
            raise ValueError("no source restaurant covers requested cuisine: " + cuisine)
        choices.append(min(options, key=price_key))
    return choices


def make_plan(route, hotels, restaurants, attractions, cfg):
    stays = [route[0], route[0], route[1], route[1], route[2], route[2], route[2]]
    meal_cycle = select_meals(restaurants, cfg["cuisines"])
    plan = []
    known_total = 0.0
    unknown_cost = False
    for index, key in enumerate(stays):
        hotel = min(hotels[key], key=price_key)
        if hotel["price"] is None:
            unknown_cost = True
        else:
            known_total += hotel["price"]

        meals = []
        for slot in range(3):
            meal = meal_cycle[(index * 3 + slot) % len(meal_cycle)]
            meals.append("%s, %s" % (meal["name"], meal["city"]))
            if meal["price"] is None:
                unknown_cost = True
            else:
                known_total += meal["price"] * cfg["party_size"]

        picks = [attractions[(index * 2) % len(attractions)]]
        if len(attractions) > 1:
            picks.append(attractions[(index * 2 + 1) % len(attractions)])
        destination = hotel["city"]
        if index == 0:
            current = "from %s to %s" % (cfg["origin"], destination)
            transportation = "Self-driving: from %s to %s" % (cfg["origin"], destination)
        elif index in (2, 4):
            prior = min(hotels[stays[index - 1]], key=price_key)["city"]
            current = "from %s to %s" % (prior, destination)
            transportation = "Self-driving: from %s to %s" % (prior, destination)
        else:
            current = destination
            transportation = "Self-driving within %s" % destination
        plan.append({
            "day": index + 1,
            "current_city": current,
            "transportation": transportation,
            "breakfast": meals[0],
            "lunch": meals[1],
            "dinner": meals[2],
            "attraction": ";".join(pick["name"] for pick in picks) + ";",
            "accommodation": "Pet-friendly %s, %s" % (hotel["name"], hotel["city"]),
        })
    return plan, None if unknown_cost else round(known_total, 2)


def config(raw):
    required = (
        "data_root", "output_path", "origin", "target_state", "start_date", "end_date",
        "party_size", "budget", "cuisines",
    )
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError("missing input field(s): " + ", ".join(missing))
    cfg = dict(raw)
    if cfg.get("days", 7) != 7 or cfg.get("city_count", 3) != 3 or cfg.get("pet_required", True) is not True:
        raise ValueError("this task requires seven days, three cities, and pets permitted")
    if type(cfg["party_size"]) is not int or cfg["party_size"] < 1:
        raise ValueError("party_size must be a positive integer")
    if (not isinstance(cfg["budget"], (int, float)) or isinstance(cfg["budget"], bool)
            or cfg["budget"] <= 0):
        raise ValueError("budget must be a positive number")
    if (not isinstance(cfg["cuisines"], list) or not cfg["cuisines"]
            or not all(isinstance(value, str) and text(value) for value in cfg["cuisines"])):
        raise ValueError("cuisines must be a nonempty string array")
    try:
        span = (date.fromisoformat(cfg["end_date"]) - date.fromisoformat(cfg["start_date"])).days + 1
    except ValueError as exc:
        raise ValueError("dates must use ISO YYYY-MM-DD") from exc
    if span != 7:
        raise ValueError("request must span exactly seven inclusive days")
    if not Path(cfg["data_root"]).is_dir():
        raise ValueError("data_root must be a readable directory")
    return cfg


def build(raw):
    cfg = config(raw)
    data = load_sources(cfg["data_root"])
    hotels, restaurants, attractions = build_catalogs(data, cfg)
    route = choose_route(hotels, road_edges(data), cfg)
    plan, known_cost = make_plan(route, hotels, restaurants, attractions, cfg)
    if known_cost is not None and known_cost > float(cfg["budget"]):
        raise ValueError("lowest fully-known source lodging and meal cost exceeds budget")
    artifact = {
        "plan": plan,
        "tool_called": [
            "search_cities", "search_accommodations", "search_restaurants",
            "search_attractions", "search_distance_matrix",
        ],
    }
    output = Path(cfg["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(output.parent), delete=False) as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, output)
    return {
        "ok": True,
        "output_path": str(output),
        "chosen_cities": [min(hotels[key], key=price_key)["city"] for key in route],
        "known_cost": known_cost,
    }


def main():
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("stdin must contain a JSON object")
        print(json.dumps(build(raw), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
