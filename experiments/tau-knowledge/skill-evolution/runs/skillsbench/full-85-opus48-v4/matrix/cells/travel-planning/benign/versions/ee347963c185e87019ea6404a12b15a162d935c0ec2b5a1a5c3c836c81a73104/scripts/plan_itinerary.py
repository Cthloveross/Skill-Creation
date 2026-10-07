"""End-to-end itinerary generator.

Stdin: params JSON (see SKILL.md).
Stdout: validation summary JSON.
Side effect: writes itinerary JSON to params['output_path'].
"""
import json
import math
import os
import sys
from itertools import permutations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from travel_db import TravelDB  # noqa: E402


def pick_cities(db, state, origin, num_cities, people, nights, warnings):
    cand = []
    for city in db.cities_in_state(state):
        accs = db.pet_friendly_accommodations(city, people=people, max_nights=nights)
        res = db.restaurants_in(city)
        att = db.attractions_in(city)
        leg_in = db.leg(origin, city)
        leg_out = db.leg(city, origin)
        if not accs or len(res) < 5 or len(att) < 2:
            continue
        if not leg_in or not leg_out:
            continue
        cheapest = accs[0]["price"] if accs[0]["price"] is not None else 1e12
        cand.append((city, cheapest, len(res), len(att)))
    # cheapest lodging first, then richer restaurant pool
    cand.sort(key=lambda t: (t[1], -t[2]))
    chosen = [c[0] for c in cand[:max(num_cities + 3, num_cities)]]
    if len(chosen) < num_cities:
        warnings.append("not enough qualifying cities in state=%s (found %d)" % (state, len(chosen)))
        return chosen[:num_cities]
    # choose the subset+order with all valid legs and minimal total driving
    best = None
    pool = chosen[: min(len(chosen), num_cities + 3)]
    for combo in permutations(pool, num_cities):
        route = [origin] + list(combo) + [origin]
        total = 0.0
        ok = True
        for a, b in zip(route, route[1:]):
            info = db.leg(a, b)
            if not info or info.get("distance") is None:
                ok = False
                break
            total += info["distance"]
        if ok and (best is None or total < best[0]):
            best = (total, list(combo))
    if best is None:
        warnings.append("could not form a fully-driveable route; using cheapest cities as-is")
        return chosen[:num_cities]
    return best[1]


def build_days(origin, cities, days):
    """Return list of day templates with route/stay info.

    Pattern per city: travel-in day (sleep in city) + one stay day.
    Then a final return-to-origin travel day. Pad/trim stay days to hit `days`.
    """
    tmpl = []
    for i, city in enumerate(cities):
        prev = origin if i == 0 else cities[i - 1]
        tmpl.append({"type": "travel", "a": prev, "b": city, "sleep": city})
        tmpl.append({"type": "stay", "city": city, "sleep": city})
    tmpl.append({"type": "travel", "a": cities[-1], "b": origin, "sleep": None})
    # adjust length to `days`
    while len(tmpl) < days:
        # insert an extra stay day in the last city, before the return day
        tmpl.insert(len(tmpl) - 1, {"type": "stay", "city": cities[-1], "sleep": cities[-1]})
    while len(tmpl) > days:
        # drop a stay day (keep travel days) from the end region
        for idx in range(len(tmpl) - 2, -1, -1):
            if tmpl[idx]["type"] == "stay":
                del tmpl[idx]
                break
        else:
            del tmpl[-1]
    return tmpl


def assign_restaurants(db, meal_slots, cuisines, people, used, warnings):
    """meal_slots: list of (slot_key, city). Returns dict slot_key -> (text, cost).
    Prioritises covering requested cuisines, then cheapest, no repeats.
    """
    pools = {}
    for _, city in meal_slots:
        if city not in pools:
            pools[city] = db.restaurants_in(city)
    assigned = {}
    covered = set()

    def take(slot_key, city, pred):
        for r in pools.get(city, []):
            if r["name"].lower() in used:
                continue
            if pred(r):
                used.add(r["name"].lower())
                cost = (r["cost"] or 0) * people
                assigned[slot_key] = ("%s, %s" % (r["name"], city), cost)
                return r
        return None

    # pass 1: cover each requested cuisine
    for cui in cuisines:
        cl = cui.lower()
        if cl in covered:
            continue
        for slot_key, city in meal_slots:
            if slot_key in assigned:
                continue
            r = take(slot_key, city, lambda r: cl in r["cuisines"].lower())
            if r:
                for c in cuisines:
                    if c.lower() in r["cuisines"].lower():
                        covered.add(c.lower())
                break
    # pass 2: fill remaining with cheapest unused
    for slot_key, city in meal_slots:
        if slot_key in assigned:
            continue
        r = take(slot_key, city, lambda r: True)
        if r:
            for c in cuisines:
                if c.lower() in r["cuisines"].lower():
                    covered.add(c.lower())
        else:
            assigned[slot_key] = ("-", 0)
            warnings.append("ran out of distinct restaurants in %s" % city)
    return assigned, covered


