#!/usr/bin/env python3
"""Validate an itinerary artifact against its public source data.

stdin: {"path": string, "data_root": string}
stdout: {"ok": bool, ...}
"""
import json
import re
import sys
from pathlib import Path

from build_itinerary import clean, has_words, norm, ohio_city_keys, pet_allowed, read_csv, source_columns


def matched(text, rows, name_column):
    candidates = [
        row
        for row in rows
        if len(norm(row.get(name_column, ""))) >= 3 and has_words(text, row.get(name_column, ""))
    ]
    return max(candidates, key=lambda row: len(norm(row[name_column]))) if candidates else None


def validate(obj, root, origin="Minneapolis", target_state="Ohio"):
    if not isinstance(obj, dict) or set(obj) != {"plan", "tool_called"}:
        raise ValueError("artifact must contain exactly plan and tool_called")
    if not isinstance(obj["tool_called"], list) or not obj["tool_called"] or not all(
        isinstance(item, str) and item.strip() for item in obj["tool_called"]
    ):
        raise ValueError("tool_called must be a nonempty string array")
    if not isinstance(obj["plan"], list) or len(obj["plan"]) != 7:
        raise ValueError("plan must contain exactly seven days")

    root = Path(root)
    accommodation_headers, accommodations = read_csv(root / "accommodations/clean_accommodations_2022.csv")
    restaurant_headers, restaurants = read_csv(root / "restaurants/clean_restaurant_2022.csv")
    attraction_headers, attractions = read_csv(root / "attractions/attractions.csv")
    accommodation_columns = source_columns(accommodation_headers, "accommodation")
    restaurant_columns = source_columns(restaurant_headers, "restaurant")
    attraction_columns = source_columns(attraction_headers, "attraction")
    required = {
        "day", "current_city", "transportation", "breakfast", "lunch", "dinner",
        "attraction", "accommodation",
    }

    observed_cuisines = ""
    route_text = ""
    for expected_day, day in enumerate(obj["plan"], 1):
        if not isinstance(day, dict) or not required.issubset(day):
            raise ValueError("invalid structure for day %d" % expected_day)
        if type(day.get("day")) is not int or day["day"] != expected_day:
            raise ValueError("invalid day number for day %d" % expected_day)
        if any(not isinstance(day[field], str) for field in required - {"day"}):
            raise ValueError("day %d has a non-string field" % expected_day)
        if not day["attraction"].strip().endswith(";"):
            raise ValueError("day %d attraction must end in a semicolon" % expected_day)
        if re.search(r"\b(flight|flights|fly|flying|airplane|air travel)\b", day["transportation"], re.I):
            raise ValueError("day %d uses air transportation" % expected_day)

        lodging = matched(day["accommodation"], accommodations, accommodation_columns["name"])
        if lodging is None or not pet_allowed(lodging):
            raise ValueError("day %d lodging lacks traceable positive pet permission" % expected_day)

        for field in ("breakfast", "lunch", "dinner"):
            meal_text = day[field].strip()
            if meal_text == "-":
                continue
            restaurant = matched(meal_text, restaurants, restaurant_columns["name"])
            if restaurant is None:
                raise ValueError("day %d %s is not source-grounded" % (expected_day, field))
            observed_cuisines += " " + clean(restaurant.get(restaurant_columns["cuisine"], ""))

        listed = [item.strip() for item in day["attraction"].strip()[:-1].split(";") if item.strip()]
        if not listed or any(
            matched(item, attractions, attraction_columns["name"]) is None for item in listed
        ):
            raise ValueError("day %d includes an invalid attraction" % expected_day)
        route_text += " " + " ".join(str(value) for value in day.values())

    for cuisine in ("American", "Mediterranean", "Chinese", "Italian"):
        if not re.search(r"\b" + re.escape(cuisine) + r"\b", observed_cuisines, re.I):
            raise ValueError("requested cuisine is absent: " + cuisine)
    if not has_words(route_text, origin):
        raise ValueError("requested origin is absent")

    source_cities = [row.get(accommodation_columns["city"], "") for row in accommodations]
    source_cities.extend(row.get(restaurant_columns["city"], "") for row in restaurants)
    source_cities.extend(row.get(attraction_columns["city"], "") for row in attractions)
    ohio_cities = ohio_city_keys(root, source_cities, target_state)
    if len([city for city in ohio_cities if has_words(route_text, city)]) < 3:
        raise ValueError("fewer than three supported Ohio cities are present")


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise ValueError("stdin requires a string path")
        with Path(request["path"]).open("r", encoding="utf-8") as handle:
            artifact = json.load(handle)
        validate(artifact, request.get("data_root", "/app/data"))
        print(json.dumps({"ok": True, "path": request["path"]}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
