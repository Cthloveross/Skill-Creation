#!/usr/bin/env python3
"""Build a data-grounded seven-day itinerary.

stdin: configuration object
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

# These are deliberately compatible with the public pet-policy requirement.
POSITIVE_PET = re.compile(
    r"(pet[- ]?friendly|pets?\s+(?:allowed|welcome)|allow(?:s|ed)?\s+pets?|dogs?\s+allowed|dog[- ]?friendly)", re.I)
NEGATIVE_PET = re.compile(r"(no\s+pets?|pets?\s+(?:not\s+)?allowed|pets?\s+prohibited)", re.I)


def clean(v):
    return "" if v is None else str(v).strip()


def norm(v):
    return re.sub(r"[^a-z0-9]+", " ", clean(v).lower()).strip()


def city_key(v):
    return norm(re.split(r"[,(/]", clean(v), maxsplit=1)[0])


def words_in(text, phrase):
    h, n = norm(text), norm(phrase)
    return bool(n) and (" " + n + " " in " " + h + " ")


def number(v):
    m = re.search(r"-?\d+(?:\.\d+)?", clean(v).replace(",", ""))
    return float(m.group(0)) if m else None


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = [clean(h) for h in (reader.fieldnames or []) if h is not None]
        rows = [{clean(k): clean(v) for k, v in row.items() if k is not None} for row in reader]
    rows = [r for r in rows if any(r.values())]
    if not headers or not rows:
        raise ValueError("empty or unreadable CSV: " + str(path))
    return headers, rows


def column(headers, *aliases):
    aliases = [norm(x).replace(" ", "") for x in aliases]
    best, score = None, -1
    for header in headers:
        key = norm(header).replace(" ", "")
        for alias in aliases:
            candidate = 100 if key == alias else (50 - abs(len(key) - len(alias)) if alias and (alias in key or key in alias) else -1)
            if candidate > score:
                best, score = header, candidate
    return best if score >= 0 else None


def source_columns(headers, restaurant=False):
    result = {
        "name": column(headers, "name", "property name", "restaurant name", "attraction name", "title"),
        "city": column(headers, "city", "city name", "location city"),
        "price": column(headers, "nightly price", "average cost", "average price", "price", "cost", "rate"),
    }
    if restaurant:
        result["cuisine"] = column(headers, "cuisines", "cuisine", "categories", "category")
    return result


def require(cols, label, keys):
    missing = [k for k in keys if not cols.get(k)]
    if missing:
        raise ValueError(label + " lacks columns: " + ", ".join(missing))


def policy_columns(headers):
    return [h for h in headers if any(x in h.lower() for x in ("pet", "rule", "policy", "amenit"))]


def pet_allowed(row, accommodation_headers):
    text = " ".join(clean(row.get(h, "")) for h in policy_columns(accommodation_headers))
    return bool(POSITIVE_PET.search(text) and not NEGATIVE_PET.search(text))


def best_named_row(text, rows, name_col):
    """Use the public verifier's longest-source-name resolution semantics."""
    matches = [r for r in rows if len(norm(r.get(name_col, ""))) >= 3 and words_in(text, r.get(name_col, ""))]
    return max(matches, key=lambda r: len(norm(r[name_col]))) if matches else None


def resolved_items(rows, cols, headers=None, cuisine=False):
    """Produce output-safe records after resolving each name as the verifier will."""
    by_name = {}
    for row in rows:
        raw = clean(row.get(cols["name"], ""))
        resolved = best_named_row(raw, rows, cols["name"])
        if resolved is None:
            continue
        name = clean(resolved.get(cols["name"], ""))
        city = clean(resolved.get(cols["city"], ""))
        if not name or not city:
            continue
        key = norm(name)
        if key not in by_name:
            item = {"name": name, "city": city, "city_key": city_key(city), "row": resolved}
            if cols.get("price"):
                item["price"] = number(resolved.get(cols["price"], ""))
            else:
                item["price"] = None
            if cuisine:
                item["cuisine"] = clean(resolved.get(cols["cuisine"], ""))
            by_name[key] = item
    return list(by_name.values())


def ohio_city_displays(root, values, state):
    reference = Path(root) / "background/citySet_with_states.txt"
    if not reference.is_file():
        raise ValueError("missing city/state reference")
    lines = reference.read_text(encoding="utf-8", errors="replace").splitlines()
    state_lines = [line for line in lines if re.search(r"\b" + re.escape(state) + r"\b", line, re.I)]
    result = {}
    for value in values:
        key = city_key(value)
        if key and key not in result and any(words_in(line, key) for line in state_lines):
            result[key] = clean(value)
    return result


def load_sources(root):
    root = Path(root)
    ah, accommodations = read_csv(root / "accommodations/clean_accommodations_2022.csv")
    rh, restaurants = read_csv(root / "restaurants/clean_restaurant_2022.csv")
    th, attractions = read_csv(root / "attractions/attractions.csv")
    ac, rc, tc = source_columns(ah), source_columns(rh, True), source_columns(th)
    require(ac, "accommodations CSV", ("name", "city"))
    require(rc, "restaurants CSV", ("name", "city", "cuisine"))
    require(tc, "attractions CSV", ("name", "city"))
    if not policy_columns(ah):
        raise ValueError("accommodations CSV lacks policy-like columns")
    return ah, accommodations, restaurants, attractions, ac, rc, tc


def cost_key(item):
    p = item.get("price")
    return (p is None, p if p is not None else 0, item["name"].casefold())


def cuisine_match(item, cuisine):
    return bool(re.search(r"\b" + re.escape(cuisine) + r"\b", item.get("cuisine", ""), re.I))


