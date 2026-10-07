#!/usr/bin/env python3
"""Validate required itinerary JSON structure and public CSV traceability.

stdin: {"path": string, "data_root": string}
stdout: JSON success or error status
"""
import json
import re
import sys
from pathlib import Path

from build_itinerary import (
    contains_words, fields, longest_match, pet_allowed, read_csv, text,
    target_city_keys, words,
)


def validate(obj, root, origin="Minneapolis", target_state="Ohio"):
    if not isinstance(obj, dict) or set(obj) != {"plan", "tool_called"}:
        raise ValueError("artifact must contain exactly plan and tool_called")
    if (not isinstance(obj["tool_called"], list) or not obj["tool_called"]
            or not all(isinstance(value, str) and value.strip() for value in obj["tool_called"])):
        raise ValueError("tool_called must be a nonempty string array")
    if not isinstance(obj["plan"], list) or len(obj["plan"]) != 7:
        raise ValueError("plan must contain exactly seven days")

    ac_headers, ac_rows = read_csv(Path(root) / "accommodations/clean_accommodations_2022.csv")
    rs_headers, rs_rows = read_csv(Path(root) / "restaurants/clean_restaurant_2022.csv")
    at_headers, at_rows = read_csv(Path(root) / "attractions/attractions.csv")
    acf = fields(ac_headers, "accommodations")
    rsf = fields(rs_headers, "restaurants")
    atf = fields(at_headers, "attractions")
    if not all((acf.get("name"), acf.get("city"), rsf.get("name"), rsf.get("cuisine"), atf.get("name"))):
        raise ValueError("public CSV schema lacks a required identity or cuisine field")

    required = {
        "day", "current_city", "transportation", "breakfast", "lunch", "dinner",
        "attraction", "accommodation",
    }
    cuisine_text = ""
    route_text = ""
    for expected_day, day in enumerate(obj["plan"], 1):
        if not isinstance(day, dict) or not required.issubset(day):
            raise ValueError("invalid day %d structure" % expected_day)
        if type(day["day"]) is not int or day["day"] != expected_day:
            raise ValueError("days must be ordered integer values 1 through 7")
        if any(not isinstance(day[key], str) for key in required - {"day"}):
            raise ValueError("day %d has a non-string text field" % expected_day)
        if not day["current_city"].strip() or not day["transportation"].strip() or not day["accommodation"].strip():
            raise ValueError("day %d has a required blank field" % expected_day)
        if re.search(r"\b(flight|flights|fly|flying|airplane|air travel)\b", day["transportation"], re.I):
            raise ValueError("day %d uses prohibited air transportation" % expected_day)
        if not day["attraction"].strip().endswith(";"):
            raise ValueError("day %d attraction must end with a semicolon" % expected_day)

        lodging = longest_match(day["accommodation"], ac_rows, acf["name"])
        if lodging is None or not pet_allowed(lodging):
            raise ValueError("day %d lodging is not traceable with explicit positive pet permission" % expected_day)
        for meal_key in ("breakfast", "lunch", "dinner"):
            meal = day[meal_key].strip()
            if meal == "-":
                continue
            restaurant = longest_match(meal, rs_rows, rsf["name"])
            if restaurant is None:
                raise ValueError("day %d %s is not source-grounded" % (expected_day, meal_key))
            cuisine_text += " " + text(restaurant.get(rsf["cuisine"], ""))
        names = [part.strip() for part in day["attraction"].strip()[:-1].split(";") if part.strip()]
        if not names:
            raise ValueError("day %d must list at least one attraction" % expected_day)
        for name in names:
            if longest_match(name, at_rows, atf["name"]) is None:
                raise ValueError("day %d attraction is not source-grounded" % expected_day)
        route_text += " " + " ".join(str(value) for value in day.values())

    for cuisine in ("American", "Mediterranean", "Chinese", "Italian"):
        if not re.search(r"\b" + re.escape(cuisine.lower()) + r"\b", cuisine_text.lower()):
            raise ValueError("missing requested cuisine " + cuisine)
    if not contains_words(route_text, origin):
        raise ValueError("itinerary does not show requested origin " + origin)
    city_values = [row.get(acf["city"], "") for row in ac_rows]
    cities = target_city_keys(root, city_values, target_state)
    visited = {city for city in cities if contains_words(route_text, city)}
    if len(visited) < 3:
        raise ValueError("itinerary covers fewer than three supported %s cities" % target_state)


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise ValueError("stdin requires a string path")
        root = request.get("data_root", "/app/data")
        with Path(request["path"]).open("r", encoding="utf-8") as handle:
            validate(json.load(handle), root)
        print(json.dumps({"ok": True, "path": request["path"]}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
