#!/usr/bin/env python3
"""Build a source-grounded seven-day, pet-friendly road itinerary.

stdin schema: documented in SKILL.md.
stdout: {"ok": true, ...} or {"ok": false, "error": "..."}.
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


def txt(value):
    return "" if value is None else str(value).strip()


def norm(value):
    return re.sub(r"[^a-z0-9]+", "", txt(value).lower())


def place_key(value):
    return norm(re.split(r"[,(/]", txt(value), maxsplit=1)[0])


def numeric(value):
    match = re.search(r"-?\d+(?:\.\d+)?", txt(value).replace(",", ""))
    return float(match.group(0)) if match else None


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        headers = [h for h in (reader.fieldnames or []) if h]
        rows = []
        for row in reader:
            clean = {txt(k): txt(v) for k, v in row.items() if k is not None}
            if any(clean.values()):
                rows.append(clean)
    return headers, rows


def column(headers, aliases):
    best, score = None, -1
    for header in headers:
        h = norm(header)
        for alias in aliases:
            a = norm(alias)
            if h == a:
                candidate = 100
            elif a and (a in h or h in a):
                candidate = 50 - abs(len(h) - len(a))
            else:
                continue
            if candidate > score:
                best, score = header, candidate
    return best


def classify(path, headers):
    name = norm(str(path))
    header_set = {norm(h) for h in headers}
    if any(word in name for word in ("accommodation", "lodging", "rental", "hotel")):
        return "accommodation"
    if any(word in name for word in ("restaurant", "dining")):
        return "restaurant"
    if any(word in name for word in ("attraction", "poi", "sight")):
        return "attraction"
    if any(word in name for word in ("distance", "matrix")):
        return "distance"
    if {"origin", "destination"}.issubset(header_set) and "flight" not in name:
        return "distance"
    return None


def load_data(root):
    data = {}
    for path in sorted(Path(root).rglob("*.csv")):
        if not path.is_file():
            continue
        headers, rows = read_csv(path)
        kind = classify(path, headers)
        if kind and kind not in data:
            data[kind] = {"headers": headers, "rows": rows, "path": str(path)}
    needed = ("accommodation", "restaurant", "attraction", "distance")
    missing = [kind for kind in needed if kind not in data]
    if missing:
        raise ValueError("missing required dataset(s): " + ", ".join(missing))
    return data


def columns(dataset, kind):
    headers = dataset["headers"]
    result = {
        "name": column(headers, ["name", "property name", "restaurant name", "attraction name", "title"]),
        "city": column(headers, ["city", "city name", "location city", "destination city"]),
    }
    if kind == "accommodation":
        result.update({
            "price": column(headers, ["price", "nightly price", "price per night", "rate"]),
            "capacity": column(headers, ["accommodates", "maximum occupancy", "max occupancy", "capacity", "guests"]),
        })
    elif kind == "restaurant":
        result.update({
            "price": column(headers, ["average cost", "average price", "meal price", "price", "cost"]),
            "cuisine": column(headers, ["cuisines", "cuisine", "categories", "category"]),
        })
    elif kind == "distance":
        result.update({
            "origin": column(headers, ["origin", "from", "source", "start city"]),
            "destination": column(headers, ["destination", "to", "target", "end city"]),
        })
    return result


def require_columns(label, found, needed):
    missing = [key for key in needed if not found.get(key)]
    if missing:
        raise ValueError("%s missing usable column(s): %s" % (label, ", ".join(missing)))


def state_city_keys(root, wanted_state):
    """Read state-associated cities from supplied reference text without fixed layout."""
    wanted = norm(wanted_state)
    keys = set()
    for path in Path(root).rglob("*.txt"):
        if "city" not in norm(path.name):
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            if wanted not in norm(line):
                continue
            quoted = re.findall(r"['\"]([^'\"]+)['\"]", line)
            if quoted:
                keys.add(place_key(quoted[0]))
                continue
            # Common reference formats contain a city followed by state.
            before = re.split(re.escape(wanted_state), line, flags=re.I)[0]
            before = before.strip(" [](){}\t,;:'\"")
            if before:
                keys.add(place_key(before))
    return {key for key in keys if key}


def state_ok(location, state, reference_keys):
    return norm(state) in norm(location) or place_key(location) in reference_keys

# This is intentionally aligned with the public requirement: permission must
# appear in source policy-like fields, and a contrary restriction always wins.
POSITIVE_PET = re.compile(
    r"(pet[- ]?friendly|pets?\s+(?:allowed|welcome)|allow(?:s|ed)?\s+pets?|dogs?\s+allowed|dog[- ]?friendly)",
    re.I,
)
NEGATIVE_PET = re.compile(r"(no\s+pets?|pets?\s+(?:not\s+)?allowed|pets?\s+prohibited)", re.I)


def policy_text(row):
    values = []
    for header, value in row.items():
        h = str(header).lower()
        if any(token in h for token in ("pet", "rule", "policy", "amenit")):
            values.append(txt(value))
    return " ".join(values)


def explicitly_pet_permitted(row):
    policy = policy_text(row)
    return bool(policy and POSITIVE_PET.search(policy) and not NEGATIVE_PET.search(policy))


def has_cuisine(record, requested):
    return norm(requested) in norm(record["cuisine"])


def catalogs(data, cfg):
    ac, rs, ats, ds = (data[k] for k in ("accommodation", "restaurant", "attraction", "distance"))
    ac_c, rs_c = columns(ac, "accommodation"), columns(rs, "restaurant")
    at_c, ds_c = columns(ats, "attraction"), columns(ds, "distance")
    require_columns("accommodations", ac_c, ("name", "city", "price", "capacity"))
    require_columns("restaurants", rs_c, ("name", "city", "price", "cuisine"))
    require_columns("attractions", at_c, ("name", "city"))
    require_columns("distance matrix", ds_c, ("origin", "destination"))
    reference = state_city_keys(cfg["data_root"], cfg["target_state"])

    hotels = defaultdict(list)
    for row in ac["rows"]:
        name, city = txt(row.get(ac_c["name"])), txt(row.get(ac_c["city"]))
        price, capacity = numeric(row.get(ac_c["price"])), numeric(row.get(ac_c["capacity"]))
        if not (name and city and state_ok(city, cfg["target_state"], reference)):
            continue
        if price is None or capacity is None or capacity < cfg["party_size"]:
            continue
        # Pet friendliness is mandatory, even if a caller supplied false.
        if not explicitly_pet_permitted(row):
            continue
        hotels[place_key(city)].append({"name": name, "city": city, "price": price, "row": row})

    restaurants = defaultdict(list)
    for row in rs["rows"]:
        name, city = txt(row.get(rs_c["name"])), txt(row.get(rs_c["city"]))
        price, cuisine = numeric(row.get(rs_c["price"])), txt(row.get(rs_c["cuisine"]))
        if name and city and price is not None and cuisine:
            restaurants[place_key(city)].append({"name": name, "city": city, "price": price, "cuisine": cuisine})

    attractions = defaultdict(list)
    for row in ats["rows"]:
        name, city = txt(row.get(at_c["name"])), txt(row.get(at_c["city"]))
        if name and city:
            attractions[place_key(city)].append({"name": name, "city": city})

    edges = set()
    for row in ds["rows"]:
        origin, destination = txt(row.get(ds_c["origin"])), txt(row.get(ds_c["destination"]))
        if origin and destination:
            edges.add((place_key(origin), place_key(destination)))

    result = {}
    for key, options in hotels.items():
        if key not in restaurants or key not in attractions:
            continue
        hotel = min(options, key=lambda item: (item["price"], item["name"].casefold()))
        result[key] = {
            "display": hotel["city"], "hotel": hotel,
            "restaurants": sorted(restaurants[key], key=lambda item: (item["price"], item["name"].casefold())),
            "attractions": attractions[key],
        }
    return result, edges


def routes(cities, edges, cfg):
    found = []
    origin = place_key(cfg["origin"])
    for group in itertools.combinations(sorted(cities), 3):
        for route in itertools.permutations(group):
            if (origin, route[0]) not in edges or (route[0], route[1]) not in edges or (route[1], route[2]) not in edges:
                continue
            coverage = sum(any(has_cuisine(r, wanted) for city in route for r in cities[city]["restaurants"])
                           for wanted in cfg["cuisines"])
            # Cuisine preferences are required by this task's public validation.
            if coverage != len(cfg["cuisines"]):
                continue
            lodging = 2 * cities[route[0]]["hotel"]["price"] + 2 * cities[route[1]]["hotel"]["price"] + 3 * cities[route[2]]["hotel"]["price"]
            found.append((route, coverage, lodging))
    return sorted(found, key=lambda item: (item[2], item[0]))


def select_meal(city, desired):
    matches = [row for row in city["restaurants"] if has_cuisine(row, desired)]
    chosen = (matches or city["restaurants"])[0]
    if matches:
        return "%s cuisine at %s, %s" % (desired.title(), chosen["name"], chosen["city"]), chosen
    return "%s, %s" % (chosen["name"], chosen["city"]), chosen


def create_plan(route, cities, cfg):
    day_keys = [route[0], route[0], route[1], route[1], route[2], route[2], route[2]]
    plan, total = [], 0.0
    for index, key in enumerate(day_keys):
        city = cities[key]
        total += city["hotel"]["price"]
        meals = []
        for slot in range(3):
            desired = cfg["cuisines"][(index * 3 + slot) % len(cfg["cuisines"])]
            label, row = select_meal(city, desired)
            meals.append(label)
            total += row["price"] * cfg["party_size"]
        available = city["attractions"]
        start = (2 * index) % len(available)
        picks = [available[start]]
        if len(available) > 1:
            picks.append(available[(start + 1) % len(available)])
        attraction = ";".join(item["name"].rstrip(";") for item in picks) + ";"
        if index == 0:
            current = "from %s to %s" % (cfg["origin"], city["display"])
            transport = "Self-driving: from %s to %s" % (cfg["origin"], city["display"])
        elif index in (2, 4):
            prior = cities[route[0 if index == 2 else 1]]["display"]
            current = "from %s to %s" % (prior, city["display"])
            transport = "Self-driving: from %s to %s" % (prior, city["display"])
        else:
            current = city["display"]
            transport = "Self-driving within %s" % city["display"]
        plan.append({
            "day": index + 1, "current_city": current, "transportation": transport,
            "breakfast": meals[0], "lunch": meals[1], "dinner": meals[2],
            "attraction": attraction,
            "accommodation": "Pet-friendly %s, %s" % (city["hotel"]["name"], city["hotel"]["city"]),
        })
    return plan, total


def validate_artifact(artifact, selected_hotels):
    if set(artifact) != {"plan", "tool_called"} or len(artifact["plan"]) != 7:
        raise ValueError("invalid artifact top-level structure")
    fields = {"day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"}
    for day, entry in enumerate(artifact["plan"], 1):
        if set(entry) != fields or type(entry["day"]) is not int or entry["day"] != day:
            raise ValueError("invalid day structure")
        if any(not isinstance(entry[key], str) for key in fields - {"day"}):
            raise ValueError("all day text fields must be strings")
        if not entry["attraction"].endswith(";") or "flight" in entry["transportation"].lower():
            raise ValueError("invalid attraction or prohibited transportation")
        hotel = selected_hotels[day - 1]
        if hotel["name"] not in entry["accommodation"] or not explicitly_pet_permitted(hotel["row"]):
            raise ValueError("selected lodging lacks source-backed positive pet permission")


def config(raw):
    required = ("data_root", "output_path", "origin", "target_state", "start_date", "end_date", "party_size", "budget", "cuisines")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError("missing input field(s): " + ", ".join(missing))
    cfg = dict(raw)
    if cfg.get("days", 7) != 7 or cfg.get("city_count", 3) != 3:
        raise ValueError("this artifact contract requires exactly 7 days and 3 cities")
    if "pet_required" in cfg and cfg["pet_required"] is not True:
        raise ValueError("pet_required must be true for this task")
    if type(cfg["party_size"]) is not int or cfg["party_size"] < 1:
        raise ValueError("party_size must be a positive integer")
    if not isinstance(cfg["budget"], (int, float)) or isinstance(cfg["budget"], bool) or cfg["budget"] <= 0:
        raise ValueError("budget must be a positive number")
    if not isinstance(cfg["cuisines"], list) or not cfg["cuisines"] or not all(isinstance(x, str) and txt(x) for x in cfg["cuisines"]):
        raise ValueError("cuisines must be a nonempty array of strings")
    try:
        span = (date.fromisoformat(cfg["end_date"]) - date.fromisoformat(cfg["start_date"])).days + 1
    except ValueError as exc:
        raise ValueError("dates must be ISO YYYY-MM-DD") from exc
    if span != 7:
        raise ValueError("dates must span exactly seven inclusive days")
    if not Path(cfg["data_root"]).is_dir():
        raise ValueError("data_root is not a readable directory")
    return cfg


def build(raw):
    cfg = config(raw)
    cities, edges = catalogs(load_data(cfg["data_root"]), cfg)
    candidates = routes(cities, edges, cfg)
    if not candidates:
        raise ValueError("no source-backed three-city route satisfies road, cuisine, and pet-lodging requirements")
    for route, coverage, _ in candidates:
        plan, total = create_plan(route, cities, cfg)
        if total > float(cfg["budget"]):
            continue
        artifact = {"plan": plan, "tool_called": ["search_cities", "search_accommodations", "search_restaurants", "search_attractions", "search_distance_matrix"]}
        selected = [cities[key]["hotel"] for key in [route[0], route[0], route[1], route[1], route[2], route[2], route[2]]]
        validate_artifact(artifact, selected)
        output = Path(cfg["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(output.parent), delete=False) as handle:
            json.dump(artifact, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary = handle.name
        os.replace(temporary, output)
        return {"ok": True, "output_path": str(output), "chosen_cities": [cities[k]["display"] for k in route], "known_cost": round(total, 2), "preference_coverage": coverage}
    raise ValueError("all feasible routes exceed the supplied budget")


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
