#!/usr/bin/env python3
"""Validate the artifact against the public data and output contract.

stdin: {"path": string, "data_root": string}
stdout: JSON status object
"""
import json
import re
import sys
from pathlib import Path

from build_itinerary import (POSITIVE_PET, NEGATIVE_PET, clean, column, has_words,
                             norm, ohio_city_keys, pet_allowed, read_csv, source_columns)


def matched(text, rows, name_column):
    candidates = [row for row in rows if len(norm(row.get(name_column, ""))) >= 3 and has_words(text, row.get(name_column, ""))]
    return max(candidates, key=lambda row: len(norm(row[name_column]))) if candidates else None


def validate(obj, root, origin="Minneapolis", target_state="Ohio"):
    if not isinstance(obj, dict) or set(obj) != {"plan", "tool_called"}:
        raise ValueError("artifact must contain exactly plan and tool_called")
    if not isinstance(obj["tool_called"], list) or not obj["tool_called"] or not all(isinstance(x, str) and x.strip() for x in obj["tool_called"]):
        raise ValueError("tool_called must be a nonempty string array")
    if not isinstance(obj["plan"], list) or len(obj["plan"]) != 7:
        raise ValueError("plan must contain exactly seven days")
    root = Path(root)
    ah, accommodations = read_csv(root / "accommodations/clean_accommodations_2022.csv")
    rh, restaurants = read_csv(root / "restaurants/clean_restaurant_2022.csv")
    th, attractions = read_csv(root / "attractions/attractions.csv")
    ac, rc, tc = source_columns(ah, "accommodation"), source_columns(rh, "restaurant"), source_columns(th, "attraction")
    required = {"day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"}
    cuisines, route = "", ""
    for number, day in enumerate(obj["plan"], 1):
        if not isinstance(day, dict) or not required.issubset(day) or type(day.get("day")) is not int or day["day"] != number:
            raise ValueError("invalid structure for day %d" % number)
        if any(not isinstance(day[key], str) for key in required - {"day"}):
            raise ValueError("day %d has a non-string field" % number)
        if not day["attraction"].strip().endswith(";"):
            raise ValueError("day %d attraction must end in a semicolon" % number)
        if re.search(r"\b(flight|flights|fly|flying|airplane|air travel)\b", day["transportation"], re.I):
            raise ValueError("day %d uses air transportation" % number)
        lodging = matched(day["accommodation"], accommodations, ac["name"])
        if lodging is None or not pet_allowed(lodging):
            raise ValueError("day %d lodging lacks traceable positive pet permission" % number)
        for key in ("breakfast", "lunch", "dinner"):
            if day[key].strip() != "-":
                meal = matched(day[key], restaurants, rc["name"])
                if meal is None:
                    raise ValueError("day %d %s is not source-grounded" % (number, key))
                cuisines += " " + clean(meal.get(rc["cuisine"], ""))
        listed = [x.strip() for x in day["attraction"].strip()[:-1].split(";") if x.strip()]
        if not listed or any(matched(x, attractions, tc["name"]) is None for x in listed):
            raise ValueError("day %d includes an invalid attraction" % number)
        route += " " + " ".join(str(value) for value in day.values())
    for cuisine in ("American", "Mediterranean", "Chinese", "Italian"):
        if not re.search(r"\b" + re.escape(cuisine) + r"\b", cuisines, re.I):
            raise ValueError("requested cuisine is absent: " + cuisine)
    if not has_words(route, origin):
        raise ValueError("requested origin is absent")
    cities = ohio_city_keys(root, [row.get(ac["city"], "") for row in accommodations] + [row.get(rc["city"], "") for row in restaurants] + [row.get(tc["city"], "") for row in attractions], target_state)
    if len([city for city in cities if has_words(route, city)]) < 3:
        raise ValueError("fewer than three supported Ohio cities are present")


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise ValueError("stdin requires a string path")
        with Path(request["path"]).open("r", encoding="utf-8") as handle:
            validate(json.load(handle), request.get("data_root", "/app/data"))
        print(json.dumps({"ok": True, "path": request["path"]}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