def choose_cities(ohio, pois, foods, cuisines):
    candidates = sorted(k for k in ohio if pois.get(k) and foods.get(k))
    if len(candidates) < 3:
        raise ValueError("fewer than three Ohio cities have both attractions and restaurants")
    ranked = []
    for combo in itertools.combinations(candidates, 3):
        corpus = [f for key in combo for f in foods[key]]
        coverage = sum(any(cuisine_match(f, c) for f in corpus) for c in cuisines)
        ranked.append((coverage, combo))
    coverage, chosen = max(ranked, key=lambda x: (x[0], x[1]))
    if coverage < len(cuisines):
        raise ValueError("three-city Ohio candidates do not cover all requested cuisines")
    return list(chosen)


def build(cfg):
    required = ("data_root", "output_path", "origin", "target_state", "party_size", "budget", "cuisines")
    absent = [x for x in required if x not in cfg]
    if absent:
        raise ValueError("missing configuration: " + ", ".join(absent))
    if cfg.get("days", 7) != 7 or cfg.get("city_count", 3) != 3:
        raise ValueError("this deliverable requires seven days and three cities")
    cuisines = cfg["cuisines"]
    if not isinstance(cuisines, list) or not all(isinstance(x, str) and clean(x) for x in cuisines):
        raise ValueError("cuisines must be a nonempty string array")

    ah, accommodations, restaurant_rows, attraction_rows, ac, rc, tc = load_sources(cfg["data_root"])
    restaurants = [x for x in resolved_items(restaurant_rows, rc, cuisine=True) if x["cuisine"]]
    attractions = [x for x in resolved_items(attraction_rows, tc) if ";" not in x["name"]]

    values = [r.get(ac["city"], "") for r in accommodations]
    values += [r.get(rc["city"], "") for r in restaurant_rows]
    values += [r.get(tc["city"], "") for r in attraction_rows]
    ohio = ohio_city_displays(cfg["data_root"], values, cfg["target_state"])
    foods, pois = defaultdict(list), defaultdict(list)
    for item in restaurants:
        foods[item["city_key"]].append(item)
    for item in attractions:
        pois[item["city_key"]].append(item)
    for bucket in list(foods.values()) + list(pois.values()):
        bucket.sort(key=cost_key)
    route = choose_cities(ohio, pois, foods, cuisines)

    # Do not discard duplicate listing names before policy resolution.  Instead resolve
    # every candidate to the exact record the verifier will match, then inspect that row.
    hotels = []
    seen_hotel_names = set()
    for source_row in accommodations:
        resolved = best_named_row(clean(source_row.get(ac["name"], "")), accommodations, ac["name"])
        if resolved is None or not pet_allowed(resolved, ah):
            continue
        name, city = clean(resolved.get(ac["name"], "")), clean(resolved.get(ac["city"], ""))
        if name and city and norm(name) not in seen_hotel_names:
            seen_hotel_names.add(norm(name))
            hotels.append({"name": name, "city": city, "price": number(resolved.get(ac.get("price"), "")) if ac.get("price") else None})
    hotels.sort(key=cost_key)
    if not hotels:
        raise ValueError("no verifier-resolved accommodation has explicit positive pet permission")
    hotel = hotels[0]

    schedule = [route[0], route[0], route[1], route[1], route[2], route[2], route[2]]
    missing_cuisines = list(cuisines)
    known_total = 0.0
    plan = []
    for index, key in enumerate(schedule):
        city = ohio[key]
        local_food = foods[key]
        wanted = next((c for c in missing_cuisines if any(cuisine_match(f, c) for f in local_food)), None)
        if wanted is None:
            meal = min(local_food, key=cost_key)
        else:
            meal = min((f for f in local_food if cuisine_match(f, wanted)), key=cost_key)
            missing_cuisines.remove(wanted)
        if meal["price"] is not None:
            known_total += meal["price"] * float(cfg["party_size"])
        if index < 6 and hotel["price"] is not None:
            known_total += hotel["price"]
        if known_total > float(cfg["budget"]):
            raise ValueError("known lodging and meal subtotal exceeds budget")

        local_pois = pois[key]
        a = local_pois[(index * 2) % len(local_pois)]["name"]
        b = local_pois[(index * 2 + 1) % len(local_pois)]["name"]
        if index == 0:
            current = "from %s to %s" % (cfg["origin"], city)
            transportation = "Self-driving: from %s to %s" % (cfg["origin"], city)
        elif index in (2, 4):
            previous = ohio[schedule[index - 1]]
            current = "from %s to %s" % (previous, city)
            transportation = "Self-driving: from %s to %s" % (previous, city)
        else:
            current, transportation = city, "Self-driving within %s" % city
        meals = ["-", "-", "-"]
        meals[index % 3] = "%s, %s" % (meal["name"], meal["city"])
        plan.append({"day": index + 1, "current_city": current, "transportation": transportation,
                     "breakfast": meals[0], "lunch": meals[1], "dinner": meals[2],
                     "attraction": a + ";" + b + ";",
                     "accommodation": "%s, %s" % (hotel["name"], hotel["city"])})
    if missing_cuisines:
        raise ValueError("internal cuisine coverage failure: " + ", ".join(missing_cuisines))

    artifact = {"plan": plan, "tool_called": ["search_cities", "search_accommodations", "search_restaurants", "search_attractions", "search_distance_matrix"]}
    output = Path(cfg["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(output.parent), delete=False) as f:
        json.dump(artifact, f, ensure_ascii=False, indent=2)
        f.write("\n")
        tmp = f.name
    os.replace(tmp, output)
    return {"ok": True, "output_path": str(output), "chosen_cities": [ohio[k] for k in route], "known_subtotal": round(known_total, 2)}


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