def main():
    params = json.load(sys.stdin)
    data_root = params.get("data_root", "/app/data")
    output_path = params.get("output_path", "/app/output/itinerary.json")
    origin = params["origin"]
    state = params["state"]
    num_cities = int(params.get("num_cities", 3))
    days = int(params.get("days", 2 * num_cities + 1))
    people = int(params.get("people", 2))
    budget = float(params.get("budget", 1e12))
    cuisines = params.get("cuisines", [])
    nights_per_city = 2

    warnings = []
    db = TravelDB(data_root)

    cities = pick_cities(db, state, origin, num_cities, people, nights_per_city, warnings)
    if len(cities) < num_cities:
        warnings.append("only %d/%d cities selected" % (len(cities), num_cities))

    tmpl = build_days(origin, cities, days)

    # accommodations: one per city (cheapest pet-friendly, occ ok, min_nights ok)
    acc_by_city = {}
    acc_cost = 0.0
    rooms = max(1, math.ceil(people / 2))
    for city in cities:
        accs = db.pet_friendly_accommodations(city, people=people, max_nights=nights_per_city)
        if accs:
            a = accs[0]
            acc_by_city[city] = a["name"]
            rneed = max(1, math.ceil(people / (a["occupancy"] or people)))
            acc_cost += (a["price"] or 0) * nights_per_city * rneed
        else:
            acc_by_city[city] = "-"
            warnings.append("no pet-friendly lodging found in %s" % city)

    # build meal slots
    meal_slots = []  # (slot_key, city)
    for i, d in enumerate(tmpl):
        if d["type"] == "travel":
            meal_slots.append(((i, "breakfast"), d["a"]))
            meal_slots.append(((i, "dinner"), d["b"]))
        else:
            for meal in ("breakfast", "lunch", "dinner"):
                meal_slots.append(((i, meal), d["city"]))
    used_r = set()
    meals, covered = assign_restaurants(db, meal_slots, cuisines, people, used_r, warnings)
    meal_cost = sum(c for _, c in meals.values())

    # attractions: distinct, 2 per stay day
    used_a = set()
    att_by_day = {}
    for i, d in enumerate(tmpl):
        if d["type"] == "stay":
            city = d["city"]
            picks = []
            for name in db.attractions_in(city):
                if name.lower() in used_a:
                    continue
                used_a.add(name.lower())
                picks.append(name)
                if len(picks) >= 2:
                    break
            att_by_day[i] = ("".join(n + ";" for n in picks)) if picks else "-"

    # driving cost + leg validity
    driving_cost = 0.0
    legs = []
    legs_valid = True
    for i, d in enumerate(tmpl):
        if d["type"] == "travel":
            c = db.driving_cost(d["a"], d["b"], people=people)
            legs.append({"from": d["a"], "to": d["b"], "valid": c is not None})
            if c is None:
                legs_valid = False
                warnings.append("missing driving leg %s -> %s" % (d["a"], d["b"]))
            else:
                driving_cost += c

    # assemble plan
    plan = []
    for i, d in enumerate(tmpl):
        day = {"day": i + 1}
        if d["type"] == "travel":
            day["current_city"] = "from %s to %s" % (d["a"], d["b"])
            day["transportation"] = "Self-driving: from %s to %s" % (d["a"], d["b"])
        else:
            day["current_city"] = d["city"]
            day["transportation"] = "-"
        for meal in ("breakfast", "lunch", "dinner"):
            txt = meals.get((i, meal), ("-", 0))[0]
            day[meal] = txt
        day["attraction"] = att_by_day.get(i, "-")
        sleep = d.get("sleep")
        day["accommodation"] = acc_by_city.get(sleep, "-") if sleep else "-"
        plan.append(day)

    tool_called = [
        "search_cities",
        "search_accommodations",
        "search_restaurants",
        "search_attractions",
        "search_distance_matrix",
    ]

    result = {"plan": plan, "tool_called": tool_called}
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total = acc_cost + meal_cost + driving_cost
    cuisines_missing = [c for c in cuisines if c.lower() not in covered]
    summary = {
        "ok": legs_valid and total <= budget and len(cities) == num_cities
              and not cuisines_missing,
        "output_path": output_path,
        "cities": cities,
        "route_legs": legs,
        "legs_valid": legs_valid,
        "cost": {
            "accommodation": round(acc_cost, 2),
            "meals": round(meal_cost, 2),
            "driving": round(driving_cost, 2),
            "total": round(total, 2),
        },
        "budget": budget,
        "within_budget": total <= budget,
        "cuisines_requested": cuisines,
        "cuisines_covered": sorted(covered),
        "cuisines_missing": cuisines_missing,
        "num_days": len(plan),
        "warnings": warnings,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
