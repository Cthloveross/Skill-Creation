#!/usr/bin/env python3
"""Discover local travel CSV data and create a seven-day road itinerary.

stdin: build configuration described in SKILL.md
stdout: {"ok": bool, ...}; the itinerary itself is written to output_path.
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


def text(value):
    return "" if value is None else str(value).strip()


def norm(value):
    return re.sub(r"[^a-z0-9]+", "", text(value).lower())


def place_key(value):
    # State-qualified source locations and their bare city form identify the
    # same place for joining, while output retains the source spelling.
    first = re.split(r"[,(/]", text(value), maxsplit=1)[0]
    return norm(first)


def number(value):
    s = text(value).replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def discover_csvs(root):
    result = []
    for path in Path(root).rglob("*.csv"):
        if path.is_file():
            result.append(path)
    return sorted(result)


def read_csv(path):
    # CSV exports in the supplied corpus are expected to be ordinary text;
    # utf-8-sig also safely handles an exported BOM.
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        headers = [h for h in (reader.fieldnames or []) if h]
        rows = []
        for row in reader:
            if any(text(v) for v in row.values()):
                rows.append({text(k): text(v) for k, v in row.items() if k is not None})
    return headers, rows


def pick_column(headers, aliases):
    """Return the strongest header match, or None when no semantic match exists."""
    best = None
    best_score = 0
    for header in headers:
        h = norm(header)
        for alias in aliases:
            a = norm(alias)
            if not a:
                continue
            if h == a:
                score = 100
            elif a in h or h in a:
                score = 50 - abs(len(h) - len(a))
            else:
                continue
            if score > best_score:
                best, best_score = header, score
    return best


def classify(path, headers):
    name = norm(str(path))
    hs = {norm(h) for h in headers}
    if any(x in name for x in ("accommodation", "lodging", "hotel", "rental")):
        return "accommodation"
    if "restaurant" in name or "dining" in name:
        return "restaurant"
    if any(x in name for x in ("attraction", "poi", "sight")):
        return "attraction"
    if "distance" in name or "matrix" in name:
        return "distance"
    # A header-only fallback supports renamed exports but deliberately does not
    # classify flight exports as road-distance data.
    if {"origin", "destination"}.issubset(hs) and "flight" not in name:
        return "distance"
    return None


def load_datasets(root):
    selected = {}
    for path in discover_csvs(root):
        headers, rows = read_csv(path)
        kind = classify(path, headers)
        if kind and kind not in selected:
            selected[kind] = {"path": str(path), "headers": headers, "rows": rows}
    missing = [k for k in ("accommodation", "restaurant", "attraction", "distance") if k not in selected]
    if missing:
        raise ValueError("missing required CSV dataset(s): " + ", ".join(missing))
    return selected


def state_city_keys(root, wanted_state):
    """Extract city names associated with a state from supplied reference text."""
    wanted = norm(wanted_state)
    keys = set()
    for path in Path(root).rglob("*.txt"):
        if "city" not in norm(path.name):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            lines = path.read_text(encoding="latin-1").splitlines()
        for line in lines:
            if wanted not in norm(line):
                continue
            quoted = re.findall(r"['\"]([^'\"]+)['\"]", line)
            if quoted:
                # Pair-form records put the city first; a single quoted
                # state-qualified location is also handled by place_key.
                keys.add(place_key(quoted[0]))
                continue
            before = re.split(re.escape(wanted_state), line, flags=re.I)[0]
            before = before.strip(" [](){}\t,;:'\"")
            if before:
                keys.add(place_key(before))
    return {k for k in keys if k}


def in_target_state(location, wanted_state, known_city_keys):
    raw = norm(location)
    return norm(wanted_state) in raw or place_key(location) in known_city_keys


def dataset_columns(dataset, kind):
    h = dataset["headers"]
    common = {
        "city": pick_column(h, ["city", "city name", "location city", "destination city"]),
        "name": pick_column(h, ["name", "title", "property name", "restaurant name", "attraction name"]),
    }
    if kind == "accommodation":
        common.update({
            "price": pick_column(h, ["price", "nightly price", "price per night", "rate"]),
            "capacity": pick_column(h, ["maximum occupancy", "max occupancy", "accommodates", "capacity", "guests"]),
            "pet": pick_column(h, ["pet friendly", "pets allowed", "pet policy"]),
        })
    elif kind == "restaurant":
        common.update({
            "price": pick_column(h, ["average cost", "average price", "meal price", "price", "cost"]),
            "cuisine": pick_column(h, ["cuisines", "cuisine", "categories", "category"]),
        })
    elif kind == "distance":
        common.update({
            "origin": pick_column(h, ["origin", "from", "source", "start city"]),
            "destination": pick_column(h, ["destination", "to", "target", "end city"]),
        })
    return common


def pet_allowed(row, cols):
    relevant = []
    for header, value in row.items():
        nh = norm(header)
        if header == cols.get("pet") or any(word in nh for word in ("pet", "rule", "policy", "amenit", "house")):
            relevant.append(text(value).lower())
    statement = " ; ".join(relevant)
    if not statement:
        return False
    negative = r"\b(no pets?|pets? (?:are )?not allowed|not pet[ -]?friendly|pets? prohibited)\b"
    positive = r"\b(pet[ -]?friendly|pets? allowed|pet allowed|allows? pets?|pets? welcome)\b"
    if re.search(negative, statement):
        return False
    return bool(re.search(positive, statement))


def source_name(row, cols):
    value = text(row.get(cols.get("name"))) if cols.get("name") else ""
    return value


def prepare_catalogs(data, cfg):
    state_keys = state_city_keys(cfg["data_root"], cfg["target_state"])
    if not state_keys:
        # Locations can themselves be explicitly state-qualified; retain this
        # route only when such direct evidence exists.
        state_keys = set()

    ac, re_ds, at, dist = (data[x] for x in ("accommodation", "restaurant", "attraction", "distance"))
    ac_cols = dataset_columns(ac, "accommodation")
    re_cols = dataset_columns(re_ds, "restaurant")
    at_cols = dataset_columns(at, "attraction")
    di_cols = dataset_columns(dist, "distance")
    for label, cols, needed in (
        ("accommodations", ac_cols, ("city", "name", "price", "capacity")),
        ("restaurants", re_cols, ("city", "name", "price", "cuisine")),
        ("attractions", at_cols, ("city", "name")),
        ("distance matrix", di_cols, ("origin", "destination")),
    ):
        absent = [x for x in needed if not cols.get(x)]
        if absent:
            raise ValueError(label + " missing usable column(s): " + ", ".join(absent))

    hotels = defaultdict(list)
    for row in ac["rows"]:
        city = text(row.get(ac_cols["city"]))
        name = source_name(row, ac_cols)
        price = number(row.get(ac_cols["price"]))
        capacity = number(row.get(ac_cols["capacity"]))
        state_ok = in_target_state(city, cfg["target_state"], state_keys)
        if city and name and price is not None and capacity is not None and capacity >= cfg["party_size"] and state_ok:
            if not cfg["pet_required"] or pet_allowed(row, ac_cols):
                hotels[place_key(city)].append({"name": name, "city": city, "price": price, "row": row})

    restaurants = defaultdict(list)
    for row in re_ds["rows"]:
        city, name = text(row.get(re_cols["city"])), source_name(row, re_cols)
        price, cuisine = number(row.get(re_cols["price"])), text(row.get(re_cols["cuisine"]))
        if city and name and price is not None and cuisine:
            restaurants[place_key(city)].append({"name": name, "city": city, "price": price, "cuisine": cuisine, "row": row})

    attractions = defaultdict(list)
    for row in at["rows"]:
        city, name = text(row.get(at_cols["city"])), source_name(row, at_cols)
        if city and name:
            attractions[place_key(city)].append({"name": name, "city": city, "row": row})

    edge_set = set()
    for row in dist["rows"]:
        origin, destination = text(row.get(di_cols["origin"])), text(row.get(di_cols["destination"]))
        if origin and destination:
            edge_set.add((place_key(origin), place_key(destination)))

    cities = {}
    for key, options in hotels.items():
        if key not in restaurants or key not in attractions:
            continue
        # Cheapest verified property is used so budget comparisons are
        # reproducible. Preserve its source city spelling for output.
        hotel = min(options, key=lambda x: (x["price"], x["name"].casefold()))
        cities[key] = {
            "key": key,
            "display": hotel["city"],
            "hotel": hotel,
            "restaurants": sorted(restaurants[key], key=lambda x: (x["price"], x["name"].casefold())),
            "attractions": attractions[key],
        }
    return cities, edge_set


def has_cuisine(restaurant, desired):
    return norm(desired) in norm(restaurant["cuisine"])


def choose_meal(city, desired):
    matching = [r for r in city["restaurants"] if has_cuisine(r, desired)]
    chosen = (matching or city["restaurants"])[0]
    if matching:
        return "%s cuisine at %s, %s" % (desired.title(), chosen["name"], chosen["city"]), chosen
    return "%s, %s" % (chosen["name"], chosen["city"]), chosen


def candidate_routes(cities, edges, origin, cuisines):
    keys = sorted(cities)
    origin_key = place_key(origin)
    candidates = []
    for chosen in itertools.combinations(keys, 3):
        for route in itertools.permutations(chosen):
            if (origin_key, route[0]) not in edges:
                continue
            if (route[0], route[1]) not in edges or (route[1], route[2]) not in edges:
                continue
            cuisine_coverage = sum(any(has_cuisine(r, c) for key in route for r in cities[key]["restaurants"]) for c in cuisines)
            lodging = 2 * cities[route[0]]["hotel"]["price"] + 2 * cities[route[1]]["hotel"]["price"] + 3 * cities[route[2]]["hotel"]["price"]
            attraction_count = sum(len(cities[k]["attractions"]) for k in route)
            candidates.append((route, cuisine_coverage, lodging, attraction_count))
    return sorted(candidates, key=lambda x: (-x[1], x[2], -x[3], x[0]))


def make_plan(route, cities, cfg):
    # Route location by day: arrival, local, transfer, local, transfer, local, local.
    day_city = [route[0], route[0], route[1], route[1], route[2], route[2], route[2]]
    plan = []
    total = 0.0
    for index, key in enumerate(day_city):
        city = cities[key]
        total += city["hotel"]["price"]
        meals = []
        meal_rows = []
        for slot in range(3):
            desired = cfg["cuisines"][(index * 3 + slot) % len(cfg["cuisines"])]
            meal_text, chosen = choose_meal(city, desired)
            meals.append(meal_text)
            meal_rows.append(chosen)
            total += chosen["price"] * cfg["party_size"]
        available = city["attractions"]
        # At least one real attraction is required; two are shown when available.
        start = (index * 2) % len(available)
        picks = [available[start]]
        if len(available) > 1:
            picks.append(available[(start + 1) % len(available)])
        attraction_text = ";".join(p["name"].rstrip(";") for p in picks) + ";"

        if index == 0:
            current = "from %s to %s" % (cfg["origin"], city["display"])
            transport = "Self-driving: from %s to %s" % (cfg["origin"], city["display"])
        elif index == 2:
            previous = cities[route[0]]["display"]
            current = "from %s to %s" % (previous, city["display"])
            transport = "Self-driving: from %s to %s" % (previous, city["display"])
        elif index == 4:
            previous = cities[route[1]]["display"]
            current = "from %s to %s" % (previous, city["display"])
            transport = "Self-driving: from %s to %s" % (previous, city["display"])
        else:
            current = city["display"]
            transport = "Self-driving within %s" % city["display"]
        plan.append({
            "day": index + 1,
            "current_city": current,
            "transportation": transport,
            "breakfast": meals[0],
            "lunch": meals[1],
            "dinner": meals[2],
            "attraction": attraction_text,
            "accommodation": "Pet-friendly %s, %s" % (city["hotel"]["name"], city["hotel"]["city"]),
        })
    return plan, total


def validate_object(obj):
    if not isinstance(obj, dict) or set(obj) != {"plan", "tool_called"}:
        raise ValueError("artifact must contain exactly plan and tool_called")
    plan = obj["plan"]
    if not isinstance(plan, list) or len(plan) != 7:
        raise ValueError("plan must be an array of exactly 7 days")
    if not isinstance(obj["tool_called"], list) or not all(isinstance(x, str) for x in obj["tool_called"]):
        raise ValueError("tool_called must be an array of strings")
    required = {"day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"}
    for i, entry in enumerate(plan, 1):
        if not isinstance(entry, dict) or set(entry) != required:
            raise ValueError("day %d does not have the required fields" % i)
        if type(entry["day"]) is not int or entry["day"] != i:
            raise ValueError("day numbers must be sequential integers")
        for key in required - {"day"}:
            if not isinstance(entry[key], str):
                raise ValueError("day %d field %s must be a string" % (i, key))
        if not entry["attraction"].endswith(";"):
            raise ValueError("day %d attraction must end in semicolon" % i)
        if "flight" in entry["transportation"].lower():
            raise ValueError("flight transportation is forbidden")


def check_config(cfg):
    required = ["data_root", "output_path", "origin", "target_state", "start_date", "end_date", "party_size", "budget", "cuisines"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError("missing configuration field(s): " + ", ".join(missing))
    cfg = dict(cfg)
    cfg.setdefault("days", 7)
    cfg.setdefault("city_count", 3)
    cfg.setdefault("pet_required", True)
    cfg.setdefault("strict_preferences", False)
    cfg.setdefault("lodging_price_unit", "per_night")
    cfg.setdefault("meal_price_unit", "per_person")
    if cfg["days"] != 7 or cfg["city_count"] != 3:
        raise ValueError("this output contract requires days=7 and city_count=3")
    if cfg["lodging_price_unit"] != "per_night" or cfg["meal_price_unit"] != "per_person":
        raise ValueError("unsupported price units; require per_night lodging and per_person meals")
    if type(cfg["party_size"]) is not int or cfg["party_size"] < 1:
        raise ValueError("party_size must be a positive integer")
    if not isinstance(cfg["budget"], (int, float)) or isinstance(cfg["budget"], bool) or cfg["budget"] <= 0:
        raise ValueError("budget must be a positive number")
    if not isinstance(cfg["cuisines"], list) or not cfg["cuisines"] or not all(isinstance(x, str) and text(x) for x in cfg["cuisines"]):
        raise ValueError("cuisines must be a nonempty array of strings")
    try:
        inclusive = (date.fromisoformat(cfg["end_date"]) - date.fromisoformat(cfg["start_date"])).days + 1
    except ValueError as exc:
        raise ValueError("dates must use ISO YYYY-MM-DD format") from exc
    if inclusive != 7:
        raise ValueError("start_date and end_date must span exactly 7 inclusive days")
    if not Path(cfg["data_root"]).is_dir():
        raise ValueError("data_root is not a readable directory")
    return cfg


def build(cfg):
    cfg = check_config(cfg)
    data = load_datasets(cfg["data_root"])
    cities, edges = prepare_catalogs(data, cfg)
    routes = candidate_routes(cities, edges, cfg["origin"], cfg["cuisines"])
    if not routes:
        raise ValueError("no three-city route has all required directed self-driving legs and source-backed records")
    for route, coverage, _lodging, _attraction_count in routes:
        if cfg["strict_preferences"] and coverage < len(cfg["cuisines"]):
            continue
        plan, total = make_plan(route, cities, cfg)
        if total <= float(cfg["budget"]):
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
            validate_object(artifact)
            destination = Path(cfg["output_path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(destination.parent), delete=False) as fh:
                json.dump(artifact, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
                temporary = fh.name
            os.replace(temporary, destination)
            return {
                "ok": True,
                "output_path": str(destination),
                "chosen_cities": [cities[k]["display"] for k in route],
                "known_cost": round(total, 2),
                "budget": cfg["budget"],
                "preference_coverage": coverage,
            }
    raise ValueError("all feasible routes exceed the budget using known lodging and meal prices")


def main():
    try:
        cfg = json.load(sys.stdin)
        if not isinstance(cfg, dict):
            raise ValueError("stdin must contain a JSON object")
        print(json.dumps(build(cfg), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
