#!/usr/bin/env python3
"""Validate a generated itinerary against public CSV data.

stdin: {"path": string, "data_root": string}
stdout: {"ok": true, "path": string} or {"ok": false, "error": string}
"""
import json
import re
import sys
from pathlib import Path

from build_itinerary import (best_named_row, clean, load_sources, ohio_city_displays,
                             pet_allowed, words_in)


def validate(artifact, root, origin="Minneapolis", state="Ohio"):
    if not isinstance(artifact, dict) or not isinstance(artifact.get("plan"), list):
        raise ValueError("artifact must be an object with a plan array")
    if len(artifact["plan"]) != 7:
        raise ValueError("plan must contain exactly seven day objects")
    tools = artifact.get("tool_called")
    if not isinstance(tools, list) or not tools or not all(isinstance(item, str) and item.strip() for item in tools):
        raise ValueError("tool_called must be a nonempty string array")

    headers, accommodations, restaurants, attractions, ac, rc, tc = load_sources(root)
    required = {"day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"}
    route_text = ""
    cuisines_seen = ""
    for expected_day, entry in enumerate(artifact["plan"], 1):
        if not isinstance(entry, dict) or not required.issubset(entry):
            raise ValueError("day %d has missing required fields" % expected_day)
        if type(entry["day"]) is not int or entry["day"] != expected_day:
            raise ValueError("day numbers must be ordered integers 1 through 7")
        if any(not isinstance(entry[field], str) for field in required - {"day"}):
            raise ValueError("day %d contains a non-string text field" % expected_day)
        if not entry["current_city"].strip() or not entry["transportation"].strip() or not entry["accommodation"].strip():
            raise ValueError("day %d contains blank required travel or lodging text" % expected_day)
        if re.search(r"\b(flight|flights|fly|flying|airplane|air travel)\b", entry["transportation"], re.I):
            raise ValueError("air travel is prohibited")
        if not entry["attraction"].strip().endswith(";"):
            raise ValueError("day %d attractions must end in semicolon" % expected_day)

        lodging = best_named_row(entry["accommodation"], accommodations, ac["name"])
        if lodging is None or not pet_allowed(lodging, headers):
            raise ValueError("day %d lodging lacks explicit public-record pet permission" % expected_day)

        for field in ("breakfast", "lunch", "dinner"):
            value = entry[field].strip()
            if value != "-":
                restaurant = best_named_row(value, restaurants, rc["name"])
                if restaurant is None:
                    raise ValueError("day %d %s is not a source restaurant" % (expected_day, field))
                cuisines_seen += " " + clean(restaurant.get(rc["cuisine"], ""))

        attractions_list = [part.strip() for part in entry["attraction"].strip()[:-1].split(";") if part.strip()]
        if not attractions_list or any(best_named_row(name, attractions, tc["name"]) is None for name in attractions_list):
            raise ValueError("day %d contains an untraceable attraction" % expected_day)
        route_text += " " + " ".join(str(value) for value in entry.values())

    for cuisine in ("American", "Mediterranean", "Chinese", "Italian"):
        if not re.search(r"\b" + re.escape(cuisine) + r"\b", cuisines_seen, re.I):
            raise ValueError("requested cuisine missing: " + cuisine)
    if not words_in(route_text, origin):
        raise ValueError("requested Minneapolis departure is absent")

    city_values = [row.get(ac["city"], "") for row in accommodations]
    city_values += [row.get(rc["city"], "") for row in restaurants]
    city_values += [row.get(tc["city"], "") for row in attractions]
    ohio = ohio_city_displays(root, city_values, state)
    visited = [key for key in ohio if words_in(route_text, key)]
    if len(visited) < 3:
        raise ValueError("fewer than three source-supported Ohio cities are named")


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise ValueError("stdin requires a JSON object with string path")
        with Path(request["path"]).open("r", encoding="utf-8") as handle:
            artifact = json.load(handle)
        validate(artifact, request.get("data_root", "/app/data"))
        print(json.dumps({"ok": True, "path": request["path"]}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
